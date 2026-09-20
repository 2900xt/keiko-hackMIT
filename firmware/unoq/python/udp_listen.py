#!/usr/bin/env python3
"""Receive the Keiko node's UDP stream: print what arrives once a second, optionally record it to a WAV.

    python3 udp_listen.py                               # listen on 0.0.0.0:5005, print stats
    python3 udp_listen.py --wav rec.wav --seconds 30    # also write 30 s of audio (DC removed, 16-bit mono), then exit
    python3 udp_listen.py --port 6000

Runs anywhere the stream is sent: on the board's own Linux side (`make record` does this, no app
restart needed) or on a laptop after pointing KEIKO_UDP_HOST in keiko.env at it. Standard library
only. Header format: see main.py.
"""
import argparse
import socket
import struct
import time
import wave

HDR = struct.Struct("<4sBBBBfIQH")

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=5005)
ap.add_argument("--wav", help="write the audio here (16-bit mono, sample rate from the stream)")
ap.add_argument("--seconds", type=float, default=0, help="stop this long after the first packet (0 = run until ctrl-c)")
a = ap.parse_args()

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", a.port))
s.settimeout(1.0)
print(f"listening on udp 0.0.0.0:{a.port}" + (f", recording {a.seconds or 'until ctrl-c'} s to {a.wav}" if a.wav else "") + " (ctrl-c to stop)", flush=True)

wav = None
dc = None
t_first = None
t0 = time.monotonic(); pkts = 0; samples = 0; last = None; last_seq = None; missing = 0
try:
    while True:
        try:
            data, addr = s.recvfrom(65536)
        except socket.timeout:
            data = None
        now = time.monotonic()
        if data and len(data) >= HDR.size:
            magic, ver, node, fmt, bits, fs, seq, t_ns, n = HDR.unpack(data[:HDR.size])
            if magic == b"KEIK":
                pkts += 1; samples += n; last = (addr[0], node, bits, fs, seq, n)
                if last_seq is not None and seq != last_seq + 1:
                    missing += (seq - last_seq - 1) & 0xFFFFFFFF
                last_seq = seq
                t_first = t_first or now
                if a.wav and fs > 0:
                    x = struct.unpack(f"<{n}h", data[HDR.size:HDR.size + 2 * n])
                    m = sum(x) / n
                    dc = m if dc is None else 0.98 * dc + 0.02 * m          # same tracker as main.py
                    if wav is None:
                        wav = wave.open(a.wav, "wb"); wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(int(round(fs)))
                    shift = 16 - bits
                    pcm = [max(-32768, min(32767, int((v - dc) * (1 << shift)))) for v in x]
                    wav.writeframes(struct.pack(f"<{n}h", *pcm))
        if now - t0 >= 1.0:
            if last:
                ip, node, bits, fs, seq, n = last
                print(f"from {ip}: node={node} pkts/s={pkts} samples/s={samples} fs={fs:.1f}Hz "
                      f"bits={bits} seq={seq} n={n} missing={missing}", flush=True)
            else:
                print("nothing yet", flush=True)
            t0 = now; pkts = 0; samples = 0
        if a.seconds and t_first and now - t_first >= a.seconds:
            break
except KeyboardInterrupt:
    pass
if wav:
    wav.close()
    print(f"wrote {a.wav}: {wave.open(a.wav).getnframes() / int(round(last[3])):.1f} s @ {int(round(last[3]))} Hz" if last else f"wrote {a.wav}", flush=True)
