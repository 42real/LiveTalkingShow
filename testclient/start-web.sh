#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

cd web
if [ ! -d node_modules ]; then
  npm install
fi
npm run start -- --host "${TEST_CLIENT_HOST:-0.0.0.0}" --port "${TEST_CLIENT_PORT:-8070}"
