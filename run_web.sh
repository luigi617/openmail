#!/usr/bin/env bash
set -euo pipefail

# Run from anywhere: base dir = where this script lives
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_PID=""
FRONTEND_PID=""
VITE_LOG=""

cleanup() {
  echo ""
  echo "Stopping FastAPI and Vite..."

  # Kill only the processes we started (if still running)
  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi

  # Clean up temp file
  if [[ -n "${VITE_LOG}" && -f "${VITE_LOG}" ]]; then
    rm -f "${VITE_LOG}" || true
  fi
}
trap cleanup EXIT INT TERM

# ---------- FastAPI ----------
echo "Starting FastAPI backend..."
cd "${BASE_DIR}/webapp"
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# ---------- Vite ----------
echo "Starting Vite frontend..."
cd "${BASE_DIR}/webapp/frontend"

VITE_LOG="$(mktemp)"
: > "${VITE_LOG}"

npm run dev 2>&1 | tee -a "${VITE_LOG}" &
FRONTEND_PID=$!

# ---------- Detect Vite port ----------
echo "Waiting for Vite dev server to start..."

VITE_PORT=""
START_TIME="$(date +%s)"
TIMEOUT_SECONDS=20

while [[ -z "${VITE_PORT}" ]]; do
  # Avoid set -e killing the loop if grep finds nothing
  VITE_PORT="$(
    grep -Eo 'Local:[[:space:]]+http://localhost:[0-9]+' "${VITE_LOG}" 2>/dev/null \
      | head -n 1 \
      | grep -Eo '[0-9]+$' 2>/dev/null || true
  )"

  # Fallback: sometimes Vite prints "Local:   http://127.0.0.1:5173/"
  if [[ -z "${VITE_PORT}" ]]; then
    VITE_PORT="$(
      grep -Eo 'Local:[[:space:]]+http://127\.0\.0\.1:[0-9]+' "${VITE_LOG}" 2>/dev/null \
        | head -n 1 \
        | grep -Eo '[0-9]+$' 2>/dev/null || true
    )"
  fi

  # Timeout protection (don’t hang forever)
  NOW="$(date +%s)"
  if (( NOW - START_TIME > TIMEOUT_SECONDS )); then
    echo "Warning: couldn't detect Vite port from logs within ${TIMEOUT_SECONDS}s."
    echo "Assuming default Vite port 5173."
    VITE_PORT="5173"
    break
  fi

  sleep 0.3
done

echo ""
echo "FastAPI running at  http://localhost:8000"
echo "Vite running at     http://localhost:${VITE_PORT}"
echo ""
echo "Press Ctrl+C to stop everything"

wait "${BACKEND_PID}" "${FRONTEND_PID}"
