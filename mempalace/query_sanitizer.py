#!/usr/bin/env python3
"""
query_sanitizer.py — Prevent system-prompt contamination in search queries.

VERSION 1.0

AI agents frequently prepend their system prompt or tool-use context to search
queries, which causes ChromaDB semantic search to match on the boilerplate
instead of the actual question.  This module implements a four-stage cascading
sanitizer that gracefully degrades rather than silently failing.

Stages:
    1. Passthrough — short queries (<=200 chars) go straight through.
    2. Question extraction — find sentences ending with "?" and use those.
    3. Tail sentence extraction — take the final meaningful sentence.
    4. Tail truncation — last 500 characters as a final fallback.

Design follows PR #385 "disaster mitigation" philosophy: we cannot prevent
agents from contaminating queries (MCP uses plain-string params), but we
can recover 70-80% of accuracy in the worst case.
"""

import re
from dataclasses import dataclass
from typing import Optional

# ── Thresholds ────────────────────────────────────────────────────────────────

MAX_PASSTHROUGH_LENGTH = 200
TAIL_TRUNCATION_LENGTH = 500

# Common system prompt markers that signal contamination
_SYSTEM_MARKERS = re.compile(
    r"(you are |your role is |system:|instructions?:|<system>|<instructions>|"
    r"as an ai |as a helpful |I am an AI|tool_use|function_call)",
    re.IGNORECASE,
)

# Sentence boundary: period/exclamation/question + whitespace + capital letter
_SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])\s+(?=[A-Z"])')


@dataclass
class SanitizeResult:
    """Result of query sanitization with metadata for debugging."""

    query: str
    stage: int
    stage_name: str
    original_length: int
    sanitized_length: int
    was_contaminated: bool


def sanitize_query(query: str, context: Optional[str] = None) -> SanitizeResult:
    """Sanitize a search query, stripping system-prompt contamination.

    Args:
        query: The raw query string from the MCP call.
        context: Optional separate context parameter (if the caller split
                 background info from the actual query, we use the query as-is).

    Returns:
        SanitizeResult with the cleaned query and metadata about which stage
        was applied.
    """
    if not isinstance(query, str) or not query.strip():
        return SanitizeResult(
            query="",
            stage=0,
            stage_name="empty",
            original_length=0,
            sanitized_length=0,
            was_contaminated=False,
        )

    original = query.strip()
    original_length = len(original)

    # If a separate context param was provided, the caller already split
    # the query from the context — trust the query as-is.
    if context and isinstance(context, str) and context.strip():
        return SanitizeResult(
            query=original,
            stage=0,
            stage_name="context_separated",
            original_length=original_length,
            sanitized_length=len(original),
            was_contaminated=False,
        )

    # Detect contamination
    contaminated = bool(_SYSTEM_MARKERS.search(original))

    # ── Stage 1: Passthrough for short queries ────────────────────────────
    if original_length <= MAX_PASSTHROUGH_LENGTH:
        return SanitizeResult(
            query=original,
            stage=1,
            stage_name="passthrough",
            original_length=original_length,
            sanitized_length=original_length,
            was_contaminated=contaminated,
        )

    # Only apply deeper stages if contamination is detected
    if not contaminated:
        return SanitizeResult(
            query=original,
            stage=1,
            stage_name="passthrough_clean",
            original_length=original_length,
            sanitized_length=original_length,
            was_contaminated=False,
        )

    # ── Stage 2: Question extraction ──────────────────────────────────────
    # Find sentences that end with "?" — these are most likely the actual query
    sentences = _SENTENCE_BOUNDARY.split(original)
    questions = [s.strip() for s in sentences if s.strip().endswith("?")]
    if questions:
        # Use the last question (most likely the actual search intent)
        extracted = questions[-1]
        return SanitizeResult(
            query=extracted,
            stage=2,
            stage_name="question_extraction",
            original_length=original_length,
            sanitized_length=len(extracted),
            was_contaminated=True,
        )

    # ── Stage 3: Tail sentence extraction ─────────────────────────────────
    # Grab the final meaningful sentence — agents usually append their
    # actual query after the system prompt preamble.
    if sentences:
        tail = sentences[-1].strip()
        if len(tail) >= 10:  # Minimum viable sentence
            return SanitizeResult(
                query=tail,
                stage=3,
                stage_name="tail_sentence",
                original_length=original_length,
                sanitized_length=len(tail),
                was_contaminated=True,
            )

    # ── Stage 4: Tail truncation ──────────────────────────────────────────
    # Last resort: take the final N characters. Still better than searching
    # on the full system prompt.
    truncated = original[-TAIL_TRUNCATION_LENGTH:].strip()
    return SanitizeResult(
        query=truncated,
        stage=4,
        stage_name="tail_truncation",
        original_length=original_length,
        sanitized_length=len(truncated),
        was_contaminated=True,
    )
