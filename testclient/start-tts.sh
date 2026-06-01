#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
. ./load-env-defaults.sh
load_env_defaults .env

cd backend
uv run python robottts_test_server.py
