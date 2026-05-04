"""Tests for the KG triple extractor.

version: 0.1
phase: kg-auto-extract
covers: mempalace.kg_extractor (extract_triples, _parse_triples_response,
        novel-predicate detection, code-fence stripping, error tolerance)
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from mempalace import kg_extractor
from mempalace.kg_extractor import (
    KNOWN_ENTITY_TYPES,
    KNOWN_PREDICATES,
    Triple,
    _parse_triples_response,
    _strip_code_fences,
    extract_triples,
)


# ── Vocabulary sanity ────────────────────────────────────────────────────────


def test_known_predicates_size_and_format():
    """v0.1 vocabulary: 25 predicates, all snake_case lowercase."""
    assert len(KNOWN_PREDICATES) == 25
    for pred in KNOWN_PREDICATES:
        assert pred == pred.lower(), f"predicate {pred!r} must be lowercase"
        assert " " not in pred, f"predicate {pred!r} must be snake_case (no spaces)"


def test_known_entity_types_size_and_format():
    """v0.1 vocabulary: 12 entity types, PascalCase."""
    assert len(KNOWN_ENTITY_TYPES) == 12
    for et in KNOWN_ENTITY_TYPES:
        assert et[0].isupper(), f"entity type {et!r} must start uppercase"


# ── Code fence stripping ─────────────────────────────────────────────────────


def test_strip_code_fences_removes_json_fence():
    raw = '```json\n{"triples": []}\n```'
    assert _strip_code_fences(raw) == '{"triples": []}'


def test_strip_code_fences_removes_bare_fence():
    raw = '```\n{"triples": []}\n```'
    assert _strip_code_fences(raw) == '{"triples": []}'


def test_strip_code_fences_passthrough_when_no_fence():
    raw = '{"triples": []}'
    assert _strip_code_fences(raw) == raw


# ── Response parsing — happy paths ───────────────────────────────────────────


def test_parse_response_empty_string_returns_empty():
    assert _parse_triples_response("") == []


def test_parse_response_empty_triples_list():
    assert _parse_triples_response('{"triples": []}') == []


def test_parse_response_single_known_predicate():
    raw = json.dumps({
        "triples": [{
            "subject": "MemPalace",
            "predicate": "depends_on",
            "object": "ChromaDB",
            "subject_type": "Project",
            "object_type": "Technology",
            "confidence": 0.9,
        }]
    })
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    t = triples[0]
    assert t.subject == "MemPalace"
    assert t.predicate == "depends_on"
    assert t.object == "ChromaDB"
    assert t.subject_type == "Project"
    assert t.object_type == "Technology"
    assert t.confidence == 0.9
    assert t.novel_predicate is False  # depends_on IS a known predicate


def test_parse_response_with_temporal_fields():
    raw = json.dumps({
        "triples": [{
            "subject": "Site Plan Tool",
            "predicate": "at_phase",
            "object": "Phase 1 Schema",
            "valid_from": "2026-04-25",
            "confidence": 0.85,
        }]
    })
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].valid_from == "2026-04-25"
    assert triples[0].valid_to is None


def test_parse_response_handles_code_fenced_json():
    raw = '```json\n' + json.dumps({
        "triples": [{
            "subject": "Atlas",
            "predicate": "uses",
            "object": "PostgreSQL",
            "confidence": 0.95,
        }]
    }) + '\n```'
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].object == "PostgreSQL"


def test_parse_response_recovers_from_surrounding_prose():
    """Model occasionally wraps JSON in prose despite the system prompt rule.
    We salvage by finding the outer braces."""
    raw = (
        "Sure, here are the triples I extracted:\n\n"
        + json.dumps({"triples": [{
            "subject": "Coolify", "predicate": "integrates_with",
            "object": "GitHub", "confidence": 0.9,
        }]})
        + "\n\nLet me know if you need more."
    )
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].predicate == "integrates_with"


# ── Response parsing — sad paths ─────────────────────────────────────────────


def test_parse_response_drops_low_confidence():
    """Below MIN_CONFIDENCE (0.5), triples are dropped entirely."""
    raw = json.dumps({
        "triples": [
            {"subject": "A", "predicate": "uses", "object": "B", "confidence": 0.3},
            {"subject": "C", "predicate": "uses", "object": "D", "confidence": 0.7},
        ]
    })
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].subject == "C"


def test_parse_response_drops_empty_subject_or_object():
    raw = json.dumps({
        "triples": [
            {"subject": "", "predicate": "uses", "object": "X", "confidence": 0.9},
            {"subject": "X", "predicate": "uses", "object": "", "confidence": 0.9},
            {"subject": "X", "predicate": "", "object": "Y", "confidence": 0.9},
            {"subject": "X", "predicate": "uses", "object": "Y", "confidence": 0.9},
        ]
    })
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].subject == "X" and triples[0].object == "Y"


def test_parse_response_total_garbage():
    """Non-JSON, non-recoverable input returns []."""
    assert _parse_triples_response("this is just prose, no JSON anywhere") == []


def test_parse_response_with_malformed_individual_triple():
    """One bad triple in a list shouldn't kill the others."""
    raw = json.dumps({
        "triples": [
            "not a dict",  # garbage
            42,  # garbage
            {"subject": "Atlas", "predicate": "uses", "object": "Python", "confidence": 0.9},
        ]
    })
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].subject == "Atlas"


def test_parse_response_normalizes_predicate_to_snake_case():
    """Even if the model emits 'Depends On', we normalize."""
    raw = json.dumps({
        "triples": [{
            "subject": "X", "predicate": "Depends On", "object": "Y", "confidence": 0.8,
        }]
    })
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].predicate == "depends_on"


def test_parse_response_invalid_entity_type_dropped():
    """If the model emits 'Wizard' as entity type, we silently drop it
    rather than propagate a bogus type into add_entity."""
    raw = json.dumps({
        "triples": [{
            "subject": "X", "predicate": "uses", "object": "Y", "confidence": 0.9,
            "subject_type": "Wizard", "object_type": "Project",
        }]
    })
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].subject_type is None  # dropped — not in known set
    assert triples[0].object_type == "Project"  # kept


# ── Novel-predicate detection ────────────────────────────────────────────────


def test_novel_predicate_auto_flagged_even_if_model_lied():
    """If the model says novel_predicate=False but the predicate isn't in
    our known set, we override and flag it. Catches model hallucination."""
    raw = json.dumps({
        "triples": [{
            "subject": "X", "predicate": "competes_with", "object": "Y",
            "confidence": 0.9, "novel_predicate": False,  # liar
        }]
    })
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].predicate == "competes_with"
    assert triples[0].novel_predicate is True  # auto-flagged


def test_known_predicate_with_novel_flag_corrected():
    """Conversely, if the model flags a known predicate as novel, downgrade."""
    raw = json.dumps({
        "triples": [{
            "subject": "X", "predicate": "depends_on", "object": "Y",
            "confidence": 0.9, "novel_predicate": True,  # wrong
        }]
    })
    triples = _parse_triples_response(raw)
    assert len(triples) == 1
    assert triples[0].novel_predicate is False  # corrected


# ── extract_triples: API integration (mocked) ────────────────────────────────


@pytest.fixture
def mock_anthropic_response():
    """Build a fake Anthropic response object matching the real shape."""

    def _build(text: str):
        block = MagicMock()
        block.type = "text"
        block.text = text
        resp = MagicMock()
        resp.content = [block]
        return resp

    return _build


def test_extract_triples_no_api_key_returns_empty(monkeypatch):
    """No ANTHROPIC_API_KEY env var → return [] without calling the API."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    triples = extract_triples("MemPalace depends on ChromaDB. " * 20)
    assert triples == []


def test_extract_triples_too_short_returns_empty():
    """Below MIN_INPUT_CHARS → don't even call the API."""
    # Even with a real key, sub-MIN_INPUT_CHARS input shorts out before the API call.
    triples = extract_triples("hi", api_key="sk-ant-fake")
    assert triples == []


def test_extract_triples_happy_path(monkeypatch, mock_anthropic_response):
    """Mock Anthropic, verify the extracted triples come through."""
    fake_response_json = json.dumps({
        "triples": [
            {
                "subject": "MemPalace", "predicate": "depends_on",
                "object": "ChromaDB", "subject_type": "Project",
                "object_type": "Technology", "confidence": 0.95,
            },
            {
                "subject": "Matt", "predicate": "authored",
                "object": "MemPalace fork", "subject_type": "Person",
                "object_type": "Project", "confidence": 0.85,
            },
        ]
    })

    fake_client = MagicMock()
    fake_client.messages.create.return_value = mock_anthropic_response(fake_response_json)
    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client

    long_input = (
        "MemPalace is a personal memory system that depends on ChromaDB for vector "
        "search. Matt authored the IEP fork of MemPalace in March 2026. " * 3
    )

    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        triples = extract_triples(long_input, api_key="sk-ant-fake")

    assert len(triples) == 2
    assert triples[0].subject == "MemPalace"
    assert triples[0].predicate == "depends_on"
    assert triples[1].subject == "Matt"
    assert triples[1].predicate == "authored"
    fake_client.messages.create.assert_called_once()
    # System prompt was passed and contains the vocab.
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert "depends_on" in call_kwargs["system"]


def test_extract_triples_api_failure_returns_empty(monkeypatch, mock_anthropic_response):
    """Any exception during the API call is swallowed; caller sees []."""
    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.side_effect = RuntimeError("network down")

    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        triples = extract_triples(
            "Some long content. " * 20, api_key="sk-ant-fake"
        )

    assert triples == []  # graceful failure, never raises


def test_extract_triples_truncates_oversize_input(monkeypatch, mock_anthropic_response):
    """Input larger than MAX_INPUT_CHARS gets truncated before sending."""
    fake_response = mock_anthropic_response(json.dumps({"triples": []}))
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client

    huge_input = "x" * (kg_extractor.MAX_INPUT_CHARS + 5_000)

    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        extract_triples(huge_input, api_key="sk-ant-fake")

    sent = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    # Truncation marker appears, and content fits in our cap + a small marker.
    assert "[... content truncated for extraction]" in sent
    assert len(sent) < kg_extractor.MAX_INPUT_CHARS + 200
