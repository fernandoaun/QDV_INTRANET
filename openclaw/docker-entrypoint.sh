#!/bin/sh
set -eu

export OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-/data/.openclaw}"
export OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-/data/workspace}"
export OPENCLAW_CONFIG_DIR="${OPENCLAW_CONFIG_DIR:-$OPENCLAW_STATE_DIR}"
# Render inyecta PORT; en Docker Compose local PORT=18789.
export OPENCLAW_GATEWAY_PORT="${PORT:-${OPENCLAW_GATEWAY_PORT:-18789}}"

mkdir -p "$OPENCLAW_STATE_DIR" "$OPENCLAW_WORKSPACE_DIR" \
  "$OPENCLAW_WORKSPACE_DIR/skills"

if [ "$(id -u)" = "0" ]; then
  chown -R node:node /data /opt/qdv 2>/dev/null || true
  if command -v runuser >/dev/null 2>&1; then
    exec runuser -u node -- "$0" "$@"
  fi
  if command -v gosu >/dev/null 2>&1; then
    exec gosu node "$0" "$@"
  fi
fi

node /opt/qdv/ensure_config.mjs

run_gateway() {
  if [ -f /app/openclaw.mjs ]; then
    exec node /app/openclaw.mjs gateway --allow-unconfigured
  fi
  if [ -f /app/dist/index.js ]; then
    exec node /app/dist/index.js gateway --allow-unconfigured
  fi
  if command -v openclaw >/dev/null 2>&1; then
    exec openclaw gateway --allow-unconfigured
  fi
  echo "ERROR: no se encontró el binario de OpenClaw en la imagen." >&2
  exit 1
}

if [ "$#" -eq 0 ]; then
  run_gateway
fi

exec "$@"
