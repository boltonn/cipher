from sqlalchemy import asc, delete, desc, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories.tag import PostgresTagRepository
from cipher.datastores.postgres.tables.entity import EntityTable, is_canonical_entity
from cipher.datastores.postgres.tables.event import EventTable
from cipher.datastores.postgres.tables.event_participant import EventParticipantTable
from cipher.datastores.postgres.tables.event_place import EventPlaceTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.datastores.postgres.utils import strip_null_bytes
from cipher.schemas._base.common import ModelTagType, SortOrder
from cipher.schemas.graph.event import (
    EVENT_FILE_TAG,
    Event,
    EventCreate,
    EventMonthCount,
    EventParticipantOption,
    EventPlaceOption,
    EventSearchParameters,
    EventSortField,
    EventUpdate,
    EventWithLinks,
    PaginatedEventsResponse,
)
from cipher.schemas.graph.event_participant import EventParticipant, EventParticipantCreate
from cipher.schemas.graph.event_place import EventPlace, EventPlaceCreate
from cipher.schemas.interaction.tag import TagSource, TagTargetType

_SORT_COLUMN = {
    EventSortField.DATE_START: EventTable.date_start,
    EventSortField.DATE_CREATED: EventTable.date_created,
    EventSortField.DATE_UPDATED: EventTable.date_updated,
    EventSortField.TITLE: func.lower(EventTable.title),
    EventSortField.EVENT_TYPE: EventTable.event_type,
    EventSortField.STATUS: EventTable.status,
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

    async def add_event(self, payload: EventCreate, *, source: TagSource | None = None) -> Event:
        """Insert a single event row; any `tags` are recorded as `source`'s decision (required with tags)."""
        row = EventTable(**strip_null_bytes(payload.model_dump(by_alias=False, exclude={"tags"})))
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        if payload.tags:
            if source is None:
                raise ValueError("Event tags need a source (who or what tagged them)")
            await PostgresTagRepository(self.session).set_tags(
                target_type=TagTargetType.EVENT, target_id=row.id, tags=payload.tags, source=source
            )
            return await self.get_event(row.id)
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
            .order_by(order, EventTable.date_start.asc(), EventTable.id)
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
        self, *, dataset_ids: list[str] | None = None, q: str | None = None, limit: int = 50
    ) -> list[str]:
        """Distinct raw source labels (`event.categories`, i.e. iCalendar CATEGORIES) in use.

        Powers the events filter bar's label combobox so an analyst picks from
        what actually exists rather than guessing. Substring-filtered by `q`.
        """
        elem = func.jsonb_array_elements_text(EventTable.categories).label("value")
        inner = select(elem).select_from(EventTable)
        if dataset_ids:
            inner = inner.where(EventTable.dataset_id.in_(dataset_ids))
        sub = inner.subquery()

        stmt = select(sub.c.value).distinct().order_by(sub.c.value).limit(limit)
        if q:
            stmt = stmt.where(sub.c.value.ilike(f"%{q}%"))
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_tag_values(
        self, *, dataset_ids: list[str] | None = None, q: str | None = None, limit: int = 50
    ) -> list[str]:
        """Distinct analyst `tags` in use, most-used first.

        Powers tag-input suggestions so an analyst reuses an existing tag
        instead of typing a near-duplicate. Substring-filtered by `q`.
        """
        elem = func.jsonb_array_elements_text(EventTable.tags).label("value")
        inner = select(elem).select_from(EventTable)
        if dataset_ids:
            inner = inner.where(EventTable.dataset_id.in_(dataset_ids))
        sub = inner.subquery()

        stmt = select(sub.c.value).group_by(sub.c.value)
        if q:
            stmt = stmt.where(sub.c.value.ilike(f"%{q}%"))
        stmt = stmt.order_by(func.count().desc(), sub.c.value.asc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_participant_options(
        self, *, dataset_ids: list[str] | None = None, q: str | None = None, limit: int = 50
    ) -> list[EventParticipantOption]:
        """Who appears on events -- linked entities (incl. provisional) and unresolved raw names -- by event count.

        Unresolved names group case-insensitively, shown in their most common spelling.
        """
        event_count = func.count(func.distinct(EventParticipantTable.event_id))
        scope = [EventTable.dataset_id.in_(dataset_ids)] if dataset_ids else []

        linked = (
            select(
                EntityTable.id,
                EntityTable.person_id,
                EntityTable.display_name,
                EntityTable.entity_type,
                is_canonical_entity(),
                event_count,
            )
            .select_from(EventParticipantTable)
            .join(EventTable, EventTable.id == EventParticipantTable.event_id)
            .join(EntityTable, EntityTable.id == EventParticipantTable.entity_id)
            .where(*scope)
            .group_by(EntityTable.id)
            .order_by(event_count.desc())
            .limit(limit)
        )
        raw_name = func.coalesce(EventParticipantTable.raw_name, EventParticipantTable.raw_email)
        unresolved = (
            select(func.mode().within_group(raw_name), event_count)
            .join(EventTable, EventTable.id == EventParticipantTable.event_id)
            .where(*scope, EventParticipantTable.entity_id.is_(None), raw_name.is_not(None))
            .group_by(func.lower(func.trim(raw_name)))
            .order_by(event_count.desc())
            .limit(limit)
        )
        if q:
            linked = linked.where(EntityTable.display_name.ilike(f"%{q}%"))
            unresolved = unresolved.where(raw_name.ilike(f"%{q}%"))

        options = [
            EventParticipantOption(
                entity_id=entity_id,
                person_id=person_id,
                name=name,
                entity_type=entity_type,
                is_provisional=not canonical,
                event_count=count,
            )
            for entity_id, person_id, name, entity_type, canonical, count in (await self.session.execute(linked)).all()
        ] + [
            EventParticipantOption(name=name, event_count=count)
            for name, count in (await self.session.execute(unresolved)).all()
        ]
        return sorted(options, key=lambda o: (-o.event_count, o.name.lower()))[:limit]

    async def list_place_options(
        self, *, dataset_ids: list[str] | None = None, q: str | None = None, limit: int = 50
    ) -> list[EventPlaceOption]:
        """Where events happen -- linked locations and unresolved raw place text -- by event count."""
        event_count = func.count(func.distinct(EventPlaceTable.event_id))
        scope = [EventTable.dataset_id.in_(dataset_ids)] if dataset_ids else []
        location_name = func.coalesce(LocationTable.name, LocationTable.address, LocationTable.city)

        linked = (
            select(LocationTable.id, location_name, event_count)
            .select_from(EventPlaceTable)
            .join(EventTable, EventTable.id == EventPlaceTable.event_id)
            .join(LocationTable, LocationTable.id == EventPlaceTable.location_id)
            .where(*scope, location_name.is_not(None))
            .group_by(LocationTable.id)
            .order_by(event_count.desc())
            .limit(limit)
        )
        unresolved = (
            select(func.mode().within_group(EventPlaceTable.raw_text), event_count)
            .join(EventTable, EventTable.id == EventPlaceTable.event_id)
            .where(*scope, EventPlaceTable.location_id.is_(None), EventPlaceTable.raw_text.is_not(None))
            .group_by(func.lower(func.trim(EventPlaceTable.raw_text)))
            .order_by(event_count.desc())
            .limit(limit)
        )
        if q:
            linked = linked.where(location_name.ilike(f"%{q}%"))
            unresolved = unresolved.where(EventPlaceTable.raw_text.ilike(f"%{q}%"))

        options = [
            EventPlaceOption(location_id=location_id, name=name, event_count=count)
            for location_id, name, count in (await self.session.execute(linked)).all()
        ] + [
            EventPlaceOption(name=name, event_count=count)
            for name, count in (await self.session.execute(unresolved)).all()
        ]
        return sorted(options, key=lambda o: (-o.event_count, o.name.lower()))[:limit]

    async def calendar_events(self, params: EventSearchParameters) -> list[Event]:
        """Every matching event in the `date_from`..`date_to` window, ascending (no paging, capped)."""
        stmt = select(EventTable).where(*self._filters(params)).order_by(EventTable.date_start.asc()).limit(2000)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [Event.model_validate(r) for r in rows]

    async def month_counts(self, *, dataset_ids: list[str] | None = None) -> list[EventMonthCount]:
        """Event counts per `date_start` month (UTC), ascending."""
        month = func.to_char(func.timezone("UTC", EventTable.date_start), "YYYY-MM")
        stmt = select(month, func.count())
        if dataset_ids:
            stmt = stmt.where(EventTable.dataset_id.in_(dataset_ids))
        rows = (await self.session.execute(stmt.group_by(month).order_by(month))).all()
        return [EventMonthCount(month=m, count=c) for m, c in rows]

    async def update_event(self, event_id: str, data: EventUpdate, *, user_id: str) -> Event | None:
        """Patch an event row; a `tags` list is recorded as `user_id`'s edit."""
        patch = strip_null_bytes(data.model_dump(exclude_unset=True, exclude={"tags"}, by_alias=False))
        if patch:
            await self.session.execute(update(EventTable).where(EventTable.id == event_id).values(**patch))
            await self.session.commit()
        if data.tags is not None and await self.get_event(event_id) is not None:
            await PostgresTagRepository(self.session).set_tags(
                target_type=TagTargetType.EVENT, target_id=event_id, tags=data.tags, source=TagSource.user(user_id)
            )
        return await self.get_event(event_id)

    async def delete_event(self, event_id: str, *, user_id: str) -> bool:
        """Delete an event row (participant/place rows cascade)."""
        return bool(await self.delete_events([event_id], user_id=user_id))

    async def delete_events(self, event_ids: list[str], *, user_id: str) -> int:
        """Mark events invalid: delete them (participant/place rows cascade). Returns rows deleted.

        A source file tagged `event` that is left with no events gets a negative `event`
        label from `user_id` -- the analyst's verdict, newer than the extractor's, wins.
        """
        deleted = await self.session.execute(
            delete(EventTable).where(EventTable.id.in_(event_ids)).returning(EventTable.id, EventTable.file_id)
        )
        rows = deleted.tuples().all()
        tag_repo = PostgresTagRepository(self.session)
        await tag_repo.delete_for_targets(
            target_type=TagTargetType.EVENT, target_ids=[event_id for event_id, _ in rows]
        )
        emptied = await self.session.execute(
            select(FileTable.sha256)
            .where(
                FileTable.id.in_({file_id for _, file_id in rows if file_id}),
                FileTable.tags.has_key(EVENT_FILE_TAG),
                ~select(EventTable.id).where(EventTable.file_id == FileTable.id).exists(),
            )
            .distinct()
        )
        await tag_repo.label(
            target_type=TagTargetType.CONTENT,
            target_ids=list(emptied.scalars().all()),
            tag=EVENT_FILE_TAG,
            label=ModelTagType.NEGATIVE,
            source=TagSource.user(user_id),
        )
        await self.session.commit()
        return len(rows)

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
        if params.dataset_ids:
            where.append(EventTable.dataset_id.in_(params.dataset_ids))
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
        if params.participant_entity_ids or params.participant_names:
            entity_name = select(EntityTable.display_name).where(EntityTable.id == EventParticipantTable.entity_id)
            matches = [EventParticipantTable.entity_id.in_(params.participant_entity_ids or [])] + [
                or_(
                    EventParticipantTable.raw_name.ilike(f"%{name}%"),
                    EventParticipantTable.raw_email.ilike(f"%{name}%"),
                    entity_name.scalar_subquery().ilike(f"%{name}%"),
                )
                for name in params.participant_names or []
            ]
            where.append(exists().where(EventParticipantTable.event_id == EventTable.id, or_(*matches)))
        if params.location_ids or params.place_names:
            location_name = select(LocationTable.name).where(LocationTable.id == EventPlaceTable.location_id)
            matches = [EventPlaceTable.location_id.in_(params.location_ids or [])] + [
                or_(EventPlaceTable.raw_text.ilike(f"%{name}%"), location_name.scalar_subquery().ilike(f"%{name}%"))
                for name in params.place_names or []
            ]
            where.append(exists().where(EventPlaceTable.event_id == EventTable.id, or_(*matches)))
        return where
