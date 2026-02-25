#!/usr/bin/env bash
set -euo pipefail

echo "[bootstrap] installing deps"
pip install -r requirements.txt

echo "[bootstrap] ingest"
python -u cli.py ingest --days 90

echo "[bootstrap] build"
python -u cli.py build --days 90

echo "[bootstrap] snapshot"
python -u cli.py snapshot

echo "[bootstrap] done"
