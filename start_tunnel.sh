#!/usr/bin/env bash
# Share the app on the internet over HTTPS so a phone can open (and install) it.
#
#   ./start_tunnel.sh
#
# Start the server first:  cd backend && .venv/bin/uvicorn app.main:app --port 8000
#
# If NGROK_DOMAIN is set in .env (your free fixed ngrok address, for example
# my-name.ngrok-free.app) the address stays the same every time, so an app
# installed on the home screen keeps working. Without it, a temporary
# Cloudflare address is used, and it changes on every start.

set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

# Read one value from .env without running the file.
NGROK_DOMAIN="$(grep -E '^NGROK_DOMAIN=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"' \r' || true)"

if ! curl -s -m 3 -o /dev/null "http://localhost:${PORT}/health"; then
  echo "The app is not running on port ${PORT}. Start it first:"
  echo "  cd backend && .venv/bin/uvicorn app.main:app --port ${PORT}"
  exit 1
fi

if [ -n "${NGROK_DOMAIN}" ]; then
  echo "Fixed address: https://${NGROK_DOMAIN}"
  exec ngrok http --url="${NGROK_DOMAIN}" "${PORT}"
fi

echo "NGROK_DOMAIN is not set in .env, so this address is temporary."
exec cloudflared tunnel --no-autoupdate --url "http://localhost:${PORT}"
