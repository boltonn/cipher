from cipher.orchestration.domain_affiliations import map_domains


def _row(domain: str, org: str, signatures: int, signers: list[str] | None = None) -> dict:
    return {
        "domain": domain,
        "organization_id": f"id-{org}",
        "organization": org,
        "signatures": signatures,
        "signer_ids": signers or [],
        "signer_names": signers or [],
    }


def test_domain_maps_to_the_organization_most_signatures_name():
    """A clear majority of a domain's signatures maps it, keeping the minority for the explanation."""
    mapped = map_domains(
        [_row("baltlog.ru", "Baltic", 7, ["Anna"]), _row("baltlog.ru", "Other", 1)], min_signatures=2, min_share=0.75
    )
    assert mapped["baltlog.ru"]["organization"] == "Baltic"
    assert mapped["baltlog.ru"]["total"] == 8
    assert mapped["baltlog.ru"]["others"] == [{"name": "Other", "signatures": 1}]


def test_split_or_thin_domains_do_not_map():
    """Too few signatures, or no clear majority, maps nothing."""
    rows = [_row("a.com", "A", 1), _row("b.com", "B1", 3), _row("b.com", "B2", 3)]
    assert map_domains(rows, min_signatures=2, min_share=0.75) == {}


def test_freemail_never_maps():
    """gmail.com says nothing about an employer, however many signatures share it."""
    assert map_domains([_row("gmail.com", "Acme", 50)], min_signatures=2, min_share=0.75) == {}
