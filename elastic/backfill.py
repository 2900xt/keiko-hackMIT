#!/usr/bin/env python3
"""Load what Keiko already recorded into Elasticsearch: the pipeline's out/events.jsonl and the website's
site/data/detections.csv (24 synthetic + field rows with clips). Each clip is run through the whale CNN again so
the doc gets what the live path produces — per-class probabilities, the 512-d embedding, spectral descriptors —
and its 3 s windows go to keiko-windows timestamped from the event start.

    python3 backfill.py                       # both sources
    python3 backfill.py --events ../pipeline/out/events.jsonl --no-site
    python3 backfill.py --dry-run             # print the docs, index nothing

Run with the pipeline venv (../.venv): needs torch + librosa for the model.
"""
import argparse
import csv
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "training" / "whale_cnn"))
sys.path.insert(0, str(HERE))
from predict import load_model, decide, windows_from_wav  # noqa: E402
from features import audio_features, logits_and_embedding, mean_embedding, unit  # noqa: E402
from keiko_es import KeikoES, detection_doc, window_doc  # noqa: E402

def common_names():
    """The pipeline's model class -> common name table (one source of truth)."""
    sys.path.insert(0, str(REPO / "pipeline"))
    from keiko_pipeline import COMMON
    return COMMON


def buoys():
    return {r["buoy_id"]: r for r in csv.DictReader(open(REPO / "site" / "data" / "buoys.csv"))}


def analyse(model, classes, spec, wav, min_conf, margin):
    """Clip -> (probs dict, embedding, per-window list [(offset_s, label, conf, whale, top, ptop, probs)], audio)."""
    import soundfile as sf
    import torch
    X, offsets = windows_from_wav(wav, spec, max_win=40)
    logits, embs = logits_and_embedding(model, torch.from_numpy(X)[:, None])
    P = torch.softmax(logits, dim=1).numpy(); embs = embs.numpy()
    clip = P.mean(0)
    wins = []
    for t, p in zip(offsets, P):
        label, conf = decide(p, classes, min_conf, margin)
        top = int(p.argmax())
        wins.append((t, label, conf, not label.startswith("no_whale"), classes[top], float(p[top]), dict(zip(classes, p.tolist()))))
    y, fs = sf.read(str(wav), dtype="float32", always_2d=True); y = y.mean(1)
    return dict(zip(classes, clip.tolist())), mean_embedding(list(embs)), wins, audio_features(y, fs), fs


def rows_from_events(path):
    for line in pathlib.Path(path).read_text().splitlines():
        if line.strip():
            r = json.loads(line); r.setdefault("source", "field"); r["clip_path"] = r.pop("clip", None)
            yield r


def rows_from_site(root):
    for r in csv.DictReader(open(root / "detections.csv")):
        yield {"id": r["id"], "buoy_id": r["buoy_id"], "timestamp_utc": r["timestamp_utc"], "latitude": float(r["latitude"]),
               "longitude": float(r["longitude"]), "confidence": float(r["confidence"]), "species": r["species"],
               "duration_s": float(r["duration_s"]) if r.get("duration_s") else None,
               "sample_rate_hz": int(r["sample_rate_hz"]) if r.get("sample_rate_hz") else None,
               "clip_path": str(root / r["clip_path"]), "spectrogram_path": r.get("spectrogram_path"),
               "source": r.get("source", "field"), "notes": r.get("notes")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", default=str(REPO / "pipeline" / "out" / "events.jsonl"))
    ap.add_argument("--no-events", action="store_true"); ap.add_argument("--no-site", action="store_true")
    ap.add_argument("--model", default=str(REPO / "training" / "whale_cnn" / "models" / "whale_cnn_v2.pt"))
    ap.add_argument("--min_conf", type=float, default=0.8); ap.add_argument("--margin", type=float, default=0.2)
    ap.add_argument("--no-windows", action="store_true", help="only the detections, not their windows")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    model, classes, spec = load_model(a.model)
    names = common_names(); bs = buoys()
    rows = []
    if not a.no_events and pathlib.Path(a.events).exists():
        rows += list(rows_from_events(a.events))
    if not a.no_site:
        rows += list(rows_from_site(REPO / "site" / "data"))
    print(f"{len(rows)} detections to load", flush=True)

    es = None
    if not a.dry_run:
        es = KeikoES.from_env(); es.ensure_indices()
    n_win = 0
    for r in rows:
        clip = r.get("clip_path")
        if not clip or not pathlib.Path(clip).exists():
            print(f"  {r['id']}: no clip, indexing metadata only"); doc = detection_doc(r)
            wins, fs = [], None
        else:
            probs, emb, wins, audio, fs = analyse(model, classes, spec, clip, a.min_conf, a.margin)
            if r.get("species") in (None, "", "unknown") and probs:
                top = max(probs, key=probs.get)
                if not top.startswith("no_whale") and probs[top] >= 0.5:
                    r["model_class"] = top; r["species"] = names.get(top, top)
            if r.get("model_class") is None:
                inv = {v: k for k, v in names.items()}; r["model_class"] = inv.get(r.get("species"))
            r.setdefault("windows", len(wins))
            b = bs.get(r["buoy_id"], {})
            doc = detection_doc(r, embedding=emb, probs=probs, audio=audio, buoy_name=b.get("name"), source=r.get("source", "field"))
        if a.dry_run:
            print(json.dumps({k: (f"<{len(v)} floats>" if k == "embedding" else v) for k, v in doc.items()}, indent=1)[:1500]); continue
        es.add_detection(doc)
        if wins and not a.no_windows:
            t0 = datetime.strptime(r["timestamp_utc"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
            buoy = {"id": r["buoy_id"], "lat": r.get("latitude"), "lon": r.get("longitude")}
            import soundfile as sf
            y, _ = sf.read(clip, dtype="float32", always_2d=True); y = y.mean(1)
            for (t, label, conf, whale, top, ptop, probs) in wins:
                seg = y[int(t * fs):int((t + spec["win_s"]) * fs)]
                es.add_window(window_doc(t0 + t + spec["win_s"], buoy, label, conf, whale, top, ptop, probs=probs,
                                         audio=audio_features(seg, fs), fs=fs, in_event=True, source=r.get("source", "field")))
                n_win += 1
        print(f"  {r['id']}: {doc['species']} conf {doc.get('confidence')} {'emb ' if 'embedding' in doc else ''}{len(wins)} windows")
    if es:
        es.close()
        print(f"indexed {es.stats['detections']} detections + {es.stats['windows']} windows ({es.stats['errors']} errors)")


if __name__ == "__main__":
    main()
