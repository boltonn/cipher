"""Name-level suggestions: signature / membership relationships whose names are not both settled yet.

A signature says "Toby Jordan-Smith works at Lambda Labs Inc." long before either name
is resolved to an entity -- most names wait in the Resolve queue. Rather than hide the
relationship until then, it is offered per *name pair*, with what each name might be:
the entity it already resolved to, the resolver's best guess, or the person who owns
the sending address. Accepting settles both names (attach the name group, create the
entity if asked, confirm it) and adds the edge in one step; dismissing leaves the names
in the Resolve queue and never offers the pair again.
"""

from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository
from cipher.datastores.postgres.repositories.entity_relationship import PostgresGraphRepository
from cipher.datastores.postgres.repositories.mention import PostgresMentionRepository
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.mention_relationship import MentionRelationshipTable
from cipher.schemas.graph.entity import EntityCreate, EntitySummary
from cipher.schemas.graph.ontology import EntitySource, EntityType, RelationshipSource, RelationshipType
from cipher.schemas.graph.organization import (
    NameSuggestion,
    NameSuggestionAccept,
    NameSuggestionAccepted,
    NameSuggestionSide,
)

_EXTRACTOR = "signature"
# producers of the person -> organization edges offered here: signatures (employed_by, part_of)
# and the events pass's memberships (member_of)
_EXTRACTORS = ("signature", "membership")
_PERSON_FIELD = "signature.person"

# signature relations with at least one unsettled end, not yet reviewed
_RELATIONS = text(
    """
    SELECT mr.id, mr.dataset_id, mr.relationship_type, mr.extractor, mr.attributes->>'role' AS role,
           s.entity_type AS s_type, s.normalized_value AS s_nv, s.surface_text AS s_text, s.entity_id AS s_eid,
           s.file_id AS file_id,
           t.entity_type AS t_type, t.normalized_value AS t_nv, t.surface_text AS t_text, t.entity_id AS t_eid
    FROM mention_relationship mr
    JOIN mention s ON s.id = mr.src_mention_id
    JOIN mention t ON t.id = mr.dst_mention_id
    WHERE mr.extractor = ANY(CAST(:extractors AS text[])) AND mr.date_reviewed IS NULL
      AND mr.relationship_type IN ('EMPLOYED_BY', 'MEMBER_OF', 'PART_OF')
      AND (s.entity_id IS NULL OR t.entity_id IS NULL)
      AND (CAST(:dataset_ids AS text[]) IS NULL OR mr.dataset_id = ANY(CAST(:dataset_ids AS text[])))
    """
)
# the resolver's top pending guess per name group
_GUESSES = text(
    """
    SELECT DISTINCT ON (em.dataset_id, em.normalized_value, e.entity_type)
           em.dataset_id, em.normalized_value, e.entity_type, em.similarity_score,
           e.id, e.display_name, e.is_verified
    FROM entity_match em JOIN entity e ON e.id = em.entity_id
    WHERE em.mention_id IS NULL AND em.provisional_entity_id IS NULL AND em.status = 'PENDING'
      AND em.normalized_value = ANY(CAST(:names AS text[]))
    ORDER BY em.dataset_id, em.normalized_value, e.entity_type, em.similarity_score DESC
    """
)
# who owns the sending address the signature was confirmed against (has_selector)
_OWNERS = text(
    """
    SELECT m.file_id, m.surface_text AS address, p.id, p.display_name, p.is_verified
    FROM mention m
    JOIN entity_relationship r ON r.dst_entity_id = m.entity_id AND r.relationship_type = 'HAS_SELECTOR'
    JOIN entity p ON p.id = r.src_entity_id AND p.entity_type = 'PERSON'
    WHERE m.extractor = :extractor AND m.field_path = :person_field AND m.selector_type = 'EMAIL'
      AND m.mentioned_type = 'STRUCTURED_FIELD' AND m.file_id = ANY(CAST(:file_ids AS text[]))
    """
)
_UNRESOLVED_COUNTS = text(
    """
    SELECT dataset_id, normalized_value, count(*) FROM mention
    WHERE entity_id IS NULL AND entity_attribute = 'name' AND normalized_value = ANY(CAST(:names AS text[]))
    GROUP BY 1, 2
    """
)
_ENTITIES = text(
    """
    SELECT id, entity_type, display_name, is_verified,
           (person_id IS NULL AND location_id IS NULL AND source <> 'MANUAL' AND entity_type <> 'SELECTOR')
             AS is_provisional
    FROM entity WHERE id = ANY(CAST(:ids AS text[]))
    """
)
# close the name group's pending review rows now that the reviewer settled it
_CLOSE_GROUP = text(
    """
    UPDATE entity_match SET status = CASE WHEN entity_id = :entity_id THEN 'CONFIRMED' ELSE 'REJECTED' END,
           reviewed_by = :reviewed_by, reviewed_at = now(), decision_source = 'analyst'
    WHERE dataset_id = :dataset_id AND mention_id IS NULL AND normalized_value = :normalized_value
      AND status = 'PENDING'
    """
)


def _summary(entity_id: str, entity_type: str, display_name: str, is_verified: bool) -> EntitySummary:
    """From a raw row: enums come back from SQL by member name (`PERSON`)."""
    return EntitySummary(
        id=entity_id, entity_type=EntityType[entity_type], display_name=display_name, is_verified=is_verified
    )


class PostgresNameSuggestionRepository:
    """Name-level signature suggestions: list, accept, dismiss."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_suggestions(
        self, *, unit_ids: set[str] | None = None, dataset_ids: list[str] | None = None
    ) -> list[NameSuggestion]:
        """Suggestions whose organization end is (or is guessed to be) one of `unit_ids`.

        `unit_ids=None` returns the ones whose organization end has no entity and no guess at all --
        organizations that so far exist only as a name in signatures. A name proposed as a sub-unit
        of an in-scope unit brings its own people along.
        """
        rows = (
            (await self.session.execute(_RELATIONS, {"extractors": list(_EXTRACTORS), "dataset_ids": dataset_ids}))
            .mappings()
            .all()
        )
        if not rows:
            return []
        names = sorted({r["s_nv"] for r in rows} | {r["t_nv"] for r in rows})
        guesses = {
            (g.dataset_id, g.normalized_value, g.entity_type): (
                _summary(g.id, g.entity_type, g.display_name, g.is_verified),
                g.similarity_score,
            )
            for g in (await self.session.execute(_GUESSES, {"names": names})).all()
        }
        unresolved = {
            (d, nv): n for d, nv, n in (await self.session.execute(_UNRESOLVED_COUNTS, {"names": names})).all()
        }
        owners = {
            o.file_id: (_summary(o.id, "PERSON", o.display_name, o.is_verified), o.address)
            for o in (
                await self.session.execute(
                    _OWNERS,
                    {
                        "extractor": _EXTRACTOR,
                        "person_field": _PERSON_FIELD,
                        "file_ids": sorted({r["file_id"] for r in rows if r["file_id"]}),
                    },
                )
            ).all()
        }
        resolved_ids = sorted({r["s_eid"] for r in rows if r["s_eid"]} | {r["t_eid"] for r in rows if r["t_eid"]})
        entities = {
            e.id: (_summary(e.id, e.entity_type, e.display_name, e.is_verified), e.is_provisional)
            for e in (await self.session.execute(_ENTITIES, {"ids": resolved_ids})).all()
        }

        groups: dict[tuple, list] = defaultdict(list)
        for r in rows:
            groups[
                (
                    r["dataset_id"],
                    r["extractor"],
                    r["relationship_type"],
                    r["s_type"],
                    r["s_nv"],
                    r["t_type"],
                    r["t_nv"],
                )
            ].append(r)

        def side(dataset_id, entity_type, nv, members, prefix) -> NameSuggestionSide:
            entity_ids = Counter(m[f"{prefix}_eid"] for m in members if m[f"{prefix}_eid"])
            entity, provisional = (
                entities.get(entity_ids.most_common(1)[0][0], (None, False)) if entity_ids else (None, False)
            )
            guess = guesses.get((dataset_id, nv, entity_type)) if entity is None else None
            owner = None
            if prefix == "s" and entity is None:
                owned = Counter(owners[m["file_id"]] for m in members if m["file_id"] in owners)
                owner = owned.most_common(1)[0][0] if owned else None
            return NameSuggestionSide(
                name=Counter(m[f"{prefix}_text"] for m in members).most_common(1)[0][0],
                normalized_value=nv,
                entity_type=EntityType[entity_type],
                entity=entity,
                entity_is_provisional=provisional,
                guess=guess[0] if guess else None,
                guess_score=guess[1] if guess else None,
                owner=owner[0] if owner else None,
                owner_address=owner[1] if owner else None,
                unresolved_mentions=unresolved.get((dataset_id, nv), 0),
            )

        suggestions = []
        for (dataset_id, extractor, rel_type, s_type, s_nv, t_type, t_nv), members in groups.items():
            roles = Counter(m["role"] for m in members if m["role"])
            suggestions.append(
                NameSuggestion(
                    dataset_id=dataset_id,
                    extractor=extractor,
                    relationship_type=RelationshipType[rel_type],
                    source=side(dataset_id, s_type, s_nv, members, "s"),
                    target=side(dataset_id, t_type, t_nv, members, "t"),
                    role=roles.most_common(1)[0][0] if roles else None,
                    sightings=len(members),
                    mention_relationship_ids=[m["id"] for m in members],
                )
            )

        def org_id(s: NameSuggestionSide) -> str | None:
            pick = s.entity or s.guess
            return pick.id if pick else None

        if unit_ids is None:
            return sorted(
                (
                    s
                    for s in suggestions
                    if org_id(s.target) is None and s.relationship_type != RelationshipType.PART_OF
                ),
                key=lambda s: (s.target.name.casefold(), -s.sightings),
            )
        # a name proposed as a sub-unit of an in-scope unit brings its people along
        sub_unit_names = {
            (s.dataset_id, s.source.normalized_value)
            for s in suggestions
            if s.relationship_type == RelationshipType.PART_OF and org_id(s.target) in unit_ids
        }
        return sorted(
            (
                s
                for s in suggestions
                if org_id(s.target) in unit_ids or (s.dataset_id, s.target.normalized_value) in sub_unit_names
            ),
            key=lambda s: (s.relationship_type != RelationshipType.PART_OF, -s.sightings),
        )

    async def accept(self, decision: NameSuggestionAccept, *, reviewed_by: str | None) -> NameSuggestionAccepted:
        """Settle both names (attach, create if asked, confirm), add the edge, and retire the suggestion."""
        entities = PostgresEntityRepository(session=self.session)
        mentions = PostgresMentionRepository(session=self.session)
        created: list[str] = []
        settled: list[str] = []
        for choice in (decision.source, decision.target):
            entity_id = choice.entity_id
            if entity_id is None:
                entity = await entities.create_entity(
                    EntityCreate(
                        dataset_id=decision.dataset_id,
                        entity_type=choice.entity_type,
                        display_name=choice.display_name.strip(),
                        source=EntitySource.EXTRACTION,
                    )
                )
                entity_id = entity.id
                created.append(entity_id)
            await mentions.attach_names(
                dataset_id=decision.dataset_id, normalized_value=choice.normalized_value, entity_id=entity_id
            )
            await entities.promote_entity(entity_id, reviewed_by=reviewed_by)
            await self.session.execute(
                _CLOSE_GROUP,
                {
                    "entity_id": entity_id,
                    "reviewed_by": reviewed_by,
                    "dataset_id": decision.dataset_id,
                    "normalized_value": choice.normalized_value,
                },
            )
            settled.append(entity_id)
        source_id, target_id = settled

        if decision.relationship_type == RelationshipType.PART_OF:
            await entities.set_organization_parent(source_id, target_id)
        else:
            insert = pg_insert(EntityRelationshipTable).values(
                dataset_id=decision.dataset_id,
                src_entity_id=source_id,
                dst_entity_id=target_id,
                relationship_type=decision.relationship_type,
                directed=True,
                source=RelationshipSource.EXTRACTION,
                attributes={"role": decision.role} if decision.role else {},
            )
            await self.session.execute(
                insert.on_conflict_do_update(
                    constraint="uq_entity_relationship_triple",
                    set_={"attributes": EntityRelationshipTable.attributes.op("||")(insert.excluded.attributes)},
                )
            )
        await self._mark_reviewed(decision.mention_relationship_ids)
        await PostgresGraphRepository(session=self.session).link_header_selectors(decision.dataset_id)
        return NameSuggestionAccepted(
            source_entity_id=source_id, target_entity_id=target_id, created_entity_ids=created
        )

    async def dismiss(self, mention_relationship_ids: list[str]) -> int:
        """Never offer these again; the names themselves stay in the Resolve queue."""
        return await self._mark_reviewed(mention_relationship_ids)

    async def _mark_reviewed(self, ids: list[str]) -> int:
        result = await self.session.execute(
            update(MentionRelationshipTable)
            .where(MentionRelationshipTable.id.in_(ids), MentionRelationshipTable.extractor.in_(_EXTRACTORS))
            .values(date_reviewed=datetime.now(UTC))
        )
        await self.session.commit()
        return result.rowcount or 0
