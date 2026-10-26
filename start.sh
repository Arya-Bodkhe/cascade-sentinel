#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export CASCADE_HOST="${CASCADE_HOST:-127.0.0.1}"
export PORT="${PORT:-8000}"
if [[ ! -f frontend/dist/index.html ]]; then
  echo "Built React files are missing. Run npm ci && npm run build in the project directory." >&2
  exit 1
fi
if ! python3 -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  echo "FastAPI/Uvicorn are unavailable. Install them with: python3 -m pip install -r requirements.txt" >&2
  exit 1
fi
exec python3 run.py
