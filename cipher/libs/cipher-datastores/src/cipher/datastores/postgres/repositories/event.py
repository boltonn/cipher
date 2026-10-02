from datetime import datetime

from sqlalchemy import asc, delete, desc, exists, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.event import EventTable
from cipher.datastores.postgres.tables.event_participant import EventParticipantTable
from cipher.datastores.postgres.tables.event_place import EventPlaceTable
from cipher.datastores.postgres.utils import strip_null_bytes
from cipher.schemas._base.common import SortOrder
from cipher.schemas.graph.event import (
    EVENT_FILE_TAG,
    Event,
    EventCreate,
    EventSearchParameters,
    EventSortField,
    EventUpdate,
    EventWithLinks,
    PaginatedEventsResponse,
)
from cipher.schemas.graph.event_participant import EventParticipant, EventParticipantCreate
from cipher.schemas.graph.event_place import EventPlace, EventPlaceCreate

_SORT_COLUMN = {
    EventSortField.DATE_START: EventTable.date_start,
    EventSortField.DATE_CREATED: EventTable.date_created,
    EventSortField.DATE_UPDATED: EventTable.date_updated,
}


class PostgresEventRepository:
    """Postgres datastore for extracted events and their participant/place links."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the event tables using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(EventTable.metadata.create_all)

    async def get_count(self) -> int:
        """Total number of event rows."""
        result = await self.session.execute(select(func.count(EventTable.id)))
        return result.scalar_one()

    async def add_event(self, payload: EventCreate) -> Event:
        """Insert a single event row."""
        row = EventTable(**strip_null_bytes(payload.model_dump(by_alias=False)))
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return Event.model_validate(row)

    async def get_event(self, event_id: str) -> Event | None:
        """Fetch one event by id."""
        row = (await self.session.execute(select(EventTable).where(EventTable.id == event_id))).scalar_one_or_none()
        return Event.model_validate(row) if row else None

    async def get_event_with_links(self, event_id: str) -> EventWithLinks | None:
        """Fetch one event with its participants and places."""
        row = (await self.session.execute(select(EventTable).where(EventTable.id == event_id))).scalar_one_or_none()
        if row is None:
            return None
        data = Event.model_validate(row).model_dump(by_alias=False, exclude={"category"})
        return EventWithLinks(
            **data,
            participants=await self.list_participants(event_id),
            places=await self.list_places(event_id),
        )

    async def list_events(self, params: EventSearchParameters) -> PaginatedEventsResponse:
        """Query events with filtering, pagination, and sorting."""
        where = self._filters(params)

        total = (await self.session.execute(select(func.count(EventTable.id)).where(*where))).scalar_one()

        column = _SORT_COLUMN[params.sort_by]
        order = desc(column) if params.sort_order == SortOrder.DESC else asc(column)
        stmt = (
            select(EventTable)
            .where(*where)
            .order_by(order)
            .offset((params.page - 1) * params.limit)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return PaginatedEventsResponse(
            total=total,
            page=params.page,
            limit=params.limit,
            data=[Event.model_validate(r) for r in rows],
        )

    async def list_category_values(
        self, *, dataset_id: str | None = None, q: str | None = None, limit: int = 50
    ) -> list[str]:
        """Distinct raw source labels (`event.categories`, i.e. iCalendar CATEGORIES) in use.

        Powers the events filter bar's label combobox so an analyst picks from
        what actually exists rather than guessing. Substring-filtered by `q`.
        """
        elem = func.jsonb_array_elements_text(EventTable.categories).label("value")
        inner = select(elem).select_from(EventTable)
        if dataset_id:
            inner = inner.where(EventTable.dataset_id == dataset_id)
        sub = inner.subquery()

        stmt = select(sub.c.value).distinct().order_by(sub.c.value).limit(limit)
        if q:
            stmt = stmt.where(sub.c.value.ilike(f"%{q}%"))
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_tag_values(
        self, *, dataset_id: str | None = None, q: str | None = None, limit: int = 50
    ) -> list[str]:
        """Distinct analyst `tags` in use, most-used first.

        Powers tag-input suggestions so an analyst reuses an existing tag
        instead of typing a near-duplicate. Substring-filtered by `q`.
        """
        elem = func.jsonb_array_elements_text(EventTable.tags).label("value")
        inner = select(elem).select_from(EventTable)
        if dataset_id:
            inner = inner.where(EventTable.dataset_id == dataset_id)
        sub = inner.subquery()

        stmt = select(sub.c.value).group_by(sub.c.value)
        if q:
            stmt = stmt.where(sub.c.value.ilike(f"%{q}%"))
        stmt = stmt.order_by(func.count().desc(), sub.c.value.asc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def calendar_events(
        self, *, date_from: datetime, date_to: datetime, dataset_id: str | None = None
    ) -> list[Event]:
        """Every event whose `date_start` falls in [date_from, date_to], ascending."""
        where = [EventTable.date_start >= date_from, EventTable.date_start <= date_to]
        if dataset_id:
            where.append(EventTable.dataset_id == dataset_id)
        stmt = select(EventTable).where(*where).order_by(EventTable.date_start.asc()).limit(2000)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [Event.model_validate(r) for r in rows]

    async def update_event(self, event_id: str, data: EventUpdate) -> Event | None:
        """Patch an event row."""
        patch = strip_null_bytes(data.model_dump(exclude_unset=True, by_alias=False))
        if patch:
            await self.session.execute(update(EventTable).where(EventTable.id == event_id).values(**patch))
            await self.session.commit()
        return await self.get_event(event_id)

    async def delete_event(self, event_id: str) -> bool:
        """Delete an event row (participant/place rows cascade)."""
        return bool(await self.delete_events([event_id]))

    async def delete_events(self, event_ids: list[str]) -> int:
        """Mark events invalid: delete them (participant/place rows cascade). Returns rows deleted.

        A source file tagged `event` that is left with no events moves to
        `negative_tags` -- the analyst's verdict replaces the extractor's label.
        """
        deleted = await self.session.execute(
            delete(EventTable).where(EventTable.id.in_(event_ids)).returning(EventTable.file_id)
        )
        file_ids = deleted.scalars().all()
        await self.session.execute(
            text(
                "UPDATE file SET tags = tags - :tag, negative_tags = negative_tags || to_jsonb(cast(:tag as text)) "
                "WHERE id = ANY(:file_ids) AND tags ? :tag "
                "AND NOT EXISTS (SELECT 1 FROM event WHERE event.file_id = file.id)"
            ),
            {"tag": EVENT_FILE_TAG, "file_ids": [file_id for file_id in set(file_ids) if file_id]},
        )
        await self.session.commit()
        return len(file_ids)

    async def delete_extracted_by_dataset_id(self, dataset_id: str) -> int:
        """Delete a dataset's extraction-built events, keeping manual + analyst-verified rows.

        The undo for `extract-events`; participant/place rows cascade.
        """
        result = await self.session.execute(
            delete(EventTable).where(
                EventTable.dataset_id == dataset_id,
                EventTable.extractor.is_distinct_from("manual"),
                EventTable.is_verified.is_(False),
            )
        )
        await self.session.commit()
        return result.rowcount or 0

    async def add_participant(self, *, event_id: str, payload: EventParticipantCreate) -> EventParticipant:
        """Attach a person/organisation to an event."""
        row = EventParticipantTable(event_id=event_id, **strip_null_bytes(payload.model_dump(by_alias=False)))
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return EventParticipant.model_validate(row)

    async def list_participants(self, event_id: str) -> list[EventParticipant]:
        """Participants attached to an event, oldest first."""
        rows = (
            (
                await self.session.execute(
                    select(EventParticipantTable)
                    .where(EventParticipantTable.event_id == event_id)
                    .order_by(EventParticipantTable.date_created.asc())
                )
            )
            .scalars()
            .all()
        )
        return [EventParticipant.model_validate(r) for r in rows]

    async def delete_participant(self, participant_id: str) -> bool:
        """Remove a participant row."""
        result = await self.session.execute(
            delete(EventParticipantTable).where(EventParticipantTable.id == participant_id)
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def unresolved_participants(self, dataset_id: str) -> list[EventParticipant]:
        """Every `entity_id IS NULL` participant on the dataset's events, for `resolve-event-links`."""
        rows = (
            (
                await self.session.execute(
                    select(EventParticipantTable)
                    .join(EventTable, EventTable.id == EventParticipantTable.event_id)
                    .where(EventTable.dataset_id == dataset_id, EventParticipantTable.entity_id.is_(None))
                )
            )
            .scalars()
            .all()
        )
        return [EventParticipant.model_validate(r) for r in rows]

    async def set_participant_entity(self, participant_id: str, entity_id: str) -> None:
        """Point a resolved participant at its `entity`."""
        await self.session.execute(
            update(EventParticipantTable).where(EventParticipantTable.id == participant_id).values(entity_id=entity_id)
        )

    async def unresolved_places(self, dataset_id: str) -> list[EventPlace]:
        """Every `location_id IS NULL` place on the dataset's events, for `resolve-event-links`."""
        rows = (
            (
                await self.session.execute(
                    select(EventPlaceTable)
                    .join(EventTable, EventTable.id == EventPlaceTable.event_id)
                    .where(
                        EventTable.dataset_id == dataset_id,
                        EventPlaceTable.location_id.is_(None),
                        EventPlaceTable.raw_text.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [EventPlace.model_validate(r) for r in rows]

    async def set_place_location(self, place_id: str, location_id: str) -> None:
        """Point a resolved place at its `location`."""
        await self.session.execute(
            update(EventPlaceTable).where(EventPlaceTable.id == place_id).values(location_id=location_id)
        )

    async def add_place(self, *, event_id: str, payload: EventPlaceCreate) -> EventPlace:
        """Attach a place to an event."""
        row = EventPlaceTable(event_id=event_id, **strip_null_bytes(payload.model_dump(by_alias=False)))
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return EventPlace.model_validate(row)

    async def list_places(self, event_id: str) -> list[EventPlace]:
        """Places attached to an event, oldest first."""
        rows = (
            (
                await self.session.execute(
                    select(EventPlaceTable)
                    .where(EventPlaceTable.event_id == event_id)
                    .order_by(EventPlaceTable.date_created.asc())
                )
            )
            .scalars()
            .all()
        )
        return [EventPlace.model_validate(r) for r in rows]

    async def delete_place(self, place_id: str) -> bool:
        """Remove a place row."""
        result = await self.session.execute(delete(EventPlaceTable).where(EventPlaceTable.id == place_id))
        await self.session.commit()
        return bool(result.rowcount)

    @staticmethod
    def _filters(params: EventSearchParameters) -> list:
        """Build the WHERE clause shared by list + count."""
        where = []
        if params.dataset_id:
            where.append(EventTable.dataset_id == params.dataset_id)
        if params.file_id:
            where.append(EventTable.file_id == params.file_id)
        if params.query:
            where.append(EventTable.title.ilike(f"%{params.query}%"))
        if params.event_type:
            where.append(EventTable.event_type == params.event_type)
        if params.category:
            where.append(EventTable.categories.contains([params.category]))
        if params.uid:
            where.append(EventTable.uid == params.uid)
        if params.status:
            where.append(EventTable.status == params.status)
        if params.date_from is not None:
            where.append(EventTable.date_start >= params.date_from)
        if params.date_to is not None:
            where.append(EventTable.date_start <= params.date_to)
        if params.is_verified is not None:
            where.append(EventTable.is_verified.is_(params.is_verified))
        if params.min_confidence is not None:
            where.append(EventTable.confidence >= params.min_confidence)
        if params.participant_entity_id:
            where.append(
                exists().where(
                    (EventParticipantTable.event_id == EventTable.id)
                    & (EventParticipantTable.entity_id == params.participant_entity_id)
                )
            )
        if params.location_id:
            where.append(
                exists().where(
                    (EventPlaceTable.event_id == EventTable.id) & (EventPlaceTable.location_id == params.location_id)
                )
            )
        return where
