#!/usr/bin/env sh
set -eu

frontend_url="${FRONTEND_URL:-http://127.0.0.1:8080}"
backend_url="${BACKEND_URL:-http://127.0.0.1:3000}"

curl --fail --silent --show-error "$backend_url/health/live" >/dev/null
curl --fail --silent --show-error "$backend_url/health/ready" >/dev/null
curl --fail --silent --show-error "$frontend_url/auth/login" >/dev/null

# Optional: stream one chat reply and fail if anything on the way buffers it.
# Set SMOKE_EMAIL and SSE_CHECK_PASSWORD (a real account; the reply goes to its
# "SSE streaming check" chat). SMOKE_STREAM_URL is where the stream is fetched:
# the frontend inside the compose network by default; your public URL also covers
# any reverse proxy in front, and must be HTTPS.
if [ -n "${SMOKE_EMAIL:-}" ]; then
  : "${SSE_CHECK_PASSWORD:?SSE_CHECK_PASSWORD is required with SMOKE_EMAIL}"
  if [ -n "${SMOKE_STREAM_URL:-}" ]; then
    set -- --base-url "$SMOKE_STREAM_URL"
  else
    # Plain HTTP on the compose network: the Secure session cookies go over it
    set -- --internal --base-url http://frontend:3000
  fi
  docker compose -f "${COMPOSE_FILE:-docker-compose.production.yml}" exec -T \
    -e SSE_CHECK_PASSWORD backend \
    python -m scripts.check_sse_streaming "$@" --email "$SMOKE_EMAIL"
else
  printf 'Skipping the streaming check (set SMOKE_EMAIL and SSE_CHECK_PASSWORD).\n'
fi

printf 'Cognolith smoke checks passed.\n'
