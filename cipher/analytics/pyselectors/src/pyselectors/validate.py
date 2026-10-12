"""Stage 4 -- hard-rule validation + attribute extraction.

A validator takes a canonical value and returns a flat ``dict[str, str]`` of
kind-specific facts. It raises ``SelectorRejected`` to drop the span entirely
(bad checksum, reserved range, ...). All imports of heavy/optional libraries are
function-local so importing this module stays cheap.
"""

import ipaddress

import phonenumbers
from phonenumbers import carrier, geocoder, timezone as pn_timezone

from cipher.schemas.graph.ontology import SelectorType
from pyselectors._crypto_checksums import CryptoInvalid, identify_crypto

_FREE_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "ymail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "icloud.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "mail.com",
        "yandex.ru",
        "yandex.com",
        "ya.ru",
        "mail.ru",
        "bk.ru",
        "list.ru",
        "inbox.ru",
        "qq.com",
        "163.com",
        "126.com",
        "sina.com",
    }
)


class SelectorRejected(Exception):
    """Raised by a validator to suppress a span (invalid checksum, reserved value, ...)."""


def _v_phone(value: str, country: str | None) -> dict[str, str]:
    if not value.startswith("+"):  # national: no country stated, so nothing to check it against
        return {"number_format": "national"}
    try:
        parsed = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException as exc:
        raise SelectorRejected(str(exc)) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise SelectorRejected("not a valid number")
    number_type = phonenumbers.number_type(parsed)
    attrs: dict[str, str] = {
        "country_code": str(parsed.country_code),
        "number_type": _PHONE_TYPE_NAMES.get(number_type, "unknown"),
    }
    region = phonenumbers.region_code_for_number(parsed)
    if region:
        attrs["region"] = region
    name = carrier.name_for_number(parsed, "en")
    if name:
        attrs["carrier"] = name
    where = geocoder.description_for_number(parsed, "en")
    if where:
        attrs["geo"] = where
    zones = pn_timezone.time_zones_for_number(parsed)
    if zones and zones[0] != "Etc/Unknown":
        attrs["timezone"] = zones[0]
    return attrs


_PHONE_TYPE_NAMES = {
    phonenumbers.PhoneNumberType.MOBILE: "mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
    phonenumbers.PhoneNumberType.VOIP: "voip",
    phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
    phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium_rate",
    phonenumbers.PhoneNumberType.PAGER: "pager",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal_number",
}


def _v_email(value: str, country: str | None) -> dict[str, str]:
    if value.count("@") != 1:
        raise SelectorRejected("bad email shape")
    local, domain = value.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise SelectorRejected("bad email domain")
    return {"domain": domain, "is_free_provider": str(domain in _FREE_EMAIL_DOMAINS).lower()}


_IP_DOC_NETS = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("2001:db8::/32"),
)


def _v_ip(value: str, country: str | None) -> dict[str, str]:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError as exc:
        raise SelectorRejected(str(exc)) from exc
    # Not real endpoints: unspecified/broadcast, loopback, multicast, reserved,
    # link-local, and the RFC 5737 / RFC 3849 documentation ranges (tutorials).
    if (
        addr.is_unspecified
        or addr.is_loopback
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_link_local
        or value == "255.255.255.255"
        or any(addr in net for net in _IP_DOC_NETS)
    ):
        raise SelectorRejected("not a routable endpoint")
    return {
        "version": str(addr.version),
        "is_private": str(addr.is_private).lower(),
        "is_global": str(addr.is_global).lower(),
        "is_loopback": str(addr.is_loopback).lower(),
        "is_multicast": str(addr.is_multicast).lower(),
    }


def _v_iban(value: str, country: str | None) -> dict[str, str]:
    from stdnum import iban

    try:
        iban.validate(value)
    except Exception as exc:  # noqa: BLE001 -- stdnum raises a family of ValidationError subclasses
        raise SelectorRejected(str(exc)) from exc
    return {"country": value[:2], "bban": value[4:], "checksum_valid": "true"}


def _v_imei(value: str, country: str | None) -> dict[str, str]:
    from stdnum import imei

    try:
        compact = imei.validate(value)
    except Exception as exc:  # noqa: BLE001
        raise SelectorRejected(str(exc)) from exc
    attrs = {"luhn_valid": "true"}
    try:
        parts = imei.split(compact)
        attrs["tac"] = parts[0]
        attrs["serial"] = parts[1]
    except Exception:  # noqa: BLE001
        pass
    return attrs


def _v_crypto(value: str, country: str | None) -> dict[str, str]:
    try:
        info = identify_crypto(value)
    except CryptoInvalid as exc:
        raise SelectorRejected(str(exc)) from exc
    return {
        "currency": info.currency,
        "network": info.network,
        "address_format": info.address_format,
        "checksum_valid": "true",
    }


def _v_social_handle(value: str, country: str | None) -> dict[str, str]:
    if not value or len(value) > 64:
        raise SelectorRejected("implausible handle")
    return {}


def _v_imsi(value: str, country: str | None) -> dict[str, str]:
    from stdnum import imsi

    try:
        imsi.validate(value)
        info = imsi.info(value)
    except Exception as exc:  # noqa: BLE001
        raise SelectorRejected(str(exc)) from exc
    attrs = {"mcc": info["mcc"], "mnc": info["mnc"], "msin": info["msin"]}
    if info.get("country"):
        attrs["country"] = info["country"]
    if info.get("operator"):
        attrs["operator"] = info["operator"]
    return attrs


_CARD_BRANDS = (
    ("visa", lambda n: n[0] == "4"),
    ("mastercard", lambda n: 51 <= int(n[:2]) <= 55 or 2221 <= int(n[:4]) <= 2720),
    ("amex", lambda n: n[:2] in {"34", "37"}),
    ("discover", lambda n: n[:4] == "6011" or n[:2] == "65"),
    ("mir", lambda n: 2200 <= int(n[:4]) <= 2204),
    ("unionpay", lambda n: n[:2] == "62"),
    ("jcb", lambda n: 3528 <= int(n[:4]) <= 3589),
)


def _v_bank_card(value: str, country: str | None) -> dict[str, str]:
    from stdnum import luhn

    digits = "".join(ch for ch in value if ch.isdigit())
    if not 12 <= len(digits) <= 19 or not luhn.is_valid(digits):
        raise SelectorRejected("bad card number")
    brand = next((name for name, test in _CARD_BRANDS if test(digits)), "unknown")
    return {"brand": brand, "iin": digits[:6], "last4": digits[-4:], "luhn_valid": "true"}


def _v_national_id_ru(value: str, country: str | None) -> dict[str, str]:
    from stdnum.ru import inn

    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) in (10, 12):
        try:
            inn.validate(digits)
        except Exception as exc:  # noqa: BLE001
            raise SelectorRejected(str(exc)) from exc
        return {"country": "RU", "subtype": "ru_inn", "checksum_valid": "true"}
    if len(digits) == 11:  # SNILS: 9 digits + 2 check, weighted 9..1
        body, check = digits[:9], int(digits[9:])
        total = sum(int(d) * (9 - i) for i, d in enumerate(body))
        rem = total % 101
        if (rem if rem != 100 else 0) != check:
            raise SelectorRejected("bad SNILS checksum")
        return {"country": "RU", "subtype": "ru_snils", "checksum_valid": "true"}
    raise SelectorRejected("unrecognised RU national id length")


def _v_national_id_cn(value: str, country: str | None) -> dict[str, str]:
    from stdnum.cn import ric

    digits = "".join(ch for ch in value if ch in "0123456789Xx")
    try:
        ric.validate(digits)
    except Exception as exc:  # noqa: BLE001
        raise SelectorRejected(str(exc)) from exc
    attrs = {"country": "CN", "subtype": "cn_ric", "checksum_valid": "true", "region_code": digits[:6]}
    attrs["birth_date"] = f"{digits[6:10]}-{digits[10:12]}-{digits[12:14]}"
    return attrs


def _v_national_id_ir(value: str, country: str | None) -> dict[str, str]:
    digits = "".join(ch for ch in value if ch.isdigit()).zfill(10)
    if len(digits) != 10 or digits == digits[0] * 10:
        raise SelectorRejected("bad IR national id shape")
    total = sum(int(d) * (10 - i) for i, d in enumerate(digits[:9]))
    rem = total % 11
    check = rem if rem < 2 else 11 - rem
    if check != int(digits[9]):
        raise SelectorRejected("bad IR code melli checksum")
    return {"country": "IR", "subtype": "ir_code_melli", "checksum_valid": "true"}


def _v_passport_mrz(value: str, country: str | None) -> dict[str, str]:
    from mrz.checker.td2 import TD2CodeChecker
    from mrz.checker.td3 import TD3CodeChecker

    lines = value.splitlines()
    checker_cls = {44: TD3CodeChecker, 36: TD2CodeChecker}.get(len(lines[0]) if lines else 0)
    if checker_cls is None or not lines[0].startswith("P"):
        raise SelectorRejected("not a passport MRZ")
    try:
        checker = checker_cls(value, check_expiry=False)
        if not checker:
            raise SelectorRejected("MRZ check digits failed")
        f = checker.fields()
    except SelectorRejected:
        raise
    except Exception as exc:  # noqa: BLE001 -- mrz raises assorted errors on malformed input
        raise SelectorRejected(str(exc)) from exc
    attrs = {
        "mrz_type": "TD3" if len(lines[0]) == 44 else "TD2",
        "document_number": f.document_number.replace("<", ""),
        "issuing_country": f.country,
        "nationality": f.nationality,
        "checksum_valid": "true",
    }
    for key, raw in (("birth_date", f.birth_date), ("expiry_date", f.expiry_date), ("sex", f.sex)):
        if raw and raw.strip("<"):
            attrs[key] = raw
    return attrs


def _v_passport(value: str, country: str | None) -> dict[str, str]:
    """An MRZ block is checked digit by digit; a bare number only has its shape (the pattern) to go on."""
    if "\n" in value:
        return _v_passport_mrz(value, country)
    return {"format": "number"}


def _v_license_plate(value: str, country: str | None) -> dict[str, str]:
    if not any(c.isdigit() for c in value) or not any(c.isalpha() for c in value):
        raise SelectorRejected("a plate has letters and digits")
    return {}


def _v_mac_address(value: str, country: str | None) -> dict[str, str]:
    if value in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
        raise SelectorRejected("null / broadcast MAC")
    first = int(value[:2], 16)
    return {
        "oui": value[:8],
        "administration": "local" if first & 2 else "universal",
        "cast": "multicast" if first & 1 else "unicast",
    }


VALIDATORS = {
    "phone": _v_phone,
    "email": _v_email,
    "ip": _v_ip,
    "iban": _v_iban,
    "imei": _v_imei,
    "imsi": _v_imsi,
    "bank_card": _v_bank_card,
    "passport": _v_passport,
    "license_plate": _v_license_plate,
    "mac_address": _v_mac_address,
    "crypto_address": _v_crypto,
    "social_handle": _v_social_handle,
    "national_id_ru": _v_national_id_ru,
    "national_id_cn": _v_national_id_cn,
    "national_id_ir": _v_national_id_ir,
}


def run(selector_type: SelectorType, value: str, *, country: str | None = None) -> dict[str, str]:
    """Validate ``value`` for its type, returning attributes. Raises ``SelectorRejected`` to drop it."""
    from pyselectors.packs.loader import load_pack

    try:
        pack = load_pack(selector_type.value, country)
        name = pack.validator
        if country and country in pack.countries and pack.countries[country].validator:
            name = pack.countries[country].validator
    except FileNotFoundError:
        name = selector_type.value

    if name is None:
        return {}
    validator = VALIDATORS.get(name)
    if validator is None:
        return {}
    return validator(value, country)
