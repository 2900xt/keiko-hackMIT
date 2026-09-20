#!/usr/bin/env python3
"""Watkins Marine Mammal Sound Database -> Moby features, the same way features.py does the Kaggle clips.

    python3 watkins_features.py                       # ~/Projects/marine-sounds-db -> ../dataset/features/moby_watkins.npz (+ .csv)
    python3 watkins_features.py --limit 50            # smoke test
    python3 watkins_features.py --merge               # also write moby_narw_watkins.npz = Kaggle rows + Watkins rows

Every kept Watkins cut becomes one or more 2 s / 2 kHz windows that go through features.clip_features(), so the
output has exactly the Kaggle layout (X2 (N, 103, 126), X1 (N, 7, 126), y (N,)) plus provenance arrays. What is
different from the Kaggle path, and why:

  species whitelist   Moby's Nyquist is 1 kHz. Only species whose calls live below it are kept (right, bowhead,
                      humpback, gray); a dolphin cut resampled to 2 kHz is just tape hiss labelled "whale".
  --min-sr 2000       cuts digitised below 2 kHz (all Watkins fin whales, 320-640 Hz) would show an empty band
                      above their own Nyquist after upsampling, a recorder-bandwidth shortcut the CNN would learn.
  --min-s 0.8         shorter cuts are mostly padding. Kept cuts under 2 s are centre-padded by *reflection*, not
                      zeros, so the 1D branch (log-RMS, flatness, ZCR) sees no silent block that Kaggle never has.
  windows             cuts longer than 2 s yield up to --max-windows evenly spaced 2 s windows (>= 1 s apart).
  level               Kaggle clips are not normalised (peak 0.01-1.0). Each Watkins window is scaled to a peak drawn
                      from the Kaggle peak distribution (deterministic per clip), so loudness is not a domain cue.
  split               15% of *tapes* (first five characters of the Watkins ID) are held out, same hash rule as
                      build_whale_clips.py, so a tape never appears on both sides.
  wild only           cuts whose location says aquarium / tank / pool / lab are dropped.

y is 1 for every row: Watkins has no noise cuts. Negatives still come from Kaggle, so a merged model can separate
"analog tape" from "MARU buoy" instead of "whale" from "noise"; check the Kaggle-only test AUROC after training on
the merge (see README).
"""
import argparse, hashlib, io, os, pathlib, re, sqlite3, sys, time, warnings, zipfile
from concurrent.futures import ProcessPoolExecutor
from math import gcd

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from features import SR, N_SAMPLES, ROWS_2D, NAMES_1D, T, clip_features, DEFAULT_ZIP, inner_zip   # noqa: E402

DEFAULT_DB = pathlib.Path.home() / "Projects" / "marine-sounds-db"
DEFAULT_OUT = HERE.parent / "dataset" / "features" / "moby_watkins.npz"
KAGGLE_NPZ = HERE.parent / "dataset" / "features" / "moby_narw.npz"
MERGED_NPZ = HERE.parent / "dataset" / "features" / "moby_narw_watkins.npz"

# Watkins common names whose calls sit below Moby's 1 kHz Nyquist (measured: >= 87% of energy < 1 kHz).
SPECIES = ["North Atlantic right whale", "Southern right whale", "Bowhead whale", "Humpback whale", "Gray whale"]
CAPTIVE_RX = re.compile(
    r"aquarium|marineland|marine land|seaquarium|sea ?world|\btank\b|\bzoo\b|silver springs|"
    r"canal 13|johns hopkins|oceanarium|niag[a]?ra|\bpool\b|\blab(?:oratory)?\b|holding pen|\bpen\b", re.I)
KAGGLE_PEAK_FALLBACK = 0.062                                              # median Kaggle clip peak
warnings.filterwarnings("ignore")


# ----------------------------------------------------------------------------- selection
def select(db: pathlib.Path, species, min_sr, min_s):
    con = sqlite3.connect(db / "marine_sounds.sqlite")
    rows = con.execute(
        """SELECT c.source_record_id, s.scientific_name, s.common_name, c.location, c.file_path, c.sample_rate, c.duration_s
           FROM clips c JOIN datasets d USING (dataset_id) JOIN species s USING (species_id)
           WHERE d.name LIKE 'Watkins%' ORDER BY c.source_record_id""").fetchall()
    con.close()
    stats, keep = {"catalogue": len(rows)}, []
    for rid, sci, common, loc, path, sr, dur in rows:
        if common not in species: stats["dropped: species not in whitelist"] = stats.get("dropped: species not in whitelist", 0) + 1; continue
        if CAPTIVE_RX.search(loc or ""): stats["dropped: captive"] = stats.get("dropped: captive", 0) + 1; continue
        if sr < min_sr: stats[f"dropped: sample rate < {min_sr}"] = stats.get(f"dropped: sample rate < {min_sr}", 0) + 1; continue
        if dur < min_s: stats[f"dropped: shorter than {min_s} s"] = stats.get(f"dropped: shorter than {min_s} s", 0) + 1; continue
        keep.append(dict(clip=str(rid), species=sci, common_name=common, tape=str(rid)[:5], path=str(db / path), orig_sr=int(sr), duration_s=float(dur)))
    stats["kept cuts"] = len(keep)
    return keep, stats


def split_of(tape: str, test_frac=0.15) -> str:
    h = int(hashlib.md5(tape.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF                 # same rule as build_whale_clips.py
    return "test" if h < test_frac else "train"


def kaggle_peak_quantiles(zip_path: pathlib.Path, n=3000, seed=0) -> np.ndarray:
    """101 quantiles of |x|.max() over a seeded sample of Kaggle clips (so Watkins levels can be matched to them)."""
    if not zip_path.exists():
        print(f"  Kaggle zip not found ({zip_path}); every Watkins window gets peak {KAGGLE_PEAK_FALLBACK}")
        return np.full(101, KAGGLE_PEAK_FALLBACK)
    import soundfile as sf
    z = zipfile.ZipFile(inner_zip(zip_path))
    names = [n_ for n_ in z.namelist() if n_.startswith("data/train/train") and n_.endswith(".aiff")]
    rng = np.random.default_rng(seed)
    pk = []
    for n_ in rng.choice(names, min(n, len(names)), replace=False):
        a, _ = sf.read(io.BytesIO(z.read(n_)), dtype="float32")
        pk.append(float(np.abs(a).max()))
    return np.quantile(pk, np.linspace(0, 1, 101))


# ----------------------------------------------------------------------------- per-cut work
_cfg = {}
def _init(cfg):
    _cfg.update(cfg)


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    from scipy.signal import resample_poly
    if sr_in == sr_out:
        return x
    g = gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


def windows_of(x: np.ndarray, max_windows: int, hop: int):
    """(list of 4000-sample windows, pad_s). Short cuts: reflect-pad centred. Long cuts: evenly spaced, >= hop apart."""
    n = N_SAMPLES
    if len(x) < n:
        pad = n - len(x)
        return [np.pad(x, (pad // 2, pad - pad // 2), mode="reflect")], pad / SR
    k = max(1, min(max_windows, 1 + (len(x) - n) // hop))
    starts = np.linspace(0, len(x) - n, k).astype(int)
    return [x[s:s + n] for s in starts], 0.0


def _cut(job):
    import soundfile as sf
    i, r = job
    q = _cfg["quantiles"]
    try:
        x, sr = sf.read(r["path"], dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        x = resample(x, sr, SR)
        ws, pad_s = windows_of(x, _cfg["max_windows"], _cfg["hop"])
    except Exception as e:
        return i, None, str(e)
    out = []
    for w, a in enumerate(ws):
        u = int(hashlib.md5(f"{r['clip']}/{w}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF       # deterministic per window
        target = float(np.interp(u * 100, np.arange(101), q))
        peak = float(np.abs(a).max())
        gain = target / peak if peak > 0 else 1.0
        a = np.clip(a * gain, -1.0, 1.0)
        x2, x1 = clip_features(a)
        out.append((w, x2.astype(np.float16), x1.astype(np.float16), round(pad_s, 3), round(20 * np.log10(gain), 2) if gain > 0 else 0.0))
    return i, out, ""


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=pathlib.Path, default=DEFAULT_DB, help="marine-sounds-db root (marine_sounds.sqlite + audio/)")
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    ap.add_argument("--zip", type=pathlib.Path, default=DEFAULT_ZIP, help="Kaggle zip, only used to measure clip levels")
    ap.add_argument("--species", nargs="+", default=SPECIES, help="Watkins common names to keep")
    ap.add_argument("--min-sr", type=int, default=2000, help="drop cuts digitised below this rate")
    ap.add_argument("--min-s", type=float, default=0.8, help="drop cuts shorter than this")
    ap.add_argument("--max-windows", type=int, default=5, help="windows per cut longer than 2 s")
    ap.add_argument("--hop-s", type=float, default=1.0, help="minimum spacing between windows of one cut")
    ap.add_argument("--test-frac", type=float, default=0.15, help="fraction of tapes held out")
    ap.add_argument("--merge", action="store_true", help=f"also write {MERGED_NPZ.name} = Kaggle rows + these rows")
    ap.add_argument("--kaggle", type=pathlib.Path, default=KAGGLE_NPZ)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    a = ap.parse_args()
    if not (a.db / "marine_sounds.sqlite").exists():
        sys.exit(f"not found: {a.db / 'marine_sounds.sqlite'}")

    cuts, stats = select(a.db, set(a.species), a.min_sr, a.min_s)
    for k, v in stats.items():
        print(f"  {k:<40s} {v:>7,d}")
    cuts = cuts[: a.limit or None]
    print("measuring Kaggle clip levels ...")
    q = kaggle_peak_quantiles(a.zip)
    print(f"  Kaggle peak p5 {q[5]:.3f}  p50 {q[50]:.3f}  p95 {q[95]:.3f}")

    t0 = time.time()
    cfg = dict(quantiles=q, max_windows=a.max_windows, hop=int(a.hop_s * SR))
    X2, X1, meta, errors = [], [], [], []
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(cfg,)) as ex:
        for j, (i, out, err) in enumerate(ex.map(_cut, list(enumerate(cuts)), chunksize=8), 1):
            r = cuts[i]
            if out is None:
                errors.append((r["clip"], err)); continue
            for w, x2, x1, pad_s, gain_db in out:
                X2.append(x2); X1.append(x1)
                meta.append((r["clip"], w, r["species"], r["common_name"], r["tape"], r["orig_sr"], r["duration_s"], pad_s, gain_db, split_of(r["tape"], a.test_frac)))
            if j % 100 == 0 or j == len(cuts):
                print(f"\r{j}/{len(cuts)} cuts -> {len(meta)} windows  {time.time() - t0:.0f} s", end="", flush=True)
    print()
    if not meta:
        sys.exit("no windows produced")
    X2, X1 = np.stack(X2), np.stack(X1)
    y = np.ones(len(meta), np.int8)
    cols = list(zip(*meta))
    arrays = dict(X2=X2, X1=X1, y=y,
                  clip=np.array(cols[0]), window=np.array(cols[1], np.int16), species=np.array(cols[2]), common_name=np.array(cols[3]),
                  tape=np.array(cols[4]), orig_sr=np.array(cols[5], np.int32), duration_s=np.array(cols[6], np.float32),
                  pad_s=np.array(cols[7], np.float32), gain_db=np.array(cols[8], np.float32), split=np.array(cols[9]),
                  kaggle_peak_quantiles=q)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(a.out, **arrays)
    csv = a.out.with_suffix(".csv")
    with open(csv, "w") as f:
        f.write("clip,window,species,common_name,tape,orig_sr,duration_s,pad_s,gain_db,split\n")
        for m in meta:
            f.write(",".join(str(v) for v in m) + "\n")
    n_test = int((arrays["split"] == "test").sum())
    print(f"{a.out}: X2 {X2.shape}  X1 {X1.shape}  y {y.shape}  {len(set(cols[4]))} tapes  train {len(y) - n_test} / test {n_test}  {time.time() - t0:.0f} s")
    print("per species:", {s: int((arrays['common_name'] == s).sum()) for s in sorted(set(cols[3]))})
    if errors:
        print(f"{len(errors)} cuts unreadable:", errors[:5])

    if a.merge:
        if not a.kaggle.exists():
            sys.exit(f"--merge needs {a.kaggle} (run features.py first)")
        k = np.load(a.kaggle)
        nk = len(k["y"])
        assert k["X2"].shape[1:] == X2.shape[1:] and k["X1"].shape[1:] == X1.shape[1:], "feature shapes differ"
        merged = dict(X2=np.concatenate([k["X2"], X2]), X1=np.concatenate([k["X1"], X1]), y=np.concatenate([k["y"].astype(np.int8), y]),
                      source=np.array(["kaggle"] * nk + ["watkins"] * len(y)),
                      clip=np.concatenate([np.array([f"train{i + 1}.aiff" for i in range(nk)]), arrays["clip"]]),
                      species=np.concatenate([np.where(k["y"] == 1, "Eubalaena glacialis", ""), arrays["species"]]),
                      group=np.concatenate([np.array([f"kaggle/{i}" for i in range(nk)]), "watkins/" + arrays["tape"]]),
                      split=np.concatenate([np.array([""] * nk), arrays["split"]]))
        merged_path = a.out.parent / MERGED_NPZ.name
        np.savez(merged_path, **merged)
        print(f"{merged_path}: X2 {merged['X2'].shape}  y {merged['y'].shape}  kaggle {nk} + watkins {len(y)}  whale {int(merged['y'].sum())}")


if __name__ == "__main__":
    main()
