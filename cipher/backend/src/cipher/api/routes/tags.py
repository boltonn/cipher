"""Tag provenance: who or what put each tag on a target."""

from typing import Annotated

from fastapi import APIRouter, Query

from cipher.api.deps.access import DatasetAccessDep, require_content_access
from cipher.api.deps.postgres import FileDatastoreDep, TagDatastoreDep
from cipher.schemas.interaction.tag import TagLabelAuthorsRequest, TagPublic, TagTargetType

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get(
    "",
    summary="Who or what tagged a target",
    response_model=list[TagPublic],
    response_model_by_alias=True,
)
async def list_tags(
    target_type: Annotated[TagTargetType, Query(alias="targetType")],
    target_id: Annotated[str, Query(alias="targetId", description="sha256 for content; entity / event id otherwise")],
    access: DatasetAccessDep,
    file_datastore: FileDatastoreDep,
    datastore: TagDatastoreDep,
) -> list[TagPublic]:
    """Every user's and model's decision on the target's tags, newest first (content needs dataset access)."""
    if target_type == TagTargetType.CONTENT:
        await require_content_access(sha256s=[target_id], access=access, file_datastore=file_datastore)
    return await datastore.list_for_target(target_type=target_type, target_id=target_id)


@router.get("/names", summary="Tag names in use, most used first", response_model=list[str])
async def list_tag_names(
    target_type: Annotated[TagTargetType, Query(alias="targetType")],
    datastore: TagDatastoreDep,
    query: Annotated[str | None, Query(description="Substring to match")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[str]:
    """Suggestions for tag pickers and filters."""
    return await datastore.names(target_type=target_type, query=query, limit=limit)


@router.post(
    "/label-authors",
    summary="Other users who labelled a tag on these targets",
    response_model=list[str],
)
async def list_label_authors(
    body: TagLabelAuthorsRequest,
    access: DatasetAccessDep,
    file_datastore: FileDatastoreDep,
    datastore: TagDatastoreDep,
) -> list[str]:
    """Display names of other users whose labels clearing `tag` would remove -- for a confirmation prompt."""
    if body.target_type == TagTargetType.CONTENT:
        await require_content_access(sha256s=body.target_ids, access=access, file_datastore=file_datastore)
    return await datastore.label_authors(
        target_type=body.target_type, target_ids=body.target_ids, tag=body.tag, exclude_user_id=access.user.id
    )
