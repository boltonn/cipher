from cipher.orchestration.extract_signatures import (
    Cue,
    SignatureReading,
    SignerAgreement,
    authored_text,
    find_candidate,
    ground,
    is_organization_signer,
    signer_agreement,
)
from cipher.schemas.graph.ontology import EntityType

BODY = """Hi team,

Attached is the revised charter party.

Best regards,

Rosa Lindqvist
Senior Analyst, Treasury
Halcyon Maritime Group
+31 10 555 0101 | rosa@halcyon-maritime.com
"""
SIGNATURE = (
    "Rosa Lindqvist\nSenior Analyst, Treasury\nHalcyon Maritime Group\n+31 10 555 0101 | rosa@halcyon-maritime.com"
)


def _text(body: str, span) -> str:
    return body[span.start : span.end]


def _reading(**kwargs) -> SignatureReading:
    return SignatureReading(is_signature=True, **kwargs)


def test_candidate_is_the_tail_with_the_cues_that_fired():
    """Signer cues (farewell, sender's name) plus a payload (the phone); the candidate is the end of the email."""
    candidate = find_candidate(BODY, sender_name="Rosa Lindqvist", sender_address="rosa@halcyon-maritime.com")
    assert candidate is not None
    assert set(candidate.cues) == {Cue.FAREWELL, Cue.SENDER_NAME, Cue.SELECTOR}
    assert candidate.text.endswith("rosa@halcyon-maritime.com")


def test_a_sign_off_with_nothing_to_learn_is_skipped():
    """'Thanks, Nick' names the sender but says nothing new -- no organization, no selector."""
    body = "Sounds good, see you Tuesday.\n\nThanks,\nNick Bolton\n"
    assert find_candidate(body, sender_name="Nick Bolton", sender_address="nbolton04@gmail.com") is None


def test_the_senders_own_address_is_not_new():
    """An email address in the tail only counts as a payload when it isn't the sender's."""
    body = "Thanks,\nNick Bolton\nnbolton04@gmail.com\n"
    assert find_candidate(body, sender_name="Nick Bolton", sender_address="nbolton04@gmail.com") is None


def test_no_cue_no_candidate():
    """A note with no farewell, no sender name and no NER hits is never sent to the model."""
    body = "Stop being a narcissist.\nYou've had over 3 months.\n"
    assert find_candidate(body, sender_name="Megan Flick", sender_address="megan.e.flick@gmail.com") is None


def test_ner_person_and_org_are_a_signer_and_a_payload():
    """No farewell and an unmatched header name: an NER person (signer) and organization (payload) suffice."""
    body = "See attached.\n\nDonte Booker\nOffice Coordinator, Idylwood Towers\n"
    spans = [(EntityType.PERSON, body.index("Donte")), (EntityType.ORGANIZATION, body.index("Idylwood"))]
    candidate = find_candidate(
        body, sender_name="Idylwood Towers", sender_address="notify@buildinglink.com", ner_spans=spans
    )
    assert candidate is not None and set(candidate.cues) == {Cue.NER_PERSON, Cue.NER_ORGANIZATION}


def test_reading_grounds_to_offsets_in_the_body():
    """Every value is pinned to its span in the email, chain broadest first, inside the signature."""
    candidate = find_candidate(BODY, sender_name="Rosa Lindqvist", sender_address="rosa@halcyon-maritime.com")
    reading = _reading(
        signature=SIGNATURE,
        person_name="Rosa Lindqvist",
        organizations=["Halcyon Maritime Group", "Treasury"],
        role="Senior Analyst",
        phones=["+31 10 555 0101"],
        emails=["rosa@halcyon-maritime.com"],
    )
    found = ground(candidate, reading, sender_name="Rosa Lindqvist", sender_address="rosa@halcyon-maritime.com")
    assert _text(BODY, found.person) == "Rosa Lindqvist"
    assert [_text(BODY, u) for u in found.units] == ["Halcyon Maritime Group", "Treasury"]
    assert [_text(BODY, p) for p in found.phones] == ["+31 10 555 0101"]
    assert found.signer_is_sender and found.context == SIGNATURE


def test_model_saying_no_signature_ends_it():
    """`is_signature=False` (a newsletter footer, a bare sign-off) yields nothing."""
    candidate = find_candidate(BODY, sender_name="Rosa Lindqvist")
    assert ground(candidate, SignatureReading(), sender_name="Rosa Lindqvist") is None


def test_values_not_in_the_text_are_dropped():
    """An invented unit never becomes a mention; no organization at all means no affiliation."""
    candidate = find_candidate(BODY, sender_name="Rosa Lindqvist")
    found = ground(
        candidate,
        _reading(person_name="Rosa Lindqvist", organizations=["Halcyon Maritime Group", "Invented Unit"]),
        sender_name="Rosa Lindqvist",
    )
    assert [u.text for u in found.units] == ["Halcyon Maritime Group"]
    assert ground(candidate, _reading(person_name="Rosa Lindqvist"), sender_name="Rosa Lindqvist") is None


def test_quoted_replies_are_cut_in_several_languages():
    """English and German reply markers end the sender's text."""
    body = "Sounds good.\n\nOn Tue, Jan 3, 2023 at 9:00 AM Rosa Lindqvist wrote:\n> Rosa Lindqvist\n> Halcyon Maritime Group\n"
    assert authored_text(body).strip() == "Sounds good."
    german = "Passt.\n\nAm 03.03.2025 um 09:00 schrieb Jonas Becker <j@x.de>:\n> Jonas Becker\n"
    assert authored_text(german).strip() == "Passt."


def test_latin_header_names_a_cyrillic_signature():
    """`Anna Sokolova` in the header matches the `Анна Соколова` line (transliteration) -- the sender cue."""
    body = "Спасибо.\n\nАнна Соколова\nГлавный бухгалтер\nООО «Балтийская Логистика»\n+7 812 555 0101\n"
    candidate = find_candidate(body, sender_name="Anna Sokolova", sender_address="user1@baltlog.ru")
    assert candidate is not None and Cue.SENDER_NAME in candidate.cues


def test_signer_who_is_someone_else_is_dropped():
    """A signature the header and address say belongs to another person is not the sender's affiliation."""
    candidate = find_candidate(BODY, sender_name="Jane Smith", sender_address="jsmith@acme.com")
    reading = _reading(signature=SIGNATURE, person_name="Rosa Lindqvist", organizations=["Halcyon Maritime Group"])
    assert ground(candidate, reading, sender_name="Jane Smith", sender_address="jsmith@acme.com") is None


def test_organization_signers_are_not_people():
    """A brand mailbox signing as itself is not a person employed there; a surname that matches stays."""
    assert is_organization_signer("Kaggle", ["Kaggle"])
    assert is_organization_signer("The Microsoft account team", ["Microsoft account team"])
    assert is_organization_signer("| Ledet Training |", ["Ledet Training"])
    assert not is_organization_signer("Henry Ford", ["Ford"])
    assert not is_organization_signer("Rosa Lindqvist", ["Halcyon Maritime Group", "Treasury"])


def test_a_bare_domain_is_not_an_organization_name():
    """`fourthbrain.ai` is the website; the named company stays."""
    body = "Thanks\n\nMolly Larkin\nDirector of Operations\nFourthBrain\nfourthbrain.ai\n"
    candidate = find_candidate(body, sender_name="Molly Larkin")
    reading = _reading(person_name="Molly Larkin", organizations=["fourthbrain.ai", "FourthBrain"])
    assert [u.text for u in ground(candidate, reading, sender_name="Molly Larkin").units] == ["FourthBrain"]


def test_signer_is_the_sender_by_address_even_with_a_nickname_header():
    """`Nick B <nbolton04@gmail.com>` signs as `Nicholas C. Bolton`: the address spells him."""

    def agree(name, address):
        return signer_agreement("Nicholas C. Bolton", sender_name=name, sender_address=address)

    assert agree("Nick B", "nbolton04@gmail.com") == SignerAgreement.MATCH
    assert agree("Coach N", "nick.bolton@acme.com") == SignerAgreement.MATCH
    assert agree("Nick Bolton", "bolton213@yahoo.com") == SignerAgreement.MATCH
    assert agree("NB", "nb@acme.com") == SignerAgreement.NEUTRAL
    assert agree("Edmond Bolton", "efbolton@x.net") == SignerAgreement.CONFLICT
    assert agree("Jane Smith", "jsmith@acme.com") == SignerAgreement.CONFLICT


def test_a_cross_script_name_mismatch_is_not_a_conflict():
    """Header `Kenji Tanaka`, signature `田中 健二`: romanized kanji can't confirm or refute him."""
    assert signer_agreement("田中 健二", sender_name="Kenji Tanaka", sender_address="k@tokai-kaiun.co.jp") == (
        SignerAgreement.NEUTRAL
    )
    assert signer_agreement("Edmond Bolton", sender_name="Nicholas Bolton", sender_address=None) == (
        SignerAgreement.CONFLICT
    )
