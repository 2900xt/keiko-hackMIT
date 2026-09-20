#!/usr/bin/env python3
"""Print the IP of this machine that a Keiko board can reach.

    python3 netinfo.py           # best guess: our address on the same subnet as the board (asks it over adb), else default route
    python3 netinfo.py --board   # the board's addresses instead

Used by `make live`. Standard library only; macOS and Linux.
"""
import argparse, glob, os, re, shutil, subprocess, sys

def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""

def adb():
    c = shutil.which("adb")
    if c: return c
    g = sorted(glob.glob(os.path.expanduser("~/Library/Arduino15/packages/arduino/tools/adb/*/adb")))
    return g[-1] if g else None

def my_ips():
    out = sh(["ifconfig"]) or sh(["ip", "-4", "addr"])
    return [ip for ip in re.findall(r"inet (?:addr:)?(\d+\.\d+\.\d+\.\d+)", out) if not ip.startswith("127.")]

def board_ips():
    a = adb()
    if not a: return []
    out = sh([a, "shell", "hostname -I"])
    return [ip for ip in out.split() if not ip.startswith(("172.17.", "172.18.", "127."))]   # skip docker bridges

def default_route_ip():
    if sys.platform == "darwin":
        iface = re.search(r"interface: (\S+)", sh(["route", "-n", "get", "default"]))
        return sh(["ipconfig", "getifaddr", iface.group(1)]).strip() if iface else ""
    m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", sh(["ip", "route", "get", "1.1.1.1"]))
    return m.group(1) if m else ""

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--board", action="store_true"); a = ap.parse_args()
    if a.board:
        print(" ".join(board_ips())); return
    mine, theirs = my_ips(), board_ips()
    for b in theirs:
        for m in mine:
            if m.rsplit(".", 1)[0] == b.rsplit(".", 1)[0]:
                print(m); return
    ip = default_route_ip() or (mine[0] if mine else "")
    if theirs:
        print(f"warning: board is on {theirs}, this machine on {mine}; no shared /24 - using {ip}", file=sys.stderr)
    elif adb():
        print(f"warning: board reports no LAN address (Wi-Fi down? not on USB?) - using {ip}; "
              f"the stream cannot reach this machine until the board is on the network", file=sys.stderr)
    print(ip)

if __name__ == "__main__":
    main()
