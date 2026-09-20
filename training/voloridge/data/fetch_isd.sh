#!/usr/bin/env bash
# NOAA ISD slice via Voloridge's own tool: stations in configs/stations.txt, years $1 (default 2024:2026), + metadata.
#   data/fetch_isd.sh              # -> data/noaa_isd/data/<year>/725090-14739-<year>.gz + isd-history/inventory.csv
#   data/fetch_isd.sh 2020:2026
set -euo pipefail
PY="${PY:-python3}"
cd "$(dirname "$0")/.."
YEARS="${1:-2024:2026}"
[[ -f vendor/voloridge/noaa_isd/fetch.py ]] || data/fetch_voloridge_tools.sh
$PY vendor/voloridge/noaa_isd/fetch.py --list --year "$YEARS" --stations-file configs/stations.txt
$PY vendor/voloridge/noaa_isd/fetch.py --year "$YEARS" --stations-file configs/stations.txt --metadata --output-dir data/noaa_isd
