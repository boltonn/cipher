"""Stage 4 -- validation + attribute extraction."""

import pytest
from pyselectors.validate import SelectorRejected, run

from cipher.schemas.graph.ontology import SelectorType


def test_phone_attributes():
    """Phone attributes."""
    attrs = run(SelectorType.PHONE, "+14155552671")
    assert attrs["region"] == "US"
    assert attrs["number_type"] in {"mobile", "fixed_line_or_mobile", "fixed_line"}
    assert "geo" in attrs


def test_phone_invalid_rejected():
    """Phone invalid rejected."""
    with pytest.raises(SelectorRejected):
        run(SelectorType.PHONE, "+1123")


def test_ip_v4_v6_and_reject():
    """Ip v4 v6 and reject."""
    assert run(SelectorType.IP, "8.8.8.8")["is_global"] == "true"
    assert run(SelectorType.IP, "2001:4860:4860::8888")["version"] == "6"
    assert run(SelectorType.IP, "10.0.0.1")["is_private"] == "true"
    with pytest.raises(SelectorRejected):
        run(SelectorType.IP, "999.1.1.1")


def test_iban_country_and_reject():
    """Iban country and reject."""
    assert run(SelectorType.IBAN, "GB82WEST12345698765432")["country"] == "GB"
    with pytest.raises(SelectorRejected):
        run(SelectorType.IBAN, "GB00WEST12345698765432")


def test_imei_tac_and_reject():
    """Imei tac and reject."""
    attrs = run(SelectorType.IMEI, "490154203237518")
    assert attrs["luhn_valid"] == "true"
    with pytest.raises(SelectorRejected):
        run(SelectorType.IMEI, "490154203237510")


def test_crypto_networks():
    """Crypto networks."""
    assert run(SelectorType.CRYPTO_ADDRESS, "0x52908400098527886E0F7030069857D2E4169EE7")["currency"] == "ETH"
    assert run(SelectorType.CRYPTO_ADDRESS, "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")["currency"] == "TRX"
    with pytest.raises(SelectorRejected):
        run(SelectorType.CRYPTO_ADDRESS, "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAeD")


def test_email_free_provider_flag():
    """Email free provider flag."""
    assert run(SelectorType.EMAIL, "x@gmail.com")["is_free_provider"] == "true"
    assert run(SelectorType.EMAIL, "x@acme.co.uk")["is_free_provider"] == "false"


def test_imsi_operator_and_reject():
    """Imsi operator and reject."""
    attrs = run(SelectorType.IMSI, "310150123456789")
    assert attrs["mcc"] == "310" and "operator" in attrs
    with pytest.raises(SelectorRejected):
        run(SelectorType.IMSI, "000000000000000")


def test_bank_card_luhn_and_brand():
    """Bank card luhn and brand."""
    attrs = run(SelectorType.BANK_CARD, "4111111111111111")
    assert attrs["brand"] == "visa" and attrs["luhn_valid"] == "true"
    with pytest.raises(SelectorRejected):
        run(SelectorType.BANK_CARD, "4111111111111112")


def test_national_id_ru_cn_ir():
    """National id ru cn ir."""
    assert run(SelectorType.NATIONAL_ID, "7830002293", country="RU")["subtype"] == "ru_inn"
    cn = run(SelectorType.NATIONAL_ID, "360426199101010071", country="CN")
    assert cn["subtype"] == "cn_ric" and cn["birth_date"] == "1991-01-01"
    assert run(SelectorType.NATIONAL_ID, "0499370899", country="IR")["subtype"] == "ir_code_melli"
    with pytest.raises(SelectorRejected):
        run(SelectorType.NATIONAL_ID, "0499370898", country="IR")
