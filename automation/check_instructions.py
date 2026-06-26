#!/usr/bin/env python3
"""CLI tool: check for pending human instructions from Discord.

Usage:
    # Check for pending instructions:
    python -m automation.check_instructions

    # Check and output as JSON:
    python -m automation.check_instructions --json

    # Check if paused:
    python -m automation.check_instructions --check-pause

    # Acknowledge and output instructions:
    python -m automation.check_instructions --acknowledge
"""

from __future__ import annotations

import argparse
import json
import sys

from automation import config
from automation.providers.file import FileInstructionProvider


def main():
    parser = argparse.ArgumentParser(description="Check for human instructions")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--check-pause", action="store_true",
                        help="Check if the agent should pause (exit code 0 = paused, 1 = not paused)")
    parser.add_argument("--acknowledge", action="store_true",
                        help="Acknowledge pending instructions after reading them")
    args = parser.parse_args()

    provider = FileInstructionProvider(config.STATE_DIR)

    # Pause check mode.
    if args.check_pause:
        if provider.is_paused():
            print("PAUSED")
            sys.exit(0)
        else:
            print("RUNNING")
            sys.exit(1)

    # Check for instructions.
    pending = provider.check_pending()

    if not pending:
        if args.json_output:
            print(json.dumps({"instructions": [], "count": 0}))
        else:
            print("No pending instructions.")
        sys.exit(0)

    if args.acknowledge:
        for instr in pending:
            provider.acknowledge(instr.id)

    if args.json_output:
        print(json.dumps({
            "instructions": [instr.to_dict() for instr in pending],
            "count": len(pending),
        }, indent=2))
    else:
        print(f"Pending instructions: {len(pending)}")
        for instr in pending:
            status = "acknowledged" if args.acknowledge else "pending"
            print(f"\n  [{status}] {instr.id} from {instr.discord_username} ({instr.created_at}):")
            print(f"  {instr.instruction_text}")


if __name__ == "__main__":
    main()
