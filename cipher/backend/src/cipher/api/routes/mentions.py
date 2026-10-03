from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pyselectors.normalize import normalize_selector

from cipher.api.deps.access import DatasetAccessDep, DatasetIdQueryDep, MentionDep, require_mention
from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import (
    EntityDatastoreDep,
    EntityMatchDatastoreDep,
    GraphDatastoreDep,
    MentionDatastoreDep,
)
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas._base.exceptions import EntityNotFoundError
from cipher.schemas.graph.entity import EntityCreate
from cipher.schemas.graph.entity_match import PaginatedResolveQueueResponse
from cipher.schemas.graph.entity_resolution import EntityMatchRef, MentionResolution
from cipher.schemas.graph.location import LocationCreate
from cipher.schemas.graph.mention import (
    MANUAL_EXTRACTOR,
    DismissNameGroupRequest,
    Mention,
    MentionCreate,
    MentionResolve,
    MentionSearchParameters,
    MentionUpdate,
    PaginatedMentionsResponse,
    ResolveNameGroupRequest,
    ResolveNameGroupResult,
)
from cipher.schemas.graph.ontology import EntitySource, EntityType, SelectorType, guess_actor_type
from cipher.schemas.graph.organization import OrganizationCreate
from cipher.schemas.graph.selector import SelectorCreate
from cipher.schemas.interaction.tag import TagSource

router = APIRouter(prefix="/mentions", tags=["mentions"])

_BY_ALIAS = {"response_model_by_alias": True}

_DETAIL_CREATE_MODEL = {
    EntityType.ORGANIZATION: OrganizationCreate,
    EntityType.LOCATION: LocationCreate,
    EntityType.SELECTOR: SelectorCreate,
}


def _normalized_value(*, surface_text: str, selector_type: SelectorType | None) -> str:
    """The name-group / selector key an analyst-drawn span joins -- same folding the extractors apply."""
    if selector_type is not None:
        value, _ = normalize_selector(selector_type, surface_text)
        return value or surface_text.strip()
    return normalize_name(surface_text)


def _trimmed_span(*, surface_text: str, start_offset: int | None, end_offset: int | None) -> dict:
    """An analyst-highlighted span without the whitespace swept up at either edge."""
    stripped = surface_text.strip()
    if start_offset is None or end_offset is None or end_offset - start_offset != len(surface_text):
        return {"surface_text": stripped}
    start_offset += len(surface_text) - len(surface_text.lstrip())
    return {"surface_text": stripped, "start_offset": start_offset, "end_offset": start_offset + len(stripped)}


@router.get("", summary="List mentions", response_model=PaginatedMentionsResponse, **_BY_ALIAS)
async def list_mentions(
    params: Annotated[MentionSearchParameters, Query()], access: DatasetAccessDep, datastore: MentionDatastoreDep
) -> PaginatedMentionsResponse:
    """List mentions in your datasets, filtered by file, dataset, resolution state, or evidence type."""
    return await datastore.list_mentions(access.scoped(params))


@router.post("", summary="Create a mention", response_model=Mention, **_BY_ALIAS)
async def create_mention(mention: MentionCreate, access: DatasetAccessDep, datastore: MentionDatastoreDep) -> Mention:
    """Record an analyst-authored mention span, keyed into its name group / selector value.

    Whitespace at the span's edges is trimmed, and mentions the span overlaps are replaced.
    """
    access.require(mention.dataset_id)
    is_selector = mention.selector_type is not None or mention.entity_type == EntityType.SELECTOR
    mention = mention.model_copy(
        update=_trimmed_span(
            surface_text=mention.surface_text, start_offset=mention.start_offset, end_offset=mention.end_offset
        )
    )
    mention = mention.model_copy(
        update={
            "normalized_value": mention.normalized_value
            or _normalized_value(surface_text=mention.surface_text, selector_type=mention.selector_type),
            "entity_attribute": mention.entity_attribute or ("value" if is_selector else "name"),
            "extractor": mention.extractor or MANUAL_EXTRACTOR,
        }
    )
    return await datastore.add_mention(mention, reviewed_by=access.user.id)


@router.get(
    "/unresolved-names",
    summary="Review queue, grouped by name",
    response_model=PaginatedResolveQueueResponse,
    **_BY_ALIAS,
)
async def list_unresolved_names(
    datastore: MentionDatastoreDep,
    dataset_id: DatasetIdQueryDep,
    matches: EntityMatchDatastoreDep,
    q: Annotated[str | None, Query(description="Filter by name substring")] = None,
    has_resolution: Annotated[
        bool | None,
        Query(alias="hasResolution", description="Only names with (true) / without (false) a pending resolution"),
    ] = None,
    entity_id: Annotated[
        str | None, Query(alias="entityId", description="Only names with a pending resolution to this entity")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    page: Annotated[int, Query(ge=1)] = 1,
) -> PaginatedResolveQueueResponse:
    """The Resolve queue: distinct unresolved names, each with its pending resolutions.

    One row per name group (not per mention), so "Nick Bolton" seen in 900 emails is a
    single item. `resolutions` are the entities the resolver proposes the name is, best
    first -- accept or reject them, or create a new entity. `suggestedType` is a
    heuristic guess only.
    """
    result = await datastore.unresolved_name_group_page(
        dataset_id=dataset_id, query=q, has_resolution=has_resolution, entity_id=entity_id, limit=limit, page=page
    )
    resolutions = await matches.pending_resolutions(
        dataset_id=dataset_id, names=[row["normalized_value"] for row in result["data"]]
    )
    for row in result["data"]:
        row["suggested_type"] = guess_actor_type(row["surface"])
        row["resolutions"] = resolutions.get(row["normalized_value"], [])[:3]
    return PaginatedResolveQueueResponse.model_validate(result)


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
    access: DatasetAccessDep,
) -> ResolveNameGroupResult:
    """Attach every unresolved `name` mention of one value to an entity, then link header selectors.

    Either `entity_id` (attach to an existing person/organization) or a new
    entity of `entity_type` is used. After attaching, `has_selector` edges are
    (re)built so the actor is linked to the addresses it appeared next to.
    """
    access.require(body.dataset_id)
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
async def dismiss_name_group(
    body: DismissNameGroupRequest, access: DatasetAccessDep, mentions: MentionDatastoreDep
) -> dict:
    """Delete every unresolved `name` mention of one value -- 'this isn't an entity'."""
    access.require(body.dataset_id)
    deleted = await mentions.delete_names(dataset_id=body.dataset_id, normalized_value=body.normalized_value)
    return {"deleted": deleted}


@router.get("/{mention_id}", summary="Get a mention", response_model=Mention, **_BY_ALIAS)
async def get_mention(mention: MentionDep) -> Mention:
    """Fetch a single mention."""
    return mention


@router.get(
    "/{mention_id}/resolution",
    summary="Why this mention did or didn't resolve",
    response_model=MentionResolution,
    **_BY_ALIAS,
)
async def get_mention_resolution(
    mention_id: str, mention: MentionDep, matches: EntityMatchDatastoreDep
) -> MentionResolution:
    """The scored candidates + per-feature explanation for a mention's name group.

    Covers the negative case too: an empty `candidates` list means nothing blocked,
    or nothing cleared the review floor.
    """
    candidates: list[EntityMatchRef] = []
    resolved_by = None
    if mention.normalized_value:
        rows = await matches.list_for_name_group(
            dataset_id=mention.dataset_id, normalized_value=mention.normalized_value
        )
        candidates = [
            EntityMatchRef(
                id=r.id,
                entity_id=r.entity_id,
                status=r.status,
                similarity_score=r.similarity_score,
                match_method=r.match_method,
                explanation=r.explanation,
            )
            for r in rows
        ]
        confirmed = next((r for r in rows if r.status == "confirmed"), None)
        if confirmed is not None:
            band = confirmed.explanation.band if confirmed.explanation else None
            resolved_by = "system" if band == "auto" and confirmed.reviewed_by is None else "analyst"

    return MentionResolution(
        mention_id=mention_id,
        normalized_value=mention.normalized_value,
        resolved_entity_id=mention.entity_id,
        resolved_by=resolved_by,
        candidates=candidates,
    )


@router.patch("/{mention_id}", summary="Update a mention", response_model=Mention, **_BY_ALIAS)
async def update_mention(
    mention_id: str, current: MentionDep, data: MentionUpdate, datastore: MentionDatastoreDep, user: CurrentUserDep
) -> Mention:
    """Relabel or correct a mention (predicted type, span, surface text, or resolved entity).

    A new `surface_text` is trimmed and re-keys the mention into the matching name group unless
    `normalized_value` is sent. A changed span or type makes the mention analyst-authored.
    """
    if data.surface_text is not None:
        trimmed = _trimmed_span(
            surface_text=data.surface_text, start_offset=data.start_offset, end_offset=data.end_offset
        )
        for field, value in trimmed.items():
            setattr(data, field, value)
    if data.surface_text is not None and "normalized_value" not in data.model_fields_set:
        data.normalized_value = _normalized_value(
            surface_text=data.surface_text, selector_type=data.selector_type or current.selector_type
        )
    mention = await datastore.update_mention(mention_id, data, reviewed_by=user.id)
    if mention is None:
        raise EntityNotFoundError("Mention", mention_id)
    return mention


@router.delete("/{mention_id}", summary="Delete a mention", dependencies=[Depends(require_mention)])
async def delete_mention(mention_id: str, datastore: MentionDatastoreDep, user: CurrentUserDep) -> dict:
    """Delete a mention span."""
    deleted = await datastore.delete_mention(mention_id, reviewed_by=user.id)
    if not deleted:
        raise EntityNotFoundError("Mention", mention_id)
    return {"deleted": True}


@router.post(
    "/{mention_id}/resolve",
    summary="Resolve a mention",
    response_model=Mention,
    dependencies=[Depends(require_mention)],
    **_BY_ALIAS,
)
async def resolve_mention(
    mention_id: str,
    body: MentionResolve,
    mentions: MentionDatastoreDep,
    entities: EntityDatastoreDep,
    user: CurrentUserDep,
) -> Mention:
    """Attach an unresolved mention to an existing entity, or create a new entity and attach it."""
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
        created = await entities.create_entity(new_entity, detail=detail, source=TagSource.user(user.id))
        entity_id = created.id

    await mentions.attach_to_entity(mention_id, entity_id)
    resolved = await mentions.get_mention(mention_id)
    if resolved is None:
        raise EntityNotFoundError("Mention", mention_id)
    return resolved
