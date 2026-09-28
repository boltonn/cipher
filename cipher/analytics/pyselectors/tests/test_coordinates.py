"""Coordinate extraction across formats and languages."""

from pyselectors import extract_coordinates


def _one(text, **kw):
    spans = extract_coordinates(text, **kw)
    assert len(spans) == 1, spans
    return spans[0]


def test_bare_decimal_pair_ignored():
    """Bare decimal pair ignored."""
    assert extract_coordinates("dimensions 55.7558, 37.6173 mm") == []


def test_decimal_with_hemispheres():
    """Decimal with hemispheres."""
    c = _one("HQ at 55.7558 N, 37.6173 E nearby")
    assert (round(c.latitude, 4), round(c.longitude, 4)) == (55.7558, 37.6173)
    assert c.coordinate_format == "decimal"


def test_negative_hemisphere():
    """Negative hemisphere."""
    c = _one("port 40.7128 N, 74.0060 W here")
    assert c.longitude < 0


def test_dms():
    """Dms."""
    c = _one("marker 55°45'21\"N 37°37'04\"E on map")
    assert round(c.latitude, 4) == 55.7558
    assert c.coordinate_format == "dms"


def test_cyrillic_markers():
    """Cyrillic markers."""
    c = _one("точка 55°45′ с.ш., 37°37′ в.д.")
    assert round(c.latitude, 3) == 55.750
    assert c.coordinate_format == "cyrillic"


def test_cjk_markers():
    """Cjk markers."""
    c = _one("目标 北纬39.9042° 东经116.4074° 附近")
    assert round(c.latitude, 4) == 39.9042
    assert c.coordinate_format == "cjk"


def test_labeled_and_negative():
    """Labeled and negative."""
    c = _one("широта: 51.5074 долгота: -0.1278")
    assert round(c.longitude, 4) == -0.1278
    assert c.coordinate_format == "labeled"


def test_out_of_range_dropped():
    """Out of range dropped."""
    assert extract_coordinates("lat=200.0, lon=999.0") == []


def test_integer_pair_with_stray_hemisphere_ignored():
    """Integer pair with stray hemisphere ignored."""
    # a table cell like "28, 29\nW" must not become a coordinate
    assert extract_coordinates("row 28, 29\nW other") == []


def test_decimal_pair_with_hemisphere_still_matches():
    """Decimal pair with hemisphere still matches."""
    c = extract_coordinates("at 28.5, 29.1 W")
    assert len(c) == 1 and c[0].longitude < 0
