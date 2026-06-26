#!/usr/bin/env python3
"""CLI tool: submit a question to the Discord human-in-the-loop system.

Usage:
    # Submit from a file containing agent output:
    python -m automation.submit_question --file output.txt

    # Submit from stdin (pipe agent output):
    echo "QUESTION_TYPE: Business ..." | python -m automation.submit_question

    # Submit with explicit fields:
    python -m automation.submit_question \\
        --type "Business" \\
        --question "Should we use Stripe or Paddle?" \\
        --context "Need a payment processor" \\
        --options "A:Stripe,B:Paddle,C:Neither" \\
        --recommended "A" \\
        --rationale "Stripe has better docs"
"""

from __future__ import annotations

import argparse
import json
import sys

from automation import config
from automation.agents.decisions import has_existing_decision
from automation.agents.question_parser import contains_question, parse_question
from automation.storage.database import Database
from automation.storage.models import Question


def main():
    parser = argparse.ArgumentParser(description="Submit a question to Discord")
    parser.add_argument("--file", "-f", help="File containing agent output to parse")
    parser.add_argument("--type", dest="qtype", help="Question type")
    parser.add_argument("--question", "-q", help="Question text")
    parser.add_argument("--context", "-c", help="Context")
    parser.add_argument("--options", help="Options as 'A:text,B:text,...'")
    parser.add_argument("--recommended", "-r", help="Recommended option")
    parser.add_argument("--rationale", help="Rationale")
    parser.add_argument("--impact", help="Expected impact")
    parser.add_argument("--confidence", help="Confidence 0-100")
    parser.add_argument("--project", "-p", help="Project slug override")
    args = parser.parse_args()

    project_slug = args.project or config.PROJECT_SLUG
    db = Database(config.DB_PATH)

    # Mode 1: Parse from file or stdin.
    if args.file or not args.question:
        if args.file:
            text = open(args.file, encoding="utf-8").read()
        else:
            text = sys.stdin.read()

        if not contains_question(text):
            print("No WAITING_FOR_DISCORD_REPLY block found in input.", file=sys.stderr)
            sys.exit(1)

        question = parse_question(text, project_slug)
        if not question:
            print("Failed to parse question from input.", file=sys.stderr)
            sys.exit(1)

    # Mode 2: Explicit fields.
    else:
        options_list = []
        if args.options:
            for part in args.options.split(","):
                if ":" in part:
                    label, text = part.split(":", 1)
                    options_list.append({"label": label.strip(), "text": text.strip()})

        question = Question(
            project_slug=project_slug,
            question_type=args.qtype or "",
            question=args.question,
            context=args.context or "",
            options=json.dumps(options_list),
            recommended=args.recommended or "",
            rationale=args.rationale or "",
            expected_impact=args.impact or "",
            confidence=args.confidence or "",
        )

    # Check DECISIONS.md first.
    existing = has_existing_decision(question.question)
    if existing:
        print(f"Already decided in DECISIONS.md:\n{existing}", file=sys.stderr)
        print(existing)
        sys.exit(0)

    # Check for duplicates.
    dup = db.find_duplicate(project_slug, question.question)
    if dup:
        print(f"Duplicate question already pending (id={dup.id}). Skipping.", file=sys.stderr)
        sys.exit(0)

    # Insert.
    question = db.insert_question(question)
    print(f"Question submitted (id={question.id}). Waiting for Discord response...")


if __name__ == "__main__":
    main()
