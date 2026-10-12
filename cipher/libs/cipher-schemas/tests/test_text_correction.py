import random

import pytest

from cipher.schemas.content.text_correction import (
    SpanFate,
    TextCorrection,
    correction_filter,
    merge_ranges,
    touches,
)
from cipher.schemas.ingestion.enrichment import EnrichmentType, affected_by_text_change

TICKET = (
    "City & County of Philadelphia\n"
    "| Location |  | Meter Number |\n"
    "| 1400 BLK |  | 14F009 |\n"
    "| WOOD ST SS |  |  |\n"
    "observed in the City of Philadelphia, Pennsylvania\n"
)
FIXED = (
    "City & County of Philadelphia\n"
    "| Location |  | Meter Number |\n"
    "| 1400 BLK WOOD ST SS |  | 14F009 |\n"
    "observed in the City of Philadelphia, Pennsylvania\n"
)


def span(text: str, surface: str, occurrence: int = 0) -> tuple[int, int]:
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(surface, start + 1)
    return start, start + len(surface)


def moved_text(correction: TextCorrection, surface: str, occurrence: int = 0) -> tuple[SpanFate, str | None]:
    move = correction.remap_span(*span(correction.old, surface, occurrence))
    return move.fate, None if move.start is None else correction.new[move.start : move.end]


def test_unchanged_text_moves_nothing():
    correction = TextCorrection(TICKET, TICKET)
    assert correction.is_unchanged
    assert correction.remap_span(5, 20).start == 5


def test_ticket_join_keeps_every_untouched_mention_on_its_words():
    correction = TextCorrection(TICKET, FIXED)
    assert moved_text(correction, "Philadelphia") == (SpanFate.MOVED, "Philadelphia")
    assert moved_text(correction, "Philadelphia", occurrence=1) == (SpanFate.MOVED, "Philadelphia")
    assert moved_text(correction, "Pennsylvania") == (SpanFate.MOVED, "Pennsylvania")
    assert moved_text(correction, "WOOD ST SS")[1] == "WOOD ST SS"


def test_text_inserted_at_a_span_edge_stays_outside_it():
    correction = TextCorrection("call Nick now", "call Mr Nick Bolton now")
    assert moved_text(correction, "Nick") == (SpanFate.MOVED, "Nick")


def test_letters_typed_onto_a_name_extend_it():
    correction = TextCorrection("Officer Tangradi, M badge 172", "Officer Tangradi, Mark badge 172")
    assert moved_text(correction, "Tangradi, M") == (SpanFate.EDITED, "Tangradi, Mark")
    correction = TextCorrection("call olton now", "call Bolton now")
    assert moved_text(correction, "olton") == (SpanFate.EDITED, "Bolton")


def test_correction_filter_only_adds_inside_corrected_text_and_never_over_a_mention():
    keep = correction_filter(corrected_ranges=[(10, 16), (30, 30)], taken=[(12, 14)])
    assert not keep(0, 5)
    assert not keep(11, 13)
    assert keep(14, 20)
    assert keep(25, 35)


def test_typo_fixed_inside_a_name_keeps_the_span_and_takes_the_new_spelling():
    correction = TextCorrection("in Philadelpia today", "in Philadelphia today")
    assert moved_text(correction, "Philadelpia") == (SpanFate.EDITED, "Philadelphia")


def test_deleted_name_is_lost():
    correction = TextCorrection("paid by Nick Bolton on Monday", "paid on Monday")
    assert moved_text(correction, "Nick Bolton") == (SpanFate.LOST, None)


def test_text_trimmed_beside_a_name_only_moves_it():
    correction = TextCorrection("xxNick Boltonyy and more", "Nick Bolton and more")
    assert moved_text(correction, "Nick Bolton") == (SpanFate.MOVED, "Nick Bolton")


def test_name_moved_within_rewritten_lines_is_found_again():
    correction = TextCorrection(TICKET, FIXED)
    assert moved_text(correction, "14F009") == (SpanFate.RELOCATED, "14F009")


def test_relocation_never_jumps_to_the_same_name_elsewhere():
    old = "Nick Bolton wrote.\nLater: zzNick Boltonzz signed."
    correction = TextCorrection(old, "Nick Bolton wrote.\nLater: someone signed.")
    assert moved_text(correction, "Nick Bolton", occurrence=1) == (SpanFate.LOST, None)


def test_changed_ranges_carry_earlier_corrections_forward():
    first = TextCorrection("aaa bbb ccc", "aaa BBB ccc")
    ranges = first.changed_ranges()
    assert [first.new[a:b] for a, b in ranges] == ["BBB"]
    second = TextCorrection(first.new, "zz aaa BBB ccc")
    carried = second.changed_ranges(ranges)
    assert "BBB" in [second.new[a:b] for a, b in carried]


def test_ranges_merge_and_touch():
    assert merge_ranges([(5, 8), (0, 2), (2, 3)]) == [(0, 3), (5, 8)]
    assert touches(3, 6, [(6, 6)])
    assert not touches(3, 5, [(6, 9)])


@pytest.mark.parametrize("seed", range(200))
def test_random_edits_never_place_a_span_on_other_words(seed: int):
    rng = random.Random(seed)
    words = ["Nick", "Bolton", "Philadelphia", "|", "WOOD", "ST", "1400", "\n", "BLK", "the", "of"]
    old = " ".join(rng.choice(words) for _ in range(60))
    new = list(old)
    for _ in range(rng.randint(1, 6)):
        at = rng.randrange(len(new))
        match rng.randrange(3):
            case 0:
                new.insert(at, rng.choice(words))
            case 1:
                del new[at : at + rng.randint(1, 12)]
            case _:
                new[at : at + rng.randint(1, 8)] = rng.choice(words)
    correction = TextCorrection(old, "".join(new))
    for _ in range(40):
        start = rng.randrange(len(old) - 1)
        end = rng.randint(start + 1, min(len(old), start + 15))
        move = correction.remap_span(start, end)
        if move.fate in (SpanFate.MOVED, SpanFate.RELOCATED):
            assert correction.new[move.start : move.end] == old[start:end]
        elif move.fate == SpanFate.EDITED:
            assert 0 <= move.start < move.end <= len(correction.new)
            assert correction.new[move.start : move.end].strip()
        else:
            assert move.start is None


def test_text_change_reaches_every_reader_and_what_follows_them_but_not_producers():
    affected = affected_by_text_change()
    assert {
        EnrichmentType.TEXT_EMBEDDING,
        EnrichmentType.SELECTOR_EXTRACTION,
        EnrichmentType.ENTITY_EXTRACTION,
        EnrichmentType.SIGNATURE_EXTRACTION,
        EnrichmentType.RELATIONSHIP_EXTRACTION,
        EnrichmentType.EVENT_EXTRACTION,
        EnrichmentType.TEXT_SUMMARIZATION,
    } <= affected
    assert not affected & {EnrichmentType.OCR, EnrichmentType.TEXT_EXTRACTION, EnrichmentType.FACE_DETECTION}
