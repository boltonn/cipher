import pytest

from cipher.schemas.content.email import EmailAddress


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("'Nick Bolton'", "Nick Bolton"),
        ('"cathi bolton"', "cathi bolton"),
        ("bolton213@yahoo.com", None),
        ("NBOLTON04@GMAIL.COM", None),
        ("  ", None),
        (None, None),
        ("Nick Bolton (nick@x.com)", "Nick Bolton (nick@x.com)"),
        ("O'Brien", "O'Brien"),
    ],
)
def test_display_name_is_cleaned(raw, expected):
    assert EmailAddress(name=raw, value="nick@x.com").name == expected
