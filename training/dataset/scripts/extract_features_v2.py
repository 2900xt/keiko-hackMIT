#!/usr/bin/env python3
"""v2 feature extraction: whales at species/genus level + explicit NOT-A-WHALE classes, from marine_sounds.sqlite.

Changes vs extract_whale_features.py:
  * label design: baleen species | non-dolphin toothed species | dolphins at GENUS level | other_baleen / other_toothed
                  + no_whale_noise (ambient, vessels, waves, detector negatives) + no_whale_biophony (fish, invertebrates,
                  pinnipeds, unidentified reef sounds). A class must have >= --min_clips clips AND >= --min_groups recording
                  groups, otherwise it folds into its "other_*" bucket.
  * per-RECORDING normalization: log-mel z-scored with the whole clip's mean/std (not per window), so relative loudness survives
  * per-class cap (--max_per_label windows) with clips subsampled evenly across recording groups, so the shard fits in RAM
  * stratified recording-group split (train/val/test) as before; ecotype kept in `taxon_label`
Outputs features/<name>/{windows.npy, manifest.csv, labels.json}.
"""
import argparse, csv, json, os, pathlib, sqlite3, time, collections, random, warnings
import numpy as np, soundfile as sf, librosa
from concurrent.futures import ProcessPoolExecutor
ROOT = pathlib.Path(__file__).resolve().parent.parent
warnings.filterwarnings("ignore")

DOLPHIN_GENERA = {"Stenella", "Delphinus", "Lagenorhynchus", "Globicephala", "Lagenodelphis", "Peponocephala", "Steno", "Tursiops",
                  "Cephalorhynchus", "Sotalia", "Inia", "Grampus", "Pseudorca", "Feresa", "Lissodelphis", "Orcaella", "Sousa"}
SPECIES_ALIAS = {"Balaenoptera musculus intermedia": "Balaenoptera musculus", "Delphinus delphis bairdii": "Delphinus delphis"}
NOISE_PATTERNS = ("noise", "non-bio", "abiotic", "non-toad")
EXCLUDE_LABELS = ("undetermined biological", "unidentified (antarctic low-frequency)", "unidentified reef biophony", "unidentified reef invertebrate/fish")

def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="v2_32k_mel128_3s")
    ap.add_argument("--sr", type=int, default=32000); ap.add_argument("--win_s", type=float, default=3.0)
    ap.add_argument("--n_fft", type=int, default=1024); ap.add_argument("--hop", type=int, default=320)
    ap.add_argument("--n_mels", type=int, default=128); ap.add_argument("--fmin", type=float, default=10.0); ap.add_argument("--fmax", type=float, default=16000.0)
    ap.add_argument("--min_clips", type=int, default=100); ap.add_argument("--min_groups", type=int, default=4)
    ap.add_argument("--max_per_label", type=int, default=6000, help="cap on windows per class (clips subsampled across groups)")
    ap.add_argument("--max_win", type=int, default=20); ap.add_argument("--workers", type=int, default=8); ap.add_argument("--seed", type=int, default=0)
    return ap.parse_args()

# ----------------------------------------------------------------------------- labels + groups
def coarse(c):
    """-> (label, hierarchy) or None to exclude."""
    tg, sci, tl, st = c["taxon_group"] or "", c["scientific_name"], (c["taxon_label"] or "").lower(), (c["sound_type"] or "").lower()
    if any(tl.startswith(p) for p in NOISE_PATTERNS) or st in ("noise", "other/noise", "ambient", "boat engine", "waves", "mechanical noise", "explosion"):
        return "no_whale_noise", "no_whale"
    if any(tl.startswith(p) for p in EXCLUDE_LABELS): return None
    if tg in ("baleen whale", "toothed whale") and sci:
        sci = SPECIES_ALIAS.get(sci, sci); genus = sci.split()[0]
        if tg == "toothed whale" and genus in DOLPHIN_GENERA: return genus + "_spp", "toothed"
        return sci.replace(" ", "_"), ("baleen" if tg == "baleen whale" else "toothed")
    if tg == "toothed whale" or tg == "baleen whale": return None
    return "no_whale_biophony", "no_whale"      # fish, invertebrates, pinnipeds, sea otter, family-level reef classes

def group_key(c):
    src, rid, loc, date = c["source"] or "", c["source_record_id"] or "", c["location"] or "?", c["observation_date"] or "?"
    if src.startswith("Watkins"): return "watkins:" + rid[:5]
    if "Cornell" in src or "Marinexplore" in src: return "cornell:fold" + ((c["note"] or "").split("fold=")[-1].split(";")[0].strip() if "fold=" in (c["note"] or "") else "?")
    if src.startswith("Orcasound"): return "orcasound:" + date
    if src.startswith("ReefSet"): return "reefset:" + loc
    if src.startswith("BEANS"): return "hiceas:" + date
    if src.startswith("DCLDE"): return "dclde:" + loc + ":" + date[:7]
    if src.startswith("AcousticTrends"): return "aad:" + loc + ":" + date[:6]
    if src.startswith("ToadFish"): parts = pathlib.Path(rid).stem.split("_"); return "toad:" + (parts[1] if len(parts) > 2 else "?") + ":" + (parts[2][:6] if len(parts) > 2 else "?")
    if "French Polynesia" in src: return "polynesia:" + rid.split("/")[0]
    return src[:20] + ":" + rid.split("/")[0]

def load(con):
    q = """SELECT c.clip_id, s.scientific_name, s.common_name, s.taxon_group, d.name AS source, c.file_path, c.duration_s, c.source_record_id,
                  c.observation_date, c.location, c.note, c.taxon_label, c.sound_type
           FROM clips c LEFT JOIN species s USING(species_id) JOIN datasets d USING(dataset_id)"""
    cols = ["clip_id","scientific_name","common_name","taxon_group","source","file_path","duration_s","source_record_id","observation_date","location","note","taxon_label","sound_type"]
    return [dict(zip(cols, r)) for r in con.execute(q)]

def n_windows(d, a):
    n = int(a.win_s * a.sr); L = int(round((d or 0) * a.sr)); return 1 if L <= n else min(a.max_win, 1 + (L - n) // (n // 2))

def assign_labels(clips, a):
    for c in clips:
        r = coarse(c); c["label"], c["hier"] = (r if r else (None, None)); c["group"] = group_key(c)
    clips = [c for c in clips if c["label"]]
    cnt = collections.Counter(c["label"] for c in clips); grp = collections.defaultdict(set)
    for c in clips: grp[c["label"]].add(c["group"])
    for c in clips:
        if c["hier"] in ("baleen", "toothed") and (cnt[c["label"]] < a.min_clips or len(grp[c["label"]]) < a.min_groups):
            c["label"] = "other_" + c["hier"]
    return clips

def subsample(clips, a, rng):
    """Cap windows per label; take clips round-robin across recording groups so many recorders survive."""
    out = []
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for c in clips: by[c["label"]][c["group"]].append(c)
    for label, groups in by.items():
        total = sum(n_windows(c["duration_s"], a) for g in groups.values() for c in g)
        if total <= a.max_per_label: out += [c for g in groups.values() for c in g]; continue
        queues = [list(g) for g in groups.values()]
        for q in queues: rng.shuffle(q)
        got = 0; i = 0
        while got < a.max_per_label and any(queues):
            q = queues[i % len(queues)]; i += 1
            if q: c = q.pop(); out.append(c); got += n_windows(c["duration_s"], a)
    return out

def assign_splits(clips, a, frac=(0.70, 0.15, 0.15)):
    rng = random.Random(a.seed); splits = ("train", "val", "test")
    by_label = collections.defaultdict(lambda: collections.defaultdict(int))
    for c in clips: by_label[c["label"]][c["group"]] += n_windows(c["duration_s"], a)
    split_of = {}
    for label in sorted(by_label, key=lambda l: sum(by_label[l].values())):
        groups = by_label[label]; total = sum(groups.values())
        have = {sp: sum(m for g, m in groups.items() if split_of.get(g) == sp) for sp in splits}
        todo = [g for g in groups if g not in split_of]; rng.shuffle(todo); todo.sort(key=lambda g: -groups[g])
        for g in todo:
            sp = max(splits, key=lambda k: (frac[splits.index(k)] * total - have[k]) / frac[splits.index(k)]); split_of[g] = sp; have[sp] += groups[g]
        for want in splits:
            if not any(split_of[g] == want for g in groups) and len(groups) >= 3:
                donor = max(splits, key=lambda k: have[k]); cand = sorted((g for g in groups if split_of[g] == donor), key=lambda g: groups[g])
                if cand: split_of[cand[0]] = want
    for c in clips: c["split"] = split_of[c["group"]]
    return clips

# ----------------------------------------------------------------------------- features
CFG = None
def _init(cfg):
    global CFG; CFG = cfg
def featurize(job):
    clip_id, fp = job; a = CFG
    try:
        y, sr0 = sf.read(str(ROOT / fp), dtype="float32", always_2d=True); y = y.mean(1)
        if sr0 != a["sr"]: y = librosa.resample(y, orig_sr=sr0, target_sr=a["sr"], res_type="soxr_hq")
        n = int(a["win_s"] * a["sr"]); hop = n // 2
        if len(y) < n: pad = n - len(y); y = np.pad(y, (pad // 2, pad - pad // 2)); starts = [0]
        else:
            starts = list(range(0, len(y) - n + 1, hop))
            if len(starts) > a["max_win"]: starts = [starts[i] for i in np.linspace(0, len(starts) - 1, a["max_win"]).round().astype(int)]
        # per-RECORDING normalization: stats over the whole clip's log-mel
        M = np.log1p(librosa.feature.melspectrogram(y=y, sr=a["sr"], n_fft=a["n_fft"], hop_length=a["hop"], n_mels=a["n_mels"], fmin=a["fmin"], fmax=a["fmax"], power=2.0))
        mu, sd = M.mean(), M.std() + 1e-6
        T = 1 + n // a["hop"]; out = np.zeros((len(starts), a["n_mels"], T), dtype=np.float16)
        for k, s in enumerate(starts):
            f0 = s // a["hop"]; seg = M[:, f0:f0 + T]
            out[k, :, :seg.shape[1]] = ((seg - mu) / sd).astype(np.float16)
        return clip_id, out, [s / a["sr"] for s in starts]
    except Exception as e:
        return clip_id, None, repr(e)

def main():
    a = args(); rng = random.Random(a.seed)
    con = sqlite3.connect(ROOT / "marine_sounds.sqlite")
    clips = assign_splits(subsample(assign_labels(load(con), a), a, rng), a)
    labels = sorted({c["label"] for c in clips}); lid = {l: i for i, l in enumerate(labels)}
    hier_of = {c["label"]: c["hier"] for c in clips}
    N = sum(n_windows(c["duration_s"], a) for c in clips); T = 1 + int(a.win_s * a.sr) // a.hop
    out = ROOT / "features" / a.name; out.mkdir(parents=True, exist_ok=True)
    print(f"{len(clips)} clips -> <= {N} windows ({a.n_mels}x{T}); {len(labels)} labels:", flush=True)
    for l in labels: print(f"   {l:36s} {sum(n_windows(c['duration_s'], a) for c in clips if c['label']==l):6d} windows  {len({c['group'] for c in clips if c['label']==l}):4d} groups", flush=True)
    X = np.lib.format.open_memmap(out / "windows.npy", mode="w+", dtype=np.float16, shape=(N, a.n_mels, T))
    by_id = {c["clip_id"]: c for c in clips}
    man = open(out / "manifest.csv", "w", newline=""); w = csv.writer(man)
    w.writerow(["window_id","clip_id","label","label_id","hierarchy","scientific_name","common_name","taxon_label","group","source","location","observation_date","split","clip_offset_s","n_windows_in_clip"])
    i = fails = 0; t0 = time.time()
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(vars(a),)) as ex:
        for k, (cid, arr, extra) in enumerate(ex.map(featurize, [(c["clip_id"], c["file_path"]) for c in clips], chunksize=32), 1):
            if arr is None: fails += 1; continue
            c = by_id[cid]; m = min(arr.shape[0], N - i); X[i:i + m] = arr[:m]
            for j in range(m):
                w.writerow([i + j, cid, c["label"], lid[c["label"]], c["hier"], c["scientific_name"], c["common_name"], c["taxon_label"], c["group"],
                            c["source"], c["location"], c["observation_date"], c["split"], round(extra[j], 3), m])
            i += m
            if k % 5000 == 0: print(f"{k}/{len(clips)} clips, {i} windows, {time.time()-t0:.0f}s", flush=True)
    man.close(); X.flush(); del X
    if i < N:
        Xm = np.load(out / "windows.npy", mmap_mode="r"); np.save(out / "windows_trim.npy", np.ascontiguousarray(Xm[:i])); del Xm; os.replace(out / "windows_trim.npy", out / "windows.npy")
    rows = list(csv.DictReader(open(out / "manifest.csv"))); per = collections.defaultdict(collections.Counter)
    for r in rows: per[r["label"]][r["split"]] += 1
    json.dump({"config": vars(a), "n_windows": i, "n_clips": len(clips) - fails, "failed_clips": fails, "shape": [i, a.n_mels, T], "label_id": lid,
               "hierarchy": hier_of, "windows_per_label_per_split": {l: dict(per[l]) for l in labels}, "split_totals": dict(collections.Counter(r["split"] for r in rows))},
              open(out / "labels.json", "w"), indent=1)
    for l in labels: print(f"{l:36s} train={per[l]['train']:5d} val={per[l]['val']:5d} test={per[l]['test']:5d}")
    print("DONE", out, f"{i} windows, {fails} failed, {time.time()-t0:.0f}s")

if __name__ == "__main__": main()
