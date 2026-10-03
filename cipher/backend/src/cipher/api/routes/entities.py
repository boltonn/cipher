from typing import Annotated

import phonenumbers
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pyselectors.normalize import normalize_selector

from cipher.api.deps.access import DatasetAccessDep
from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import (
    CommentDatastoreDep,
    EntityDatastoreDep,
    EntityMatchDatastoreDep,
    GraphDatastoreDep,
    MentionDatastoreDep,
    MentionRelationshipDatastoreDep,
    NameSuggestionDatastoreDep,
    RelationshipCandidateDatastoreDep,
)
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas._base.base import camelize_keys
from cipher.schemas._base.exceptions import EntityNotFoundError
from cipher.schemas.graph.entity import (
    Entity,
    EntityBatchRequest,
    EntityBreakdown,
    EntityCreate,
    EntityMergeRequest,
    EntityProfile,
    EntityRetypeRequest,
    EntitySearchParameters,
    EntitySearchResult,
    EntitySummary,
    EntityUpdate,
    PaginatedEntitiesResponse,
    PaginatedRelatedEntitiesResponse,
    RelatedEntitySearchParameters,
    RelatedEntitySort,
    SelectorMention,
    UnresolveNameRequest,
)
from cipher.schemas.graph.entity_match import (
    EntityMatch,
    EntityMatchBatchReview,
    EntityMatchReview,
    EntityMatchSearchParameters,
    EntityMergeSearchParameters,
    NameGroupDismissRequest,
    PaginatedEntityMatchesResponse,
    PaginatedEntityMatchGroupsResponse,
    PaginatedEntityMergeGroupsResponse,
)
from cipher.schemas.graph.entity_relationship import (
    EntityRelationship,
    EntityRelationshipCreate,
    GraphResponse,
    PaginatedRelationshipCandidatesResponse,
    PaginatedRelationshipsResponse,
    RelationshipCandidateMethod,
    RelationshipCandidateSearchParameters,
    RelationshipReview,
    RelationshipSearchParameters,
    TopConnectionsRequest,
    TopConnectionsResponse,
    TraversalDirection,
)
from cipher.schemas.graph.location import LocationUpdate
from cipher.schemas.graph.mention import (
    MentionedType,
    MentionProvenance,
    MentionSearchParameters,
    PaginatedMentionsResponse,
    ResolvedName,
)
from cipher.schemas.graph.mention_relationship import RelationshipEvidence
from cipher.schemas.graph.ontology import (
    RELATIONSHIP_ROLE_ENUM,
    EntityType,
    Ontology,
    RelationshipSource,
    RelationshipType,
    SelectorType,
    build_ontology,
    validate_relationship,
)
from cipher.schemas.graph.organization import (
    NameSuggestion,
    NameSuggestionAccept,
    NameSuggestionAccepted,
    NameSuggestionDismiss,
    OrganizationPeopleParameters,
    OrganizationStructure,
    OrganizationSuggestion,
    OrganizationTree,
    OrganizationUpdate,
    PaginatedOrganizationPeople,
)
from cipher.schemas.graph.selector import SelectorEvidence, SelectorLinkRequest, SelectorRegion, SelectorUpdate
from cipher.schemas.interaction.comment import CommentableType
from cipher.schemas.interaction.tag import TagSource

router = APIRouter(prefix="/entities", tags=["entities"])

_BY_ALIAS = {"response_model_by_alias": True}


def _normalize_selector_value(
    selector_type: SelectorType, raw: str, region_hint: str | None
) -> tuple[str | None, dict[str, str]]:
    """Canonicalize + validate a manually entered selector via the extraction pipeline.

    Returns ``(normalized_value | None, attributes)``; a None value means the
    input failed validation for its type (bad phone, IBAN checksum, ...).
    """
    if not raw.strip():
        return None, {}
    return normalize_selector(selector_type, raw, region_hint)


@router.post("", summary="Create an entity node", response_model=Entity, **_BY_ALIAS)
async def create_entity(entity: EntityCreate, user: CurrentUserDep, datastore: EntityDatastoreDep) -> Entity:
    """Manually create an entity node (detail rows are attached separately); its tags are yours."""
    return await datastore.create_entity(entity, source=TagSource.user(user.id))


@router.get("", summary="List/filter entities", response_model=PaginatedEntitiesResponse, **_BY_ALIAS)
async def list_entities(
    params: Annotated[EntitySearchParameters, Query()], datastore: EntityDatastoreDep
) -> PaginatedEntitiesResponse:
    """List entity nodes with fuzzy name match, type/tag/selector filters, and pagination."""
    return await datastore.list_entities(params)


@router.get(
    "/search",
    summary="Resolve a name or selector to entities",
    response_model=list[EntitySearchResult],
    **_BY_ALIAS,
)
async def search_entities(
    datastore: EntityDatastoreDep,
    dataset_id: Annotated[str, Query(alias="datasetId", description="Dataset to search within")],
    q: Annotated[str | None, Query(description="Name/alias to fuzzy-match")] = None,
    selector: Annotated[str | None, Query(description="Normalized selector value for exact match")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
) -> list[EntitySearchResult]:
    """Fast entity resolution: exact selector lookup and/or trigram name match."""
    results: list[EntitySearchResult] = []
    if selector:
        hit = await datastore.search_by_selector(dataset_id=dataset_id, normalized_value=selector)
        if hit:
            results.append(
                EntitySearchResult(
                    **EntitySummary.model_validate(hit.model_dump()).model_dump(),
                    match_reason="exact selector",
                    score=1.0,
                )
            )
    if q:
        results.extend(await datastore.search_by_name(dataset_id=dataset_id, query=q, limit=limit))
    return results[:limit]


@router.get(
    "/ontology", summary="Entity-layer registry (types, relationships, roles)", response_model=Ontology, **_BY_ALIAS
)
async def get_ontology() -> Ontology:
    """The relationship types, endpoint constraints, and role vocabularies the connection UI is built from."""
    return build_ontology()


@router.get(
    "/breakdown",
    summary="Entity / selector counts for a dataset",
    response_model=EntityBreakdown,
    **_BY_ALIAS,
)
async def get_entity_breakdown(
    datastore: EntityDatastoreDep,
    dataset_id: Annotated[
        str | None, Query(alias="datasetId", description="Scope to one dataset; omit for all")
    ] = None,
) -> EntityBreakdown:
    """Counts by entity type, selector type, and selector subtype -- feeds the dataset-view chart."""
    return await datastore.entity_breakdown(dataset_id=dataset_id)


@router.get(
    "/selector-regions",
    summary="Phone regions valid for selector normalization",
    response_model=list[SelectorRegion],
    **_BY_ALIAS,
)
async def list_selector_regions() -> list[SelectorRegion]:
    """ISO-3166-1 alpha-2 regions the phone normalizer accepts, each with its calling code.

    This is the exact set `region_hint` may take, so the frontend picker can't offer a
    value the backend would reject.
    """
    return sorted(
        (
            SelectorRegion(code=r, calling_code=phonenumbers.country_code_for_region(r))
            for r in phonenumbers.SUPPORTED_REGIONS
        ),
        key=lambda region: region.code,
    )


@router.get(
    "/matches", summary="Entity resolution review queue", response_model=PaginatedEntityMatchesResponse, **_BY_ALIAS
)
async def list_entity_matches(
    params: Annotated[EntityMatchSearchParameters, Query()], datastore: EntityMatchDatastoreDep
) -> PaginatedEntityMatchesResponse:
    """List candidate mention-to-entity resolutions awaiting review."""
    return await datastore.list_matches(params)


@router.get(
    "/matches/groups",
    summary="Grouped resolution review queue",
    response_model=PaginatedEntityMatchGroupsResponse,
    **_BY_ALIAS,
)
async def list_entity_match_groups(
    params: Annotated[EntityMatchSearchParameters, Query()], datastore: EntityMatchDatastoreDep
) -> PaginatedEntityMatchGroupsResponse:
    """One card per name group -- top candidate + alternatives -- for fast bulk triage."""
    return await datastore.list_match_groups(params)


@router.post("/matches/{match_id}/resolve", summary="Resolve an entity match", response_model_by_alias=True)
async def resolve_entity_match(
    match_id: str, review: EntityMatchReview, user: CurrentUserDep, datastore: EntityMatchDatastoreDep
):
    """Confirm or reject a candidate resolution."""
    resolved = await datastore.resolve_match(match_id, review.model_copy(update={"reviewed_by": user.id}))
    if resolved is None:
        raise EntityNotFoundError("EntityMatch", match_id)
    return resolved


@router.post("/matches/resolve-batch", summary="Bulk-resolve entity matches")
async def resolve_entity_matches_batch(
    body: EntityMatchBatchReview, user: CurrentUserDep, datastore: EntityMatchDatastoreDep
) -> dict:
    """Apply many confirm/reject decisions in one transaction -- the fast bulk-annotation path."""
    return camelize_keys(await datastore.resolve_matches_batch(reviewed_by=user.id, decisions=body.decisions))


@router.post("/matches/name-group/dismiss", summary="Dismiss a name group ('none of these')")
async def dismiss_entity_match_name_group(
    body: NameGroupDismissRequest, user: CurrentUserDep, datastore: EntityMatchDatastoreDep
) -> dict:
    """Reject every pending candidate for a name group -- a captured negative for calibration."""
    rejected = await datastore.dismiss_name_group(
        dataset_id=body.dataset_id,
        normalized_value=body.normalized_value,
        reviewed_by=user.id,
        review_note=body.review_note,
    )
    return {"rejected": rejected}


@router.get(
    "/merges",
    summary="Grouped entity-merge review queue",
    response_model=PaginatedEntityMergeGroupsResponse,
    **_BY_ALIAS,
)
async def list_entity_merge_groups(
    params: Annotated[EntityMergeSearchParameters, Query()], datastore: EntityMatchDatastoreDep
) -> PaginatedEntityMergeGroupsResponse:
    """One card per provisional entity -- the canonical entities it may duplicate.

    Populate with `cipher dedupe-entities`. Confirm a row via
    `POST /entities/matches/{id}/resolve` (it runs the merge).
    """
    return await datastore.list_merge_groups(params)


@router.get(
    "/relationship-candidates",
    summary="Relationship review queue",
    response_model=PaginatedRelationshipCandidatesResponse,
    **_BY_ALIAS,
)
async def list_relationship_candidates(
    params: Annotated[RelationshipCandidateSearchParameters, Query()],
    datastore: RelationshipCandidateDatastoreDep,
) -> PaginatedRelationshipCandidatesResponse:
    """List proposed edges awaiting review."""
    return await datastore.list_candidates(params)


@router.get(
    "/relationship-candidates/{candidate_id}/evidence",
    summary="Source passages behind a proposed edge",
    response_model=list[RelationshipEvidence],
    **_BY_ALIAS,
)
async def list_relationship_candidate_evidence(
    candidate_id: str,
    access: DatasetAccessDep,
    datastore: RelationshipCandidateDatastoreDep,
    relations: MentionRelationshipDatastoreDep,
) -> list[RelationshipEvidence]:
    """Each extractor sighting of the two entities together (e.g. every signature), with a text snippet."""
    candidate = await datastore.get_by_id(candidate_id)
    if candidate is None:
        raise EntityNotFoundError("RelationshipCandidate", candidate_id)
    if candidate.method == RelationshipCandidateMethod.EMAIL_DOMAIN:
        addresses = (candidate.explanation or {}).get("addresses", [])
        return await relations.emails_from(addresses, dataset_ids=access.scope(None))
    return await relations.evidence_for(
        src_entity_id=candidate.src_entity_id,
        dst_entity_id=candidate.dst_entity_id,
        relationship_type=candidate.relationship_type,
        dataset_ids=access.scope(None),
    )


@router.get(
    "/name-suggestions/unplaced",
    summary="Signature employers that are not an organization yet",
    response_model=list[NameSuggestion],
    **_BY_ALIAS,
)
async def list_unplaced_name_suggestions(
    access: DatasetAccessDep, names: NameSuggestionDatastoreDep
) -> list[NameSuggestion]:
    """People whose signatures name an organization with no entity and no resolver guess."""
    return await names.list_suggestions(dataset_ids=access.scope(None))


@router.get(
    "/name-suggestions/evidence",
    summary="Source passages behind a name-level suggestion",
    response_model=list[RelationshipEvidence],
    **_BY_ALIAS,
)
async def list_name_suggestion_evidence(
    ids: Annotated[list[str], Query(alias="ids")], access: DatasetAccessDep, relations: MentionRelationshipDatastoreDep
) -> list[RelationshipEvidence]:
    """Each signature behind it, both names marked."""
    return await relations.evidence_for(mention_relationship_ids=ids, dataset_ids=access.scope(None))


@router.post(
    "/name-suggestions/accept",
    summary="Accept a name-level suggestion",
    response_model=NameSuggestionAccepted,
    **_BY_ALIAS,
)
async def accept_name_suggestion(
    body: NameSuggestionAccept, user: CurrentUserDep, access: DatasetAccessDep, names: NameSuggestionDatastoreDep
) -> NameSuggestionAccepted:
    """Settle both names (attach the name group; create the entity if no id is given; confirm it) and add the edge."""
    access.require(body.dataset_id)
    try:
        return await names.accept(body, reviewed_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/name-suggestions/dismiss", summary="Dismiss a name-level suggestion")
async def dismiss_name_suggestion(body: NameSuggestionDismiss, names: NameSuggestionDatastoreDep) -> dict:
    """Never offer it again; the names stay in the Resolve queue."""
    return camelize_keys({"dismissed": await names.dismiss(body.mention_relationship_ids)})


@router.post(
    "/relationship-candidates/{candidate_id}/resolve",
    summary="Resolve a relationship candidate",
    response_model_by_alias=True,
)
async def resolve_relationship_candidate(
    candidate_id: str, review: RelationshipReview, user: CurrentUserDep, datastore: RelationshipCandidateDatastoreDep
):
    """Confirm (promote to a real edge) or reject a proposed edge."""
    resolved = await datastore.resolve(candidate_id, review.model_copy(update={"reviewed_by": user.id}))
    if resolved is None:
        raise EntityNotFoundError("RelationshipCandidate", candidate_id)
    return resolved


@router.get("/{entity_id}", summary="Get an entity", response_model=Entity, **_BY_ALIAS)
async def get_entity(entity_id: str, datastore: EntityDatastoreDep) -> Entity:
    """Fetch a single entity node."""
    entity = await datastore.get_entity(entity_id)
    if entity is None:
        raise EntityNotFoundError("Entity", entity_id)
    return entity


@router.patch("/{entity_id}", summary="Update an entity", response_model=Entity, **_BY_ALIAS)
async def update_entity(
    entity_id: str, data: EntityUpdate, user: CurrentUserDep, datastore: EntityDatastoreDep
) -> Entity:
    """Patch an entity node; a tag list edit is recorded as yours."""
    entity = await datastore.update_entity(entity_id, data, user_id=user.id)
    if entity is None:
        raise EntityNotFoundError("Entity", entity_id)
    return entity


_DETAIL_UPDATE_MODEL = {
    EntityType.ORGANIZATION: OrganizationUpdate,
    EntityType.LOCATION: LocationUpdate,
    EntityType.SELECTOR: SelectorUpdate,
}


@router.patch("/{entity_id}/detail", summary="Update an entity's type-specific detail")
async def update_entity_detail(entity_id: str, body: dict, datastore: EntityDatastoreDep) -> dict:
    """Patch the organization/location/selector detail row for an entity.

    Person detail (date of birth, sex, nationality) is edited through the persons API.
    """
    entity = await datastore.get_entity(entity_id)
    if entity is None:
        raise EntityNotFoundError("Entity", entity_id)
    if entity.entity_type == EntityType.PERSON:
        raise HTTPException(
            status_code=400,
            detail=f"Edit person detail via PATCH /persons/{entity.person_id}",
        )
    model = _DETAIL_UPDATE_MODEL.get(entity.entity_type)
    if model is None:
        raise HTTPException(status_code=400, detail=f"No editable detail for {entity.entity_type}")
    try:
        data = model.model_validate(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        detail = await datastore.update_detail(entity_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if detail is None:
        raise EntityNotFoundError("Entity detail", entity_id)
    return camelize_keys(detail)


@router.get(
    "/{entity_id}/structure",
    summary="An organization's hierarchy, locations and people",
    response_model=OrganizationStructure,
    **_BY_ALIAS,
)
async def get_organization_structure(entity_id: str, datastore: EntityDatastoreDep) -> OrganizationStructure:
    """Parent chain (`part_of` upward), sub-units, `located_in` locations and `employed_by`/`member_of` people."""
    entity = await datastore.get_entity(entity_id)
    if entity is None:
        raise EntityNotFoundError("Entity", entity_id)
    if entity.entity_type != EntityType.ORGANIZATION:
        raise HTTPException(status_code=400, detail="Only organizations have a structure")
    return await datastore.organization_structure(entity_id)


@router.get(
    "/{entity_id}/structure/suggestions",
    summary="Pending people suggested for an organization unit",
    response_model=list[OrganizationSuggestion],
    **_BY_ALIAS,
)
async def list_organization_suggestions(entity_id: str, datastore: EntityDatastoreDep) -> list[OrganizationSuggestion]:
    """Person<->unit candidates awaiting review on this unit or below; resolve via /relationship-candidates."""
    await _require_organization(entity_id, datastore)
    return await datastore.organization_suggestions(entity_id)


@router.get(
    "/{entity_id}/structure/name-suggestions",
    summary="Signature relationships on this unit whose names are not settled yet",
    response_model=list[NameSuggestion],
    **_BY_ALIAS,
)
async def list_organization_name_suggestions(
    entity_id: str, access: DatasetAccessDep, datastore: EntityDatastoreDep, names: NameSuggestionDatastoreDep
) -> list[NameSuggestion]:
    """Per name pair: what each name resolved to, the resolver's guess, or who owns the sending address."""
    await _require_organization(entity_id, datastore)
    tree = await datastore.organization_tree(entity_id)
    return await names.list_suggestions(unit_ids={n.entity.id for n in tree.nodes}, dataset_ids=access.scope(None))


async def _require_organization(entity_id: str, datastore: EntityDatastoreDep) -> None:
    entity = await datastore.get_entity(entity_id)
    if entity is None:
        raise EntityNotFoundError("Entity", entity_id)
    if entity.entity_type != EntityType.ORGANIZATION:
        raise HTTPException(status_code=400, detail="Only organizations have a structure")


@router.get(
    "/{entity_id}/structure/tree",
    summary="The whole organization hierarchy this unit belongs to",
    response_model=OrganizationTree,
    **_BY_ALIAS,
)
async def get_organization_tree(entity_id: str, datastore: EntityDatastoreDep) -> OrganizationTree:
    """Every unit from the top-most `part_of` ancestor down, parent-linked, with per-unit people counts."""
    await _require_organization(entity_id, datastore)
    return await datastore.organization_tree(entity_id)


@router.get(
    "/{entity_id}/structure/people",
    summary="People within or connected to an organization unit",
    response_model=PaginatedOrganizationPeople,
    **_BY_ALIAS,
)
async def list_organization_people(
    entity_id: str, params: Annotated[OrganizationPeopleParameters, Query()], datastore: EntityDatastoreDep
) -> PaginatedOrganizationPeople:
    """One row per person<->unit edge; members are `employed_by`/`member_of`, anything else is connected."""
    await _require_organization(entity_id, datastore)
    return await datastore.organization_people(entity_id, params)


@router.delete("/{entity_id}", summary="Delete an entity")
async def delete_entity(
    entity_id: str,
    datastore: EntityDatastoreDep,
    comment_datastore: CommentDatastoreDep,
    mention_datastore: MentionDatastoreDep,
    discard_mentions: Annotated[
        bool, Query(alias="discardMentions", description="Also delete its mentions ('not an entity')")
    ] = False,
) -> dict:
    """Delete an entity node and its detail/edges (cascade).

    By default mentions pointing at it are unresolved (FK ``SET NULL``) and go
    back to Review; with ``discardMentions`` they are deleted too, so the value
    doesn't return. Relationships and resolution/merge decisions naming it
    cascade-delete. Comments reference it polymorphically (no real FK), so
    they're purged explicitly first.
    """
    if await datastore.get_entity(entity_id) is None:
        raise EntityNotFoundError("Entity", entity_id)
    deleted_mentions = await mention_datastore.delete_by_entity(entity_id) if discard_mentions else 0
    deleted_comments = await comment_datastore.delete_by_commentable(
        commentable_type=CommentableType.ENTITY, commentable_id=entity_id
    )
    await datastore.delete_entity(entity_id)
    logger.info(f"Deleted entity {entity_id}: {deleted_mentions} mentions, {deleted_comments} comments")
    return {"deleted": True, "mentionsDeleted": deleted_mentions}


@router.get("/{entity_id}/profile", summary="Entity dossier", response_model=EntityProfile, **_BY_ALIAS)
async def get_entity_profile(entity_id: str, access: DatasetAccessDep, datastore: EntityDatastoreDep) -> EntityProfile:
    """Aggregate view: attributes, selectors, mention counts, related entities, linked faces.

    The entity graph is open to everyone; the sample mentions quote file text, so only
    those from your datasets are included.
    """
    profile = await datastore.get_profile(entity_id)
    if profile is None:
        raise EntityNotFoundError("Entity", entity_id)
    return profile.model_copy(update={"top_mentions": [m for m in profile.top_mentions if access.allows(m.dataset_id)]})


@router.post("/{entity_id}/promote", summary="Promote a provisional entity", response_model=Entity, **_BY_ALIAS)
async def promote_entity(entity_id: str, user: CurrentUserDep, datastore: EntityDatastoreDep) -> Entity:
    """Keep a provisional entity as a new canonical one (a person gets its own person page).

    Rejects its pending merge proposals -- the analyst has said it is none of them.
    """
    entity = await datastore.promote_entity(entity_id, reviewed_by=user.id)
    if entity is None:
        raise EntityNotFoundError("Entity", entity_id)
    return entity


@router.post("/promote-batch", summary="Verify many auto-created entities")
async def promote_entities_batch(body: EntityBatchRequest, user: CurrentUserDep, datastore: EntityDatastoreDep) -> dict:
    """Bulk Verify -- keep each auto-created entity as a real one (see `promote`)."""
    promoted = [await datastore.promote_entity(entity_id, reviewed_by=user.id) for entity_id in body.entity_ids]
    return {"promoted": sum(entity is not None for entity in promoted)}


@router.post("/retype", summary="Change the type of auto-created entities")
async def retype_entities(body: EntityRetypeRequest, datastore: EntityDatastoreDep) -> dict:
    """Person <-> organization for auto-created entities (e.g. `Idylwood Towers` minted as a person).

    Their name mentions follow; edges the new type can't have are removed. Verified entities
    are refused -- edit those by hand.
    """
    totals = {"retyped": 0, "mentions": 0, "edges_removed": 0}
    for entity_id in dict.fromkeys(body.entity_ids):
        try:
            counts = await datastore.retype_entity(entity_id, body.entity_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if counts is None:
            raise EntityNotFoundError("Entity", entity_id)
        totals["retyped"] += 1
        totals["mentions"] += counts["mentions"]
        totals["edges_removed"] += counts["edges_removed"]
    return camelize_keys(totals)


@router.post("/{entity_id}/merge", summary="Merge auto-created entities into this one")
async def merge_into_entity(entity_id: str, body: EntityMergeRequest, datastore: EntityDatastoreDep) -> dict:
    """Fold each auto-created source into the path entity: mentions, edges and reviews move, its names become aliases.

    Sources must be auto-created (provisional) and share the target's type -- a verified
    entity is never deleted by a merge from this endpoint.
    """
    target = await datastore.get_entity(entity_id)
    if target is None:
        raise EntityNotFoundError("Entity", entity_id)
    source_ids = [source_id for source_id in dict.fromkeys(body.source_ids) if source_id != entity_id]
    for source_id in source_ids:
        source = await datastore.get_entity(source_id)
        if source is None:
            raise EntityNotFoundError("Entity", source_id)
        if not source.is_provisional or source.entity_type != target.entity_type:
            raise HTTPException(
                status_code=422, detail=f"{source.display_name} must be an auto-created {target.entity_type}"
            )
    for source_id in source_ids:
        await datastore.merge_entities(canonical_id=entity_id, provisional_id=source_id)
    return {"merged": len(source_ids)}


@router.post("/{entity_id}/names/unresolve", summary="Send a resolved name back to the Resolve queue")
async def unresolve_entity_name(entity_id: str, body: UnresolveNameRequest, datastore: EntityMatchDatastoreDep) -> dict:
    """Undo a name-group resolution: its mentions detach and its resolution returns to pending."""
    detached = await datastore.unresolve_name_group(entity_id=entity_id, normalized_value=body.normalized_value)
    return {"detached": detached}


@router.get(
    "/{entity_id}/merge-candidates",
    summary="Canonical entities this provisional entity may duplicate",
    response_model=list[EntityMatch],
    **_BY_ALIAS,
)
async def get_entity_merge_candidates(entity_id: str, datastore: EntityMatchDatastoreDep) -> list[EntityMatch]:
    """Merge proposals filed against this entity by `dedupe-entities` (empty unless it's a stub)."""
    return await datastore.list_for_provisional(provisional_entity_id=entity_id)


@router.get(
    "/{entity_id}/related",
    summary="Paginated neighbours of an entity",
    response_model=PaginatedRelatedEntitiesResponse,
    **_BY_ALIAS,
)
async def list_related_entities(
    entity_id: str,
    datastore: EntityDatastoreDep,
    direction: Annotated[TraversalDirection, Query()] = TraversalDirection.BOTH,
    relationship_type: Annotated[RelationshipType | None, Query()] = None,
    entity_type: Annotated[
        EntityType | None, Query(alias="entityType", description="Only neighbours of this type")
    ] = None,
    sort: Annotated[RelatedEntitySort, Query()] = RelatedEntitySort.WEIGHT,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    page: Annotated[int, Query(ge=1)] = 1,
) -> PaginatedRelatedEntitiesResponse:
    """Neighbours of an entity with their connecting edge, sortable by edge weight."""
    return await datastore.list_related(
        entity_id,
        RelatedEntitySearchParameters(
            direction=direction.value,
            relationship_type=relationship_type,
            entity_type=entity_type,
            sort=sort,
            limit=limit,
            page=page,
        ),
    )


@router.post(
    "/{entity_id}/selectors",
    summary="Attach a selector to an actor entity",
    response_model=SelectorMention,
    **_BY_ALIAS,
)
async def attach_selector(
    entity_id: str,
    body: SelectorLinkRequest,
    datastore: EntityDatastoreDep,
    graph: GraphDatastoreDep,
    mentions: MentionDatastoreDep,
) -> SelectorMention:
    """Link a selector to the entity and report how many mentions already carry its normalized value."""
    actor = await datastore.get_entity(entity_id)
    if actor is None:
        raise EntityNotFoundError("Entity", entity_id)
    try:
        validate_relationship(
            relationship_type=RelationshipType.HAS_SELECTOR,
            src_type=actor.entity_type,
            dst_type=EntityType.SELECTOR,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    normalized, attributes = _normalize_selector_value(body.selector_type, body.raw_value, body.region_hint)
    if not normalized:
        raise HTTPException(status_code=422, detail=f"'{body.raw_value}' is not a valid {body.selector_type} selector")

    # An analyst link carries no dataset -- the selector node and the edge are
    # dataset-agnostic (like a person bridge node).
    selector, _ = await datastore.get_or_create_selector(
        dataset_id=None,
        selector_type=body.selector_type,
        selector_subtype=body.selector_subtype,
        raw_value=body.raw_value.strip(),
        normalized_value=normalized,
        region_hint=body.region_hint,
        attributes=attributes or None,
    )
    await graph.upsert_relationship(
        EntityRelationshipCreate(
            src_entity_id=entity_id,
            dst_entity_id=selector.id,
            relationship_type=RelationshipType.HAS_SELECTOR,
            source=RelationshipSource.MANUAL,
        )
    )
    matching = await mentions.list_mentions(MentionSearchParameters(normalized_value=normalized, limit=1))
    return SelectorMention(
        entity_id=selector.id,
        selector_type=body.selector_type,
        selector_subtype=body.selector_subtype,
        normalized_value=normalized,
        mention_count=matching.total,
    )


@router.get(
    "/{entity_id}/names",
    summary="Names the evidence uses for an entity",
    response_model=list[ResolvedName],
    **_BY_ALIAS,
)
async def entity_names(
    entity_id: str, datastore: EntityDatastoreDep, mentions: MentionDatastoreDep
) -> list[ResolvedName]:
    """Resolved name groups, most mentions first, each flagged if it is one of the entity's curated aliases."""
    entity = await datastore.get_entity(entity_id)
    if entity is None:
        raise EntityNotFoundError("Entity", entity_id)
    aliases = {normalize_name(a) for a in (entity.aliases or [])} | {normalize_name(entity.display_name)}
    return [
        ResolvedName(**row, is_alias=row["normalized_value"] in aliases)
        for row in await mentions.names_for_entity(entity_id)
    ]


@router.get(
    "/{entity_id}/selector-evidence",
    summary="Header usage and current owners of candidate selectors",
    response_model=list[SelectorEvidence],
    **_BY_ALIAS,
)
async def selector_evidence(
    entity_id: str, mentions: MentionDatastoreDep, ids: Annotated[list[str], Query()]
) -> list[SelectorEvidence]:
    """The evidence behind a proposed link: how often each address is used, under which names, and who owns it."""
    return await mentions.selector_evidence(ids)


@router.post(
    "/{entity_id}/selectors/{selector_id}",
    summary="Link an existing selector node to an actor entity",
)
async def link_selector(
    entity_id: str, selector_id: str, datastore: EntityDatastoreDep, graph: GraphDatastoreDep
) -> dict:
    """Manual `has_selector` edge to this exact selector node (the one its mentions point at).

    Unlike `POST /{entity_id}/selectors`, which creates-or-reuses a dataset-agnostic node
    from a typed value, this links the node the data already uses -- so every email that
    carries it is attributed. Manual edges are never pruned by the inferred-link reconcile.
    """
    actor = await datastore.get_entity(entity_id)
    selector = await datastore.get_entity(selector_id)
    if actor is None:
        raise EntityNotFoundError("Entity", entity_id)
    if selector is None:
        raise EntityNotFoundError("Selector", selector_id)
    try:
        validate_relationship(
            relationship_type=RelationshipType.HAS_SELECTOR,
            src_type=actor.entity_type,
            dst_type=selector.entity_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await graph.upsert_relationship(
        EntityRelationshipCreate(
            src_entity_id=entity_id,
            dst_entity_id=selector_id,
            relationship_type=RelationshipType.HAS_SELECTOR,
            source=RelationshipSource.MANUAL,
        )
    )
    return {"linked": True}


@router.delete("/{entity_id}/selectors/{selector_id}", summary="Detach a selector from an entity")
async def detach_selector(entity_id: str, selector_id: str, graph: GraphDatastoreDep) -> dict:
    """Remove the has_selector edge. The selector node and its detail row are left intact."""
    removed = await graph.delete_relationship(
        src_entity_id=entity_id,
        dst_entity_id=selector_id,
        relationship_type=RelationshipType.HAS_SELECTOR,
    )
    if not removed:
        raise EntityNotFoundError("Selector link", selector_id)
    return {"detached": True}


@router.get(
    "/{entity_id}/mentions",
    summary="Mentions of an entity",
    response_model=PaginatedMentionsResponse,
    **_BY_ALIAS,
)
async def list_entity_mentions(
    entity_id: str,
    access: DatasetAccessDep,
    datastore: MentionDatastoreDep,
    mentioned_type: Annotated[MentionedType | None, Query()] = None,
    provenance: Annotated[MentionProvenance | None, Query()] = None,
    file_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    page: Annotated[int, Query(ge=1)] = 1,
) -> PaginatedMentionsResponse:
    """List the evidence spans that mention this entity in your datasets, optionally one evidence class."""
    return await datastore.list_mentions(
        access.scoped(
            MentionSearchParameters(
                entity_id=entity_id,
                mentioned_type=mentioned_type,
                provenance=provenance,
                file_id=file_id,
                resolved=True,
                limit=limit,
                page=page,
            )
        )
    )


@router.get(
    "/{entity_id}/relationships",
    summary="Confirmed edges touching an entity",
    response_model=PaginatedRelationshipsResponse,
    **_BY_ALIAS,
)
async def list_entity_relationships(
    entity_id: str,
    datastore: GraphDatastoreDep,
    direction: Annotated[TraversalDirection, Query()] = TraversalDirection.BOTH,
    relationship_type: Annotated[RelationshipType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    page: Annotated[int, Query(ge=1)] = 1,
) -> PaginatedRelationshipsResponse:
    """List depth-1 confirmed edges for an entity."""
    return await datastore.list_relationships(
        RelationshipSearchParameters(
            entity_id=entity_id,
            direction=direction,
            relationship_type=relationship_type,
            limit=limit,
            page=page,
        )
    )


@router.post(
    "/top-connections", summary="Rank strongest connections", response_model=TopConnectionsResponse, **_BY_ALIAS
)
async def top_connections(request: TopConnectionsRequest, datastore: GraphDatastoreDep) -> TopConnectionsResponse:
    """Rank the seeds' neighbours by summed edge weight; seeds may be actors or bare selectors."""
    return await datastore.top_connections(request)


@router.get("/{entity_id}/graph", summary="Bounded graph traversal", response_model=GraphResponse, **_BY_ALIAS)
async def traverse_entity_graph(
    entity_id: str,
    datastore: GraphDatastoreDep,
    depth: Annotated[int, Query(ge=1, le=3)] = 2,
    direction: Annotated[TraversalDirection, Query()] = TraversalDirection.BOTH,
    types: Annotated[str | None, Query(description="Comma-separated relationship types")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    min_weight: Annotated[
        float, Query(alias="minWeight", ge=0, description="Drop weighted edges below this (keeps unweighted)")
    ] = 0,
) -> GraphResponse:
    """Return the subgraph reachable from an entity within `depth` hops."""
    relationship_types = None
    if types:
        try:
            relationship_types = [RelationshipType(t.strip()) for t in types.split(",") if t.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await datastore.traverse(
        start_entity_id=entity_id,
        max_depth=depth,
        relationship_types=relationship_types,
        direction=direction,
        limit=limit,
        min_weight=min_weight,
    )


@router.post(
    "/{entity_id}/relationships",
    summary="Assert an edge from an entity",
    response_model=EntityRelationship,
    **_BY_ALIAS,
)
async def create_entity_relationship(
    entity_id: str,
    relationship: EntityRelationshipCreate,
    datastore: GraphDatastoreDep,
    entities: EntityDatastoreDep,
) -> EntityRelationship:
    """Manually assert a typed edge; validated against the ontology's endpoint rules."""
    if relationship.src_entity_id != entity_id:
        raise HTTPException(status_code=422, detail="src_entity_id must match the path entity")
    relationship = relationship.model_copy(update={"source": RelationshipSource.MANUAL})
    src = await entities.get_entity(relationship.src_entity_id)
    dst = await entities.get_entity(relationship.dst_entity_id)
    if src is None or dst is None:
        raise EntityNotFoundError("Entity", relationship.dst_entity_id if src else relationship.src_entity_id)
    try:
        validate_relationship(
            relationship_type=relationship.relationship_type,
            src_type=src.entity_type,
            dst_type=dst.entity_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    role = relationship.attributes.get("role")
    if role is not None:
        role_enum = RELATIONSHIP_ROLE_ENUM.get(relationship.relationship_type)
        if role_enum is None:
            raise HTTPException(status_code=422, detail=f"{relationship.relationship_type} edges take no role")
        try:
            role_enum(role)
        except ValueError as exc:
            valid = ", ".join(r.value for r in role_enum)
            raise HTTPException(status_code=422, detail=f"role must be one of: {valid}") from exc

    if relationship.relationship_type == RelationshipType.PART_OF:
        try:
            await entities.set_organization_parent(entity_id, relationship.dst_entity_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return next(
            r
            for r in (
                await datastore.list_relationships(
                    RelationshipSearchParameters(
                        entity_id=entity_id,
                        direction=TraversalDirection.OUT,
                        relationship_type=RelationshipType.PART_OF,
                    )
                )
            ).data
        )

    # An edge does not belong to a dataset -- it's just a link between two nodes,
    # visible whenever both nodes are. Manual edges leave dataset_id NULL.
    return await datastore.upsert_relationship(relationship)
