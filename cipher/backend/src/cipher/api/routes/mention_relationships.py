"""Relationships between mentions of one text, and the email-signature review built on them.

An extractor (the email-signature reader, an LLM pack, GLiNER) proposes relationships between
spans before either is resolved; analysts can draw their own. Each is reviewed in its text:
accepted (becomes an entity edge once both ends are resolved), rejected, corrected, or reopened.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from cipher.api.deps.access import DatasetAccessDep
from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import MentionDatastoreDep, MentionRelationshipDatastoreDep
from cipher.schemas._base.exceptions import EntityNotFoundError
from cipher.schemas.graph.mention_relationship import (
    EmailSignature,
    EmailSignatureSearchParameters,
    MentionRelationshipDraft,
    MentionRelationshipUpdate,
    MentionRelationshipView,
    PaginatedEmailSignaturesResponse,
)

router = APIRouter(tags=["mention relationships"])

_BY_ALIAS = {"response_model_by_alias": True}


async def _view(
    relation_id: str, access: DatasetAccessDep, relations: MentionRelationshipDatastoreDep
) -> MentionRelationshipView:
    view = await relations.get_view(relation_id)
    if view is None:
        raise EntityNotFoundError("MentionRelationship", relation_id)
    access.require(view.dataset_id)
    return view


def _unprocessable(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/email-signatures",
    summary="Email-signature review queue",
    response_model=PaginatedEmailSignaturesResponse,
    **_BY_ALIAS,
)
async def list_email_signatures(
    params: Annotated[EmailSignatureSearchParameters, Query()],
    access: DatasetAccessDep,
    relations: MentionRelationshipDatastoreDep,
) -> PaginatedEmailSignaturesResponse:
    """Emails whose sender's email signature was read, newest first, with relationships left to review."""
    params.dataset_ids = access.narrow(params.dataset_ids).scope(None)
    return await relations.list_email_signatures(params)


@router.get(
    "/email-signatures/{file_id}",
    summary="Where an email's email signature is",
    response_model=EmailSignature,
    **_BY_ALIAS,
)
async def get_email_signature(
    file_id: str, access: DatasetAccessDep, relations: MentionRelationshipDatastoreDep
) -> EmailSignature:
    """The span of the email's text its email signature covers."""
    signature = await relations.get_email_signature(file_id)
    if signature is None:
        raise EntityNotFoundError("EmailSignature", file_id)
    access.require(signature.dataset_id)
    return signature


@router.get(
    "/mention-relationships",
    summary="Relationships between mentions of a file",
    response_model=list[MentionRelationshipView],
    **_BY_ALIAS,
)
async def list_mention_relationships(
    file_id: Annotated[str, Query(alias="fileId")],
    access: DatasetAccessDep,
    relations: MentionRelationshipDatastoreDep,
) -> list[MentionRelationshipView]:
    """Every relationship proposed or drawn between two mentions of the file, with both mentions."""
    return [view for view in await relations.list_for_file(file_id) if access.allows(view.dataset_id)]


@router.post(
    "/mention-relationships",
    summary="Draw a relationship between two mentions",
    response_model=MentionRelationshipView,
    **_BY_ALIAS,
)
async def create_mention_relationship(
    draft: MentionRelationshipDraft,
    access: DatasetAccessDep,
    mentions: MentionDatastoreDep,
    relations: MentionRelationshipDatastoreDep,
) -> MentionRelationshipView:
    """Record an analyst-drawn relationship (pending until accepted, like an extracted one)."""
    src = await mentions.get_mention(draft.src_mention_id)
    if src is None:
        raise EntityNotFoundError("Mention", draft.src_mention_id)
    access.require(src.dataset_id)
    try:
        return await relations.create_manual(draft)
    except ValueError as exc:
        raise _unprocessable(exc) from exc


@router.patch(
    "/mention-relationships/{relation_id}",
    summary="Correct a relationship",
    response_model=MentionRelationshipView,
    **_BY_ALIAS,
)
async def update_mention_relationship(
    relation_id: str,
    patch: MentionRelationshipUpdate,
    access: DatasetAccessDep,
    relations: MentionRelationshipDatastoreDep,
) -> MentionRelationshipView:
    """Change a pending relationship's type, attributes (role) or direction."""
    await _view(relation_id, access, relations)
    try:
        return await relations.update_relation(relation_id, patch)
    except ValueError as exc:
        raise _unprocessable(exc) from exc


@router.post(
    "/mention-relationships/{relation_id}/accept",
    summary="Accept a relationship",
    response_model=MentionRelationshipView,
    **_BY_ALIAS,
)
async def accept_mention_relationship(
    relation_id: str, user: CurrentUserDep, access: DatasetAccessDep, relations: MentionRelationshipDatastoreDep
) -> MentionRelationshipView:
    """Add it to the graph as an entity edge; both ends must be resolved first."""
    await _view(relation_id, access, relations)
    try:
        return await relations.accept(relation_id, reviewed_by=user.id)
    except ValueError as exc:
        raise _unprocessable(exc) from exc


@router.post(
    "/mention-relationships/{relation_id}/reject",
    summary="Reject a relationship",
    response_model=MentionRelationshipView,
    **_BY_ALIAS,
)
async def reject_mention_relationship(
    relation_id: str, user: CurrentUserDep, access: DatasetAccessDep, relations: MentionRelationshipDatastoreDep
) -> MentionRelationshipView:
    """Not a real relationship; never offered again."""
    await _view(relation_id, access, relations)
    return await relations.reject(relation_id, reviewed_by=user.id)


@router.post(
    "/mention-relationships/{relation_id}/reopen",
    summary="Reopen a reviewed relationship",
    response_model=MentionRelationshipView,
    **_BY_ALIAS,
)
async def reopen_mention_relationship(
    relation_id: str, access: DatasetAccessDep, relations: MentionRelationshipDatastoreDep
) -> MentionRelationshipView:
    """Back to pending; an accepted one's analyst-made edge is removed."""
    await _view(relation_id, access, relations)
    return await relations.reopen(relation_id)


@router.delete("/mention-relationships/{relation_id}", summary="Delete a drawn relationship")
async def delete_mention_relationship(
    relation_id: str, access: DatasetAccessDep, relations: MentionRelationshipDatastoreDep
) -> dict:
    """Delete one an analyst drew; extracted ones are rejected instead."""
    await _view(relation_id, access, relations)
    if not await relations.delete_manual(relation_id):
        raise HTTPException(status_code=422, detail="Only a relationship you drew can be deleted; reject this one")
    return {"deleted": True}
