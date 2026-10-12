"""Pure-logic tests for the free-text selector pass (no DB, no models)."""

from cipher.orchestration.extract_selectors import _context_snippet, _span_to_mention
from cipher.schemas.graph.mention import MentionedType
from cipher.schemas.graph.ontology import EntityType, SelectorSubtype, SelectorType
from cipher.schemas.graph.spans import SelectorSpan


def _span(**kw):
    base = dict(
        selector_type=SelectorType.PHONE,
        raw_value="+1 415 555 2671",
        normalized_value="+14155552671",
        start_offset=10,
        end_offset=25,
        confidence=0.72,
    )
    base.update(kw)
    return SelectorSpan(**base)


def test_context_snippet_windows_and_collapses_newlines():
    """Context snippet windows and collapses newlines."""
    content = "abc\n" * 40
    snippet = _context_snippet(content, 60, 64)
    assert "\n" not in snippet
    assert len(snippet) <= 4 + 80 + 80


def test_span_to_mention_carries_offsets_and_confidence():
    """Span to mention carries offsets and confidence."""
    content = "x" * 100
    m = _span_to_mention(_span(), dataset_id="d", file_id="f", extracted_id="x", content=content, entity_id="sel1")
    assert m.entity_id == "sel1"
    assert m.mentioned_type is MentionedType.EXTRACTED_TEXT
    assert m.entity_type is EntityType.SELECTOR
    assert m.entity_attribute == "value"
    assert (m.start_offset, m.end_offset) == (10, 25)
    assert m.selector_type is SelectorType.PHONE
    assert m.extractor == "selectors"
    assert m.extraction_confidence == 0.72


def test_span_to_mention_preserves_subtype():
    """Span to mention preserves subtype."""
    m = _span_to_mention(
        _span(
            selector_type=SelectorType.CRYPTO_ADDRESS,
            selector_subtype=SelectorSubtype.BTC_ADDRESS,
            raw_value="bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",
            normalized_value="bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",
        ),
        dataset_id="d",
        file_id="f",
        extracted_id="x",
        content="y" * 200,
        entity_id="sel2",
    )
    assert m.selector_subtype is SelectorSubtype.BTC_ADDRESS


def test_span_to_mention_unresolved_when_no_entity():
    """Span to mention unresolved when no entity."""
    m = _span_to_mention(_span(), dataset_id="d", file_id="f", extracted_id="x", content="z" * 100)
    assert m.entity_id is None


class _FakeEntities:
    async def get_or_create_selector(self, **kw):
        return type("E", (), {"id": f"sel:{kw['normalized_value']}"})(), True


class _FakeMentions:
    async def add_mentions_batch(self, mentions):
        self.written = mentions
        return len(mentions)


async def _run_text_pass(content: str, skip_offsets=None):
    from cipher.orchestration.extract_selectors import _extract_text_selectors

    extracted = type("X", (), {"id": "x", "content": content, "metadata": None})()
    mentions = _FakeMentions()
    await _extract_text_selectors(
        dataset_id="d",
        file_id="f",
        extracted=extracted,
        entity_repo=_FakeEntities(),
        mention_repo=mentions,
        selector_cache={},
        skip_offsets=skip_offsets,
    )
    return getattr(mentions, "written", [])


async def test_every_repeat_of_an_address_is_kept():
    """A reply chain quoting one address 12 times marks all 12, not the first few."""
    content = "".join(f"On Fri, Jul {day}, 2025 Megan Flick <megan.e.flick@gmail.com> wrote:\n" for day in range(12))
    written = await _run_text_pass(content)
    assert len([m for m in written if m.normalized_value == "megan.e.flick@gmail.com"]) == 12


async def test_rescan_only_adds_missing_spans():
    """Spans an earlier run wrote are skipped, so a rescan never duplicates."""
    content = "a@example.com and b@example.com"
    first = await _run_text_pass(content)
    done = {(m.selector_type, m.start_offset) for m in first if m.normalized_value == "a@example.com"}
    second = await _run_text_pass(content, skip_offsets=done)
    assert {m.normalized_value for m in second} == {m.normalized_value for m in first} - {"a@example.com"}
