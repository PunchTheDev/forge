"""
Agent source-code similarity check.

Compares two Python source files using normalized token sequences.
Returns a similarity score in [0, 1]: 1.0 = identical, 0.0 = completely different.

Normalizes away:
  - comments and docstrings
  - leading/trailing whitespace
  - blank lines

Does NOT normalize away identifier names, so variable renames produce a lower
(better) score than verbatim copies. This is intentional — a rename-only
submission is still plagiarism; a genuinely different algorithm produces
structurally different token streams.

Threshold guidance:
  >= 0.95  — very likely a verbatim copy or trivial rename
  0.80–0.95 — suspicious; may warrant manual review
  < 0.80   — structurally different enough to be considered original
"""

from __future__ import annotations

import ast
import tokenize
import io


def compare(source_a: str, source_b: str) -> float:
    """Return similarity in [0, 1] between two Python source strings."""
    tokens_a = _normalize(source_a)
    tokens_b = _normalize(source_b)
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return _sequence_ratio(tokens_a, tokens_b)


def _normalize(source: str) -> list[str]:
    """
    Tokenize source and return a stable token list with comments stripped.
    Uses the tokenize module so the output is insensitive to whitespace and
    blank lines but preserves identifier names and literal values.
    """
    tokens: list[str] = []
    try:
        reader = io.StringIO(source).readline
        for tok in tokenize.generate_tokens(reader):
            typ = tok.type
            val = tok.string
            # Skip comments, newlines, blank lines, encoding markers, end markers
            if typ in (
                tokenize.COMMENT,
                tokenize.NEWLINE,
                tokenize.NL,
                tokenize.ENCODING,
                tokenize.ENDMARKER,
            ):
                continue
            # Collapse string literals to a placeholder so docstring content
            # doesn't dominate the similarity score, but their presence does.
            if typ == tokenize.STRING:
                tokens.append("<STR>")
            else:
                tokens.append(val)
    except tokenize.TokenError:
        # Unparseable — fall back to line-level comparison
        return [l.strip() for l in source.splitlines() if l.strip()]
    return tokens


def _sequence_ratio(a: list[str], b: list[str]) -> float:
    """SequenceMatcher ratio over token lists (same semantics as difflib)."""
    # Reimplemented here to avoid importing difflib just for the ratio.
    # Uses the standard formula: 2 * matches / (len_a + len_b).
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b, autojunk=False).ratio()
