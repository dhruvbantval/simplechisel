#!/usr/bin/env bash
# Hot-reload development: runs the pipeline backend and the Vite dev server
# together. Vite proxies /api to the backend, so the site calls same-origin and
# edits to the dashboard reload instantly.
#
#   farm/webapp/dev.sh
#
# Backend on :8000, site on :5173 (Vite's default). Ctrl-C stops both.
set -euo pipefail

WEBAPP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASH="$(cd "$WEBAPP/../dashboard" && pwd)"
BACKEND_PORT="${PORT:-8000}"

( cd "$DASH"; [ -d node_modules ] || npm install )

echo "==> Starting backend on :$BACKEND_PORT"
PYBIN="$WEBAPP/../.venv/bin/python"
[ -x "$PYBIN" ] || PYBIN=python3
PORT="$BACKEND_PORT" "$PYBIN" "$WEBAPP/server.py" &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT

echo "==> Starting Vite dev server (proxies /api to :$BACKEND_PORT)"
cd "$DASH"
API_PROXY="http://127.0.0.1:$BACKEND_PORT" exec npm run dev
