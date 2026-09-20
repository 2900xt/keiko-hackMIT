"""Offline check of main.py's block handling: feed synthetic MCU blocks, verify the UDP packets."""

import os
import socket
import struct
import sys
import tempfile
import wave

import numpy as np

os.environ["KEIKO_UDP_PORT"] = "5599"
os.environ["KEIKO_WAV"] = os.path.join(tempfile.mkdtemp(), "test.wav")
os.environ["KEIKO_QUIET"] = "1"
sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind(("127.0.0.1", 5599))
rx.settimeout(1)

FS, BLOCK = 3333.3, 256
node = main.Node()
t = 0.0
for seq in range(40):
    n = np.arange(BLOCK) / FS + t
    x = (8400 + 2000 * np.sin(2 * np.pi * 50 * n)).astype("<i2")   # 1.7 V bias + 50 Hz tone
    node.on_block(seq, int(t * 1e6) & 0xFFFFFFFF, 0, x.tobytes())
    t += BLOCK / FS

    pkt, _ = rx.recvfrom(65536)
    magic, ver, nid, fmt, bits, fs, pseq, t_ns, cnt = main.HDR.unpack(pkt[: main.HDR.size])
    assert magic == b"KEIK" and ver == 1 and pseq == seq and cnt == BLOCK and bits == 14
    assert np.array_equal(np.frombuffer(pkt[main.HDR.size:], dtype="<i2"), x)

assert abs(node.fs - FS) < 5, node.fs
assert abs(node.dc - 8400) < 50, node.dc
node.wav.close()
with wave.open(os.environ["KEIKO_WAV"]) as w:
    assert w.getframerate() == round(FS) and w.getnframes() > 30 * BLOCK
print(f"ok  fs={node.fs:.1f}  dc={node.dc:.0f} counts  wav frames={w.getnframes()}")
