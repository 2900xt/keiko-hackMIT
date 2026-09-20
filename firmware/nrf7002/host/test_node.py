"""Offline check of the packet format the nRF7002 node emits, using the simulator (src/main.c has the same
struct, pinned by its BUILD_ASSERT): header fields, sample count, sequence continuity, real-time pacing."""

import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sim_node import HDR, build_packet, synth  # noqa: E402

# 1. the packer itself
blk = [synth(i, 8192.0, 900, 440, 100, 0) for i in range(256)]
pkt = build_packet(7, blk, node=1, fs=8192.0, t_ns=123)
assert HDR.size == 26, HDR.size                                   # matches struct keik_hdr
magic, ver, node, fmt, bits, fs, seq, t_ns, n = HDR.unpack(pkt[:HDR.size])
assert (magic, ver, node, fmt, bits, seq, t_ns, n) == (b"KEIK", 1, 1, 0, 12, 7, 123, 256), (magic, ver, node, fmt, bits, seq, t_ns, n)
assert abs(fs - 8192.0) < 1e-3 and len(pkt) == 26 + 512
mean = sum(blk) / len(blk)
assert abs(mean - 2048) < 4, mean                                 # 0.9 V of 1.8 V full scale -> mid-scale counts
assert 0 <= min(blk) and max(blk) <= 4095

# 2. the simulator end to end: 1 s at 8192 Hz should land ~32 packets in order, in about a second
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind(("127.0.0.1", 0)); rx.settimeout(0.5)          # packets are 31 ms apart; silence means the sim is done
port = rx.getsockname()[1]
t0 = time.monotonic()
p = subprocess.Popen([sys.executable, os.path.join(HERE, "sim_node.py"), "--port", str(port), "--seconds", "1"],
                     stdout=subprocess.DEVNULL)
seqs, samples = [], 0
while True:
    try:
        d, _ = rx.recvfrom(65536)
    except socket.timeout:
        break
    m, v, nd, f, b, fs, s, t, n = HDR.unpack(d[:HDR.size])
    assert m == b"KEIK" and nd == 1 and b == 12 and n == 256 and len(d) == HDR.size + 2 * n
    seqs.append(s); samples += n
p.wait()
elapsed = time.monotonic() - t0
assert seqs == list(range(len(seqs))), "sequence gap"
assert 30 <= len(seqs) <= 34, len(seqs)
assert elapsed < 2.5, elapsed
print(f"ok  header {HDR.size} B  bits=12 fs=8192 node=1  {len(seqs)} pkts / {samples} samples in {elapsed:.1f} s")
