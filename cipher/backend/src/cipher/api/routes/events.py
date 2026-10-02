"""Events: the dated-occurrence surface.

Travel, lodging, reservations, meetings, gatherings, deliveries pulled from
documents or parsed from calendar attachments.
Feeds the calendar and table views. Events link to people via `event_participant`
(-> entity) and to places via `event_place` (-> location); each link carries
surface text until resolution runs.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response

from cipher.api.deps.postgres import EventDatastoreDep
from cipher.schemas._base.exceptions import EntityNotFoundError
from cipher.schemas.graph.event import (
    Event,
    EventCreate,
    EventIdsRequest,
    EventSearchParameters,
    EventUpdate,
    EventWithLinks,
    PaginatedEventsResponse,
)
from cipher.schemas.graph.event_participant import EventParticipant, EventParticipantCreate
from cipher.schemas.graph.event_place import EventPlace, EventPlaceCreate

router = APIRouter(prefix="/events", tags=["events"])

_BY_ALIAS = {"response_model_by_alias": True}


@router.get("", summary="List events", response_model=PaginatedEventsResponse, **_BY_ALIAS)
async def list_events(
    params: Annotated[EventSearchParameters, Query()], datastore: EventDatastoreDep
) -> PaginatedEventsResponse:
    """List events, filtered by dataset, file, type, status, date range, participant, or place."""
    return await datastore.list_events(params)


@router.get("/calendar", summary="Events in a date window", response_model=list[Event], **_BY_ALIAS)
async def calendar_events(
    datastore: EventDatastoreDep,
    date_from: Annotated[datetime, Query(alias="dateFrom")],
    date_to: Annotated[datetime, Query(alias="dateTo")],
    dataset_id: Annotated[str | None, Query(alias="datasetId")] = None,
) -> list[Event]:
    """Every event whose `date_start` falls in [dateFrom, dateTo], ordered ascending."""
    return await datastore.calendar_events(date_from=date_from, date_to=date_to, dataset_id=dataset_id)


@router.get("/categories", summary="Distinct source labels in use", response_model=list[str])
async def category_values(
    datastore: EventDatastoreDep,
    dataset_id: Annotated[str | None, Query(alias="datasetId")] = None,
    q: Annotated[str | None, Query(description="Substring filter")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[str]:
    """The raw iCalendar `CATEGORIES` values present on events, for the filter combobox."""
    return await datastore.list_category_values(dataset_id=dataset_id, q=q, limit=limit)


@router.get("/tags", summary="Distinct tags in use", response_model=list[str])
async def tag_values(
    datastore: EventDatastoreDep,
    dataset_id: Annotated[str | None, Query(alias="datasetId")] = None,
    q: Annotated[str | None, Query(description="Substring filter")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[str]:
    """Analyst `tags` present on events, most-used first -- powers tag-input suggestions."""
    return await datastore.list_tag_values(dataset_id=dataset_id, q=q, limit=limit)


@router.post("", summary="Create an event", response_model=Event, **_BY_ALIAS)
async def create_event(payload: EventCreate, datastore: EventDatastoreDep) -> Event:
    """Record an event (analyst-authored, or written by an extraction pass)."""
    return await datastore.add_event(payload)


@router.post("/mark-invalid", summary="Mark events invalid", status_code=204)
async def mark_events_invalid(payload: EventIdsRequest, datastore: EventDatastoreDep) -> Response:
    """Delete events that are not real; a source file left with none is tagged `event` negative."""
    await datastore.delete_events(payload.event_ids)
    return Response(status_code=204)


@router.get("/{event_id}", summary="Get an event", response_model=EventWithLinks, **_BY_ALIAS)
async def get_event(event_id: str, datastore: EventDatastoreDep) -> EventWithLinks:
    """Fetch one event with its participants and places."""
    event = await datastore.get_event_with_links(event_id)
    if event is None:
        raise EntityNotFoundError("Event", event_id)
    return event


@router.patch("/{event_id}", summary="Update an event", response_model=Event, **_BY_ALIAS)
async def update_event(event_id: str, data: EventUpdate, datastore: EventDatastoreDep) -> Event:
    """Patch an event's fields (time, status, details, verification)."""
    event = await datastore.update_event(event_id, data)
    if event is None:
        raise EntityNotFoundError("Event", event_id)
    return event


@router.delete("/{event_id}", summary="Delete an event", status_code=204)
async def delete_event(event_id: str, datastore: EventDatastoreDep) -> Response:
    """Delete an event and its participant/place rows."""
    if not await datastore.delete_event(event_id):
        raise EntityNotFoundError("Event", event_id)
    return Response(status_code=204)


@router.get(
    "/{event_id}/participants",
    summary="List participants",
    response_model=list[EventParticipant],
    **_BY_ALIAS,
)
async def list_participants(event_id: str, datastore: EventDatastoreDep) -> list[EventParticipant]:
    """People and organisations attached to the event."""
    return await datastore.list_participants(event_id)


@router.post(
    "/{event_id}/participants",
    summary="Attach a participant",
    response_model=EventParticipant,
    **_BY_ALIAS,
)
async def add_participant(
    event_id: str, payload: EventParticipantCreate, datastore: EventDatastoreDep
) -> EventParticipant:
    """Attach a person/organisation to the event (resolved entity or bare name)."""
    if await datastore.get_event(event_id) is None:
        raise EntityNotFoundError("Event", event_id)
    return await datastore.add_participant(event_id=event_id, payload=payload)


@router.delete("/participants/{participant_id}", summary="Detach a participant", status_code=204)
async def delete_participant(participant_id: str, datastore: EventDatastoreDep) -> Response:
    """Remove a participant row."""
    if not await datastore.delete_participant(participant_id):
        raise EntityNotFoundError("EventParticipant", participant_id)
    return Response(status_code=204)


@router.get("/{event_id}/places", summary="List places", response_model=list[EventPlace], **_BY_ALIAS)
async def list_places(event_id: str, datastore: EventDatastoreDep) -> list[EventPlace]:
    """Places attached to the event (venue, origin, destination)."""
    return await datastore.list_places(event_id)


@router.post("/{event_id}/places", summary="Attach a place", response_model=EventPlace, **_BY_ALIAS)
async def add_place(event_id: str, payload: EventPlaceCreate, datastore: EventDatastoreDep) -> EventPlace:
    """Attach a place to the event (resolved location or bare text)."""
    if await datastore.get_event(event_id) is None:
        raise EntityNotFoundError("Event", event_id)
    return await datastore.add_place(event_id=event_id, payload=payload)


@router.delete("/places/{place_id}", summary="Detach a place", status_code=204)
async def delete_place(place_id: str, datastore: EventDatastoreDep) -> Response:
    """Remove a place row."""
    if not await datastore.delete_place(place_id):
        raise EntityNotFoundError("EventPlace", place_id)
    return Response(status_code=204)
