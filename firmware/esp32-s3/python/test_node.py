"""Offline check of main.py: feed synthetic KBLK serial frames through the parser, verify the UDP packets."""

import os
import random
import socket
import struct
import sys
import tempfile
import wave

import numpy as np

os.environ["KEIKO_UDP_HOST"] = "127.0.0.1"
os.environ["KEIKO_UDP_PORT"] = "5598"
os.environ["KEIKO_QUIET"] = "1"
sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

main.WAV_PATH = os.path.join(tempfile.mkdtemp(), "test.wav")

# CRC-16/CCITT-FALSE check value -- the sketch's crc16_ccitt is the same algorithm, this pins both to the standard
assert main.crc16_ccitt(b"123456789") == 0x29B1

rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind(("127.0.0.1", 5598))
rx.settimeout(1)

FS, BLOCK = 8000.0, 256


def frame(seq, t0_us, dropped, x):
    body = main.FRAME_HDR.pack(main.FRAME_MAGIC, seq, t0_us, dropped, len(x)) + x.tobytes()
    return body + struct.pack("<H", main.crc16_ccitt(body))


node = main.Node()
parser = main.FrameParser(node)
blocks, stream = [], b"\x00KBL\xffKB"          # junk before the first frame, including a partial magic
t = 0.0
for seq in range(40):
    n = np.arange(BLOCK) / FS + t
    x = (2100 + 500 * np.sin(2 * np.pi * 125 * n)).astype("<i2")  # 1.7 V bias + 125 Hz tone (4 cycles/block), 12-bit counts
    f = frame(seq, int(t * 1e6) & 0xFFFFFFFF, 0, x)
    if seq == 20:                               # one corrupted frame: flipped sample byte, must be dropped by the CRC
        bad = bytearray(f); bad[main.FRAME_HDR.size + 7] ^= 0x55
        stream += bytes(bad)
    else:
        blocks.append((seq, x))
        stream += f
    t += BLOCK / FS

random.seed(1)
i = 0
while i < len(stream):                          # arbitrary chunking, like ser.read() gives
    k = random.randint(1, 700)
    parser.feed(stream[i:i + k])
    i += k

for seq, x in blocks:
    pkt, _ = rx.recvfrom(65536)
    magic, ver, nid, fmt, bits, fs, pseq, t_ns, cnt = main.HDR.unpack(pkt[: main.HDR.size])
    assert magic == b"KEIK" and ver == 1 and nid == 1 and pseq == seq and cnt == BLOCK and bits == 12, (nid, pseq, cnt, bits)
    assert np.array_equal(np.frombuffer(pkt[main.HDR.size:], dtype="<i2"), x)
try:
    rx.recvfrom(65536); raise AssertionError("corrupted frame was forwarded")
except socket.timeout:
    pass

assert node.crc_bad == 1, node.crc_bad
assert node.missing == 1, node.missing            # seq 20 never arrived: counted as missing, not silently skipped
assert abs(node.fs - FS) < 5, node.fs
assert abs(node.dc - 2100) < 20, node.dc
node.wav.close()
with wave.open(main.WAV_PATH) as w:
    assert w.getframerate() == round(FS) and w.getnframes() == 38 * BLOCK   # 39 good blocks, the first is not logged (fs unknown yet)
# hot reload: a file-only key applies, a key set in the real environment (KEIKO_UDP_HOST above) does not get overridden
envf = os.path.join(tempfile.mkdtemp(), "keiko.env")
open(envf, "w").write("KEIKO_UDP_HOST=10.9.9.9\nKEIKO_NODE_ID=7\n")
assert main.reload_settings(envf) and main.NODE_ID == 7 and main.UDP_HOST == "127.0.0.1", (main.NODE_ID, main.UDP_HOST)
print(f"ok  fs={node.fs:.1f}  dc={node.dc:.0f} counts  crc_bad={node.crc_bad} missing={node.missing}  wav frames={w.getnframes()}  reload ok")
