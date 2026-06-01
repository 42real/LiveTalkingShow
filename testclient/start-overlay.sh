#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
. ./load-env-defaults.sh
load_env_defaults .env

if ! command -v npm >/dev/null 2>&1; then
  for node_dir in "$HOME/anaconda3/bin" "$HOME/miniconda3/bin"; do
    if [ -x "$node_dir/npm" ]; then
      export PATH="$node_dir:$PATH"
      break
    fi
  done
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js or add npm to PATH before starting the overlay test client." >&2
  exit 1
fi

cd overlay
if [ ! -d node_modules ]; then
  npm install
fi
./start.sh
