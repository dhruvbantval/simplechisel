#!/usr/bin/env bash
# One command: build the dashboard, then serve the site AND the pipeline API
# from a single origin. Open the printed URL, click Generate, watch the success
# rate appear -- tests, cosim run, and JSON all happen behind the button.
#
#   cosim/webapp/serve.sh
#   PORT=9000 cosim/webapp/serve.sh
#
# This is the production-shaped path (static build + API, same split that
# deploys to Vercel). For hot-reload development use dev.sh instead.
set -euo pipefail

WEBAPP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASH="$(cd "$WEBAPP/../CPU-Dashboard" && pwd)"
PORT="${PORT:-8000}"

# Same-origin API: the built site calls /api on the host that served it.
export VITE_API_BASE=""

echo "==> Building dashboard"
( cd "$DASH"
  [ -d node_modules ] || npm install
  npm run build )

echo "==> Publishing build to the backend's static dir"
rm -rf "$WEBAPP/static"
cp -r "$DASH/dist" "$WEBAPP/static"

echo "==> Starting backend + site on http://127.0.0.1:$PORT"
echo "    Open it, go to Generate, and click Generate tests."
exec python3 "$WEBAPP/server.py"
