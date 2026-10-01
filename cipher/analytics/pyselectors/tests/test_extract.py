"""End-to-end pipeline checks for extract_selectors."""

from pyselectors import extract_selectors

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType


def _by_type(text: str, **kw) -> dict[SelectorType, list]:
    out: dict[SelectorType, list] = {}
    for span in extract_selectors(text, **kw):
        out.setdefault(span.selector_type, []).append(span)
    return out


def test_empty_text():
    """Empty text."""
    assert extract_selectors("") == []


def test_email_offsets_and_lowercasing():
    """Email offsets and lowercasing."""
    text = "reach me at Jo.Smith@Acme.CO.UK tomorrow"
    (span,) = extract_selectors(text)
    assert span.selector_type is SelectorType.EMAIL
    assert span.normalized_value == "jo.smith@acme.co.uk"
    assert text[span.start_offset : span.end_offset] == "Jo.Smith@Acme.CO.UK"
    assert span.attributes["domain"] == "acme.co.uk"


def test_defanged_email():
    """Defanged email."""
    text = "write to john.doe at example dot com when ready"
    spans = extract_selectors(text)
    emails = [s for s in spans if s.selector_type is SelectorType.EMAIL]
    assert emails and emails[0].normalized_value == "john.doe@example.com"


def test_phone_region_hint_to_e164():
    """Phone region hint to e164."""
    spans = extract_selectors("call 020 7946 0958 tonight", language="en", region="GB")
    phones = [s for s in spans if s.selector_type is SelectorType.PHONE]
    assert phones and phones[0].normalized_value == "+442079460958"
    assert phones[0].attributes["region"] == "GB"


def test_phone_international_without_region():
    """Phone international without region."""
    spans = extract_selectors("+44 20 7946 0958")
    phones = [s for s in spans if s.selector_type is SelectorType.PHONE]
    assert phones and phones[0].normalized_value == "+442079460958"


def test_persian_digits_fold_in_phone():
    """Persian digits fold in phone."""
    # +98 912 345 6789 written with Persian (Extended Arabic-Indic) digits.
    text = "تلفن: +۹۸۹۱۲۳۴۵۶۷۸۹"
    spans = extract_selectors(text, language="fa")
    phones = [s for s in spans if s.selector_type is SelectorType.PHONE]
    assert phones and phones[0].normalized_value == "+989123456789"


def test_iban_checksum_gate():
    """Iban checksum gate."""
    assert SelectorType.IBAN in _by_type("IBAN GB82 WEST 1234 5698 7654 32 please")
    assert SelectorType.IBAN not in _by_type("GB00 WEST 1234 5698 7654 32")


def test_imei_luhn_gate():
    """Imei luhn gate."""
    assert SelectorType.IMEI in _by_type("device imei 490154203237518 registered")
    assert SelectorType.IMEI not in _by_type("device imei 490154203237510 registered")


def test_crypto_subtypes_and_attributes():
    """Crypto subtypes and attributes."""
    text = "btc bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4 eth 0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
    spans = extract_selectors(text, language="en")
    subs = {s.selector_subtype for s in spans if s.selector_type is SelectorType.CRYPTO_ADDRESS}
    assert subs == {SelectorSubtype.BTC_ADDRESS, SelectorSubtype.ETH_ADDRESS}
    eth = next(s for s in spans if s.selector_subtype is SelectorSubtype.ETH_ADDRESS)
    assert eth.attributes["network"] == "evm"


def test_bad_eth_checksum_dropped():
    """Bad eth checksum dropped."""
    spans = extract_selectors("addr 0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAeD", language="en")
    assert not [s for s in spans if s.selector_type is SelectorType.CRYPTO_ADDRESS]


def test_telegram_url_high_confidence():
    """Telegram url high confidence."""
    (span,) = extract_selectors("dm me https://t.me/durov")
    assert span.selector_type is SelectorType.SOCIAL_HANDLE
    assert span.selector_subtype is SelectorSubtype.TELEGRAM
    assert span.normalized_value == "durov"
    assert span.confidence >= 0.85


def test_private_ip_attributes():
    """Private ip attributes."""
    (span,) = extract_selectors("login from 10.1.2.3 at noon")
    assert span.selector_type is SelectorType.IP
    assert span.attributes["is_private"] == "true"
    assert span.attributes["version"] == "4"


def test_context_lifts_confidence():
    """Context lifts confidence."""
    plain = extract_selectors("number 8 (999) 111-22-33 here", language="ru")
    cued = extract_selectors("телефон 8 (999) 111-22-33 here", language="ru")
    p = next(s for s in plain if s.selector_type is SelectorType.PHONE)
    c = next(s for s in cued if s.selector_type is SelectorType.PHONE)
    assert c.confidence > p.confidence


def test_type_filter():
    """Type filter."""
    text = "mail a@b.com phone +14155552671"
    only_email = extract_selectors(text, types={SelectorType.EMAIL})
    assert {s.selector_type for s in only_email} == {SelectorType.EMAIL}


def test_regional_national_id_needs_language_hint():
    """Regional national id needs language hint."""
    ru = extract_selectors("ИНН 7830002293 в договоре", language="ru")
    nid = [s for s in ru if s.selector_type is SelectorType.NATIONAL_ID]
    assert nid and nid[0].selector_subtype is SelectorSubtype.RU_INN
    assert nid[0].attributes["country"] == "RU"


def test_cn_ric_with_birthdate():
    """Cn ric with birthdate."""
    spans = extract_selectors("身份证号 360426199101010071", language="zh")
    ric = next(s for s in spans if s.selector_type is SelectorType.NATIONAL_ID)
    assert ric.selector_subtype is SelectorSubtype.CN_RIC
    assert ric.attributes["birth_date"] == "1991-01-01"


def test_bank_card_and_imsi_global():
    """Bank card and imsi global."""
    types = {
        s.selector_type for s in extract_selectors("card 4111 1111 1111 1111 and IMSI 310150123456789", language="en")
    }
    assert SelectorType.BANK_CARD in types
    assert SelectorType.IMSI in types


def test_passport_mrz_td3():
    """Passport mrz td3."""
    text = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10"
    (span,) = extract_selectors(text)
    assert span.selector_type is SelectorType.PASSPORT
    assert span.attributes["document_number"] == "L898902C3"
    assert span.attributes["issuing_country"] == "UTO"
    assert span.attributes["mrz_type"] == "TD3"


def test_qq_requires_context():
    """Qq requires context."""
    without = extract_selectors("reference 123456789 in the report", language="zh")
    assert not [s for s in without if s.selector_subtype is SelectorSubtype.QQ]
    withcue = extract_selectors("加我扣扣 123456789 好友", language="zh")
    assert [s for s in withcue if s.selector_subtype is SelectorSubtype.QQ]


def test_regional_handle_urls_normalize_to_username():
    """Regional handle urls normalize to username."""
    spans = extract_selectors("سروش splus.ir/mychan and ok.ru/profile/593124", language="fa")
    by_sub = {s.selector_subtype: s.normalized_value for s in spans}
    assert by_sub[SelectorSubtype.SOROUSH] == "mychan"
    assert by_sub[SelectorSubtype.ODNOKLASSNIKI] == "593124"


def test_bare_15_digit_run_not_imei_without_context():
    """Bare 15 digit run not imei without context."""
    assert SelectorType.IMEI not in _by_type("ref 490154203237518 line item")
    assert SelectorType.IMEI in _by_type("device IMEI 490154203237518 registered")


def test_bare_16_digit_run_not_bank_card_without_context():
    """Bare 16 digit run not bank card without context."""
    assert SelectorType.BANK_CARD not in _by_type("code 4111111111111111 xyz")
    assert SelectorType.BANK_CARD in _by_type("pay by card 4111 1111 1111 1111")


def test_ip_gated_and_reserved_dropped():
    """Ip gated and reserved dropped."""
    assert SelectorType.IP not in _by_type("opencv-python Version <= 3.3.0.10 upgrade to")
    assert SelectorType.IP not in _by_type("four 8-bit numbers e.g. 192.168.1.1 written")
    assert SelectorType.IP not in _by_type("subnet mask 255.255.255.0 and 255.255.255.255 broadcast")
    (span,) = extract_selectors("login attempt from IP address 174.196.135.66 today")
    assert span.selector_type is SelectorType.IP


def test_social_url_action_paths_rejected():
    """Social url action paths yield no handle (the site itself is still a `domain`)."""
    assert SelectorType.SOCIAL_HANDLE not in _by_type("unsubscribe http://www.facebook.com/o.php?k=d60152&u=1")
    assert SelectorType.SOCIAL_HANDLE not in _by_type("get the app at https://twitter.com/download?s=13")
    assert SelectorType.SOCIAL_HANDLE not in _by_type("see https://www.instagram.com/p/CabcDEF/ for the post")
    (span,) = extract_selectors("real one https://www.facebook.com/michael.golt/posts/101")
    assert span.normalized_value == "michael.golt"


def test_bare_handle_keeps_hyphens_no_dot_runon():
    """Bare handle keeps hyphens no dot runon."""
    (span,) = extract_selectors("pay via Venmo (@matt-regan-1) please", language="en")
    assert span.normalized_value == "matt-regan-1"
    # a sentence boundary must not glue the next word on (a `.` ends the handle)
    handles = [
        s.normalized_value for s in extract_selectors("Twitter bot @NYT_first_said.You can see", language="en")
    ]
    assert "nyt_first_said" in handles and not any("you" in h for h in handles)


def test_email_tld_does_not_run_into_next_word():
    """Email tld does not run into next word."""
    got = [s.normalized_value for s in extract_selectors("write tips@medium.com Like what you see")]
    assert got == ["tips@medium.com"]


def test_domains_reduce_to_registrable_domain():
    """URLs and bare domains become the site's registrable domain; emails and filenames don't."""
    spans = extract_selectors(
        "Visit Udemy.com or https://click.e.target.com/terms?x=1 and www.bbc.co.uk/news. "
        "Mail nick@dell.com about main.py and report.pdf."
    )
    assert [(s.selector_type, s.normalized_value) for s in spans] == [
        (SelectorType.DOMAIN, "udemy.com"),
        (SelectorType.DOMAIN, "target.com"),
        (SelectorType.DOMAIN, "bbc.co.uk"),
        (SelectorType.EMAIL, "nick@dell.com"),
    ]


def test_web_address_helpers():
    """Name spans that are (part of) a website are recognised."""
    from pyselectors.domains import is_web_address, web_host_containing

    assert is_web_address("Udemy.com") and is_web_address("Target.com/CircleCard")
    assert not is_web_address("Hotels.com Rewards") and not is_web_address("Towards")
    content = "read (towardsdatascience.com) or upenn.edu/usa -- Dell"
    assert web_host_containing(content, 6, 13) == "towardsdatascience.com"
    assert web_host_containing(content, 43, 46) is None  # path, not host
    assert web_host_containing(content, 50, 54) is None
