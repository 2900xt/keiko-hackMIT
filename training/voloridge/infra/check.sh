#!/usr/bin/env bash
# Can we reach the box, and what is it? Run this first after getting credentials.
source "$(dirname "$0")/env.sh"
echo "== $VOLO_USER@$VOLO_HOST"
vssh 'echo "host:   $(hostname)"; echo "os:     $(. /etc/os-release && echo $PRETTY_NAME)";
      echo "cpu:    $(nproc) cores, $(free -g | awk "/Mem:/{print \$2}") GB RAM";
      echo "disk:   $(df -h ~ | awk "NR==2{print \$4\" free on \"\$1}")";
      if command -v nvidia-smi >/dev/null; then nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader; else echo "gpu:    none (nvidia-smi missing)"; fi;
      echo "region: $(curl -s --max-time 2 http://169.254.169.254/latest/meta-data/placement/region || echo ?)";
      echo "role:   $(curl -s --max-time 2 http://169.254.169.254/latest/meta-data/iam/security-credentials/ || echo none)";
      echo "python: $(python3 --version 2>&1)"; echo "keiko:  $([ -d '"$VOLO_REMOTE_DIR"' ] && echo present || echo not synced yet)"'
