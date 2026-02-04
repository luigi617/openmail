#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""

# Load .env
ENV_FILE="${BASE_DIR}/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
else
  echo "ERROR: .env file not found"
  exit 1
fi

# Set default PORT if not provided
PORT="${PORT:-8000}"

# Check if PORT is already in use
if lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: Port ${PORT} is already in use"
  exit 1
fi

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

# Optional: expose backend origin to frontend build
cat > .env.production <<EOF
VITE_BACKEND_ORIGIN=http://localhost:${PORT}
EOF

npm ci
npm run build

echo "Starting FastAPI..."
cd "${BASE_DIR}/webapp"

uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --log-level warning &

BACKEND_PID=$!

echo ""
echo "Open: http://localhost:${PORT}"
echo "Press Ctrl+C to stop"
wait "${BACKEND_PID}"
