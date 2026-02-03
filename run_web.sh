#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""

cleanup() {
  echo ""
  echo "Stopping server..."
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "Building frontend..."
cd "${BASE_DIR}/webapp/frontend"
npm ci
npm run build

echo "Starting FastAPI (prod-like)..."
cd "${BASE_DIR}/webapp"

# No --reload (faster) and prod-ish settings
uvicorn main:app --host 0.0.0.0 --port 8000 --log-level warning &
BACKEND_PID=$!

echo ""
echo "Open: http://localhost:8000"
echo "Press Ctrl+C to stop"
wait "${BACKEND_PID}"
