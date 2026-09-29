from cipher.datastores.postgres.repositories.selector_links import HeaderEvidence, decide_header_links

ACTORS = {"nick": "Nick B", "edmond": "Edmond Bolton", "cathi": "Cathi Bolton"}


def _row(address: str, name: str, resolved: str | None, emails: int) -> HeaderEvidence:
    return HeaderEvidence(address_id=address, address=address, name=name, resolved_id=resolved, emails=emails)


def test_spelled_address_goes_to_the_person_it_spells():
    """`nbolton04` is Nick's even though Edmond's name sits on it 182 times."""
    evidence = [
        _row("nbolton04@gmail.com", "Nick B", "nick", 930),
        _row("nbolton04@gmail.com", "Edmond Bolton", "edmond", 182),
    ]
    assert decide_header_links(evidence, ACTORS) == {("nick", "nbolton04@gmail.com")}


def test_misresolved_family_names_do_not_count_but_unresolved_matching_names_do():
    """`bolton213`: 'Mary Bolton' resolved to Edmond is noise; unresolved 'Nick Bolton' supports Nick."""
    evidence = [
        _row("bolton213@yahoo.com", "Mary Bolton", "edmond", 129),
        _row("bolton213@yahoo.com", "nicky bolton", "edmond", 20),
        _row("bolton213@yahoo.com", "Nick B", "nick", 6),
        _row("bolton213@yahoo.com", "Nick Bolton", None, 2429),
    ]
    assert decide_header_links(evidence, ACTORS) == {("nick", "bolton213@yahoo.com")}


def test_one_off_pairing_is_not_ownership():
    """A single 'Cathi Bolton' on the family domain doesn't make it hers."""
    evidence = [
        _row("mail@efbolton.net", "Ed Bolton", "edmond", 7),
        _row("mail@efbolton.net", "Cathi Bolton", "cathi", 1),
    ]
    assert decide_header_links(evidence, ACTORS) == {("edmond", "mail@efbolton.net")}


def test_on_behalf_of_name_on_a_company_address_is_not_linked():
    """A one-off "Cathi" on a Wayfair on-behalf-of address is not ownership."""
    evidence = [
        _row("service@wayfair.com", "Cathi", "cathi", 2),
        _row("service@wayfair.com", "Wayfair", None, 300),
    ]
    assert decide_header_links(evidence, ACTORS) == set()
