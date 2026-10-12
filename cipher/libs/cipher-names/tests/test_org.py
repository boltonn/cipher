import pytest

from cipher.names import compare_org_names
from cipher.names.compare import Level


@pytest.mark.parametrize(
    ("a", "b", "level"),
    [
        ("Amazon Web Services, Inc", "Amazon Web Services", Level.EXACT),
        ("Adaire (no reply)", "Adaire's", Level.EXACT),
        ("AWS", "Amazon Web Services", Level.STRONG),
        ("Adaire", "Adaire Leasing", Level.MODERATE),
        ("Amazn Web Services", "Amazon Web Services", Level.MODERATE),
        ("Digital Services", "Web Services", Level.NONE),
        ("Amazon Web Services, Inc", "HBO Digital Services, Inc", Level.CONFLICT),
        ("ABC Financial Services, Inc", "Northcoast Warranty Services, Inc", Level.CONFLICT),
    ],
)
def test_compare_org_names(a, b, level):
    assert compare_org_names(a, b).level == level
