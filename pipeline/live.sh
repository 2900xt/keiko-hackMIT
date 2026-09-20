#!/bin/sh
# Run the pipeline against the real UNO Q node, over USB (adb) for control and Wi-Fi for the audio stream:
#   1. find this machine's IP on the board's subnet, 2. point the node's UDP stream at it (no restart),
#   3. make sure the app is running, 4. run keiko_pipeline.py (extra args are passed through, e.g. --archive).
set -e
HERE=$(cd "$(dirname "$0")" && pwd); NODE="$HERE/../firmware/unoq"
PY=${PY:-$HERE/../.venv/bin/python}; [ -x "$PY" ] || PY=python3
IP=${UDP_HOST:-$("$PY" "$HERE/netinfo.py")}
[ -n "$IP" ] || { echo "could not determine this machine's IP; run with UDP_HOST=<ip>"; exit 1; }
echo "board: $("$PY" "$HERE/netinfo.py" --board)   this machine: $IP"
make -s -C "$NODE" retarget UDP_HOST="$IP"
make -s -C "$NODE" status || make -s -C "$NODE" start UDP_HOST="$IP"
echo "node health (should show fs≈3333 Hz and mcu_drops=0; if only 'App started', power-cycle the board):"
make -s -C "$NODE" logs 2>/dev/null | tail -2
exec "$PY" "$HERE/keiko_pipeline.py" "$@"
