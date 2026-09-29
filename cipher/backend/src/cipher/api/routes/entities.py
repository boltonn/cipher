from typing import Annotated

import phonenumbers
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pyselectors.normalize import normalize_selector

from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import (
    CommentDatastoreDep,
    EntityDatastoreDep,
    EntityMatchDatastoreDep,
    GraphDatastoreDep,
    MentionDatastoreDep,
    RelationshipCandidateDatastoreDep,
)
from cipher.schemas._base.base import camelize_keys
from cipher.schemas._base.exceptions import EntityNotFoundError
from cipher.schemas.graph.entity import (
    Entity,
    EntityBreakdown,
    EntityCreate,
    EntityProfile,
    EntitySearchParameters,
    EntitySearchResult,
    EntitySummary,
    EntityUpdate,
    PaginatedEntitiesResponse,
    PaginatedRelatedEntitiesResponse,
    RelatedEntitySearchParameters,
    RelatedEntitySort,
    SelectorMention,
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
)
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
from cipher.schemas.graph.organization import OrganizationUpdate
from cipher.schemas.graph.selector import SelectorEvidence, SelectorLinkRequest, SelectorRegion, SelectorUpdate
from cipher.schemas.interaction.comment import CommentableType

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
async def create_entity(entity: EntityCreate, datastore: EntityDatastoreDep) -> Entity:
    """Manually create an entity node (detail rows are attached separately)."""
    return await datastore.create_entity(entity)


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
async def update_entity(entity_id: str, data: EntityUpdate, datastore: EntityDatastoreDep) -> Entity:
    """Patch an entity node."""
    entity = await datastore.update_entity(entity_id, data)
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
    detail = await datastore.update_detail(entity_id, data)
    if detail is None:
        raise EntityNotFoundError("Entity detail", entity_id)
    return camelize_keys(detail)


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
async def get_entity_profile(entity_id: str, datastore: EntityDatastoreDep) -> EntityProfile:
    """Aggregate view: attributes, selectors, mention counts, related entities, linked faces."""
    profile = await datastore.get_profile(entity_id)
    if profile is None:
        raise EntityNotFoundError("Entity", entity_id)
    return profile


@router.post("/{entity_id}/promote", summary="Promote a provisional entity", response_model=Entity, **_BY_ALIAS)
async def promote_entity(entity_id: str, user: CurrentUserDep, datastore: EntityDatastoreDep) -> Entity:
    """Keep a provisional entity as a new canonical one (a person gets its own person page).

    Rejects its pending merge proposals -- the analyst has said it is none of them.
    """
    entity = await datastore.promote_entity(entity_id, reviewed_by=user.id)
    if entity is None:
        raise EntityNotFoundError("Entity", entity_id)
    return entity


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
    datastore: MentionDatastoreDep,
    mentioned_type: Annotated[MentionedType | None, Query()] = None,
    provenance: Annotated[MentionProvenance | None, Query()] = None,
    file_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    page: Annotated[int, Query(ge=1)] = 1,
) -> PaginatedMentionsResponse:
    """List the evidence spans that mention this entity, optionally one evidence class."""
    return await datastore.list_mentions(
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

    # An edge does not belong to a dataset -- it's just a link between two nodes,
    # visible whenever both nodes are. Manual edges leave dataset_id NULL.
    return await datastore.upsert_relationship(relationship)
