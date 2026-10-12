from sqlalchemy import asc, delete, desc, exists, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories._merge import repoint_entity_references
from cipher.datastores.postgres.repositories.tag import PostgresTagRepository
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.face_match import FaceMatchTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.schemas._base.common import SortOrder
from cipher.schemas.identity.face_match import FaceMatchStatus
from cipher.schemas.identity.person import (
    PaginatedPersonSimilarityResponse,
    PaginatedPersonsResponse,
    Person,
    PersonCreate,
    PersonMergeResult,
    PersonMergeSuggestion,
    PersonSearchParameters,
    PersonSimilarityResult,
    PersonSimilaritySearchRequest,
    PersonSortField,
    PersonSource,
    PersonUpdate,
)
from cipher.schemas.interaction.tag import TagSource, TagTargetType


class PostgresPersonRepository:
    """Postgres datastore implementation for persons using SQLAlchemy."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the person table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(PersonTable.metadata.create_all)

    async def get_count(self) -> int:
        """Get total count of persons."""
        result = await self.session.execute(select(func.count(PersonTable.id)))
        return result.scalar_one()

    async def add_person(self, person: PersonCreate, *, source: TagSource | None = None) -> Person:
        """Create a new person; its `tags` are recorded as `source`'s on the person's entity (same id).

        `person.tags` mirrors the entity's tags once `upsert_person_entity` creates the bridge.
        """
        person_table = PersonTable(**person.model_dump(exclude={"tags"}))
        self.session.add(person_table)
        await self.session.commit()
        await self.session.refresh(person_table)
        created = Person.model_validate(person_table)
        if person.tags:
            if source is None:
                raise ValueError("Person tags need a source (who or what tagged them)")
            await PostgresTagRepository(self.session).set_tags(
                target_type=TagTargetType.ENTITY, target_id=created.id, tags=person.tags, source=source
            )
        return created

    async def get_person_by_id(self, person_id: str) -> Person | None:
        """Retrieve a person by ID."""
        result = await self.session.execute(select(PersonTable).where(PersonTable.id == person_id))
        person_table = result.scalar_one_or_none()
        return Person.model_validate(person_table) if person_table else None

    async def update_person(self, person_id: str, data: PersonUpdate, *, user_id: str) -> Person | None:
        """Update a person by ID; a `tags` list is recorded as `user_id`'s edit on the person's entity."""
        if data.tags is not None:
            await PostgresTagRepository(self.session).set_tags(
                target_type=TagTargetType.ENTITY, target_id=person_id, tags=data.tags, source=TagSource.user(user_id)
            )
        update_dict = data.model_dump(exclude_unset=True, exclude={"tags"}, by_alias=False)
        stmt = update(PersonTable).where(PersonTable.id == person_id).values(**update_dict).returning(PersonTable)
        result = await self.session.execute(stmt)
        person_table = result.scalar_one_or_none()
        # Validate to the Pydantic model before commit() expires
        # person_table's attributes -- reading them afterward would trigger
        # a lazy load, which fails outside an awaited context (MissingGreenlet).
        person = Person.model_validate(person_table) if person_table else None
        await self.session.commit()
        return person

    async def delete_person(self, person_id: str) -> bool:
        """Delete a person by ID.

        Assigned faces are kept, just unlinked. Reviewed `face_match` decisions
        (confirmed / rejected) are kept too -- the person's id still groups the
        faces they were made about; only its pending matches go.
        """
        await self._release_faces([person_id])
        result = await self.session.execute(delete(PersonTable).where(PersonTable.id == person_id))
        await self.session.commit()
        return bool(result.rowcount)

    async def _release_faces(self, person_ids: list[str]) -> int:
        """Unlink the faces of persons about to be deleted and drop their pending matches. Returns faces unlinked."""
        faces = await self.session.execute(
            update(FaceTable)
            .where(FaceTable.person_id.in_(person_ids))
            .values(
                person_id=None,
                assignment_method=None,
                assignment_confidence=None,
                is_representative=False,
                is_primary=False,
            )
        )
        await self.session.execute(
            delete(FaceMatchTable).where(
                FaceMatchTable.person_id.in_(person_ids), FaceMatchTable.status == FaceMatchStatus.PENDING
            )
        )
        return faces.rowcount or 0

    async def merge_persons(self, *, target_id: str, source_id: str) -> PersonMergeResult:
        """Fold ``source_id`` into ``target_id`` and delete the source, atomically.

        Everything that points at the source person -- by its own id or by its
        shared-id `entity` bridge node -- is repointed onto the target:
        assigned `face` rows, pending `face_match` rows, `event_participant`
        links, `comment` threads (person and entity), name `mention` rows,
        `entity_relationship` edges (selectors, family, communication,
        co-occurrence...), and the `entity_relationship_candidate` /
        `entity_match` review queues. Colliding rows and self-referential
        edges are dropped rather than repointed. Moved faces lose their
        representative / primary flags (that curation was specific to the
        source record, and keeping it risks blowing the per-person cap or
        leaving two primaries). Scalar fields are unioned: the target keeps
        its own name / DOB / sex, only borrowing the source's where its own is
        empty, and the source's name and aliases are folded into the target's
        alias list.

        Both persons must exist and differ; raises ``ValueError`` otherwise.
        """
        if target_id == source_id:
            raise ValueError("cannot merge a person into itself")

        rows = await self.session.execute(select(PersonTable).where(PersonTable.id.in_([target_id, source_id])))
        by_id = {row.id: row for row in rows.scalars().all()}
        target, source = by_id.get(target_id), by_id.get(source_id)
        if target is None:
            raise ValueError(f"target person not found: {target_id}")
        if source is None:
            raise ValueError(f"source person not found: {source_id}")

        faces_moved = (
            await self.session.execute(
                update(FaceTable)
                .where(FaceTable.person_id == source_id)
                .values(person_id=target_id, is_representative=False, is_primary=False)
            )
        ).rowcount or 0

        # face_match: (face_id, person_id) is unique -- drop source rows that
        # would collide with an existing target row, then repoint the rest.
        await self.session.execute(
            delete(FaceMatchTable).where(
                FaceMatchTable.person_id == source_id,
                FaceMatchTable.face_id.in_(select(FaceMatchTable.face_id).where(FaceMatchTable.person_id == target_id)),
            )
        )
        matches_moved = (
            await self.session.execute(
                update(FaceMatchTable).where(FaceMatchTable.person_id == source_id).values(person_id=target_id)
            )
        ).rowcount or 0

        # Everything keyed on the source's id / shared-id entity bridge:
        # mentions, relationship edges + candidates, entity-match review rows,
        # event participations, comment threads.
        refs = await repoint_entity_references(self.session, source_id=source_id, target_id=target_id)

        merged_aliases = list(
            dict.fromkeys([*target.aliases, *source.aliases, *([source.name] if source.name else [])])
        )
        if target.name:
            merged_aliases = [a for a in merged_aliases if a != target.name]
        merged_notes = "\n\n".join(n for n in [target.notes, source.notes] if n) or None

        await self.session.execute(
            update(PersonTable)
            .where(PersonTable.id == target_id)
            .values(
                name=target.name or source.name,
                aliases=merged_aliases,
                notes=merged_notes,
                date_of_birth=target.date_of_birth or source.date_of_birth,
                sex=target.sex or source.sex,
            )
        )

        # Drop the source's shared-id entity bridge node, then the person.
        await self.session.execute(delete(EntityTable).where(EntityTable.id == source_id))
        await self.session.execute(delete(PersonTable).where(PersonTable.id == source_id))
        await self.session.commit()

        return PersonMergeResult(
            person_id=target_id,
            faces_moved=faces_moved,
            matches_moved=matches_moved,
            event_participants_moved=refs["event_participants"],
            comments_moved=refs["comments"],
            mentions_moved=refs["mentions"],
            relationships_moved=refs["relationships"],
            relationship_candidates_moved=refs["relationship_candidates"],
            entity_matches_moved=refs["entity_matches"],
        )

    async def purge_face_clustering(self, *, only_unverified: bool = True) -> dict[str, int]:
        """Delete auto-created face-clustering persons and unlink their faces.

        The undo for `cluster-faces`: for every `source = face_clustering`
        person (by default only those an analyst has not verified), clear the
        representative/primary flags and assignment on their faces, null the
        link, then delete the person. Returns `{persons, faces}` counts.
        """
        where = [PersonTable.source == PersonSource.FACE_CLUSTERING]
        if only_unverified:
            where.append(PersonTable.is_verified.is_(False))

        person_ids = list((await self.session.execute(select(PersonTable.id).where(*where))).scalars().all())
        if not person_ids:
            return {"persons": 0, "faces": 0}

        faces_unlinked = await self._release_faces(person_ids)
        # Drop the shared-id entity bridge nodes too (entity.id == person.id).
        await self.session.execute(delete(EntityTable).where(EntityTable.id.in_(person_ids)))
        await self.session.execute(delete(PersonTable).where(PersonTable.id.in_(person_ids)))
        await self.session.commit()
        return {"persons": len(person_ids), "faces": faces_unlinked}

    async def search_persons(self, request: PersonSearchParameters) -> PaginatedPersonsResponse:
        """Query persons with filtering, pagination, and sorting."""
        where_clause = []
        if request.query:
            pattern = f"%{request.query}%"
            tag_matches = func.jsonb_array_elements_text(PersonTable.tags).table_valued("value")
            where_clause.append(
                or_(
                    PersonTable.name.ilike(pattern),
                    exists(select(literal(1)).select_from(tag_matches).where(tag_matches.c.value.ilike(pattern))),
                )
            )
        if request.tags:
            where_clause.append(PersonTable.tags.overlap(request.tags))
        if request.is_verified is not None:
            where_clause.append(PersonTable.is_verified == request.is_verified)
        if request.source is not None:
            where_clause.append(PersonTable.source == request.source)
        if request.unnamed is True:
            where_clause.append(or_(PersonTable.name.is_(None), PersonTable.name == ""))
        elif request.unnamed is False:
            where_clause.append(PersonTable.name.is_not(None))

        count_stmt = select(func.count(PersonTable.id))
        if where_clause:
            count_stmt = count_stmt.where(*where_clause)
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar_one()

        is_named = func.coalesce(PersonTable.name, "") != ""
        if request.sort_by == PersonSortField.RELEVANCE:
            face_count = (
                select(func.count(FaceTable.id))
                .where(FaceTable.person_id == PersonTable.id, FaceTable.date_rejected.is_(None))
                .scalar_subquery()
            )
            order = [desc(PersonTable.is_verified), desc(is_named), desc(face_count), asc(PersonTable.name)]
        else:
            sort_column = {
                PersonSortField.NAME: PersonTable.name,
                PersonSortField.DATE_CREATED: PersonTable.date_created,
                PersonSortField.DATE_UPDATED: PersonTable.date_updated,
            }[request.sort_by]
            direction = desc if request.sort_order == SortOrder.DESC else asc
            # Unnamed face clusters sort after every named person, whichever way names run.
            order = [desc(is_named), direction(sort_column).nulls_last()]

        data_stmt = select(PersonTable)
        if where_clause:
            data_stmt = data_stmt.where(*where_clause)
        data_stmt = data_stmt.order_by(*order, PersonTable.id)
        data_stmt = data_stmt.offset((request.page - 1) * request.limit).limit(request.limit)

        result = await self.session.execute(data_stmt)
        persons = [Person.model_validate(p) for p in result.scalars().all()]

        return PaginatedPersonsResponse(
            total=total_count,
            page=request.page,
            limit=request.limit,
            data=persons,
        )

    async def search_similar_persons(self, request: PersonSimilaritySearchRequest) -> PaginatedPersonSimilarityResponse:
        """Find candidate persons by KNN search against representative faces.

        A person has no single centroid embedding: they match if the query
        embedding is close to *any* of their representative faces. For each
        person we keep only their single best-matching representative face
        (via DISTINCT ON), then rank persons by that best match.
        """
        distance_expr = FaceTable.embedding.max_inner_product(request.embedding)

        best_face_per_person = (
            select(
                FaceTable.person_id.label("person_id"),
                FaceTable.id.label("face_id"),
                (-distance_expr).label("similarity_score"),
            )
            .where(
                FaceTable.is_representative.is_(True),
                FaceTable.person_id.is_not(None),
                FaceTable.embedding.is_not(None),
            )
            .distinct(FaceTable.person_id)
            .order_by(FaceTable.person_id, asc(distance_expr))
            .subquery()
        )

        stmt = select(
            PersonTable,
            best_face_per_person.c.face_id,
            best_face_per_person.c.similarity_score,
        ).join(best_face_per_person, PersonTable.id == best_face_per_person.c.person_id)
        if request.min_similarity is not None:
            stmt = stmt.where(best_face_per_person.c.similarity_score >= request.min_similarity)
        stmt = stmt.order_by(desc(best_face_per_person.c.similarity_score)).limit(request.limit)

        result = await self.session.execute(stmt)
        rows = list(result.all())

        persons = [
            PersonSimilarityResult(
                **Person.model_validate(person).model_dump(),
                # Similarity is surfaced as a 0-1 "match strength", not a raw
                # signed cosine value: floor negative cosine similarity to 0,
                # and cap float32 rounding overshoot (e.g. 1.0000001192...) to 1.
                similarity_score=max(0.0, min(1.0, similarity_score)),
                matched_face_id=face_id,
            )
            for person, face_id, similarity_score in rows
        ]

        return PaginatedPersonSimilarityResponse(
            total=len(persons),
            page=1,
            limit=request.limit,
            data=persons,
        )

    async def suggest_merge_candidates(
        self, *, person_id: str, min_similarity: float = 0.5, limit: int = 8
    ) -> list[PersonMergeSuggestion]:
        """Other persons whose representative faces resemble this person's.

        For every *other* person, take the strongest match between any of their
        representative faces and any of this person's, keep those above
        ``min_similarity``, and return them most-similar first -- the "did you
        mean to merge these?" shortlist. Returns nothing if this person has no
        representative face with an embedding.
        """
        mine = (
            select(FaceTable.embedding.label("emb"))
            .where(
                FaceTable.person_id == person_id,
                FaceTable.is_representative.is_(True),
                FaceTable.embedding.is_not(None),
            )
            .subquery()
        )
        # pgvector max_inner_product is the negative inner product; for the
        # normalized face embeddings that is -cosine, so similarity = -distance
        # and the closest pairing is the smallest (most negative) value.
        distance = FaceTable.embedding.max_inner_product(mine.c.emb)
        best = (
            select(
                FaceTable.person_id.label("person_id"),
                func.min(distance).label("dist"),
            )
            .where(
                FaceTable.is_representative.is_(True),
                FaceTable.embedding.is_not(None),
                FaceTable.person_id.is_not(None),
                FaceTable.person_id != person_id,
            )
            .group_by(FaceTable.person_id)
            .subquery()
        )
        stmt = (
            select(PersonTable, best.c.dist)
            .join(best, PersonTable.id == best.c.person_id)
            .where(best.c.dist <= -min_similarity)
            .order_by(asc(best.c.dist))
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            PersonMergeSuggestion(
                **Person.model_validate(person).model_dump(),
                similarity_score=max(0.0, min(1.0, -float(dist))),
            )
            for person, dist in rows
        ]
