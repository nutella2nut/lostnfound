#!/usr/bin/env bash
# Launcher for the Discord HITL bot (run on the macOS host).
#
# Sets up a local venv at ./.venv-host the first time, installs deps,
# loads automation/.env, then runs `python -m automation`.

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
VENV="$PROJECT_ROOT/.venv-host"

# 1. Ensure venv exists with discord.py installed.
if [ ! -x "$VENV/bin/python" ]; then
    echo "[run_bot] Creating venv at $VENV..."
    python3 -m venv "$VENV"
fi

echo "[run_bot] Installing/upgrading dependencies..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r automation/requirements.txt

# 2. Load .env.
if [ ! -f automation/.env ]; then
    echo "[run_bot] ERROR: automation/.env not found." >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
source automation/.env
set +a

# 3. Run.
echo "[run_bot] Starting bot. Logs stream below; Ctrl-C to stop."
exec "$VENV/bin/python" -m automation
