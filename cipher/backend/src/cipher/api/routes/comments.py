from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import CommentDatastoreDep
from cipher.schemas.base import BaseModel
from cipher.schemas.comment import (
    Comment,
    CommentBase,
    CommentableType,
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


@router.post("", summary="Add a comment", response_model=Comment, response_model_by_alias=True)
async def create_comment(payload: CommentBase, user: CurrentUserDep, datastore: CommentDatastoreDep):
    """Add a comment to a resource (dataset, image, person, ...)."""
    comment = CommentCreate(**payload.model_dump(), user_id=user.id)
    return await datastore.add_comment(comment)


@router.get(
    "",
    summary="Get comments on a resource",
    response_model=list[CommentPublic],
    response_model_by_alias=True,
)
async def get_comments(
    params: Annotated[CommentQueryParams, Depends()], datastore: CommentDatastoreDep
):
    """Get all comments on a resource, oldest first."""
    return await datastore.get_comments(
        commentable_type=params.commentable_type, commentable_id=params.commentable_id
    )


@router.patch("/{id}", summary="Update a comment", response_model=Comment, response_model_by_alias=True)
async def update_comment(id: str, data: CommentUpdate, datastore: CommentDatastoreDep):
    """Update a comment's content."""
    comment = await datastore.update_comment(comment_id=id, data=data)
    if comment is None:
        raise HTTPException(status_code=404, detail=f"Comment not found: {id}")
    return comment


@router.delete("/{id}", summary="Delete comment by ID")
async def delete_comment(id: str, datastore: CommentDatastoreDep) -> bool:
    """Delete a comment by its ID."""
    return await datastore.delete_comment(comment_id=id)
