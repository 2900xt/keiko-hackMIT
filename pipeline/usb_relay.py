#!/usr/bin/env python3
"""Carry the node's UDP stream over the USB cable instead of Wi-Fi.

adb can forward TCP ports over USB but not UDP, so this wraps each datagram in a 2-byte length prefix:

    node side (runs on the board's Linux host, python3, stdlib only):
        usb_relay.py node [--udp-port 5005] [--tcp-port 5006]
        UDP :5005 (the stream, with KEIKO_UDP_HOST=auto) -> framed TCP 127.0.0.1:5006 (= this Mac via `adb reverse`)

    host side (this machine):
        usb_relay.py host [--udp-port 5005] [--tcp-port 5006]
        framed TCP :5006 -> UDP 127.0.0.1:5005, where keiko_pipeline.py listens as usual

`make live VIA=usb` (or live.sh when the board and this machine share no network) sets up all of it.
"""
import argparse, socket, struct, sys, time

def node(udp_port, tcp_port):
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    u.bind(("0.0.0.0", udp_port))
    while True:
        try:
            t = socket.create_connection(("127.0.0.1", tcp_port), timeout=5); t.settimeout(None)
            t.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as e:
            print(f"usb_relay node: waiting for host on tcp {tcp_port} ({e})", file=sys.stderr); time.sleep(2); continue
        print(f"usb_relay node: udp {udp_port} -> tcp {tcp_port}", file=sys.stderr)
        try:
            while True:
                d, _ = u.recvfrom(65536)
                t.sendall(struct.pack("<H", len(d)) + d)
        except OSError as e:
            print(f"usb_relay node: host went away ({e}), reconnecting", file=sys.stderr); t.close()

def host(udp_port, tcp_port):
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("127.0.0.1", tcp_port)); ls.listen(1)
    print(f"usb_relay host: tcp {tcp_port} -> udp 127.0.0.1:{udp_port}", file=sys.stderr)
    while True:
        c, _ = ls.accept(); f = c.makefile("rb")
        print("usb_relay host: node connected", file=sys.stderr)
        try:
            while True:
                h = f.read(2)
                if len(h) < 2: break
                d = f.read(struct.unpack("<H", h)[0])
                if not d: break
                u.sendto(d, ("127.0.0.1", udp_port))
        except OSError:
            pass
        c.close(); print("usb_relay host: node disconnected", file=sys.stderr)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("side", choices=["node", "host"])
    ap.add_argument("--udp-port", type=int, default=5005); ap.add_argument("--tcp-port", type=int, default=5006)
    a = ap.parse_args()
    try:
        (node if a.side == "node" else host)(a.udp_port, a.tcp_port)
    except KeyboardInterrupt:
        pass
