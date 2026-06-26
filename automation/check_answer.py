#!/usr/bin/env python3
"""CLI tool: check if a submitted question has been answered.

Usage:
    # Check a specific question:
    python -m automation.check_answer --id 42

    # Check the latest pending question for this project:
    python -m automation.check_answer --latest

    # Block until an answer arrives (with timeout):
    python -m automation.check_answer --id 42 --wait --timeout 3600
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from automation import config
from automation.storage.database import Database
from automation.storage.models import QuestionStatus


def main():
    parser = argparse.ArgumentParser(description="Check for an answer to a question")
    parser.add_argument("--id", type=int, help="Question ID to check")
    parser.add_argument("--latest", action="store_true", help="Check the latest question")
    parser.add_argument("--wait", action="store_true", help="Block until answered")
    parser.add_argument("--timeout", type=int, default=0, help="Max seconds to wait (0=forever)")
    parser.add_argument("--project", "-p", help="Project slug override")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_slug = args.project or config.PROJECT_SLUG
    db = Database(config.DB_PATH)

    # Determine which question to check.
    question_id = args.id
    if not question_id and args.latest:
        # Find the latest question for this project.
        sent = db.get_sent_questions(project_slug)
        pending = db.get_pending_questions(project_slug)
        all_active = sent + pending
        if all_active:
            question_id = all_active[-1].id
        else:
            print("No active questions found.", file=sys.stderr)
            sys.exit(1)

    if not question_id:
        print("Specify --id or --latest", file=sys.stderr)
        sys.exit(1)

    start = time.time()
    while True:
        question = db.get_question(question_id)
        if not question:
            print(f"Question {question_id} not found.", file=sys.stderr)
            sys.exit(1)

        if question.status == QuestionStatus.ANSWERED:
            answer = db.get_answer_for_question(question_id)
            if answer:
                if args.json_output:
                    print(json.dumps({
                        "question_id": question.id,
                        "question": question.question,
                        "status": "answered",
                        "answer_text": answer.answer_text,
                        "answer_option": answer.answer_option,
                        "answered_by": answer.discord_username,
                        "answered_at": answer.created_at,
                    }, indent=2))
                else:
                    print(f"Question #{question.id}: ANSWERED")
                    if answer.answer_option:
                        print(f"  Option: {answer.answer_option}")
                    print(f"  Answer: {answer.answer_text}")
                    print(f"  By: {answer.discord_username}")
                sys.exit(0)

        elif question.status == QuestionStatus.ERROR:
            print(f"Question #{question_id} is in ERROR state.", file=sys.stderr)
            sys.exit(2)

        if not args.wait:
            status = question.status.value
            if args.json_output:
                print(json.dumps({"question_id": question.id, "status": status}))
            else:
                print(f"Question #{question_id}: {status.upper()}")
            sys.exit(3)

        # Wait mode.
        elapsed = time.time() - start
        if args.timeout and elapsed >= args.timeout:
            print(f"Timeout after {args.timeout}s. Question still {question.status.value}.", file=sys.stderr)
            sys.exit(4)

        time.sleep(2)


if __name__ == "__main__":
    main()
