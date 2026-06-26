#!/usr/bin/env python3
"""CLI tool: emit an agent event to the Discord HITL system.

Usage:
    # Emit a progress update:
    python -m automation.submit_event --type progress_update \
        --session abc123 --data '{"task": "Implemented OAuth", "progress_pct": 40}'

    # Emit a context checkpoint:
    python -m automation.submit_event --type context_checkpoint \
        --session abc123 --data '{"pct": 50, "action": "checkpoint_saved"}'

    # Report context level (updates context_level.json):
    python -m automation.submit_event --context-level 52 --session abc123

    # Emit session start:
    python -m automation.submit_event --type session_start --session abc123

    # Emit session end:
    python -m automation.submit_event --type session_end --session abc123 \
        --data '{"reason": "context_limit", "final_pct": 65}'
"""

from __future__ import annotations

import argparse
import json
import sys

from automation import config
from automation.providers.file import FileContextProvider, FileEventProvider
from automation.storage.models import AgentEvent, ContextLevel


def main():
    parser = argparse.ArgumentParser(description="Emit an agent event")
    parser.add_argument("--type", "-t", dest="event_type",
                        help="Event type: progress_update, context_checkpoint, session_start, session_end, error, milestone")
    parser.add_argument("--session", "-s", default="", help="Session ID")
    parser.add_argument("--data", "-d", default="{}", help="JSON data payload")
    parser.add_argument("--context-level", type=int, default=None,
                        help="Update context level (percentage). Can be used alone or with --type.")
    args = parser.parse_args()

    # Update context level if requested.
    if args.context_level is not None:
        ctx_provider = FileContextProvider(config.STATE_DIR)
        level = ContextLevel(pct=args.context_level, session_id=args.session)
        ctx_provider.write_level(level)
        print(f"Context level updated: {args.context_level}%")

    # Emit event if type is given.
    if args.event_type:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON data: {e}", file=sys.stderr)
            sys.exit(1)

        event = AgentEvent(
            type=args.event_type,
            session_id=args.session,
            data=data,
        )
        event_provider = FileEventProvider(config.STATE_DIR)
        event_provider.emit(event)
        print(f"Event emitted: {args.event_type}")
    elif args.context_level is None:
        print("Specify --type or --context-level", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
