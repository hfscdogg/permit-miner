#!/usr/bin/env bash
# run.sh — Start the Permit Miner FastAPI web server
# Requires: pip install -r requirements.txt && cp .env.example .env (fill in values)

set -e
cd "$(dirname "$0")"

exec uvicorn web.app:app --host 0.0.0.0 --port 8000
