#!/bin/sh
# Demo without a board: loop a public-domain humpback song (National Park Service, Glacier Bay) into the pipeline
# as if a node were streaming it. Ctrl-C stops both. Extra args go to keiko_pipeline.py (e.g. --archive --source synthetic).
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-$HERE/../.venv/bin/python}; [ -x "$PY" ] || PY=python3
CLIP=${CLIP:-$HERE/samples/humpback_nps.mp3}; PORT=${PORT:-5005}
"$PY" "$HERE/replay_wav.py" "$CLIP" --port "$PORT" --loop >/dev/null 2>&1 &
REPLAY=$!
trap 'kill $REPLAY 2>/dev/null' EXIT INT TERM
sleep 1
"$PY" "$HERE/keiko_pipeline.py" --port "$PORT" --min_conf 0.6 "$@"
