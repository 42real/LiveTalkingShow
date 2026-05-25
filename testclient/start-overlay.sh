#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

cd overlay
if [ ! -d node_modules ]; then
  npm install
fi
./start.sh
