#!/usr/bin/env bash
# Local-only synthetic judge demonstration. Run after installing backend requirements.
set -euo pipefail
cd "$(dirname "$0")"
echo "HimanshuDigitalTwin research demo: http://127.0.0.1:8000"
exec python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
