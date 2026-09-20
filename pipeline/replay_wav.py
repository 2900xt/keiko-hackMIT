#!/usr/bin/env python3
"""Stream a WAV file over UDP as if it came from a Keiko node (same packets as firmware/unoq/python/main.py).

    python3 replay_wav.py call.wav                    # -> 127.0.0.1:5005 in real time
    python3 replay_wav.py call.wav --host 10.0.0.5 --speed 4 --loop

Any sample rate works; the pipeline resamples. WAV/FLAC/MP3 with soundfile installed, 16-bit WAV without.
Use it to demo or test without a board.
"""
import argparse, socket, struct, time, wave

HDR = struct.Struct("<4sBBBBfIQH")
ap = argparse.ArgumentParser()
ap.add_argument("wav"); ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=5005)
ap.add_argument("--node", type=int, default=0); ap.add_argument("--speed", type=float, default=1.0)
ap.add_argument("--block", type=int, default=256); ap.add_argument("--loop", action="store_true")
a = ap.parse_args()

try:
    import soundfile as sf
    y, fs = sf.read(a.wav, dtype="int16", always_2d=True); pcm = [int(v) for v in y[:, 0]]; n = len(pcm)
except ImportError:                                   # stdlib fallback: 16-bit PCM WAV only
    with wave.open(a.wav, "rb") as w:
        fs, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        assert sw == 2, "16-bit PCM WAV only"
        pcm = struct.unpack(f"<{n * ch}h", w.readframes(n))[::ch]
# 16-bit audio -> 14-bit ADC counts around mid-scale, like the UNO Q node sends
counts = [8192 + (v >> 2) for v in pcm]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print(f"streaming {a.wav}: {n / fs:.1f} s @ {fs} Hz -> {a.host}:{a.port} x{a.speed}", flush=True)
seq = 0
while True:
    t0 = time.monotonic()
    for i in range(0, len(counts), a.block):
        blk = counts[i:i + a.block]
        s.sendto(HDR.pack(b"KEIK", 1, a.node, 0, 14, float(fs), seq, time.monotonic_ns(), len(blk)) + struct.pack(f"<{len(blk)}h", *blk), (a.host, a.port))
        seq += 1
        due = t0 + (i + len(blk)) / fs / a.speed
        if (d := due - time.monotonic()) > 0:
            time.sleep(d)
    if not a.loop:
        break
print("done", flush=True)
