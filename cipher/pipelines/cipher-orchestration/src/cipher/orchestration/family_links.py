"""Family suggestions from patronymics: the name itself says who the father is.

`Ivan Petrovich Sidorov` is the son of a Pyotr Sidorov; `Anna Petrovna Sidorova` is his sister;
`Ahmed bin Khalid Al-Saud` is the son of a Khalid Al-Saud. When the dataset holds exactly one
person who fits, a `family_of` suggestion is filed for review (never applied on its own):

* **parent** -- the patronymic's stem is the person's given name (spelling or sound, any script)
  and the surnames agree (gendered East Slavic forms allowed: Sidorov / Sidorova);
* **sibling** -- two people share the patronymic stem and the surname.
"""

from collections import defaultdict
from itertools import combinations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories import PostgresRelationshipCandidateRepository
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.names import Culture, fold, parse_name, phonetic_key, to_latin
from cipher.schemas.graph.entity_relationship import RelationshipCandidateCreate, RelationshipCandidateMethod
from cipher.schemas.graph.ontology import EntityType, FamilyRole, RelationshipType

_SLAVIC_SUFFIXES = ("yovych", "inichna", "ovych", "ovich", "evich", "ovna", "evna", "ivna", "ichna", "ich")


def _latin(token: str) -> str:
    """Romanized, with ё's two spellings as one (`pyotr` / `petr`, `fyodor` / `fedor`)."""
    return fold(to_latin(token)).replace("yo", "e").replace("io", "e")


def _stem(token: str) -> str:
    """`sergey` / `sergei` -> `serge`, `nikolai` -> `nikola`: a given name without its soft ending."""
    return _latin(token).rstrip("yij")


def _patronymic_stem(patronymic: str, culture: Culture) -> str:
    """The father's given name inside a patronymic: `petrovich` -> `petr`, `khalid` -> `khalid`."""
    word = _latin(patronymic)
    if culture == Culture.EAST_SLAVIC:
        for suffix in _SLAVIC_SUFFIXES:
            if word.endswith(suffix) and len(word) > len(suffix) + 1:
                return word[: -len(suffix)].rstrip("yij")
    return word


def _same_given(stem: str, given: str) -> bool:
    other = _stem(given)
    return stem == other or (bool(phonetic_key(stem)) and phonetic_key(stem) == phonetic_key(other))


def _family_name(surname: str | None) -> str:
    """Gender-neutral surname: `sidorova` -> `sidorov`."""
    return _latin(surname).removesuffix("a") if surname else ""


async def _people(session: AsyncSession, dataset_id: str) -> list[tuple[str, str]]:
    """`(entity_id, name)` for the dataset's people, including verified people mentioned in it."""
    mentioned = select(MentionTable.entity_id).where(
        MentionTable.dataset_id == dataset_id, MentionTable.entity_id.is_not(None)
    )
    rows = await session.execute(
        select(EntityTable.id, EntityTable.display_name).where(
            EntityTable.entity_type == EntityType.PERSON,
            or_(EntityTable.dataset_id == dataset_id, EntityTable.id.in_(mentioned.scalar_subquery())),
        )
    )
    return [(r.id, r.display_name) for r in rows]


async def propose_family_from_patronymics(session: AsyncSession, dataset_id: str) -> dict[str, int]:
    """File parent / sibling `family_of` suggestions the patronymics support. Idempotent."""
    parsed = [(eid, name, parse_name(name)) for eid, name in await _people(session, dataset_id)]
    by_given: dict[str, list[tuple[str, str, str]]] = defaultdict(list)  # surname -> (id, name, given)
    children: list[tuple[str, str, str, str]] = []  # (id, name, stem, surname)
    for eid, name, p in parsed:
        surname = _family_name(p.primary_surname)
        if p.given_primary:
            by_given[surname].append((eid, name, p.given_primary))
        if p.patronymic and p.culture in (Culture.EAST_SLAVIC, Culture.ARABIC):
            children.append((eid, name, _patronymic_stem(p.patronymic, p.culture), surname))

    candidates: list[RelationshipCandidateCreate] = []
    for child_id, child_name, stem, surname in children:
        fathers = [
            (eid, name)
            for eid, name, given in by_given.get(surname, [])
            if eid != child_id and _same_given(stem, given)
        ]
        if len(fathers) == 1:
            father_id, father_name = fathers[0]
            candidates.append(
                RelationshipCandidateCreate(
                    dataset_id=dataset_id,
                    src_entity_id=father_id,
                    dst_entity_id=child_id,
                    relationship_type=RelationshipType.FAMILY_OF,
                    confidence=0.6,
                    method=RelationshipCandidateMethod.PATRONYMIC,
                    attributes={"role": FamilyRole.PARENT.value},
                    explanation={"reason": f"{child_name}'s patronymic names {father_name} as the father"},
                )
            )
    parents = len(candidates)

    by_lineage: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for child_id, child_name, stem, surname in children:
        if surname:
            by_lineage[(stem, surname)].append((child_id, child_name))
    for siblings in by_lineage.values():
        for (a_id, a_name), (b_id, b_name) in combinations(siblings, 2):
            candidates.append(
                RelationshipCandidateCreate(
                    dataset_id=dataset_id,
                    src_entity_id=a_id,
                    dst_entity_id=b_id,
                    relationship_type=RelationshipType.FAMILY_OF,
                    confidence=0.5,
                    method=RelationshipCandidateMethod.PATRONYMIC,
                    attributes={"role": FamilyRole.SIBLING.value},
                    explanation={"reason": f"{a_name} and {b_name} share a patronymic and a surname"},
                )
            )
    await PostgresRelationshipCandidateRepository(session=session).create_batch(candidates)
    return {"parent_suggestions": parents, "sibling_suggestions": len(candidates) - parents}
