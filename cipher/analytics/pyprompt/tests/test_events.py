"""The events pack: flat `LlmEvent` -> typed `ParsedEvent` with a `details` blob."""

from pyprompt.runner import _coerce_event
from pyprompt.schemas import LlmEvent

from cipher.schemas.graph.event import (
    DeliveryDetails,
    LodgingDetails,
    ReservationDetails,
    TravelDetails,
)


def _event(**kw) -> LlmEvent:
    return LlmEvent(title="x", event_type=kw.pop("event_type", "other"), **kw)


def test_build_details_maps_each_type():
    travel = _coerce_event(_event(event_type="travel", operator="Lufthansa", number="LH441", confirmation="GX48"))
    assert isinstance(travel.details, TravelDetails)
    assert travel.details.operator == "Lufthansa" and travel.details.number == "LH441"

    lodging = _coerce_event(_event(event_type="lodging", operator="Adlon", nights=3, guests=1))
    assert isinstance(lodging.details, LodgingDetails) and lodging.details.nights == 3

    reservation = _coerce_event(_event(event_type="reservation", operator="Borchardt", party_size=4))
    assert isinstance(reservation.details, ReservationDetails) and reservation.details.party_size == 4

    delivery = _coerce_event(_event(event_type="delivery", carrier="DHL", tracking_number="JD014"))
    assert isinstance(delivery.details, DeliveryDetails) and delivery.details.carrier == "DHL"


def test_no_details_when_type_has_none_or_fields_empty():
    assert _coerce_event(_event(event_type="meeting", operator="ignored-for-meeting")).details is None
    assert _coerce_event(_event(event_type="travel")).details is None


def test_bad_detail_value_drops_the_blob_not_the_event():
    parsed = _coerce_event(_event(event_type="lodging", operator="Adlon", nights=-1))
    assert parsed.details is None
    assert parsed.title == "x"


def test_confidence_is_clamped():
    assert _coerce_event(_event(confidence=1.4)).confidence == 1.0
    assert _coerce_event(_event(confidence=-0.2)).confidence == 0.0
    assert _coerce_event(_event(confidence=None)).confidence is None
