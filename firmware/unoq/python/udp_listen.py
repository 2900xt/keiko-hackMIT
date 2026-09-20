#!/usr/bin/env python3
"""Receive the Keiko node's UDP stream and print what arrives, once a second.

    python3 udp_listen.py            # listens on 0.0.0.0:5005
    python3 udp_listen.py 6000       # another port

Use it on the board (`make shell`, then inside the app folder) or on a laptop after
pointing KEIKO_UDP_HOST in keiko.env at the laptop's IP. Header format: see main.py.
"""
import socket
import struct
import sys
import time

HDR = struct.Struct("<4sBBBBfIQH")
port = int(sys.argv[1]) if len(sys.argv) > 1 else 5005

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", port))
s.settimeout(1.0)
print(f"listening on udp 0.0.0.0:{port} (ctrl-c to stop)", flush=True)

t0 = time.monotonic(); pkts = 0; samples = 0; last = None; last_seq = None; missing = 0
while True:
    try:
        data, addr = s.recvfrom(65536)
    except socket.timeout:
        data = None
    if data and len(data) >= HDR.size:
        magic, ver, node, fmt, bits, fs, seq, t_ns, n = HDR.unpack(data[:HDR.size])
        if magic == b"KEIK":
            pkts += 1; samples += n; last = (addr[0], node, bits, fs, seq, n)
            if last_seq is not None and seq != last_seq + 1:
                missing += (seq - last_seq - 1) & 0xFFFFFFFF
            last_seq = seq
    if time.monotonic() - t0 >= 1.0:
        if last:
            ip, node, bits, fs, seq, n = last
            print(f"from {ip}: node={node} pkts/s={pkts} samples/s={samples} fs={fs:.1f}Hz "
                  f"bits={bits} seq={seq} n={n} missing={missing}", flush=True)
        else:
            print("nothing yet", flush=True)
        t0 = time.monotonic(); pkts = 0; samples = 0
