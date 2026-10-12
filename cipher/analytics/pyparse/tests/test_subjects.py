import pytest
from pyparse.parsers.email.subjects import strip_reply_prefixes, subject_key


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Re: Lunch Friday", ("Lunch Friday", True)),
        ("RE: Fwd: RE[2]: Lunch Friday", ("Lunch Friday", True)),
        ("AW: WG: Angebot", ("Angebot", True)),
        ("Отв: Пересл: встреча", ("встреча", True)),
        ("回复：会议安排", ("会议安排", True)),
        ("Lunch Friday", ("Lunch Friday", False)),
        ("Regarding the lease", ("Regarding the lease", False)),
    ],
)
def test_strip_reply_prefixes(subject: str, expected: tuple[str, bool]):
    """Stacked multilingual prefixes go; a word merely starting with one stays."""
    assert strip_reply_prefixes(subject) == expected


def test_subject_key_matches_replies_and_skips_empty_subjects():
    """Replies key to their original; a subject with nothing left after the prefixes has no key."""
    assert subject_key("Re:  LUNCH   friday!") == subject_key("Lunch Friday") == "lunch friday"
    assert subject_key("Re:") is None
    assert subject_key("hi") is None
    assert subject_key(None) is None
