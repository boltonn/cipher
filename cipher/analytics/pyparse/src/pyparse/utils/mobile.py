import phonenumbers
from phonenumbers import NumberParseException

from cipher.schemas._base.common import PhoneNumberType


def normalize_phone_number(phone: str, default_region: str | None = None) -> tuple[str, PhoneNumberType]:
    """Normalize phone number to E.164 format if possible.

    Returns: (normalized_number, number_type)
    """
    if not phone or phone.lower() in ("null", "unknown", ""):
        return (phone or "unknown", PhoneNumberType.RAW_PHONE_NUMBER)

    try:
        parsed = phonenumbers.parse(phone, default_region)
        if phonenumbers.is_possible_number(parsed):
            e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            return (e164, PhoneNumberType.ITU_E164)
        else:
            return (phone, PhoneNumberType.RAW_PHONE_NUMBER)
    except NumberParseException:
        return (phone, PhoneNumberType.RAW_PHONE_NUMBER)
