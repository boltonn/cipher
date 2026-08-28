from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from cipher.api.deps.postgres import (
    EntityDatastoreDep,
    EntityMatchDatastoreDep,
    GraphDatastoreDep,
    MentionDatastoreDep,
    RelationshipCandidateDatastoreDep,
)
from cipher.schemas.entity import (
    Entity,
    EntityCreate,
    EntityProfile,
    EntitySearchParameters,
    EntitySearchResult,
    EntitySummary,
    EntityUpdate,
    PaginatedEntitiesResponse,
)
from cipher.schemas.entity_match import (
    EntityMatchReview,
    EntityMatchSearchParameters,
    PaginatedEntityMatchesResponse,
)
from cipher.schemas.entity_relationship import (
    EntityRelationship,
    EntityRelationshipCreate,
    GraphResponse,
    PaginatedRelationshipCandidatesResponse,
    PaginatedRelationshipsResponse,
    RelationshipCandidateSearchParameters,
    RelationshipReview,
    RelationshipSearchParameters,
    TraversalDirection,
)
from cipher.schemas.exceptions import EntityNotFoundError
from cipher.schemas.location import LocationUpdate
from cipher.schemas.mention import MentionedType, MentionSearchParameters, PaginatedMentionsResponse
from cipher.schemas.ontology import EntityType, RelationshipType, validate_relationship
from cipher.schemas.organization import OrganizationUpdate
from cipher.schemas.selector import SelectorUpdate

router = APIRouter(prefix="/entities", tags=["entities"])

_BY_ALIAS = {"response_model_by_alias": True}


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
    dataset_id: Annotated[str, Query(description="Dataset to search within")],
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
    "/matches", summary="Entity resolution review queue", response_model=PaginatedEntityMatchesResponse, **_BY_ALIAS
)
async def list_entity_matches(
    params: Annotated[EntityMatchSearchParameters, Query()], datastore: EntityMatchDatastoreDep
) -> PaginatedEntityMatchesResponse:
    """List candidate mention-to-entity resolutions awaiting review."""
    return await datastore.list_matches(params)


@router.post("/matches/{match_id}/resolve", summary="Resolve an entity match", response_model_by_alias=True)
async def resolve_entity_match(match_id: str, review: EntityMatchReview, datastore: EntityMatchDatastoreDep):
    """Confirm or reject a candidate resolution."""
    resolved = await datastore.resolve_match(match_id, review)
    if resolved is None:
        raise EntityNotFoundError("EntityMatch", match_id)
    return resolved


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
    candidate_id: str, review: RelationshipReview, datastore: RelationshipCandidateDatastoreDep
):
    """Confirm (promote to a real edge) or reject a proposed edge."""
    resolved = await datastore.resolve(candidate_id, review)
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
    return detail


@router.delete("/{entity_id}", summary="Delete an entity")
async def delete_entity(entity_id: str, datastore: EntityDatastoreDep) -> dict:
    """Delete an entity node and its detail/edges (cascade)."""
    deleted = await datastore.delete_entity(entity_id)
    if not deleted:
        raise EntityNotFoundError("Entity", entity_id)
    return {"deleted": True}


@router.get("/{entity_id}/profile", summary="Entity dossier", response_model=EntityProfile, **_BY_ALIAS)
async def get_entity_profile(entity_id: str, datastore: EntityDatastoreDep) -> EntityProfile:
    """Aggregate view: attributes, selectors, mention counts, related entities, linked faces."""
    profile = await datastore.get_profile(entity_id)
    if profile is None:
        raise EntityNotFoundError("Entity", entity_id)
    return profile


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
    file_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    page: Annotated[int, Query(ge=1)] = 1,
) -> PaginatedMentionsResponse:
    """List the evidence spans that mention this entity."""
    return await datastore.list_mentions(
        MentionSearchParameters(
            entity_id=entity_id,
            mentioned_type=mentioned_type,
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


@router.get("/{entity_id}/graph", summary="Bounded graph traversal", response_model=GraphResponse, **_BY_ALIAS)
async def traverse_entity_graph(
    entity_id: str,
    datastore: GraphDatastoreDep,
    depth: Annotated[int, Query(ge=1, le=3)] = 2,
    direction: Annotated[TraversalDirection, Query()] = TraversalDirection.BOTH,
    types: Annotated[str | None, Query(description="Comma-separated relationship types")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
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
    return await datastore.upsert_relationship(relationship)
