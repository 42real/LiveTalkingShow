#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

[ -f "app.py" ] || {
    echo "app.py not found in $SCRIPT_DIR" >&2
    exit 1
}

[ -d ".venv" ] || uv sync --python 3.10 --inexact

[ -f "models/wav2lip.pth" ] || echo "models/wav2lip.pth is missing; wav2lip startup will fail until the model is provided"

echo "Starting LiveTalking Service..."
exec uv run --no-sync --python "${LIVETALKING_PYTHON:-.venv/bin/python}" python app.py "$@"
