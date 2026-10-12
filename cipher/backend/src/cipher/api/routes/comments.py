from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from cipher.api.deps.access import DatasetAccess, DatasetAccessDep, require_content_access
from cipher.api.deps.postgres import CommentDatastoreDep, EntityDatastoreDep, FileDatastoreDep
from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository
from cipher.datastores.postgres.repositories.file import PostgresFileRepository
from cipher.schemas._base.base import BaseModel
from cipher.schemas.interaction.comment import (
    Comment,
    CommentableType,
    CommentBase,
    CommentCreate,
    CommentPublic,
    CommentUpdate,
)

router = APIRouter(
    prefix="/comments",
    tags=["comments"],
    responses={418: {"description": "I'm a teapot"}},
)


class CommentQueryParams(BaseModel):
    commentable_type: CommentableType
    commentable_id: str


async def _require_commentable(
    *,
    commentable_type: CommentableType,
    commentable_id: str,
    access: DatasetAccess,
    file_datastore: PostgresFileRepository,
    entity_datastore: PostgresEntityRepository,
) -> None:
    """The thing being commented on must exist; dataset content (a dataset, file or image) must be accessible.

    Any entity -- person, organization, location, selector -- is open to everyone.
    """
    if commentable_type == CommentableType.ENTITY:
        if await entity_datastore.get_entity(commentable_id) is None:
            raise HTTPException(status_code=404, detail=f"Entity not found: {commentable_id}")
    elif commentable_type == CommentableType.DATASET:
        access.require(commentable_id)
    elif commentable_type == CommentableType.FILE:
        file = await file_datastore.get_file_by_id(file_id=commentable_id)
        if file is None:
            raise HTTPException(status_code=404, detail=f"File not found: {commentable_id}")
        access.require(file.dataset_id)
    elif commentable_type == CommentableType.IMAGE:
        await require_content_access(sha256s=[commentable_id], access=access, file_datastore=file_datastore)


async def _own_comment(id: str, access: DatasetAccessDep, datastore: CommentDatastoreDep) -> Comment:
    """Guard for `{id}`: only the author (or an admin) may change a comment."""
    comment = await datastore.get_comment_by_id(comment_id=id)
    if comment is None:
        raise HTTPException(status_code=404, detail=f"Comment not found: {id}")
    if comment.user_id != access.user.id and not access.user.is_admin:
        raise HTTPException(status_code=403, detail="You can only change your own comments.")
    return comment


@router.post("", summary="Add a comment", response_model=Comment, response_model_by_alias=True)
async def create_comment(
    payload: CommentBase,
    access: DatasetAccessDep,
    datastore: CommentDatastoreDep,
    file_datastore: FileDatastoreDep,
    entity_datastore: EntityDatastoreDep,
):
    """Add a comment to a dataset, file, image, or any entity (person, organization, location, ...)."""
    await _require_commentable(
        commentable_type=payload.commentable_type,
        commentable_id=payload.commentable_id,
        access=access,
        file_datastore=file_datastore,
        entity_datastore=entity_datastore,
    )
    comment = CommentCreate(**payload.model_dump(), user_id=access.user.id)
    return await datastore.add_comment(comment)


@router.get(
    "",
    summary="Get comments on a resource",
    response_model=list[CommentPublic],
    response_model_by_alias=True,
)
async def get_comments(
    params: Annotated[CommentQueryParams, Depends()],
    access: DatasetAccessDep,
    datastore: CommentDatastoreDep,
    file_datastore: FileDatastoreDep,
    entity_datastore: EntityDatastoreDep,
):
    """Get all comments on a resource, oldest first."""
    await _require_commentable(
        commentable_type=params.commentable_type,
        commentable_id=params.commentable_id,
        access=access,
        file_datastore=file_datastore,
        entity_datastore=entity_datastore,
    )
    return await datastore.get_comments(commentable_type=params.commentable_type, commentable_id=params.commentable_id)


@router.patch(
    "/{id}",
    summary="Update a comment",
    response_model=Comment,
    response_model_by_alias=True,
    dependencies=[Depends(_own_comment)],
)
async def update_comment(id: str, data: CommentUpdate, datastore: CommentDatastoreDep):
    """Update your comment's content."""
    return await datastore.update_comment(comment_id=id, data=data)


@router.delete("/{id}", summary="Delete comment by ID", dependencies=[Depends(_own_comment)])
async def delete_comment(id: str, datastore: CommentDatastoreDep) -> bool:
    """Delete your comment."""
    return await datastore.delete_comment(comment_id=id)
