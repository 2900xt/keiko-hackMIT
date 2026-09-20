#!/usr/bin/env python3
"""Keiko pipeline (MVP): hydrophone UDP stream -> 3 s windows -> whale CNN -> detection events.

    python3 keiko_pipeline.py                      # listen on 0.0.0.0:5005 for node packets (see firmware/unoq/python/main.py)
    python3 keiko_pipeline.py --wav rec.wav        # same logic over a file, as fast as possible (offline test)
    python3 keiko_pipeline.py --archive            # also add each event to site/data (then commit that folder)
    python3 keiko_pipeline.py --elastic            # also ship every window + event to Elasticsearch (elastic/.env)
    python3 keiko_pipeline.py --server ws://127.0.0.1:8765   # also stream to server/keiko_server.py (live map)

Every --hop seconds the last --win seconds of audio are resampled to the model's 32 kHz, turned into the same
log-mel window predict.py uses, and classified. A run of whale windows becomes one event; when it ends the clip
is written to --out as WAV plus a line in events.jsonl, and with --archive it goes through
site/tools/keiko_data.py add (clip, spectrogram, CSV/JSON row) so the website shows it. With --elastic every
window (label, per-class probabilities, spectral descriptors, packet loss) goes to keiko-windows and every event,
with the CNN's 512-d embedding for kNN and a sentence for semantic search, to keiko-detections (see elastic/).

Deps: the training/whale_cnn venv (torch, librosa, soundfile, pandas, scikit-learn) plus scipy, matplotlib, pillow
for --archive. See README.md. To feed it without a board: `python3 replay_wav.py some.wav` in another terminal.
"""
import argparse
import collections
import csv
import importlib.util
import json
import pathlib
import socket
import struct
import sys
import time
from datetime import datetime, timezone

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "training" / "whale_cnn"))
sys.path.insert(0, str(REPO / "elastic"))
from predict import load_model, decide  # noqa: E402  (pulls in torch + train.py)
from features import audio_features, logits_and_embedding, mean_embedding  # noqa: E402  (elastic/features.py, numpy only)
import librosa  # noqa: E402
import torch  # noqa: E402

HDR = struct.Struct("<4sBBBBfIQH")   # magic ver node fmt bits fs seq t_ns n  (firmware/unoq/python/main.py)

COMMON = {  # model class -> name the website shows
    "Balaena_mysticetus": "bowhead whale", "Balaenoptera_acutorostrata": "common minke whale",
    "Balaenoptera_bonaerensis": "Antarctic minke whale", "Balaenoptera_musculus": "blue whale",
    "Balaenoptera_physalus": "fin whale", "Delphinapterus_leucas": "beluga", "Delphinus_spp": "common dolphin",
    "Eubalaena_glacialis": "North Atlantic right whale", "Globicephala_spp": "pilot whale",
    "Grampus_spp": "Risso's dolphin", "Lagenodelphis_spp": "Fraser's dolphin",
    "Lagenorhynchus_spp": "white-sided dolphin", "Megaptera_novaeangliae": "humpback whale",
    "Orcinus_orca": "killer whale", "Physeter_macrocephalus": "sperm whale", "Pseudorca_spp": "false killer whale",
    "Stenella_spp": "spotted/spinner dolphin", "Tursiops_spp": "bottlenose dolphin",
    "other_baleen": "baleen whale (unidentified)", "other_toothed": "toothed whale (unidentified)",
}


def utc(ts=None):
    return datetime.fromtimestamp(ts if ts is not None else time.time(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- audio buffer + features -------------------------------------------------
class Stream:
    """Per-node ring of DC-removed float samples at the node's own sample rate."""

    def __init__(self, keep_s=60.0):
        self.fs = 0.0
        self.dc = None
        self.buf = np.zeros(0, dtype=np.float32)
        self.keep_s = keep_s
        self.t_end = None            # wall-clock time (s) of the last sample
        self.total = 0               # samples ever pushed
        self.packets = 0             # datagrams since the last window (for the window doc's `net`)
        self.dropped = 0             # sequence gaps since the last window
        self.last_seq = None

    def push(self, raw, bits, fs, t_end):
        """raw: ADC counts (or 16-bit audio when bits==16)."""
        x = np.asarray(raw, dtype=np.float32)
        m = float(x.mean())
        self.dc = m if self.dc is None else 0.98 * self.dc + 0.02 * m
        x = (x - self.dc) / float(1 << (bits - 1))
        self.fs = fs
        self.buf = np.concatenate([self.buf, x])
        keep = int(self.keep_s * fs)
        if len(self.buf) > keep:
            self.buf = self.buf[-keep:]
        self.total += len(x)
        self.t_end = t_end

    def note_packet(self, seq):
        self.packets += 1
        if self.last_seq is not None and seq > self.last_seq + 1:
            self.dropped += seq - self.last_seq - 1
        self.last_seq = seq

    def take_net(self):
        net = {"packets": self.packets, "dropped_packets": self.dropped}
        self.packets = self.dropped = 0
        return net

    def last(self, seconds):
        n = int(seconds * self.fs)
        return self.buf[-n:] if len(self.buf) >= n else None

    def slice_back(self, seconds_back, seconds):
        """`seconds` of audio ending `seconds_back` s before the newest sample (clipped to what we still have)."""
        end = len(self.buf) - int(seconds_back * self.fs)
        start = max(0, end - int(seconds * self.fs))
        return self.buf[start:max(start, end)]


def logmel(y, fs, spec):
    """One model window from `y` (float, at `fs`), exactly as predict.py / extract_whale_features do it."""
    sr = int(spec["sr"])
    if fs != sr:
        y = librosa.resample(y.astype(np.float32), orig_sr=float(fs), target_sr=sr, res_type="soxr_hq")
    n = int(spec["win_s"] * sr)
    if len(y) < n:
        pad = n - len(y); y = np.pad(y, (pad // 2, pad - pad // 2))
    y = y[:n]
    T = 1 + n // int(spec["hop"])
    m = librosa.feature.melspectrogram(y=y, sr=sr, n_fft=int(spec["n_fft"]), hop_length=int(spec["hop"]),
                                       n_mels=int(spec["n_mels"]), fmin=spec["fmin"], fmax=spec["fmax"], power=2.0)
    x = np.log1p(m); x = (x - x.mean()) / (x.std() + 1e-6)
    out = np.zeros((int(spec["n_mels"]), T), dtype=np.float32); out[:, :x.shape[1]] = x[:, :T]
    return out


# ---- link to the central server -----------------------------------------------
class ServerLink:
    """Best-effort WebSocket client for server/keiko_server.py: JSON messages out, reconnects on its own, never
    blocks the audio loop for long (a send that fails drops the message and schedules a reconnect)."""

    def __init__(self, url, buoy):
        from websockets.sync.client import connect
        self._connect, self.url, self.buoy = connect, url, buoy
        self.ws = None; self.next_try = 0.0; self.sent = 0
        self.floor = None; self.agc = None

    def _open(self):
        if self.ws or time.time() < self.next_try:
            return
        try:
            self.ws = self._connect(self.url, open_timeout=2, close_timeout=1)
            self.ws.send(json.dumps({"role": "node", "buoy": self.buoy}))
            print(f"server: connected to {self.url}", flush=True)
        except Exception as e:
            self.ws = None; self.next_try = time.time() + 3
            print(f"server: {self.url} unreachable ({e.__class__.__name__}), retrying", flush=True)

    def send(self, msg):
        self._open()
        if not self.ws:
            return
        try:
            self.ws.send(json.dumps(msg)); self.sent += 1
        except Exception as e:
            print(f"server: send failed ({e.__class__.__name__}), reconnecting", flush=True)
            try: self.ws.close()
            except Exception: pass
            self.ws = None; self.next_try = time.time() + 1

    def audio_frame(self, st, ts):
        """The live strip's input: the newest 256 samples (oscilloscope) and 80 power bins 0-1 kHz from the last 0.25 s.
        Both are normalized against a slow running level so a 3 mV piezo and a full-scale replay look the same."""
        y = st.last(0.25)
        if y is None or st.fs <= 0:
            return
        n = len(y); win = np.hanning(n)
        spec = np.abs(np.fft.rfft(y * win)) ** 2 / n
        freqs = np.fft.rfftfreq(n, 1.0 / st.fs)
        edges = np.linspace(0, 1000, 81)
        idx = np.clip(np.searchsorted(edges, freqs, side="right") - 1, 0, 80)
        bins = np.zeros(81); np.add.at(bins, idx, spec); bins = bins[:80]
        db = 10 * np.log10(bins + 1e-12)
        floor = float(np.percentile(db, 30))
        self.floor = floor if self.floor is None else 0.95 * self.floor + 0.05 * floor     # background level, slow
        bins = np.clip((db - self.floor) / 35.0, 0, 1)                                     # 35 dB above the floor = full
        tail = y[-256:]
        peak = float(np.max(np.abs(tail))) + 1e-9
        self.agc = peak if self.agc is None else max(peak, 0.98 * self.agc)                  # fast attack, slow release
        rms = float(np.sqrt(np.mean(tail ** 2)) + 1e-9)
        self.send({"type": "audio", "ts": ts, "samples": [round(float(v), 3) for v in tail / (self.agc * 1.1)],
                   "bins": [round(float(v), 3) for v in bins], "level_db": round(20 * np.log10(rms), 1)})


# ---- events -----------------------------------------------------------------
class Detector:
    def __init__(self, a, model, classes, spec, buoy):
        self.a, self.model, self.classes, self.spec, self.buoy = a, model, classes, spec, buoy
        self.win_hist = collections.deque(maxlen=64)  # (t_end, label, conf, is_whale)
        self.event = None
        self.n_windows = 0; self.t_start = time.time()
        self.out = pathlib.Path(a.out); self.out.mkdir(parents=True, exist_ok=True)
        self.link = ServerLink(a.server, buoy["id"]) if a.server else None
        self.es = None
        if a.elastic:
            from keiko_es import KeikoES, detection_doc, window_doc   # elastic/keiko_es.py
            self.es = KeikoES.from_env(); self.es.ensure_indices()
            self._detection_doc, self._window_doc = detection_doc, window_doc
        self.keiko_data = None
        if a.archive:
            p = REPO / "site" / "tools" / "keiko_data.py"
            s = importlib.util.spec_from_file_location("keiko_data", p); self.keiko_data = importlib.util.module_from_spec(s)
            s.loader.exec_module(self.keiko_data)

    @torch.no_grad()
    def classify(self, y, fs):
        """-> label, conf, top class, its prob, all probs (np), the 512-d embedding (np)."""
        x = torch.from_numpy(logmel(y, fs, self.spec))[None, None]
        logits, emb = logits_and_embedding(self.model, x)
        p = torch.softmax(logits, dim=1)[0].numpy()
        label, conf = decide(p, self.classes, self.a.min_conf, self.a.margin)
        top = int(p.argmax())
        return label, conf, self.classes[top], float(p[top]), p, emb[0].numpy()

    def step(self, st, t_end):
        """Called every hop: classify the newest window, update the open event, emit it when it ends."""
        y = st.last(self.a.win)
        if y is None:
            return
        label, conf, top, ptop = self.classify(y, st.fs)
        self.n_windows += 1
        whale = not label.startswith("no_whale")
        if not self.a.quiet:
            print(f"{utc(t_end)}  {'WHALE ' if whale else '      '}{label:28s} {conf:.2f}   (top {top} {ptop:.2f})", flush=True)
        self.win_hist.append((t_end, label, conf, whale))
        if self.link:
            self.link.send({"type": "window", "ts": utc(t_end), "label": label, "species": COMMON.get(label, label) if whale else None,
                            "conf": round(conf, 3), "whale": whale, "top": top, "top_p": round(ptop, 3), "in_event": self.event is not None})

        ev = self.event
        if ev is None:
            recent = list(self.win_hist)[-self.a.min_windows:]
            if len(recent) == self.a.min_windows and all(w[3] for w in recent):
                self.event = {"t0": recent[0][0] - self.a.win, "t_last": t_end, "labels": [w[1] for w in recent],
                              "confs": [w[2] for w in recent], "misses": 0}
            return
        if whale:
            ev["t_last"] = t_end; ev["labels"].append(label); ev["confs"].append(conf); ev["misses"] = 0
        else:
            ev["misses"] += 1
        if ev["misses"] >= self.a.patience or (t_end - ev["t0"]) >= self.a.max_s:
            self.emit(st, ev, t_end)
            self.event = None

    def ship_window(self, st, t_end, label, conf, whale, top, ptop, probs, audio, in_event):
        if not self.es:
            return
        self.es.add_window(self._window_doc(t_end, self.buoy, label, conf, whale, top, ptop, probs=probs, audio=audio,
                                            fs=st.fs, net=st.take_net(), in_event=in_event, source=self.a.source))

    def flush(self, st, t_now):
        """Stream went quiet: close an open event once it is older than the patience window."""
        ev = self.event
        if ev and st.t_end is not None and t_now - ev["t_last"] >= self.a.patience * self.a.hop:
            self.emit(st, ev, st.t_end)
            self.event = None

    def emit(self, st, ev, t_now):
        pad = 0.5
        dur = ev["t_last"] - ev["t0"] + 2 * pad
        back = max(0.0, t_now - ev["t_last"] - pad)
        y = st.slice_back(back, dur)
        if len(y) < st.fs * 0.5:
            return
        species = collections.Counter(ev["labels"]).most_common(1)[0][0]
        conf = float(np.mean(ev["confs"]))
        when = utc(ev["t0"] + pad)
        det_id = f"{self.buoy['id']}-{datetime.strptime(when, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y%m%dT%H%M%S')}"
        wav = self.out / f"{det_id}.wav"
        import soundfile as sf
        sf.write(str(wav), np.clip(y, -1, 1), int(round(st.fs)), subtype="PCM_16")
        rec = {"id": det_id, "buoy_id": self.buoy["id"], "timestamp_utc": when, "latitude": self.buoy["lat"],
               "longitude": self.buoy["lon"], "confidence": round(conf, 2), "species": COMMON.get(species, species),
               "model_class": species, "windows": len(ev["labels"]), "duration_s": round(len(y) / st.fs, 1),
               "sample_rate_hz": int(round(st.fs)), "clip": str(wav)}
        with open(self.out / "events.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"EVENT {det_id}  {rec['species']}  conf={conf:.2f}  {rec['duration_s']} s  -> {wav}", flush=True)
        if self.link:
            self.link.send({"type": "detection", "id": det_id, "ts": when, "buoy_id": self.buoy["id"], "lat": self.buoy["lat"],
                            "lon": self.buoy["lon"], "species": rec["species"], "model_class": species, "confidence": rec["confidence"],
                            "duration_s": rec["duration_s"], "windows": rec["windows"], "f0": 0, "sweep": 0})
        if self.keiko_data:
            ns = argparse.Namespace(wav=str(wav), buoy=self.buoy["id"], time=when, lat=self.buoy["lat"], lon=self.buoy["lon"],
                                    confidence=conf, species=rec["species"], id=det_id, source=self.a.source,
                                    notes=f"keiko_pipeline {species} over {len(ev['labels'])} windows")
            self.keiko_data.cmd_add(ns)


# ---- inputs -------------------------------------------------------------------
def run_udp(a, det, streams):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((a.host, a.port)); s.settimeout(1.0)
    print(f"listening on udp {a.host}:{a.port}", flush=True)
    next_step = {}; seen = set(); quiet_since = time.time(); hinted = 0
    link = det.link; next_tel = 0.0; next_frame = 0.0; pkts = 0
    while True:
        if link and time.time() >= next_tel:
            next_tel = time.time() + 2
            fs = next((s_.fs for s_ in streams.values()), 0)
            link.send({"type": "telemetry", "id": det.buoy["id"], "ts": utc(), "lat": det.buoy["lat"], "lon": det.buoy["lon"],
                       "sample_rate_hz": int(round(fs)), "packets": pkts, "windows": det.n_windows, "uptime_s": int(time.time() - det.t_start)})
        try:
            data, addr = s.recvfrom(65536)
        except socket.timeout:
            now = time.time()
            for st in streams.values():
                det.flush(st, now)
            if now - quiet_since > 10 and now - hinted > 30:
                hinted = now
                print(f"no packets for {now - quiet_since:.0f} s. Node side: make logs (fs= line present?), "
                      f"make retarget UDP_HOST=<this machine's ip>; both on the same network? (make live streams over USB)", flush=True)
            continue
        quiet_since = time.time()
        if addr[0] not in seen:
            seen.add(addr[0]); print(f"receiving from {addr[0]}", flush=True)
        if len(data) < HDR.size:
            continue
        magic, ver, node, fmt, bits, fs, seq, t_ns, n = HDR.unpack(data[:HDR.size])
        if magic != b"KEIK" or fs <= 0:
            continue
        raw = np.frombuffer(data[HDR.size:HDR.size + 2 * n], dtype="<i2")
        st = streams.setdefault(node, Stream())
        now = time.time()
        st.push(raw, bits, fs, now); pkts += 1
        if link and now >= next_frame:
            next_frame = now + 1 / 15
            link.audio_frame(st, utc(now))
        if now >= next_step.get(node, 0):
            next_step[node] = now + a.hop
            det.step(st, now)


def run_wav(a, det, streams):
    import soundfile as sf
    y, fs = sf.read(a.wav, dtype="float32", always_2d=True); y = y.mean(1)
    t0 = a.start or pathlib.Path(a.wav).stat().st_mtime - len(y) / fs
    st = streams.setdefault(0, Stream())
    block = 256; next_step = 0.0
    for i in range(0, len(y), block):
        chunk = y[i:i + block]
        t = t0 + (i + len(chunk)) / fs
        st.push(chunk * 32768.0, 16, fs, t)      # file audio is already DC-free and +-1; treat as 16-bit counts
        if t - t0 >= next_step:
            next_step += a.hop
            det.step(st, t)
    if det.event:
        det.emit(st, det.event, st.t_end); det.event = None
    print(f"done: {det.n_windows} windows from {a.wav}", flush=True)


def load_buoy(a):
    rows = {r["buoy_id"]: r for r in csv.DictReader(open(REPO / "site" / "data" / "buoys.csv"))}
    b = rows.get(a.buoy)
    if b is None and (a.lat is None or a.lon is None):
        sys.exit(f"unknown buoy {a.buoy} and no --lat/--lon given")
    return {"id": a.buoy, "lat": a.lat if a.lat is not None else float(b["latitude"]),
            "lon": a.lon if a.lon is not None else float(b["longitude"]), "name": b["name"] if b else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0"); ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--wav", help="run over a WAV file instead of listening")
    ap.add_argument("--start", type=float, help="with --wav: unix time of the file's first sample (default: from mtime)")
    ap.add_argument("--model", default=str(REPO / "training" / "whale_cnn" / "models" / "whale_cnn_v2.pt"))
    ap.add_argument("--win", type=float, default=3.0, help="window length s (must match the model)")
    ap.add_argument("--hop", type=float, default=1.5, help="seconds between classifications")
    ap.add_argument("--min_conf", type=float, default=0.8, help="predict.py abstain rule: top whale class prob")
    ap.add_argument("--margin", type=float, default=0.2, help="predict.py abstain rule: P(whale) - P(no_whale)")
    ap.add_argument("--min_windows", type=int, default=2, help="consecutive whale windows to open an event")
    ap.add_argument("--patience", type=int, default=2, help="consecutive no-whale windows that close an event")
    ap.add_argument("--max_s", type=float, default=30.0, help="force-close events longer than this")
    ap.add_argument("--buoy", default="KEIKO-01"); ap.add_argument("--lat", type=float); ap.add_argument("--lon", type=float)
    ap.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parent / "out"))
    ap.add_argument("--archive", action="store_true", help="add events to site/data via keiko_data.py")
    ap.add_argument("--elastic", action="store_true", help="ship windows + events to Elasticsearch (elastic/.env)")
    ap.add_argument("--source", default="field", choices=["field", "synthetic"], help="source column for --archive (use synthetic for replays/tests)")
    ap.add_argument("--quiet", action="store_true", help="only print events")
    ap.add_argument("--server", metavar="WS_URL", help="stream windows, audio and events to server/keiko_server.py, e.g. ws://127.0.0.1:8765")
    a = ap.parse_args()

    model, classes, spec = load_model(a.model)
    buoy = load_buoy(a)
    print(f"model {pathlib.Path(a.model).name}: {len(classes)} classes, {spec['sr']} Hz {spec['win_s']} s windows; "
          f"thresholds min_conf={a.min_conf} margin={a.margin}; buoy {buoy['id']} @ {buoy['lat']:.5f},{buoy['lon']:.5f}; "
          f"events -> {a.out}" + (" + site/data" if a.archive else "") + (" + elasticsearch" if a.elastic else ""), flush=True)
    det = Detector(a, model, classes, spec, buoy)
    streams = {}
    try:
        (run_wav if a.wav else run_udp)(a, det, streams)
    except KeyboardInterrupt:
        pass
    finally:
        if det.es:
            det.es.close()
            print(f"elasticsearch: {det.es.stats['windows']} windows, {det.es.stats['detections']} detections, {det.es.stats['errors']} errors", flush=True)


if __name__ == "__main__":
    main()
