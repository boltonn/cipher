from pytabular.records import parse_duration_seconds


def test_parse_duration_seconds_forms():
    """Plain seconds, m:ss and h:mm:ss parse; junk and negatives do not."""
    assert parse_duration_seconds("180") == 180
    assert parse_duration_seconds("12,5") == 12.5
    assert parse_duration_seconds("3:05") == 185
    assert parse_duration_seconds("1:03:00") == 3780
    assert parse_duration_seconds("-4") is None
    assert parse_duration_seconds("3 min") is None
