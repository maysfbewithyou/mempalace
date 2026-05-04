"""KG triple extractor — pulls structured facts out of drawer content.

version: 0.1
phase: kg-auto-extract (initial wiring)

Purpose
-------
Reads a chunk of unstructured text (typically the verbatim content of a drawer
just filed via mempalace_add_drawer) and returns a list of subject-predicate-
object triples ready to be persisted via KnowledgeGraph.add_triple. Used by:

  - tool_add_drawer        (when MEMPALACE_KG_AUTO_EXTRACT=true; default false)
  - mempalace kg-backfill  (one-time / incremental backfill CLI)

Failure mode
------------
Extraction is best-effort. ANY error inside extract_triples() is caught and
logged; the function returns an empty list rather than raising. The caller
(typically tool_add_drawer) MUST tolerate that — extraction failure should
never fail the underlying drawer write.

Vocabulary v0.1
---------------
The KNOWN_PREDICATES + KNOWN_ENTITY_TYPES sets below are the preferred
vocabulary the model is asked to use. The extractor is "flexible-evolving":
the model is allowed to coin a novel predicate when nothing fits, but must
mark it `novel_predicate=True` so the operator can review and either promote
it to the known set, alias it to an existing one, or reject it.

Logging
-------
Every novel predicate is logged at INFO with subject/object context, so a
weekly grep over container logs gives the operator a deliberate review queue.

Cost / latency
--------------
Default model is claude-haiku-4-5-20251001. Approx ~$0.0005 per drawer at
typical drawer sizes (5 KB in, 1-2 KB JSON out). Latency 1-2 s.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import List, NamedTuple, Optional

logger = logging.getLogger("mempalace.kg_extractor")


# ── Vocabulary v0.1 ──────────────────────────────────────────────────────────
# See HARDENING_CHANGELOG.md (Version 6.0) for the grounding rationale.
# Predicates intentionally lowercase + snake_case (matches add_triple's
# normalization at line 134 of knowledge_graph.py).

KNOWN_PREDICATES = frozenset({
    # People / orgs / authorship
    "member_of", "works_with", "authored", "assigned_to",
    # Project structure
    "part_of", "owned_by", "integrates_with",
    # Versioning / lifecycle
    "has_version", "supersedes", "tagged_as", "at_phase",
    # Status
    "has_status", "is_locked",
    # Documents / references / governance
    "documented_in", "references", "governed_by",
    # Technical relationships
    "depends_on", "uses", "runs_on", "pinned_to", "deployed_at",
    # Findings & decisions
    "identified_in", "resolved_by", "blocks", "decided_at",
})

KNOWN_ENTITY_TYPES = frozenset({
    "Person", "Organization", "Project", "Component", "Document",
    "Version", "Decision", "Finding", "Event", "Technology",
    "Service", "Phase",
})


# ── Triple type ──────────────────────────────────────────────────────────────

class Triple(NamedTuple):
    """One extracted subject-predicate-object fact ready to hand to add_triple."""

    subject: str
    predicate: str
    object: str
    subject_type: Optional[str] = None
    object_type: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    confidence: float = 0.5
    novel_predicate: bool = False


# ── Configuration knobs ──────────────────────────────────────────────────────

DEFAULT_MODEL = os.environ.get(
    "MEMPALACE_KG_EXTRACTOR_MODEL", "claude-haiku-4-5-20251001"
)
# Cap input size to keep extraction cost predictable. ~30 KB ≈ ~7500 tokens.
MAX_INPUT_CHARS = int(
    os.environ.get("MEMPALACE_KG_EXTRACTOR_MAX_INPUT_CHARS", str(30_000))
)
# Max tokens for the response. JSON triples are short; 2000 is comfortable
# headroom for a drawer that yields ~30 triples.
MAX_OUTPUT_TOKENS = int(
    os.environ.get("MEMPALACE_KG_EXTRACTOR_MAX_OUTPUT_TOKENS", str(2000))
)
# Skip extraction below this confidence. Set on every Triple at parse time.
MIN_CONFIDENCE = float(
    os.environ.get("MEMPALACE_KG_EXTRACTOR_MIN_CONFIDENCE", "0.5")
)
# Drawers shorter than this likely have nothing extractable.
MIN_INPUT_CHARS = int(
    os.environ.get("MEMPALACE_KG_EXTRACTOR_MIN_INPUT_CHARS", "60")
)


# ── Prompt construction ──────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    """The vocabulary + extraction rules. Static enough to prompt-cache."""
    pred_list = "\n".join(f"  - {p}" for p in sorted(KNOWN_PREDICATES))
    type_list = ", ".join(sorted(KNOWN_ENTITY_TYPES))
    return f"""You extract structured knowledge graph triples from text.

Output format: a JSON object {{"triples": [...]}}. Each triple has these fields:

  - subject (string, required)         — a specific named entity
  - predicate (string, required)       — the relationship verb (snake_case)
  - object (string, required)          — the entity the subject relates to
  - subject_type (string, optional)    — one of the known entity types if known
  - object_type (string, optional)     — one of the known entity types if known
  - valid_from (string, optional)      — YYYY-MM-DD if text says when it became true
  - valid_to (string, optional)        — YYYY-MM-DD if text says when it stopped
  - confidence (number, 0.0-1.0)       — how sure you are
  - novel_predicate (boolean)          — true if predicate is NOT in the preferred list

Preferred predicates (use these when one fits):
{pred_list}

Preferred entity types: {type_list}

RULES:
1. Output ONLY the JSON object — no prose, no code fences, no commentary.
2. Use a preferred predicate whenever one applies. If nothing fits, coin a
   new snake_case predicate AND set novel_predicate: true.
3. Subjects and objects must be specific named entities (proper nouns,
   version strings, file names, dates, etc.) — never vague pronouns or
   generic phrases like "the system" or "we".
4. Skip a candidate triple if confidence < {MIN_CONFIDENCE}.
5. Be conservative — quality over quantity. Better to emit 5 high-confidence
   triples than 30 noisy ones.
6. Do NOT extract opinions, hypotheticals, or future plans as facts. Only
   what the text states as currently or historically true.
7. If the text contains no extractable structured facts, return
   {{"triples": []}}.
"""


def _build_user_prompt(text: str) -> str:
    return f"Extract triples from this content:\n\n<content>\n{text}\n</content>"


# ── Public entrypoint ────────────────────────────────────────────────────────

def _maybe_default_log():
    """Lazy-acquire the default ExtractLog. Returns None if unavailable.

    Kept lazy because importing kg_extract_log creates a SQLite file on first
    use, which we don't want during simple module imports / tests that never
    actually call extract_triples.
    """
    try:
        from .kg_extract_log import get_default_log
        return get_default_log()
    except Exception:  # noqa: BLE001
        return None


def extract_triples(
    text: str,
    *,
    model: Optional[str] = None,
    timeout: float = 30.0,
    api_key: Optional[str] = None,
    source: str = "manual",
    drawer_id: Optional[str] = None,
    extract_log=None,
) -> List[Triple]:
    """Extract triples from `text` via the Anthropic API.

    Never raises. Returns [] on any error (key missing, API failure, JSON
    parse failure, content too short). Logs failures at appropriate level.
    Records every call (success/error/skipped) to the ExtractLog so cost
    telemetry and anomaly detection have complete data.

    Parameters
    ----------
    text : str
        Drawer content (or any prose) to extract from.
    model : str, optional
        Override DEFAULT_MODEL. Useful for tests / cost-sensitive runs.
    timeout : float
        Per-request timeout in seconds.
    api_key : str, optional
        Override env var ANTHROPIC_API_KEY. Almost never used in production —
        present so tests can pass a deterministic key without env mutation.
    source : str
        Where this call originated. Default "manual"; tool_add_drawer passes
        "tool_add_drawer", the backfill CLI passes "kg-backfill". Used for
        per-source cost reports.
    drawer_id : str, optional
        Drawer this extraction is bound to (so the log can correlate triples
        back to the drawer they came from).
    extract_log : ExtractLog, optional
        Override the default log for tests. Pass an explicit ExtractLog
        instance to assert calls were logged correctly.
    """
    chosen_model = model or DEFAULT_MODEL
    log = extract_log if extract_log is not None else _maybe_default_log()

    def _log_record(**fields):
        """Record a row in the ExtractLog, swallowing any failure."""
        if log is None:
            return
        try:
            log.record(
                source=source, model=chosen_model, drawer_id=drawer_id, **fields,
            )
        except Exception:  # noqa: BLE001
            logger.exception("kg_extractor: failed to write to ExtractLog")

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        logger.warning(
            "kg_extractor: ANTHROPIC_API_KEY not set; extraction skipped"
        )
        _log_record(status="no_api_key")
        return []

    if not text or len(text.strip()) < MIN_INPUT_CHARS:
        _log_record(status="too_short")
        return []

    # Truncate oversize input so a runaway drawer doesn't blow our token budget.
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS] + "\n[... content truncated for extraction]"

    started = time.monotonic()
    try:
        # Lazy import — the package should load even if anthropic isn't installed
        # (e.g. in lightweight unit tests that never reach this branch).
        import anthropic

        client = anthropic.Anthropic(api_key=key, timeout=timeout)
        resp = client.messages.create(
            model=chosen_model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=_build_system_prompt(),
            messages=[{"role": "user", "content": _build_user_prompt(text)}],
        )
    except Exception as exc:  # noqa: BLE001 — best-effort by design
        logger.exception("kg_extractor: API call failed: %s", exc)
        _log_record(
            status="error",
            duration_ms=int((time.monotonic() - started) * 1000),
            error_message=str(exc)[:500],
        )
        return []

    duration_ms = int((time.monotonic() - started) * 1000)

    # Pull token usage off the response. Anthropic's usage object exposes
    # input_tokens / output_tokens.
    in_tokens = 0
    out_tokens = 0
    try:
        usage = getattr(resp, "usage", None)
        if usage is not None:
            in_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            out_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    except Exception:  # noqa: BLE001
        pass  # token telemetry is best-effort; missing tokens shouldn't crash

    raw = ""
    try:
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                raw = block.text
                break
    except Exception:  # noqa: BLE001
        logger.exception("kg_extractor: malformed Anthropic response shape")
        _log_record(
            status="error",
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            duration_ms=duration_ms,
            error_message="malformed Anthropic response shape",
        )
        return []

    triples = _parse_triples_response(raw)
    novel_count = sum(1 for t in triples if t.novel_predicate)

    _log_record(
        status="success",
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        triples_extracted=len(triples),
        novel_predicates=novel_count,
        duration_ms=duration_ms,
    )

    return triples


# ── Response parsing ─────────────────────────────────────────────────────────

# Match an opening ```json (or just ```) fence and a closing fence.
_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    """If the model wrapped its JSON in ``` fences, strip them."""
    m = _CODE_FENCE_RE.match(text.strip())
    return m.group(1) if m else text


def _parse_triples_response(raw: str) -> List[Triple]:
    """Parse the model's JSON response into a list of Triple.

    Robust to:
      - markdown code fences around the JSON
      - extra prose before/after the JSON object (best-effort substring)
      - missing optional fields
      - confidence below threshold (those are dropped)
      - malformed individual triples (those are skipped, others kept)
    """
    if not raw:
        return []

    # Strip markdown fences first.
    cleaned = _strip_code_fences(raw)

    # If the model snuck prose in around the JSON, find the outer braces.
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first == -1 or last == -1 or last <= first:
            logger.error(
                "kg_extractor: response is not JSON and contains no JSON object"
            )
            logger.debug("kg_extractor: raw response head: %r", cleaned[:300])
            return []
        try:
            data = json.loads(cleaned[first : last + 1])
        except json.JSONDecodeError as exc:
            logger.error("kg_extractor: failed to salvage JSON: %s", exc)
            logger.debug("kg_extractor: raw response head: %r", cleaned[:300])
            return []

    items = data.get("triples", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        logger.error("kg_extractor: 'triples' field is not a list")
        return []

    triples: List[Triple] = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        try:
            confidence = float(raw_item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        if confidence < MIN_CONFIDENCE:
            continue

        subject = (raw_item.get("subject") or "").strip()
        predicate = (raw_item.get("predicate") or "").strip().lower().replace(" ", "_")
        obj = (raw_item.get("object") or "").strip()
        if not (subject and predicate and obj):
            continue

        # Validate entity types — drop the field if not in our known set,
        # rather than silently propagate a bogus type into add_entity.
        sub_type = raw_item.get("subject_type")
        if sub_type not in KNOWN_ENTITY_TYPES:
            sub_type = None
        obj_type = raw_item.get("object_type")
        if obj_type not in KNOWN_ENTITY_TYPES:
            obj_type = None

        novel_flag = bool(raw_item.get("novel_predicate", False))
        # Cross-check the model's self-report against our actual known set.
        # If the model said "novel" but the predicate IS known, downgrade.
        # If the model said "not novel" but it ISN'T known, upgrade + log.
        actually_novel = predicate not in KNOWN_PREDICATES
        if actually_novel and not novel_flag:
            logger.info(
                "kg_extractor: model failed to flag novel predicate %r "
                "(subject=%r object=%r); auto-flagging",
                predicate, subject, obj,
            )
        novel_flag = actually_novel

        if novel_flag:
            logger.info(
                "kg_extractor: novel predicate %r — subject=%r object=%r "
                "(weekly review queue)",
                predicate, subject, obj,
            )

        triples.append(
            Triple(
                subject=subject,
                predicate=predicate,
                object=obj,
                subject_type=sub_type,
                object_type=obj_type,
                valid_from=raw_item.get("valid_from") or None,
                valid_to=raw_item.get("valid_to") or None,
                confidence=confidence,
                novel_predicate=novel_flag,
            )
        )

    return triples
