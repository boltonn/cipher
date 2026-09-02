from typing import Annotated

from fastapi import APIRouter, Query

from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import EntityDatastoreDep, GraphDatastoreDep, MentionDatastoreDep
from cipher.schemas._base.exceptions import EntityNotFoundError
from cipher.schemas.graph.entity import EntityCreate
from cipher.schemas.graph.location import LocationCreate
from cipher.schemas.graph.mention import (
    DismissNameGroupRequest,
    Mention,
    MentionCreate,
    MentionResolve,
    MentionSearchParameters,
    MentionUpdate,
    PaginatedMentionsResponse,
    PaginatedUnresolvedNamesResponse,
    ResolveNameGroupRequest,
    ResolveNameGroupResult,
)
from cipher.schemas.graph.ontology import EntitySource, EntityType, guess_actor_type
from cipher.schemas.graph.organization import OrganizationCreate
from cipher.schemas.graph.selector import SelectorCreate

router = APIRouter(prefix="/mentions", tags=["mentions"])

_BY_ALIAS = {"response_model_by_alias": True}

_DETAIL_CREATE_MODEL = {
    EntityType.ORGANIZATION: OrganizationCreate,
    EntityType.LOCATION: LocationCreate,
    EntityType.SELECTOR: SelectorCreate,
}


@router.get("", summary="List mentions", response_model=PaginatedMentionsResponse, **_BY_ALIAS)
async def list_mentions(
    params: Annotated[MentionSearchParameters, Query()], datastore: MentionDatastoreDep
) -> PaginatedMentionsResponse:
    """List mentions, filtered by file, dataset, resolution state, or evidence type."""
    return await datastore.list_mentions(params)


@router.post("", summary="Create a mention", response_model=Mention, **_BY_ALIAS)
async def create_mention(mention: MentionCreate, datastore: MentionDatastoreDep) -> Mention:
    """Record an analyst-authored mention span."""
    return await datastore.add_mention(mention)


@router.get(
    "/unresolved-names",
    summary="Review queue, grouped by name",
    response_model=PaginatedUnresolvedNamesResponse,
    **_BY_ALIAS,
)
async def list_unresolved_names(
    datastore: MentionDatastoreDep,
    dataset_id: Annotated[str, Query(alias="datasetId")],
    q: Annotated[str | None, Query(description="Filter by name substring")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    page: Annotated[int, Query(ge=1)] = 1,
) -> PaginatedUnresolvedNamesResponse:
    """Distinct unresolved `name` values awaiting a person/organization decision.

    One row per name (not per mention), so "Nick Bolton" seen in 900 emails is a
    single reviewable item. `suggestedType` is a heuristic guess only.
    """
    result = await datastore.unresolved_name_group_page(dataset_id=dataset_id, query=q, limit=limit, page=page)
    for row in result["data"]:
        row["suggested_type"] = guess_actor_type(row["surface"])
    return PaginatedUnresolvedNamesResponse.model_validate(result)


@router.post(
    "/resolve-names",
    summary="Resolve a whole name group",
    response_model=ResolveNameGroupResult,
    **_BY_ALIAS,
)
async def resolve_name_group(
    body: ResolveNameGroupRequest,
    mentions: MentionDatastoreDep,
    entities: EntityDatastoreDep,
    graph: GraphDatastoreDep,
    user: CurrentUserDep,
) -> ResolveNameGroupResult:
    """Attach every unresolved `name` mention of one value to an entity, then link header selectors.

    Either `entity_id` (attach to an existing person/organization) or a new
    entity of `entity_type` is used. After attaching, `has_selector` edges are
    (re)built so the actor is linked to the addresses it appeared next to.
    """
    entity_id = body.entity_id
    if entity_id is None:
        created = await entities.create_entity(
            EntityCreate(
                dataset_id=body.dataset_id,
                entity_type=body.entity_type,
                display_name=(body.display_name or body.normalized_value).strip()[:200],
                source=EntitySource.EXTRACTION,
            )
        )
        entity_id = created.id

    attached = await mentions.attach_names(
        dataset_id=body.dataset_id, normalized_value=body.normalized_value, entity_id=entity_id
    )
    edges = await graph.link_header_selectors(body.dataset_id)
    return ResolveNameGroupResult(entity_id=entity_id, mentions_attached=attached, has_selector_edges=edges)


@router.post("/dismiss-names", summary="Discard a name group")
async def dismiss_name_group(body: DismissNameGroupRequest, mentions: MentionDatastoreDep) -> dict:
    """Delete every unresolved `name` mention of one value -- 'this isn't an entity'."""
    deleted = await mentions.delete_names(dataset_id=body.dataset_id, normalized_value=body.normalized_value)
    return {"deleted": deleted}


@router.get("/{mention_id}", summary="Get a mention", response_model=Mention, **_BY_ALIAS)
async def get_mention(mention_id: str, datastore: MentionDatastoreDep) -> Mention:
    """Fetch a single mention."""
    mention = await datastore.get_mention(mention_id)
    if mention is None:
        raise EntityNotFoundError("Mention", mention_id)
    return mention


@router.patch("/{mention_id}", summary="Update a mention", response_model=Mention, **_BY_ALIAS)
async def update_mention(mention_id: str, data: MentionUpdate, datastore: MentionDatastoreDep) -> Mention:
    """Relabel or correct a mention (predicted type, surface text, or resolved entity)."""
    mention = await datastore.update_mention(mention_id, data)
    if mention is None:
        raise EntityNotFoundError("Mention", mention_id)
    return mention


@router.delete("/{mention_id}", summary="Delete a mention")
async def delete_mention(mention_id: str, datastore: MentionDatastoreDep) -> dict:
    """Delete a mention span."""
    deleted = await datastore.delete_mention(mention_id)
    if not deleted:
        raise EntityNotFoundError("Mention", mention_id)
    return {"deleted": True}


@router.post("/{mention_id}/resolve", summary="Resolve a mention", response_model=Mention, **_BY_ALIAS)
async def resolve_mention(
    mention_id: str,
    body: MentionResolve,
    mentions: MentionDatastoreDep,
    entities: EntityDatastoreDep,
    user: CurrentUserDep,
) -> Mention:
    """Attach an unresolved mention to an existing entity, or create a new entity and attach it."""
    mention = await mentions.get_mention(mention_id)
    if mention is None:
        raise EntityNotFoundError("Mention", mention_id)

    entity_id = body.entity_id
    if entity_id is None:
        if not body.new_entity:
            raise EntityNotFoundError("Entity", "one of entity_id / new_entity is required")
        new_entity = EntityCreate.model_validate(body.new_entity)
        detail = None
        detail_model = _DETAIL_CREATE_MODEL.get(new_entity.entity_type)
        if body.new_entity_detail and detail_model is not None:
            detail_payload = {**body.new_entity_detail, "datasetId": new_entity.dataset_id}
            # Location detail is bridged by shared id, not an entity_id FK.
            if new_entity.entity_type != EntityType.LOCATION:
                detail_payload["entityId"] = ""
            detail = detail_model.model_validate(detail_payload)
        created = await entities.create_entity(new_entity, detail=detail)
        entity_id = created.id

    await mentions.attach_to_entity(mention_id, entity_id)
    resolved = await mentions.get_mention(mention_id)
    if resolved is None:
        raise EntityNotFoundError("Mention", mention_id)
    return resolved
