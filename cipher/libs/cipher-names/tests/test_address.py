import pytest

from cipher.names.address import AddressAgreement, address_name_agreement, is_role_address

MATCH, CONFLICT, NEUTRAL = AddressAgreement.MATCH, AddressAgreement.CONFLICT, AddressAgreement.NEUTRAL


@pytest.mark.parametrize(
    ("address", "names", "expected"),
    [
        ("nbolton04@gmail.com", ["Nick B"], MATCH),
        ("nbolton04@gmail.com", ["Nick Bolton"], MATCH),
        ("nbolton04@gmail.com", ["Edmond Bolton"], CONFLICT),
        ("efbolton@hotmail.com", ["E F Bolton"], MATCH),
        ("efbolton@hotmail.com", ["Edmond Bolton"], MATCH),
        ("efbolton@hotmail.com", ["Cathi Bolton"], CONFLICT),
        ("mail@efbolton.net", ["Ed Bolton"], MATCH),
        ("mail@efbolton.net", ["Cathi Bolton"], CONFLICT),
        ("nick.bolton@atlanticsoccerfactory.com", ["Nick B"], MATCH),
        ("bolton213@yahoo.com", ["Nick B"], NEUTRAL),
        ("bolton213@yahoo.com", ["Edmond Bolton"], NEUTRAL),
        ("service@wayfair.com", ["Cathi Bolton"], NEUTRAL),
        ("info@cvent.com", ["Nick Bolton"], NEUTRAL),
    ],
)
def test_address_name_agreement(address: str, names: list[str], expected: AddressAgreement):
    """An address agrees with, contradicts, or says nothing about each name."""
    assert address_name_agreement(address, names) == expected


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("info@cvent.com", True),
        ("noreply@github.com", True),
        ("no-reply+abc@accounts.google.com", True),
        ("do_not_reply@bank.com", True),
        ("notifications-123@facebookmail.com", True),
        ("nbolton04@gmail.com", False),
        ("mail@efbolton.net", False),
        ("information.officer@acme.com", False),
    ],
)
def test_is_role_address(address: str, expected: bool):
    """Shared/automated mailboxes are recognised by their local part."""
    assert is_role_address(address) is expected
