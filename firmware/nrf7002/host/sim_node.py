#!/usr/bin/env python3
"""Stand-in for the nRF7002 DK: emits the exact UDP stream src/main.c sends, from this Mac.

    python3 sim_node.py                          # -> 127.0.0.1:5005, node 1, 12-bit, 8192 Hz, 0.9 V bias + 440 Hz tone
    python3 sim_node.py --host 10.0.0.5 --tone 0 --noise 40
    python3 sim_node.py --wav call.wav           # play a 16-bit WAV through it (resampled by index, good enough for tests)

Lets the pipeline and `make listen`/`make record` be exercised before the board exists, and is what
`make test` drives. Standard library only. To replay real recordings with proper resampling use
pipeline/replay_wav.py instead; this one is about matching the node's header byte for byte.
"""
import argparse
import math
import random
import socket
import struct
import time
import wave

HDR = struct.Struct("<4sBBBBfIQH")   # magic ver node fmt bits fs seq t_ns n  (src/main.c: struct keik_hdr)
ADC_BITS = 12
FULL_SCALE_MV = 1800                  # ADC_GAIN_1_3 x 0.6 V reference (boards/*.overlay)


def build_packet(seq, samples, *, node=1, fs=8192.0, t_ns=None, bits=ADC_BITS):
    """One datagram exactly as the node's sender loop packs it: 26-byte header + n x int16 counts."""
    t_ns = time.monotonic_ns() if t_ns is None else t_ns
    return HDR.pack(b"KEIK", 1, node, 0, bits, float(fs), seq & 0xFFFFFFFF, t_ns, len(samples)) + struct.pack(f"<{len(samples)}h", *samples)


def synth(i, fs, bias_mv, tone_hz, tone_mv, noise_mv):
    """Sample i of the synthetic input, in ADC counts (0..4095 for 0..1.8 V)."""
    mv = bias_mv + tone_mv * math.sin(2 * math.pi * tone_hz * i / fs) + random.gauss(0, noise_mv)
    return max(0, min((1 << ADC_BITS) - 1, int(round(mv * (1 << ADC_BITS) / FULL_SCALE_MV))))


def wav_counts(path):
    with wave.open(path, "rb") as w:
        fs, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        assert sw == 2, "16-bit PCM WAV only"
        pcm = struct.unpack(f"<{n * ch}h", w.readframes(n))[::ch]
    # 16-bit audio -> 12-bit counts around mid-scale (0.9 V), like a well-biased front end
    return fs, [max(0, min(4095, 2048 + (v >> 4))) for v in pcm]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--node", type=int, default=1); ap.add_argument("--fs", type=float, default=8192.0)
    ap.add_argument("--block", type=int, default=256)
    ap.add_argument("--bias", type=float, default=900, help="DC bias in mV (front end sits at ~VDD/2)")
    ap.add_argument("--tone", type=float, default=440, help="test tone Hz (0 = off)")
    ap.add_argument("--tone-mv", type=float, default=100); ap.add_argument("--noise", type=float, default=5, help="noise sigma mV")
    ap.add_argument("--wav", help="stream this 16-bit WAV instead of the synthetic signal")
    ap.add_argument("--seconds", type=float, default=0, help="stop after this long (0 = until ctrl-c)")
    a = ap.parse_args()

    src = None
    if a.wav:
        wfs, src = wav_counts(a.wav)
        print(f"{a.wav}: {len(src) / wfs:.1f} s @ {wfs} Hz, sent as {a.fs:.0f} Hz counts", flush=True)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if a.host == "255.255.255.255":
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    print(f"sim nrf7002 node {a.node} -> udp {a.host}:{a.port}  {a.fs:.0f} Hz x {a.block}/pkt "
          f"({a.fs / a.block:.1f} pkt/s, {HDR.size + 2 * a.block} B)", flush=True)

    t_start = time.monotonic(); seq = 0; i = 0
    try:
        while True:
            if src:
                blk = [src[(i + k) % len(src)] for k in range(a.block)]
            else:
                blk = [synth(i + k, a.fs, a.bias, a.tone, a.tone_mv, a.noise) for k in range(a.block)]
            s.sendto(build_packet(seq, blk, node=a.node, fs=a.fs), (a.host, a.port))
            seq += 1; i += a.block
            due = t_start + i / a.fs                       # real-time pacing, same cadence as the board
            time.sleep(max(0.0, due - time.monotonic()))
            if a.seconds and time.monotonic() - t_start >= a.seconds:
                break
    except KeyboardInterrupt:
        pass
    print(f"sent {seq} packets", flush=True)


if __name__ == "__main__":
    main()
