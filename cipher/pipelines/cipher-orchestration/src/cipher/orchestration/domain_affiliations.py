"""Email-domain affiliations: "sends from @baltlog.ru, and baltlog.ru people sign as ООО «Балтийская Логистика»".

A company domain is evidence of employment, but only once the dataset itself says
which organization the domain belongs to. That comes from signatures: when the
people who sign from a domain overwhelmingly name one organization, the domain
*is* that organization's. Every other resolved sender from the domain -- someone
whose own signature was never read (short replies, mobile mail) -- is then
suggested as `employed_by` that organization.

The rule, kept deliberately small so a reviewer can follow it:

1. **Map domain -> organization** from signatures: the company (broadest unit) each
   signature names, grouped by the sender address's domain. A domain maps when one
   organization has at least `min_signatures` of its signatures and at least
   `min_share` of all of them. Freemail domains never map.
2. **Suggest** each header sender from a mapped domain -- the person their header name
   resolved to, or who owns the sending address -- with no employment edge or suggestion
   for that organization yet. Senders not resolved to a person yet are counted and
   skipped; they are picked up on the next `resolve-entities` after review.

Each suggestion stores an `explanation` with the numbers behind it (domain, the
sender's addresses and email count, signatures for the organization vs. other
organizations, and a few colleagues who sign that way), which the organization page
renders as a sentence. Re-runnable: the candidate triple constraint drops repeats,
including suggestions a reviewer already rejected.
"""

from collections import defaultdict
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cipher.datastores.postgres.tables.entity_relationship_candidate import EntityRelationshipCandidateTable
from cipher.names.address import FREEMAIL_LABELS
from cipher.orchestration.extract_signatures import EXTRACTOR, PERSON_FIELD
from cipher.schemas.graph.entity_relationship import RelationshipCandidateMethod
from cipher.schemas.graph.ontology import RelationshipType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_MIN_SIGNATURES = 2
DEFAULT_MIN_SHARE = 0.75
_MAX_COLLEAGUES = 3
_COMPANY_FIELD = "signature.unit.0"

# (domain, organization) -> signatures, signing senders, colleague names
_SIGNATURES_BY_DOMAIN = text(
    """
    SELECT lower(split_part(et.metadata->'sent_from'->>'value', '@', 2)) AS domain,
           org.entity_id AS organization_id, e.display_name AS organization,
           count(DISTINCT org.file_id) AS signatures,
           array_agg(DISTINCT person.entity_id) FILTER (WHERE person.entity_id IS NOT NULL) AS signer_ids,
           array_agg(DISTINCT pe.display_name) FILTER (WHERE pe.display_name IS NOT NULL) AS signer_names
    FROM mention org
    JOIN extracted_text et ON et.id = org.mentioned_id
    JOIN entity e ON e.id = org.entity_id
    LEFT JOIN mention person ON person.file_id = org.file_id AND person.extractor = :extractor
         AND person.field_path = :person_field
    LEFT JOIN entity pe ON pe.id = person.entity_id
    WHERE org.dataset_id = :dataset_id AND org.extractor = :extractor AND org.field_path = :company_field
      AND org.entity_id IS NOT NULL
    GROUP BY 1, 2, 3
    """
)
# header senders -> address, emails sent; the person is the resolved header name, or whoever owns the
# sending address (`has_selector`). `person_id` is NULL while neither is resolved yet.
_SENDERS = text(
    """
    SELECT coalesce(p.id, owner.src_entity_id) AS person_id, lower(et.metadata->'sent_from'->>'value') AS address,
           count(DISTINCT et.file_id) AS emails
    FROM extracted_text et
    JOIN file f ON f.id = et.file_id AND f.dataset_id = :dataset_id
    LEFT JOIN mention n ON n.file_id = et.file_id AND n.field_path = 'header.from' AND n.selector_type IS NULL
    LEFT JOIN entity p ON p.id = n.entity_id AND p.entity_type = 'PERSON'
    LEFT JOIN mention addr ON addr.file_id = et.file_id AND addr.field_path = 'header.from' AND addr.selector_type = 'EMAIL'
    LEFT JOIN entity_relationship owner ON owner.dst_entity_id = addr.entity_id AND owner.relationship_type = 'HAS_SELECTOR'
    LEFT JOIN entity oe ON oe.id = owner.src_entity_id AND oe.entity_type = 'PERSON'
    WHERE et.metadata->'sent_from'->>'value' IS NOT NULL AND (owner.src_entity_id IS NULL OR oe.id IS NOT NULL)
    GROUP BY 1, 2
    """
)
# people already tied to an organization (edge or any-status suggestion) -- never re-proposed
_ALREADY_TIED = text(
    """
    SELECT src_entity_id, dst_entity_id FROM entity_relationship
    WHERE relationship_type IN ('EMPLOYED_BY', 'MEMBER_OF')
    UNION
    SELECT src_entity_id, dst_entity_id FROM entity_relationship_candidate
    WHERE dataset_id = :dataset_id AND relationship_type IN ('EMPLOYED_BY', 'MEMBER_OF')
    """
)


def _is_freemail(domain: str) -> bool:
    return not domain or domain.split(".")[0] in FREEMAIL_LABELS


def map_domains(rows: list[dict], *, min_signatures: int, min_share: float) -> dict[str, dict]:
    """`domain -> {organization_id, organization, signatures, total, colleagues, others}` for clear-cut domains."""
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not _is_freemail(row["domain"]):
            by_domain[row["domain"]].append(row)
    mapped = {}
    for domain, orgs in by_domain.items():
        orgs.sort(key=lambda r: r["signatures"], reverse=True)
        best, total = orgs[0], sum(r["signatures"] for r in orgs)
        if best["signatures"] >= min_signatures and best["signatures"] / total >= min_share:
            mapped[domain] = {
                "organization_id": best["organization_id"],
                "organization": best["organization"],
                "signatures": best["signatures"],
                "total": total,
                "signer_ids": set(best["signer_ids"] or []),
                "colleagues": sorted(best["signer_names"] or [])[:_MAX_COLLEAGUES],
                "others": [{"name": r["organization"], "signatures": r["signatures"]} for r in orgs[1:]],
            }
    return mapped


async def propose_domain_affiliations(
    session: "AsyncSession",
    dataset_id: str,
    *,
    min_signatures: int = DEFAULT_MIN_SIGNATURES,
    min_share: float = DEFAULT_MIN_SHARE,
) -> int:
    """Suggest `employed_by` for senders whose company domain signatures map to one organization. Returns rows offered."""
    params = {
        "dataset_id": dataset_id,
        "extractor": EXTRACTOR,
        "person_field": PERSON_FIELD,
        "company_field": _COMPANY_FIELD,
    }
    signature_rows = [dict(r._mapping) for r in (await session.execute(_SIGNATURES_BY_DOMAIN, params)).all()]
    domains = map_domains(signature_rows, min_signatures=min_signatures, min_share=min_share)
    if not domains:
        return 0
    tied = {(r[0], r[1]) for r in (await session.execute(_ALREADY_TIED, {"dataset_id": dataset_id})).all()}

    senders: dict[tuple[str, str], dict] = {}
    unresolved: set[str] = set()
    for person_id, address, emails in (await session.execute(_SENDERS, {"dataset_id": dataset_id})).all():
        domain = (address or "").rpartition("@")[2]
        mapping = domains.get(domain)
        if mapping is None:
            continue
        if person_id is None:
            unresolved.add(address)
            continue
        if person_id in mapping["signer_ids"] or (person_id, mapping["organization_id"]) in tied:
            continue
        entry = senders.setdefault((person_id, domain), {"addresses": [], "emails": 0})
        entry["addresses"].append(address)
        entry["emails"] += emails

    values = []
    for (person_id, domain), entry in senders.items():
        mapping = domains[domain]
        share = mapping["signatures"] / mapping["total"]
        values.append(
            {
                "dataset_id": dataset_id,
                "src_entity_id": person_id,
                "dst_entity_id": mapping["organization_id"],
                "relationship_type": RelationshipType.EMPLOYED_BY,
                "confidence": round(0.6 * share, 2),
                "method": RelationshipCandidateMethod.EMAIL_DOMAIN,
                "attributes": {},
                "explanation": {
                    "domain": domain,
                    "addresses": sorted(entry["addresses"]),
                    "emails_sent": entry["emails"],
                    "organization": mapping["organization"],
                    "organization_signatures": mapping["signatures"],
                    "domain_signatures": mapping["total"],
                    "colleagues": mapping["colleagues"],
                    "other_organizations": mapping["others"],
                },
            }
        )
    if values:
        await session.execute(
            pg_insert(EntityRelationshipCandidateTable)
            .values(values)
            .on_conflict_do_nothing(constraint="uq_entity_relationship_candidate_triple")
        )
        await session.commit()
    logger.info(
        f"Email-domain suggestions: {len(domains)} domains mapped, {len(values)} senders offered, "
        f"{len(unresolved)} senders skipped until their name or address resolves to a person"
    )
    return len(values)
