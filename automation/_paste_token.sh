#!/usr/bin/env bash
# Reads the bot token from the system clipboard and writes it into automation/.env.
# Usage: bash automation/_paste_token.sh
set -euo pipefail
cd "$(dirname "$0")/.."
TOKEN="$(pbpaste)"
if [ -z "$TOKEN" ] || [[ ! "$TOKEN" =~ ^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$ ]]; then
    echo "Clipboard doesn't contain a Discord bot token (got ${#TOKEN} chars)." >&2
    exit 1
fi
# Replace the DISCORD_BOT_TOKEN line in .env.
python3 - "$TOKEN" <<'PY'
import sys, pathlib, re
token = sys.argv[1]
env = pathlib.Path("automation/.env")
text = env.read_text()
new = re.sub(r"^DISCORD_BOT_TOKEN=.*$", f"DISCORD_BOT_TOKEN={token}", text, flags=re.M)
env.write_text(new)
print(f"Updated DISCORD_BOT_TOKEN ({len(token)} chars) in {env}")
PY
