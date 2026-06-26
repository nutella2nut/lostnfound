"""
Regression guard for precise wording (§3 / §8.1).

Scans templates and Python source for banned vague phrases.
Templates are scanned as raw text; Python files are scanned via AST
to match only string literals (not variable names or comments).
"""

import ast
import os
import re
from pathlib import Path

from django.test import TestCase

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # repo root

BANNED_PATTERNS = [
    re.compile(r"\bcome\s+collect\b", re.IGNORECASE),
    re.compile(r"\bcome\s+(get|grab|pick)\b", re.IGNORECASE),
    re.compile(r"\bpick\s+(it|them|your\s+\w+)\s+up\b", re.IGNORECASE),
    re.compile(r"\bgrab\s+(it|them|your\s+\w+)\b", re.IGNORECASE),
    re.compile(r"\byour\s+stuff\b", re.IGNORECASE),
    re.compile(r"\byour\s+things\b", re.IGNORECASE),
    re.compile(r"\bcontact\s+us\b", re.IGNORECASE),
    re.compile(r"\bwe['\u2019]ll\s+let\s+you\s+know\b", re.IGNORECASE),
    re.compile(r"\blost\s+something\??\b", re.IGNORECASE),
    re.compile(r"\bfound\s+something\??\b", re.IGNORECASE),
]

# Per-file allowlist: {relative_path: [pattern_string, ...]}
# Each entry must have a comment explaining why.
ALLOWED_EXCEPTIONS = {
    # Example: "templates/inventory/foo.html": [r"\blost\s+something"],
}

# Template directories to scan
TEMPLATE_DIRS = [
    BASE_DIR / "templates" / "inventory",
    BASE_DIR / "templates" / "registration",
]

# Python source files to scan (string literals only, via AST)
PYTHON_SOURCE_FILES = [
    BASE_DIR / "inventory" / "views.py",
    BASE_DIR / "inventory" / "forms.py",
    BASE_DIR / "inventory" / "models.py",
]


def _context_snippet(text, start, end, width=80):
    """Return up to `width` chars of context around the match."""
    ctx_start = max(0, start - (width // 2))
    ctx_end = min(len(text), end + (width // 2))
    snippet = text[ctx_start:ctx_end].replace("\n", " ")
    return snippet


def _get_allowed_patterns(filepath_rel):
    """Return compiled regexes that are allowed for a given file."""
    allowed_strs = ALLOWED_EXCEPTIONS.get(filepath_rel, [])
    return [re.compile(s, re.IGNORECASE) for s in allowed_strs]


def _scan_text(text, filepath_rel, line_offset=0):
    """Scan text for banned patterns. Returns list of (file, line, match, context)."""
    violations = []
    allowed = _get_allowed_patterns(filepath_rel)
    lines = text.split("\n")

    for line_num_0, line in enumerate(lines):
        for pattern in BANNED_PATTERNS:
            m = pattern.search(line)
            if m:
                # Check if this match is in the allowed list
                is_allowed = any(a.search(line) for a in allowed)
                if not is_allowed:
                    actual_line = line_num_0 + 1 + line_offset
                    context = _context_snippet(
                        text,
                        text.index(line) + m.start(),
                        text.index(line) + m.end(),
                    )
                    violations.append(
                        (filepath_rel, actual_line, m.group(), context)
                    )
    return violations


def _extract_string_literals(source, filepath):
    """Extract all string literals from Python source via AST."""
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    strings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            # f-string: walk its string parts
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    strings.append((node.lineno, part.value))
    return strings


class WordingAuditTest(TestCase):
    """Ensure banned vague phrases do not appear in templates or Python source."""

    def test_templates_no_banned_phrases(self):
        """Scan all HTML templates for banned wording patterns."""
        violations = []
        for template_dir in TEMPLATE_DIRS:
            if not template_dir.exists():
                continue
            for html_file in sorted(template_dir.rglob("*.html")):
                rel = str(html_file.relative_to(BASE_DIR))
                text = html_file.read_text(encoding="utf-8", errors="replace")
                violations.extend(_scan_text(text, rel))

        if violations:
            msg_lines = ["Banned phrases found in templates:\n"]
            for filepath, line, matched, context in violations:
                msg_lines.append(
                    f"  {filepath}:{line}  matched={matched!r}  "
                    f"context=...{context}..."
                )
            self.fail("\n".join(msg_lines))

    def test_python_source_no_banned_phrases(self):
        """Scan string literals in Python source files for banned wording."""
        violations = []
        for py_file in PYTHON_SOURCE_FILES:
            if not py_file.exists():
                continue
            rel = str(py_file.relative_to(BASE_DIR))
            source = py_file.read_text(encoding="utf-8", errors="replace")
            string_literals = _extract_string_literals(source, py_file)

            allowed = _get_allowed_patterns(rel)
            for lineno, value in string_literals:
                for pattern in BANNED_PATTERNS:
                    m = pattern.search(value)
                    if m:
                        is_allowed = any(a.search(value) for a in allowed)
                        if not is_allowed:
                            context = _context_snippet(
                                value, m.start(), m.end()
                            )
                            violations.append(
                                (rel, lineno, m.group(), context)
                            )

        if violations:
            msg_lines = ["Banned phrases found in Python source:\n"]
            for filepath, line, matched, context in violations:
                msg_lines.append(
                    f"  {filepath}:{line}  matched={matched!r}  "
                    f"context=...{context}..."
                )
            self.fail("\n".join(msg_lines))

    def test_footer_disclaimer_present(self):
        """Every template must include the TRACE footer disclaimer."""
        footer_text = "TRACE is operated by TISB"
        missing = []
        for template_dir in TEMPLATE_DIRS:
            if not template_dir.exists():
                continue
            for html_file in sorted(template_dir.rglob("*.html")):
                # Skip partials (underscore-prefixed) and email templates
                if html_file.name.startswith("_"):
                    continue
                if "email" in html_file.parts:
                    continue
                rel = str(html_file.relative_to(BASE_DIR))
                text = html_file.read_text(encoding="utf-8", errors="replace")
                # Footer may be in the template directly or via an included
                # sidebar partial (_sidebar.html / _sidebar_public.html)
                has_footer = (
                    footer_text in text
                    or 'include "inventory/_sidebar.html"' in text
                    or 'include "inventory/_sidebar_public.html"' in text
                )
                if not has_footer:
                    missing.append(rel)

        if missing:
            self.fail(
                "Footer disclaimer missing from:\n  "
                + "\n  ".join(missing)
            )
