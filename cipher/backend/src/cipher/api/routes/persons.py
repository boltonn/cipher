from io import BytesIO
from typing import Annotated
from uuid import uuid4

from face.api.deps import FaceModelDep
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from filetyper.models.magic import MagicNumberFilterTyper
from loguru import logger
from PIL import Image as PILImage

from cipher.api.deps.postgres import (
    CommentDatastoreDep,
    DatasetDatastoreDep,
    EntityDatastoreDep,
    FaceDatastoreDep,
    FaceMatchDatastoreDep,
    FileDatastoreDep,
    GraphDatastoreDep,
    ImageDatastoreDep,
    PersonDatastoreDep,
)
from cipher.api.settings import Settings
from cipher.schemas._base.exceptions import ValidationError
from cipher.schemas.content.image import ImageCreate
from cipher.schemas.identity.face import (
    DEFAULT_FACE_MATCH_SIMILARITY,
    Face,
    FaceAssignment,
    FaceAssignmentMethod,
    FacePublic,
    FaceRepresentativeUpdate,
    face_annotation_to_face_create,
)
from cipher.schemas.identity.face_match import FaceMatchCreate, FaceMatchMethod
from cipher.schemas.identity.person import (
    PaginatedPersonsResponse,
    Person,
    PersonCreate,
    PersonMerge,
    PersonMergeResult,
    PersonMergeSuggestion,
    PersonSearchParameters,
    PersonUpdate,
)
from cipher.schemas.ingestion.dataset import DatasetCreate
from cipher.schemas.ingestion.file import FileCreate
from cipher.schemas.interaction.comment import CommentableType
from cipher.utils.io import HashType, compute_hash

# Same floor the rest of the app treats as "this counts as a match" (the
# similarity search UI's default threshold) -- candidates below this are not
# proposed at all, rather than proposed and left for an analyst to reject.
POTENTIAL_MATCH_MIN_SIMILARITY = DEFAULT_FACE_MATCH_SIMILARITY

# Magic-number based (non-ML) file typing, shared with the ingestion CLI's
# FileTyper -- keeps reference-photo uploads on the same filetype taxonomy
# (e.g. "jpeg" not "jpg") rather than trusting the client-supplied filename.
_file_typer = MagicNumberFilterTyper()

router = APIRouter(
    prefix="/persons",
    tags=["persons"],
    responses={418: {"description": "I'm a teapot"}},
)

settings = Settings()

REFERENCE_DATASET_NAME = "Person References"


async def _get_or_create_reference_dataset(dataset_datastore: DatasetDatastoreDep) -> str:
    """Get or create the dataset that holds uploaded person reference photos."""
    dataset = await dataset_datastore.get_by_name(REFERENCE_DATASET_NAME)
    if dataset:
        return dataset.id
    dataset = await dataset_datastore.add_dataset(
        DatasetCreate(
            name=REFERENCE_DATASET_NAME,
            description="Reference photos uploaded to create or identify people",
        )
    )
    return dataset.id


@router.post("", summary="Create a new person", response_model=Person, response_model_by_alias=True)
async def create_person(
    person: PersonCreate,
    datastore: PersonDatastoreDep,
    entity_datastore: EntityDatastoreDep,
) -> Person:
    """Create a new person.

    Persons created through the app are always verified -- there is no
    manual toggle, since a human explicitly chose to create them.
    """
    person = person.model_copy(update={"is_verified": True})
    created = await datastore.add_person(person)
    await entity_datastore.upsert_person_entity(created)
    return created


@router.get("/{id}", summary="Get person by ID", response_model=Person, response_model_by_alias=True)
async def get_person_by_id(id: str, datastore: PersonDatastoreDep):
    """Get a single person by their ID."""
    person = await datastore.get_person_by_id(person_id=id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"Person not found: {id}")
    return person


@router.get(
    "",
    summary="Get all persons",
    response_model=PaginatedPersonsResponse,
    response_model_by_alias=True,
)
async def get_persons(params: Annotated[PersonSearchParameters, Depends()], datastore: PersonDatastoreDep):
    """Get all persons, optionally filtered by name/tags/verification, with pagination."""
    return await datastore.search_persons(request=params)


async def _create_reference_face(
    file: UploadFile,
    face_index: int,
    model: FaceModelDep,
    dataset_datastore: DatasetDatastoreDep,
    file_datastore: FileDatastoreDep,
    image_datastore: ImageDatastoreDep,
    face_datastore: FaceDatastoreDep,
) -> Face:
    """Detect faces in an uploaded reference photo and persist the chosen one."""
    img_bytes = await file.read()
    img = PILImage.open(BytesIO(img_bytes)).convert("RGB")
    annotations = await model.infer_async(img)
    if not annotations:
        raise HTTPException(status_code=404, detail="No face detected in uploaded image")
    annotations = sorted(annotations, key=lambda a: a["confidence"], reverse=True)
    if face_index >= len(annotations):
        raise HTTPException(
            status_code=400,
            detail=f"face_index {face_index} out of range ({len(annotations)} face(s) detected)",
        )
    best = annotations[face_index]

    dataset_id = await _get_or_create_reference_dataset(dataset_datastore)

    # Never guess a filetype from the client-supplied filename/extension --
    # detect it from the actual bytes, falling back to the upload's declared
    # mime type, and only then to the registry's "unknown" entry.
    type_info = _file_typer.infer_bytes(img_bytes) or _file_typer.map_mime_type_to_filetype_info(
        file.content_type or ""
    )

    settings.person_reference_dir.mkdir(parents=True, exist_ok=True)
    extensions = type_info.get("extensions") or []
    ext = f".{extensions[0]}" if extensions else ""
    dest_path = settings.person_reference_dir / f"{uuid4()}{ext}"
    dest_path.write_bytes(img_bytes)

    file_record = await file_datastore.upsert_file(
        FileCreate(
            dataset_id=dataset_id,
            filename=file.filename or dest_path.name,
            filetype_group=type_info["filetype_group"],
            filetype=type_info["filetype"],
            mime_type=type_info["mime_type"],
            md5=compute_hash(dest_path, HashType.MD5),
            sha256=compute_hash(dest_path, HashType.SHA256),
            size=dest_path.stat().st_size,
            path=str(dest_path.resolve()),
            uri=dest_path.resolve().as_uri(),
        )
    )

    image_record = await image_datastore.upsert_image(
        ImageCreate(id=file_record.sha256, width=img.width, height=img.height),
        file_id=file_record.id,
    )

    face_create = face_annotation_to_face_create(best, image_id=image_record.id, detector_model="insightface-buffalo_l")
    return await face_datastore.add_face(face_create)


async def _propose_potential_matches(
    person_id: str,
    reference_face_id: str,
    face_datastore: FaceDatastoreDep,
    face_match_datastore: FaceMatchDatastoreDep,
) -> list[str]:
    """Propose candidate matches for a newly added reference face.

    Runs inline within the create/add-example request so its response
    already reflects the new `matched` face statuses. Finds still-unassigned
    faces that look similar and records them as pending candidate matches
    for an analyst to confirm or reject, rather than auto-assigning them.

    Returns the ids of the faces a candidate match was proposed for, so the
    caller can refresh their `appears_in_photo_with` edges (a pending match
    is enough to place two people in a photo together).
    """
    candidates = await face_datastore.get_potential_person_matches(
        face_id=reference_face_id,
        min_similarity=POTENTIAL_MATCH_MIN_SIMILARITY,
    )
    matches = [
        FaceMatchCreate(
            face_id=candidate_face_id,
            person_id=person_id,
            similarity_score=similarity_score,
            match_method=FaceMatchMethod.AUTOMATIC_SIMILARITY,
        )
        for candidate_face_id, similarity_score in candidates
    ]
    await face_match_datastore.create_matches_batch(matches)
    return [candidate_face_id for candidate_face_id, _ in candidates]


class PersonFromFaceRequest(PersonCreate):
    """Create-person payload for an already-detected face -- no upload needed."""

    face_id: str


@router.post(
    "/from-face",
    summary="Create a person directly from an already-detected face",
    response_model=Person,
    response_model_by_alias=True,
)
async def create_person_from_face(
    request: PersonFromFaceRequest,
    person_datastore: PersonDatastoreDep,
    face_datastore: FaceDatastoreDep,
    face_match_datastore: FaceMatchDatastoreDep,
    entity_datastore: EntityDatastoreDep,
    graph_datastore: GraphDatastoreDep,
):
    """Create a person from a face that's already been detected and persisted.

    Skips re-upload/re-detection (e.g. picked from the faces browser), and
    runs the same inline similarity sweep as the other creation paths.
    """
    face = await face_datastore.get_face_by_id(face_id=request.face_id)
    if face is None:
        raise HTTPException(status_code=404, detail=f"Face not found: {request.face_id}")

    person = await person_datastore.add_person(
        PersonCreate(
            name=request.name,
            aliases=request.aliases,
            notes=request.notes,
            tags=request.tags,
            date_of_birth=request.date_of_birth,
            sex=request.sex,
            is_verified=True,
        )
    )
    await entity_datastore.upsert_person_entity(person)

    await face_datastore.assign_person(
        face_id=request.face_id,
        assignment=FaceAssignment(person_id=person.id, assignment_method=FaceAssignmentMethod.MANUAL),
    )
    await face_datastore.set_representative(
        face_id=request.face_id, data=FaceRepresentativeUpdate(is_representative=True, is_primary=True)
    )

    candidate_face_ids = await _propose_potential_matches(
        person_id=person.id,
        reference_face_id=request.face_id,
        face_datastore=face_datastore,
        face_match_datastore=face_match_datastore,
    )

    await graph_datastore.recompute_face_cooccurrence_for_faces([request.face_id, *candidate_face_ids])
    return person


@router.post(
    "/from-image",
    summary="Create a person from an uploaded reference photo",
    response_model=Person,
    response_model_by_alias=True,
)
async def create_person_from_image(
    file: UploadFile,
    person_datastore: PersonDatastoreDep,
    face_datastore: FaceDatastoreDep,
    face_match_datastore: FaceMatchDatastoreDep,
    dataset_datastore: DatasetDatastoreDep,
    file_datastore: FileDatastoreDep,
    image_datastore: ImageDatastoreDep,
    entity_datastore: EntityDatastoreDep,
    graph_datastore: GraphDatastoreDep,
    model: FaceModelDep,
    name: Annotated[str | None, Form()] = None,
    sex: Annotated[str | None, Form()] = None,
    date_of_birth: Annotated[str | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form(description="Comma-separated tags")] = None,
    face_index: Annotated[
        int, Form(ge=0, description="Which detected face to use, ranked by descending confidence")
    ] = 0,
):
    """Detect faces in an uploaded photo, store the chosen one, and create a person from it.

    Persons created through the app are always verified -- there is no
    manual toggle, since a human explicitly chose to create them.
    """
    face = await _create_reference_face(
        file, face_index, model, dataset_datastore, file_datastore, image_datastore, face_datastore
    )

    person = await person_datastore.add_person(
        PersonCreate(
            name=name,
            sex=sex,
            date_of_birth=date_of_birth,
            notes=notes,
            tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else [],
            is_verified=True,
        )
    )
    await entity_datastore.upsert_person_entity(person)

    await face_datastore.assign_person(
        face_id=face.id,
        assignment=FaceAssignment(person_id=person.id, assignment_method=FaceAssignmentMethod.MANUAL),
    )
    await face_datastore.set_representative(
        face_id=face.id, data=FaceRepresentativeUpdate(is_representative=True, is_primary=True)
    )

    candidate_face_ids = await _propose_potential_matches(
        person_id=person.id,
        reference_face_id=face.id,
        face_datastore=face_datastore,
        face_match_datastore=face_match_datastore,
    )

    await graph_datastore.recompute_face_cooccurrence_for_faces([face.id, *candidate_face_ids])
    return person


@router.post(
    "/{id}/examples",
    summary="Add a reference/example face to an existing person",
    response_model=Face,
    response_model_by_alias=True,
)
async def add_person_example(
    id: str,
    file: UploadFile,
    person_datastore: PersonDatastoreDep,
    face_datastore: FaceDatastoreDep,
    face_match_datastore: FaceMatchDatastoreDep,
    dataset_datastore: DatasetDatastoreDep,
    file_datastore: FileDatastoreDep,
    image_datastore: ImageDatastoreDep,
    graph_datastore: GraphDatastoreDep,
    model: FaceModelDep,
    face_index: Annotated[
        int, Form(ge=0, description="Which detected face to use, ranked by descending confidence")
    ] = 0,
):
    """Detect a face in an uploaded photo and add it as a representative example for an existing person.

    Capped at 10 representative faces per person (enforced by `set_representative`).
    """
    person = await person_datastore.get_person_by_id(person_id=id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"Person not found: {id}")

    face = await _create_reference_face(
        file, face_index, model, dataset_datastore, file_datastore, image_datastore, face_datastore
    )

    await face_datastore.assign_person(
        face_id=face.id,
        assignment=FaceAssignment(person_id=id, assignment_method=FaceAssignmentMethod.MANUAL),
    )
    try:
        updated = await face_datastore.set_representative(
            face_id=face.id, data=FaceRepresentativeUpdate(is_representative=True)
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    candidate_face_ids = await _propose_potential_matches(
        person_id=id,
        reference_face_id=face.id,
        face_datastore=face_datastore,
        face_match_datastore=face_match_datastore,
    )

    await graph_datastore.recompute_face_cooccurrence_for_faces([face.id, *candidate_face_ids])
    return updated


@router.get(
    "/{id}/representative-faces",
    summary="Get a person's representative faces",
    response_model=list[FacePublic],
    response_model_by_alias=True,
)
async def get_person_representative_faces(id: str, datastore: FaceDatastoreDep):
    """Get a person's representative (reference) faces, primary face first."""
    return await datastore.get_representative_faces(person_id=id)


@router.get(
    "/{id}/merge-candidates",
    summary="Suggest persons that may be the same identity (merge shortlist)",
    response_model=list[PersonMergeSuggestion],
    response_model_by_alias=True,
)
async def get_merge_candidates(
    id: str,
    datastore: PersonDatastoreDep,
    min_similarity: float = 0.5,
    limit: int = 8,
) -> list[PersonMergeSuggestion]:
    """Rank other persons by how closely their representative faces match this one's."""
    person = await datastore.get_person_by_id(person_id=id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"Person not found: {id}")
    return await datastore.suggest_merge_candidates(person_id=id, min_similarity=min_similarity, limit=limit)


@router.post(
    "/{id}/merge",
    summary="Merge another person into this one",
    response_model=PersonMergeResult,
    response_model_by_alias=True,
)
async def merge_person(
    id: str,
    data: PersonMerge,
    person_datastore: PersonDatastoreDep,
    entity_datastore: EntityDatastoreDep,
    face_datastore: FaceDatastoreDep,
    graph_datastore: GraphDatastoreDep,
) -> PersonMergeResult:
    """Fold `source_id` into the person at `{id}`, then delete the source.

    Faces, pending matches, event participations, comments, name mentions,
    relationship edges and the relationship-candidate / entity-match review
    queues all move onto `{id}` (colliding and self-referential rows dropped).
    Moved faces lose their representative/primary flags -- re-pick exemplars on
    the survivor.
    """
    target = await person_datastore.get_person_by_id(person_id=id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Person not found: {id}")
    source = await person_datastore.get_person_by_id(person_id=data.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Person not found: {data.source_id}")

    moved_image_ids = await face_datastore.image_ids_for_person(person_id=data.source_id)

    try:
        result = await person_datastore.merge_persons(target_id=id, source_id=data.source_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    refreshed = await person_datastore.get_person_by_id(person_id=id)
    if refreshed is not None:
        await entity_datastore.upsert_person_entity(refreshed)
    if moved_image_ids:
        await graph_datastore.recompute_face_cooccurrence_for_images(moved_image_ids)
    return result


@router.patch("/{id}", summary="Update a person", response_model=Person, response_model_by_alias=True)
async def update_person(
    id: str,
    data: PersonUpdate,
    datastore: PersonDatastoreDep,
    entity_datastore: EntityDatastoreDep,
):
    """Update a person by their ID."""
    person = await datastore.update_person(person_id=id, data=data)
    if person is None:
        raise HTTPException(status_code=404, detail=f"Person not found: {id}")
    await entity_datastore.upsert_person_entity(person)
    return person


@router.delete("/{id}", summary="Delete person by ID")
async def delete_person(
    id: str,
    datastore: PersonDatastoreDep,
    entity_datastore: EntityDatastoreDep,
    comment_datastore: CommentDatastoreDep,
) -> bool:
    """Delete a person and their bridged entity node.

    Faces are unlinked (``person_id`` set null) and face matches cascade-delete;
    mentions/relationships on the bridge entity unresolve/cascade the same way
    they would for any entity. Comments on either the person or the bridge
    entity (``entity.id == person.id``) reference it polymorphically, so both
    are purged explicitly first.
    """
    deleted = await datastore.delete_person(person_id=id)
    if deleted:
        deleted_comments = await comment_datastore.delete_by_commentable(
            commentable_type=CommentableType.PERSON, commentable_id=id
        ) + await comment_datastore.delete_by_commentable(commentable_type=CommentableType.ENTITY, commentable_id=id)
        await entity_datastore.delete_person_entity(person_id=id)
        logger.info(f"Purged {deleted_comments} comments for person {id} before delete")
    return deleted
