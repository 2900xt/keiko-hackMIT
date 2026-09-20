#!/usr/bin/env bash
# Voloridge's per-dataset fetch scripts + READMEs -> vendor/voloridge (gitignored). Anonymous S3, no creds needed.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p vendor/voloridge
if command -v aws >/dev/null 2>&1; then
  aws s3 sync --no-sign-request s3://voloridge-hack-mit-2026/src vendor/voloridge
else
  # no aws cli: pull the pieces we use over plain HTTPS
  B=https://voloridge-hack-mit-2026.s3.us-east-1.amazonaws.com
  for f in challenge.txt src/noaa_isd/README.md src/noaa_isd/fetch.py; do
    out="vendor/voloridge/${f#src/}"; mkdir -p "$(dirname "$out")"; curl -sSL "$B/$f" -o "$out"
  done
fi
ls vendor/voloridge
