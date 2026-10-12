"""Whole-cell validation (`resolve_cell`), cell coordinates, and the passport / plate / MAC packs."""

import pytest
from pyselectors import cue_words, extract_selectors, parse_coordinate_cell, parse_degrees, resolve_cell

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType


@pytest.mark.parametrize(
    ("value", "selector_type", "region", "normalized"),
    [
        ("+7 916 123-45-67", SelectorType.PHONE, None, "+79161234567"),
        ("89161234567", SelectorType.PHONE, "RU", "+79161234567"),
        ("@ivan_petrov", SelectorType.SOCIAL_HANDLE, None, "ivan_petrov"),
        ("7707083893", SelectorType.NATIONAL_ID, None, "7707083893"),
        ("45 06 123456", SelectorType.PASSPORT, None, "4506123456"),
        ("А123ВС77", SelectorType.LICENSE_PLATE, None, "A123BC77"),
        ("aabb.ccdd.eeff", SelectorType.MAC_ADDRESS, None, "aa:bb:cc:dd:ee:ff"),
    ],
)
def test_resolve_cell_accepts(value: str, selector_type: SelectorType, region: str | None, normalized: str):
    span = resolve_cell(value, selector_type, region=region)
    assert span is not None and span.normalized_value == normalized


@pytest.mark.parametrize(
    ("value", "selector_type"),
    [
        ("Ivan Petrov", SelectorType.SOCIAL_HANDLE),
        ("12345", SelectorType.SOCIAL_HANDLE),
        ("12345", SelectorType.LICENSE_PLATE),
        ("1577", SelectorType.NATIONAL_ID),
        ("Ivan", SelectorType.PASSPORT),
        ("00:00:00:00:00:00", SelectorType.MAC_ADDRESS),
        ("call me on +7 916 123-45-67", SelectorType.PHONE),
    ],
)
def test_resolve_cell_rejects(value: str, selector_type: SelectorType):
    assert resolve_cell(value, selector_type) is None


def test_resolve_cell_tries_national_id_overlays():
    span = resolve_cell("7707083893", SelectorType.NATIONAL_ID)
    assert span is not None and span.selector_subtype is SelectorSubtype.RU_INN


def test_new_types_need_context_in_text():
    found = {s.selector_type for s in extract_selectors("госномер А123ВС77, паспорт 45 06 123456", language="ru")}
    assert {SelectorType.LICENSE_PLATE, SelectorType.PASSPORT} <= found
    assert not extract_selectors("invoice AB 1234 CD total 451234567 USD")


def test_mac_in_text_needs_no_context():
    [span] = extract_selectors("connected from 00:1A:2B:3C:4D:5E yesterday")
    assert span.selector_type is SelectorType.MAC_ADDRESS and span.attributes["oui"] == "00:1a:2b"


@pytest.mark.parametrize(
    ("value", "degrees", "axis"),
    [
        ("55.7558", 55.7558, None),
        ("55°45′N", 55.75, "lat"),
        ("37°37'W", -37.616667, "lon"),
        ("55,75 с.ш.", 55.75, "lat"),
    ],
)
def test_parse_degrees(value: str, degrees: float, axis: str | None):
    parsed = parse_degrees(value)
    assert parsed is not None and parsed[0] == pytest.approx(degrees, abs=1e-5) and parsed[1] == axis


def test_parse_coordinate_cell_accepts_bare_pairs():
    span = parse_coordinate_cell("55.7558, 37.6173")
    assert span is not None and (span.latitude, span.longitude) == (55.7558, 37.6173)
    assert parse_coordinate_cell("12, 34") is None


def test_cue_words_feed_column_headers():
    assert "госномер" in cue_words(SelectorType.LICENSE_PLATE)["ru"]
    assert all(term for terms in cue_words(SelectorType.PHONE).values() for term in terms)
