from typing import Annotated

from fastapi import APIRouter, Query

from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import EntityDatastoreDep, MentionDatastoreDep
from cipher.schemas.entity import EntityCreate
from cipher.schemas.exceptions import EntityNotFoundError
from cipher.schemas.location import LocationCreate
from cipher.schemas.mention import (
    Mention,
    MentionCreate,
    MentionResolve,
    MentionSearchParameters,
    MentionUpdate,
    PaginatedMentionsResponse,
)
from cipher.schemas.ontology import EntityType
from cipher.schemas.organization import OrganizationCreate
from cipher.schemas.selector import SelectorCreate

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
            detail = detail_model.model_validate(
                {**body.new_entity_detail, "entityId": "", "datasetId": new_entity.dataset_id}
            )
        created = await entities.create_entity(new_entity, detail=detail)
        entity_id = created.id

    await mentions.attach_to_entity(mention_id, entity_id)
    resolved = await mentions.get_mention(mention_id)
    if resolved is None:
        raise EntityNotFoundError("Mention", mention_id)
    return resolved
