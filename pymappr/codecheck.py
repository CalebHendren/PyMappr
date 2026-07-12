"""Static validation for Python/R map scripts, LLM-free.

Used two ways: the tests validate every script the deterministic code
export (``pymappr/codegen.py``) produces, and the experimental LLM
Assist dialog offers a "Validate code" button so users can sanity-check
a model's reply before running it.

The checks are deliberately modest and fully offline:

* **Python** - a real syntax check via :func:`ast.parse`, plus a warning
  when a "script" contains no imports at all.
* **R** - a small scanner that understands comments, strings (including
  R 4 raw strings), and bracket nesting, catching the failure modes LLMs
  actually produce: truncated replies, unbalanced brackets, unclosed
  strings.
* **Both** - leftover placeholders (TODO, ``<your file>``, path/to, ...)
  that the user still needs to fill in.

Passing means "this parses", never "this is correct": the user still has
to run the code and compare its output to the map.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

LANGUAGES = ("Python", "R")

_MAX_REPORTED = 12

_PLACEHOLDER_PATTERNS = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bREPLACE[ _-]?ME\b", re.IGNORECASE),
    # Deliberately case-sensitive: placeholders are conventionally
    # written in caps ("YOUR_FILE.csv"), while prose ("your file") isn't.
    re.compile(r"\bYOUR[ _](API[ _]?KEY|FILE|PATH|DATA)\b"),
    re.compile(r"\bpath/to\b", re.IGNORECASE),
    re.compile(r"<\s*(?:your|path|file|insert)[^>\n]*>", re.IGNORECASE),
]

_OPENERS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = {")": "(", "]": "[", "}": "{"}


@dataclass(frozen=True)
class Issue:
    """One finding: *severity* is "error" or "warning"."""

    severity: str
    message: str
    line: int | None = None

    def __str__(self) -> str:
        where = f"line {self.line}: " if self.line else ""
        return f"{self.severity}: {where}{self.message}"


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def validate_code(language: str, code: str) -> list[Issue]:
    """Every issue found in *code*, errors first."""
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language!r}")
    check = validate_python if language == "Python" else validate_r
    issues = check(code) + find_placeholders(code)
    return sorted(issues, key=lambda issue: (issue.severity != "error",
                                             issue.line or 0))


# ----------------------------------------------------------------- python

def validate_python(code: str) -> list[Issue]:
    """Syntax-check Python source with the real parser."""
    if not code.strip():
        return [Issue("error", "The code is empty.")]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        detail = (exc.text or "").strip()
        message = f"Python syntax error: {exc.msg}"
        if detail:
            message += f" \N{RIGHTWARDS ARROW} {detail[:80]}"
        return [Issue("error", message, exc.lineno)]
    except (ValueError, RecursionError) as exc:  # NUL bytes, absurd nesting
        return [Issue("error", f"Could not parse the code: {exc}")]
    if not any(isinstance(node, (ast.Import, ast.ImportFrom))
               for node in ast.walk(tree)):
        return [Issue("warning", "No imports found - this does not look "
                                 "like a complete script.")]
    return []


# ---------------------------------------------------------------------- R

def _r_raw_string_end(code: str, start: int) -> int | None:
    """End index (exclusive) of an R 4 raw string starting at *start*
    (the r/R), or None if it never closes."""
    match = re.match(r'[rR]("|\')(-*)(\(|\[|\{)', code[start:])
    if match is None:
        return None
    quote, dashes, opener = match.groups()
    closer = {"(": ")", "[": "]", "{": "}"}[opener] + dashes + quote
    end = code.find(closer, start + match.end())
    return None if end < 0 else end + len(closer)


def validate_r(code: str) -> list[Issue]:
    """Scan R source for unbalanced brackets and unclosed strings.

    Comments, ordinary strings, backtick names, and raw strings are
    skipped, so brackets inside them never count.
    """
    if not code.strip():
        return [Issue("error", "The code is empty.")]
    issues: list[Issue] = []
    stack: list[tuple[str, int]] = []  # (opener, line)
    line = 1
    in_string: str | None = None  # the quote character, or None
    string_line = 0
    i = 0
    while i < len(code):
        char = code[i]
        if char == "\n":
            line += 1
            i += 1
            continue
        if in_string is not None:
            if char == "\\":
                i += 2
                continue
            if char == in_string:
                in_string = None
            i += 1
            continue
        if char == "#":  # comment: skip to end of line
            end = code.find("\n", i)
            i = len(code) if end < 0 else end
            continue
        if char in "rR":
            end = _r_raw_string_end(code, i)
            if end is None and re.match(r'[rR]("|\')(-*)(\(|\[|\{)',
                                        code[i:]):
                return issues + [Issue("error", "Unclosed raw string.",
                                       line)]
            if end is not None:
                line += code.count("\n", i, end)
                i = end
                continue
            i += 1
            continue
        if char in "\"'`":
            in_string = char
            string_line = line
            i += 1
            continue
        if char in _OPENERS:
            stack.append((char, line))
        elif char in _CLOSERS:
            if not stack:
                issues.append(Issue("error",
                                    f"Unmatched closing {char!r}.", line))
            else:
                opener, opened_at = stack.pop()
                if _OPENERS[opener] != char:
                    issues.append(Issue(
                        "error",
                        f"Mismatched brackets: {opener!r} (line "
                        f"{opened_at}) closed by {char!r}.", line))
        i += 1
    if in_string is not None:
        issues.append(Issue("error", f"Unclosed string (started with "
                                     f"{in_string}).", string_line))
    for opener, opened_at in stack[:_MAX_REPORTED]:
        issues.append(Issue("error", f"Unclosed {opener!r}.", opened_at))
    return issues


# ----------------------------------------------------------- placeholders

def find_placeholders(code: str) -> list[Issue]:
    """Warn about markers the user is expected to fill in by hand."""
    issues: list[Issue] = []
    for number, text in enumerate(code.splitlines(), start=1):
        for pattern in _PLACEHOLDER_PATTERNS:
            match = pattern.search(text)
            if match:
                issues.append(Issue(
                    "warning",
                    f"Placeholder to fill in: {match.group(0)!r}", number))
                break
        if len(issues) >= _MAX_REPORTED:
            break
    return issues


def summarize(language: str, issues: list[Issue]) -> str:
    """A one-paragraph human-readable result for the UI."""
    if not issues:
        return (f"{language} check passed: the code parses and no "
                "placeholders are left. This is a syntax check only - "
                "run the code yourself and compare its output to your "
                "map.")
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = len(issues) - errors
    parts = []
    if errors:
        parts.append(f"{errors} error{'s' if errors != 1 else ''}")
    if warnings:
        parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
    listed = "\n".join(str(issue) for issue in issues[:_MAX_REPORTED])
    more = len(issues) - _MAX_REPORTED
    if more > 0:
        listed += f"\n\N{HORIZONTAL ELLIPSIS} and {more} more"
    return f"{language} check found {' and '.join(parts)}:\n{listed}"
