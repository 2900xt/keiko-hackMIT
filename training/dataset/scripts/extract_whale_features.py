#!/usr/bin/env python3
"""Extract fixed-size log-mel spectrogram tensors for the whale clips in marine_sounds.sqlite.

Pipeline per clip: mono -> resample to SR -> fixed WIN_S windows (center+pad if short, 50% overlap if long,
capped at MAX_WIN per clip) -> log1p(mel) -> per-window z-score -> float16.

Outputs (features/<name>/):
  windows.npy      float16 memmap, shape (N, N_MELS, T)
  manifest.csv     one row per window: window_id, clip_id, species, label, label_id, group, source, location,
                   observation_date, split, clip_offset_s, n_windows_in_clip
  labels.json      label -> id, plus class counts per split and the config used
Split is by recording *group* (tape / fold / date / site), never by window, so no session leaks across splits.
"""
import argparse, csv, json, hashlib, os, pathlib, sqlite3, sys, time, collections, warnings
import numpy as np
import soundfile as sf
import librosa
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
warnings.filterwarnings("ignore")

def cfg_from_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="whales_32k_mel128_3s")
    ap.add_argument("--sr", type=int, default=32000)
    ap.add_argument("--win_s", type=float, default=3.0)
    ap.add_argument("--n_fft", type=int, default=1024)
    ap.add_argument("--hop", type=int, default=320)
    ap.add_argument("--n_mels", type=int, default=128)
    ap.add_argument("--fmin", type=float, default=10.0)
    ap.add_argument("--fmax", type=float, default=16000.0)
    ap.add_argument("--min_clips", type=int, default=100, help="species with fewer clips fold into 'other_whale'")
    ap.add_argument("--max_win", type=int, default=30, help="cap windows per clip (long tape cuts)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="debug: only first N clips")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--resplit_only", action="store_true", help="recompute split column of an existing manifest without re-extracting")
    return ap.parse_args()

# ----------------------------------------------------------------------------- clip selection + grouping
def load_clips(con, min_clips):
    rows = con.execute("""
        SELECT c.clip_id, s.scientific_name, s.common_name, s.taxon_group, d.name AS source, c.file_path, c.duration_s,
               c.source_record_id, c.observation_date, c.location, c.note
        FROM clips c JOIN species s USING(species_id) JOIN datasets d USING(dataset_id)
        WHERE s.taxon_group IN ('baleen whale','toothed whale')""").fetchall()
    cols = ["clip_id","scientific_name","common_name","taxon_group","source","file_path","duration_s","source_record_id","observation_date","location","note"]
    clips = [dict(zip(cols, r)) for r in rows]
    counts = collections.Counter(c["scientific_name"] for c in clips)
    for c in clips:
        c["label"] = c["scientific_name"].replace(" ", "_") if counts[c["scientific_name"]] >= min_clips else "other_whale"
        c["group"] = group_key(c)
    return clips

def group_key(c):
    """Recording-session key used for leak-free splitting."""
    src, rid = c["source"], c["source_record_id"] or ""
    if src.startswith("Watkins"):            return "watkins:" + rid[:5]                  # year + tape number
    if "Cornell" in src or "Marinexplore" in src:
        f = (c["note"] or "").split("fold=")[-1].split(";")[0].strip() if "fold=" in (c["note"] or "") else "?"
        return "cornell:fold" + f
    if src.startswith("Orcasound"):          return "orcasound:" + (c["observation_date"] or "?")
    if src.startswith("ReefSet"):            return "reefset:" + (c["location"] or "?")
    if src.startswith("BEANS"):              return "hiceas:" + (c["observation_date"] or "?")
    if src.startswith("DCLDE"):              return "dclde:" + (c["location"] or "?") + ":" + (c["observation_date"] or "?")[:7]
    if src.startswith("AcousticTrends"):     return "aad:" + (c["location"] or "?") + ":" + (c["observation_date"] or "?")[:6]
    return src + ":" + rid.split("/")[0]

def assign_splits(clips, seed=0, frac=(0.70, 0.15, 0.15)):
    """Stratified GROUP split: every recording group lands in exactly one split, and within each label the window
    mass is pushed toward frac (train/val/test). Labels are processed rarest-first so scarce species get their
    groups spread before common species consume the shared groups."""
    import random
    rng = random.Random(seed); splits = ("train", "val", "test")
    weight = lambda c: max(1, n_windows(c["duration_s"] or 0, CFG_SPLIT))
    by_label = collections.defaultdict(lambda: collections.defaultdict(int))     # label -> group -> window mass
    for c in clips: by_label[c["label"]][c["group"]] += weight(c)
    split_of = {}
    for label in sorted(by_label, key=lambda l: sum(by_label[l].values())):
        groups = by_label[label]; total = sum(groups.values())
        have = {sp: sum(m for g, m in groups.items() if split_of.get(g) == sp) for sp in splits}
        todo = [g for g in groups if g not in split_of]; rng.shuffle(todo)
        todo.sort(key=lambda g: -groups[g])                                     # big groups first, then fill gaps with small ones
        for g in todo:
            deficit = {sp: frac[i] * total - have[sp] for i, sp in enumerate(splits)}
            sp = max(splits, key=lambda k: deficit[k] / max(frac[splits.index(k)], 1e-9))
            split_of[g] = sp; have[sp] += groups[g]
        # guarantee: if the label has >=3 groups, every split gets at least one
        for want in splits:
            if not any(split_of[g] == want for g in groups) and len(groups) >= 3:
                donor_sp = max(splits, key=lambda k: have[k]); cand = sorted((g for g in groups if split_of[g] == donor_sp), key=lambda g: groups[g])
                if cand: split_of[cand[0]] = want
    for c in clips: c["split"] = split_of[c["group"]]
    return clips
CFG_SPLIT = {"win_s": 3.0, "sr": 32000, "max_win": 30}

# ----------------------------------------------------------------------------- feature extraction
CFG = None
def _init(cfg):
    global CFG; CFG = cfg

def n_windows(duration_s, cfg):
    n = int(cfg["win_s"] * cfg["sr"]); hop = n // 2
    L = int(round(duration_s * cfg["sr"]))
    return 1 if L <= n else min(cfg["max_win"], 1 + (L - n) // hop)

def featurize(job):
    """job = (clip_id, file_path) -> (clip_id, float16 array (k, n_mels, T), offsets list) or (clip_id, None, err)"""
    clip_id, fp = job; cfg = CFG
    try:
        y, sr0 = sf.read(str(ROOT / fp), dtype="float32", always_2d=True); y = y.mean(1)
        if sr0 != cfg["sr"]: y = librosa.resample(y, orig_sr=sr0, target_sr=cfg["sr"], res_type="soxr_hq")
        n = int(cfg["win_s"] * cfg["sr"]); hop = n // 2
        if len(y) < n:
            pad = n - len(y); y = np.pad(y, (pad // 2, pad - pad // 2)); starts = [0]
        else:
            starts = list(range(0, len(y) - n + 1, hop))
            if len(starts) > cfg["max_win"]:
                idx = np.linspace(0, len(starts) - 1, cfg["max_win"]).round().astype(int); starts = [starts[i] for i in idx]
        T = 1 + n // cfg["hop"]; out = np.zeros((len(starts), cfg["n_mels"], T), dtype=np.float16)
        for k, s in enumerate(starts):
            m = librosa.feature.melspectrogram(y=y[s:s + n], sr=cfg["sr"], n_fft=cfg["n_fft"], hop_length=cfg["hop"],
                                               n_mels=cfg["n_mels"], fmin=cfg["fmin"], fmax=cfg["fmax"], power=2.0)
            x = np.log1p(m); x = (x - x.mean()) / (x.std() + 1e-6)
            out[k, :, :x.shape[1]] = x[:, :T].astype(np.float16)
        return clip_id, out, [s / cfg["sr"] for s in starts]
    except Exception as e:
        return clip_id, None, repr(e)

def resplit_manifest(out, clips):
    split_of = {c["clip_id"]: c["split"] for c in clips}
    rows = list(csv.DictReader(open(out / "manifest.csv")))
    for r in rows: r["split"] = split_of.get(int(r["clip_id"]), r["split"])
    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    summ = json.load(open(out / "labels.json"))
    per = collections.defaultdict(lambda: collections.Counter())
    for r in rows: per[r["label"]][r["split"]] += 1
    summ["windows_per_label_per_split"] = {l: dict(per[l]) for l in sorted(per)}
    summ["split_totals"] = dict(collections.Counter(r["split"] for r in rows))
    json.dump(summ, open(out / "labels.json", "w"), indent=1)
    print("resplit:", summ["split_totals"])
    for l in sorted(per): print(f"{l:32s} train={per[l]['train']:5d} val={per[l]['val']:5d} test={per[l]['test']:5d}")

def main():
    a = cfg_from_args(); cfg = vars(a)
    con = sqlite3.connect(ROOT / "marine_sounds.sqlite")
    CFG_SPLIT.update({"win_s": a.win_s, "sr": a.sr, "max_win": a.max_win})
    clips = assign_splits(load_clips(con, a.min_clips), seed=a.seed)
    if a.resplit_only:
        return resplit_manifest(ROOT / "features" / a.name, clips)
    if a.limit: clips = clips[:a.limit]
    labels = sorted({c["label"] for c in clips}); label_id = {l: i for i, l in enumerate(labels)}
    N = sum(n_windows(c["duration_s"] or 0, cfg) for c in clips)
    T = 1 + int(a.win_s * a.sr) // a.hop
    out = ROOT / "features" / a.name; out.mkdir(parents=True, exist_ok=True)
    print(f"{len(clips)} clips -> up to {N} windows of ({a.n_mels}, {T}); {len(labels)} labels", flush=True)
    X = np.lib.format.open_memmap(out / "windows.npy", mode="w+", dtype=np.float16, shape=(N, a.n_mels, T))
    by_id = {c["clip_id"]: c for c in clips}
    man = open(out / "manifest.csv", "w", newline=""); w = csv.writer(man)
    w.writerow(["window_id","clip_id","species","common_name","taxon_group","label","label_id","group","source","location","observation_date","split","clip_offset_s","n_windows_in_clip"])
    i = 0; fails = 0; t0 = time.time()
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(cfg,)) as ex:
        for k, (cid, arr, extra) in enumerate(ex.map(featurize, [(c["clip_id"], c["file_path"]) for c in clips], chunksize=16), 1):
            if arr is None: fails += 1; print("FAIL", cid, extra, flush=True); continue
            c = by_id[cid]; m = arr.shape[0]
            if i + m > N: m = N - i; arr = arr[:m]
            X[i:i + m] = arr
            for j in range(m):
                w.writerow([i + j, cid, c["scientific_name"], c["common_name"], c["taxon_group"], c["label"], label_id[c["label"]], c["group"],
                            c["source"], c["location"], c["observation_date"], c["split"], round(extra[j], 3), m])
            i += m
            if k % 1000 == 0: print(f"{k}/{len(clips)} clips, {i} windows, {time.time()-t0:.0f}s", flush=True)
    man.close(); X.flush(); del X
    if i < N:  # trim memmap to the windows actually written
        Xm = np.load(out / "windows.npy", mmap_mode="r"); np.save(out / "windows_trim.npy", np.ascontiguousarray(Xm[:i])); del Xm
        os.replace(out / "windows_trim.npy", out / "windows.npy")
    # summary
    rows = list(csv.DictReader(open(out / "manifest.csv")))
    per = collections.defaultdict(lambda: collections.Counter())
    for r in rows: per[r["label"]][r["split"]] += 1
    summary = {"config": cfg, "n_windows": i, "n_clips": len(clips) - fails, "failed_clips": fails, "shape": [i, a.n_mels, T],
               "label_id": label_id, "windows_per_label_per_split": {l: dict(per[l]) for l in labels},
               "split_totals": dict(collections.Counter(r["split"] for r in rows))}
    json.dump(summary, open(out / "labels.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "windows_per_label_per_split"}, indent=1))
    for l in labels: print(f"{l:40s}", dict(per[l]))
    print("DONE", out, f"{time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
