#!/usr/bin/env bash
# Run something on the instance inside the venv, from the repo root there.
#   ./remote.sh run  <name> <cmd...>   # detached tmux session <name>; log at ~/keiko/runs/<name>.log
#   ./remote.sh logs <name>            # tail -f that log
#   ./remote.sh ls                     # tmux sessions + nvidia-smi
#   ./remote.sh kill <name>
#   ./remote.sh sh   <cmd...>          # foreground, in venv
source "$(dirname "$0")/env.sh"
ACT="source ~/keiko-venv/bin/activate && cd $VOLO_REMOTE_DIR && mkdir -p runs"
case "${1:-}" in
  run)  name="$2"; shift 2; cmd="$*"
        vssh "$ACT && tmux new-session -d -s '$name' \"bash -lc '$ACT && echo START \$(date -u +%FT%TZ) && $cmd; echo EXIT \$? \$(date -u +%FT%TZ)' 2>&1 | tee runs/$name.log\""
        echo "started tmux:$name on $VOLO_HOST — ./remote.sh logs $name" ;;
  logs) vssh "tail -n 50 -f $VOLO_REMOTE_DIR/runs/$2.log" ;;
  ls)   vssh "tmux ls 2>/dev/null || echo 'no tmux sessions'; command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv" ;;
  kill) vssh "tmux kill-session -t $2" ;;
  sh)   shift; vssh "$ACT && $*" ;;
  *)    sed -n 2,8p "$0"; exit 1 ;;
esac
