#!/usr/bin/env python3
"""
Keiko detection database tool.

The database is the site/data/ folder of this repo:

  data/detections.csv         one row per detection (the source of truth)
  data/detections.json        same rows, for the website
  data/buoys.csv              buoy registry
  data/clips/<id>.wav         audio clip of the call
  data/spectrograms/<id>.png  spectrogram of the clip

Commands
  add      append a detection from a WAV file (renders its spectrogram)
  rebuild  regenerate detections.json (and any missing spectrograms) from the CSV
  synth    generate N synthetic detections to seed or demo the database

Examples
  python3 tools/keiko_data.py add --wav call.wav --buoy KEIKO-01 \
      --time 2026-09-20T14:03:11Z --lat 42.34 --lon -70.97 --confidence 0.87
  python3 tools/keiko_data.py rebuild
  python3 tools/keiko_data.py synth --n 24 --seed 1
"""
import argparse, csv, json, math, random, shutil, struct, sys, wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data"
CSV, JSON_, BUOYS = ROOT / "detections.csv", ROOT / "detections.json", ROOT / "buoys.csv"
FIELDS = ["id", "buoy_id", "timestamp_utc", "latitude", "longitude", "confidence", "species",
          "peak_hz", "duration_s", "sample_rate_hz", "clip_path", "spectrogram_path", "source", "notes"]


# ---------- io ---------------------------------------------------------------
def read_rows():
    if not CSV.exists():
        return []
    with CSV.open(newline="") as f:
        return list(csv.DictReader(f))


def write_rows(rows):
    rows.sort(key=lambda r: r["timestamp_utc"])
    with CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    typed = []
    for r in rows:
        t = dict(r)
        for k in ("latitude", "longitude", "confidence", "peak_hz", "duration_s"):
            t[k] = float(r[k]) if r[k] != "" else None
        t["sample_rate_hz"] = int(r["sample_rate_hz"]) if r["sample_rate_hz"] else None
        typed.append(t)
    JSON_.write_text(json.dumps({"generated_utc": now_iso(), "count": len(typed), "detections": typed}, indent=1))


def read_buoys():
    with BUOYS.open(newline="") as f:
        return {r["buoy_id"]: r for r in csv.DictReader(f)}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_id(buoy, ts):
    return f"{buoy}-{ts.strftime('%Y%m%dT%H%M%S')}"


# ---------- audio ------------------------------------------------------------
def read_wav(path):
    with wave.open(str(path), "rb") as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw != 2:
        sys.exit(f"{path}: only 16-bit PCM WAV supported")
    import numpy as np
    x = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return sr, x


def write_wav(path, sr, x):
    import numpy as np
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())


# The website's "sea" ramp (site/lib/dsp.ts): deep water -> blue -> sea-spray
# white, with quiet bins transparent. value -> (r, g, b, alpha).
SEA = [(0.00, 10, 20, 32, 0.00), (0.30, 23, 44, 62, 0.45), (0.55, 40, 104, 150, 0.85),
       (0.78, 87, 184, 236, 1.00), (1.00, 230, 238, 245, 1.00)]


def sea_rgba(v):
    """Map an array of 0..1 values to uint8 RGBA through the SEA ramp."""
    import numpy as np
    xs = [s[0] for s in SEA]
    chans = [np.interp(v, xs, [s[k] for s in SEA]) for k in (1, 2, 3)] + [np.interp(v, xs, [s[4] for s in SEA]) * 255]
    return np.stack(chans, axis=-1).round().astype("uint8")


def render_spectrogram(wav_path, png_path, fmax=1000.0, width=288, height=96):
    """Mel-scaled log-power spectrogram, sea colormap, transparent floor, no axes. Same look as the website."""
    import numpy as np
    from scipy.signal import spectrogram
    from PIL import Image
    sr, x = read_wav(wav_path)
    nper = max(64, min(512, int(sr * 0.064)))
    f, t, S = spectrogram(x, fs=sr, nperseg=nper, noverlap=nper * 3 // 4, scaling="spectrum", mode="magnitude")
    S = 20 * np.log10(S + 1e-9)
    # resample onto a mel axis up to fmax and onto `width` columns
    mel = lambda hz: 2595 * np.log10(1 + hz / 700.0)
    mel_grid = np.linspace(0, mel(fmax), height)
    hz_grid = 700 * (10 ** (mel_grid / 2595) - 1)
    rows = np.stack([np.interp(hz_grid, f, S[:, j]) for j in range(S.shape[1])], axis=1)  # (height, time)
    cols = np.linspace(0, rows.shape[1] - 1, width)
    img = np.stack([np.interp(cols, np.arange(rows.shape[1]), rows[i]) for i in range(height)])
    # floor at the median (the noise floor of a real recording) so only what rises above it gets colour
    lo, hi = np.percentile(img, 70), np.percentile(img, 99.5)
    img = np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1)
    Image.fromarray(sea_rgba(img)[::-1], "RGBA").save(png_path)  # low frequency at the bottom


def peak_hz(wav_path, fmin=20.0, fmax=1000.0):
    """Loudest bin between fmin and fmax; below ~20 Hz is DC drift and cable rumble, not a call."""
    import numpy as np
    sr, x = read_wav(wav_path)
    x = x - x.mean()
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    spec[(freqs < fmin) | (freqs > fmax)] = 0
    return float(freqs[spec.argmax()])


# ---------- commands ---------------------------------------------------------
def cmd_add(a):
    buoys = read_buoys()
    if a.buoy not in buoys:
        sys.exit(f"unknown buoy {a.buoy}; add it to data/buoys.csv first")
    ts = datetime.fromisoformat(a.time.replace("Z", "+00:00")).astimezone(timezone.utc)
    det_id = a.id or make_id(a.buoy, ts)
    clip = ROOT / "clips" / f"{det_id}.wav"
    png = ROOT / "spectrograms" / f"{det_id}.png"
    shutil.copyfile(a.wav, clip)
    render_spectrogram(clip, png)
    sr, x = read_wav(clip)
    rows = [r for r in read_rows() if r["id"] != det_id]
    rows.append({
        "id": det_id, "buoy_id": a.buoy, "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latitude": f"{a.lat:.5f}", "longitude": f"{a.lon:.5f}", "confidence": f"{a.confidence:.2f}",
        "species": a.species or "unknown", "peak_hz": f"{peak_hz(clip):.0f}", "duration_s": f"{len(x) / sr:.1f}",
        "sample_rate_hz": str(sr), "clip_path": f"clips/{det_id}.wav", "spectrogram_path": f"spectrograms/{det_id}.png",
        "source": a.source, "notes": a.notes or "",
    })
    write_rows(rows)
    print(f"added {det_id}  ({len(rows)} detections total)")


def cmd_rebuild(a):
    rows = read_rows()
    for r in rows:
        png = ROOT / r["spectrogram_path"]
        if not png.exists() and (ROOT / r["clip_path"]).exists():
            render_spectrogram(ROOT / r["clip_path"], png)
            print(f"rendered {png.name}")
    write_rows(rows)
    print(f"wrote {JSON_.name} with {len(rows)} detections")


def cmd_synth(a):
    """Synthetic calls: noise floor + frequency sweep under a sine envelope, near the buoy in open water."""
    import numpy as np
    rng = random.Random(a.seed)
    buoys = read_buoys()
    b = buoys[a.buoy]
    blat, blon = float(b["latitude"]), float(b["longitude"])
    sr = 8000
    rows = [r for r in read_rows() if r["source"] != "synthetic"] if a.replace else read_rows()
    start = datetime.now(timezone.utc) - timedelta(days=a.days)
    for i in range(a.n):
        ts = start + timedelta(seconds=rng.uniform(0, a.days * 86400))
        det_id = make_id(a.buoy, ts)
        f0, sweep, amp, dur = rng.uniform(80, 400), rng.uniform(-150, 150), rng.uniform(0.4, 0.8), rng.uniform(1.5, 5.0)
        n = int(sr * (dur + 0.6)); t = np.arange(n) / sr - 0.3; ph = np.clip(t / dur, 0, 1)
        env = np.where((t > 0) & (t < dur), np.sin(ph * np.pi) * amp, 0)
        phase = 2 * np.pi * np.cumsum(f0 + sweep * ph) / sr
        x = (np.random.default_rng(rng.getrandbits(32)).uniform(-0.5, 0.5, n) * 0.12 + env * np.sin(phase)).astype("float32")
        clip = ROOT / "clips" / f"{det_id}.wav"; png = ROOT / "spectrograms" / f"{det_id}.png"
        write_wav(clip, sr, x); render_spectrogram(clip, png)
        # position: uniform within 450 m of the buoy (open water, no shoreline)
        r, ang = 450 * math.sqrt(rng.random()), rng.uniform(0, 2 * math.pi)
        east, north = r * math.sin(ang), r * math.cos(ang)
        lat = blat + north / 111320; lon = blon + east / (111320 * math.cos(math.radians(blat)))
        rows.append({
            "id": det_id, "buoy_id": a.buoy, "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "latitude": f"{lat:.5f}", "longitude": f"{lon:.5f}",
            "confidence": f"{min(0.99, max(0.4, 0.45 + amp * 0.55 + rng.uniform(-0.08, 0.08))):.2f}",
            "species": "unknown", "peak_hz": f"{f0 + sweep / 2:.0f}", "duration_s": f"{dur:.1f}", "sample_rate_hz": str(sr),
            "clip_path": f"clips/{det_id}.wav", "spectrogram_path": f"spectrograms/{det_id}.png",
            "source": "synthetic", "notes": "generated by tools/keiko_data.py synth",
        })
    write_rows(rows)
    print(f"wrote {a.n} synthetic detections ({len(rows)} total)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add", help="append a detection from a WAV file")
    s.add_argument("--wav", required=True); s.add_argument("--buoy", required=True); s.add_argument("--time", required=True, help="ISO-8601 UTC")
    s.add_argument("--lat", type=float, required=True); s.add_argument("--lon", type=float, required=True)
    s.add_argument("--confidence", type=float, required=True); s.add_argument("--species"); s.add_argument("--id")
    s.add_argument("--source", default="field"); s.add_argument("--notes"); s.set_defaults(fn=cmd_add)
    s = sub.add_parser("rebuild", help="regenerate detections.json and missing spectrograms"); s.set_defaults(fn=cmd_rebuild)
    s = sub.add_parser("synth", help="generate synthetic detections")
    s.add_argument("--n", type=int, default=24); s.add_argument("--seed", type=int, default=1); s.add_argument("--days", type=float, default=14)
    s.add_argument("--buoy", default="KEIKO-01"); s.add_argument("--replace", action="store_true", help="drop existing synthetic rows first")
    s.set_defaults(fn=cmd_synth)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
