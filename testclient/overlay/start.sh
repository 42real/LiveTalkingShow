#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [ -f ../load-env-defaults.sh ]; then
  . ../load-env-defaults.sh
  load_env_defaults .env
elif [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
export ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}"
export LIVETALKING_SERVER="${LIVETALKING_SERVER:-http://127.0.0.1:8050}"
export LIVETALKING_CLICK_THROUGH="${LIVETALKING_CLICK_THROUGH:-1}"
export LIVETALKING_PLAY_AUDIO="${LIVETALKING_PLAY_AUDIO:-0}"
export LIVETALKING_AUTO_SESSION="${LIVETALKING_AUTO_SESSION:-1}"
export LIVETALKING_CLOSE_SESSION_ON_EXIT="${LIVETALKING_CLOSE_SESSION_ON_EXIT:-0}"
export LIVETALKING_OUTPUT="${LIVETALKING_OUTPUT:-ws}"
if [ -n "${LIVETALKING_EXTRA_PATH:-}" ]; then
  export PATH="${LIVETALKING_EXTRA_PATH}:${PATH:-}"
fi
unset ELECTRON_RUN_AS_NODE
if [ -x ./node_modules/.bin/electron ]; then
  ./node_modules/.bin/electron .
else
  echo "electron binary not found, please run npm install first" >&2
  exit 1
fi
