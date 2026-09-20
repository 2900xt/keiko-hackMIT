#!/bin/sh
# Run the pipeline against the real UNO Q node. Control always goes over USB (adb); the audio stream goes
#   VIA=wifi (default) over the network: find this machine's IP on the board's subnet, point the node's UDP stream
#            at it. Both must be on the same Wi-Fi (a phone hotspot works; `make wifi` in ../firmware/unoq joins it).
#   VIA=usb  over the same cable: the node streams to the board itself, usb_relay.py carries the datagrams over an
#            `adb reverse` TCP port. Fallback for networks that isolate clients (MIT GUEST does).
# Either way: make sure the app is running, print its health line, run keiko_pipeline.py (extra args pass through,
# e.g. --archive). Ctrl-C stops everything and, for usb, removes the relay again.
set -e
HERE=$(cd "$(dirname "$0")" && pwd); NODE="$HERE/../firmware/unoq"
PY=${PY:-$HERE/../.venv/bin/python}; [ -x "$PY" ] || PY=python3
VIA=${VIA:-wifi}; PORT=${PORT:-5005}; TCP_PORT=${TCP_PORT:-5006}
ADB=$(command -v adb || ls "$HOME"/Library/Arduino15/packages/arduino/tools/adb/*/adb 2>/dev/null | tail -1)

case "$VIA" in
usb)
    [ -n "$ADB" ] || { echo "adb not found: brew install android-platform-tools (or make core in firmware/unoq)"; exit 1; }
    "$ADB" get-state >/dev/null 2>&1 || { echo "no UNO Q on USB (adb sees no device). Plug it in directly, wait ~1 min, retry."; exit 1; }
    echo "board: $("$PY" "$HERE/netinfo.py" --board)   stream: over USB (adb reverse tcp:$TCP_PORT)"
    make -s -C "$NODE" retarget UDP_HOST=auto
    # ([u]sb_relay, and never in the same adb shell as the start line: pkill -f would match, and kill, its own shell)
    cleanup() { set +e; kill $RELAY 2>/dev/null; "$ADB" shell "pkill -f '[u]sb_relay.py node'" >/dev/null 2>&1; "$ADB" reverse --remove "tcp:$TCP_PORT" 2>/dev/null; }
    trap cleanup EXIT INT TERM
    "$ADB" reverse "tcp:$TCP_PORT" "tcp:$TCP_PORT" >/dev/null
    "$ADB" push "$HERE/usb_relay.py" /tmp/usb_relay.py >/dev/null
    "$PY" "$HERE/usb_relay.py" host --udp-port "$PORT" --tcp-port "$TCP_PORT" &
    RELAY=$!
    "$ADB" shell "pkill -f '[u]sb_relay.py node'; true"       # a stale one from an earlier run (separate call: see cleanup)
    "$ADB" shell "nohup python3 /tmp/usb_relay.py node --udp-port $PORT --tcp-port $TCP_PORT >/tmp/usb_relay.log 2>&1 &"
    ;;
wifi)
    IP=${UDP_HOST:-$("$PY" "$HERE/netinfo.py")}
    [ -n "$IP" ] || { echo "could not determine this machine's IP; run with UDP_HOST=<ip>"; exit 1; }
    echo "board: $("$PY" "$HERE/netinfo.py" --board)   this machine: $IP   stream: over Wi-Fi"
    make -s -C "$NODE" retarget UDP_HOST="$IP"
    ;;
*)  echo "VIA must be usb or wifi"; exit 1 ;;
esac

make -s -C "$NODE" status || make -s -C "$NODE" start
echo "node health (should show fs≈3333 Hz and mcu_drops=0; if only 'App started', power-cycle the board):"
make -s -C "$NODE" logs 2>/dev/null | tail -2
"$PY" "$HERE/keiko_pipeline.py" --port "$PORT" "$@"
