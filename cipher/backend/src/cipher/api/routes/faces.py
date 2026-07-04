from io import BytesIO
from typing import Annotated

from face.api.deps import FaceModelDep, model_lifespan
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from PIL import Image as PILImage
from pydantic import Field

from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import FaceDatastoreDep, FaceMatchDatastoreDep, FaceSimilaritySearchFormParametersDep
from cipher.api.utils import download_uri
from cipher.schemas.base import BaseModel
from cipher.schemas.exceptions import ValidationError
from cipher.schemas.face import (
    BaseFaceSearchParameters,
    Face,
    FaceAssignment,
    FaceBoundingBox,
    FaceEmbedding,
    FaceIdKnnSearchRequest,
    FaceLandmark,
    FaceRepresentativeUpdate,
    FaceSimilaritySearchParameters,
    FaceSimilaritySearchRequest,
    PaginatedFaceSimilarityResponse,
    PaginatedFacesResponse,
    face_annotation_to_face_create,
)
from cipher.schemas.face_match import (
    FaceMatch,
    FaceMatchReview,
    FaceMatchSearchParameters,
    FaceMatchStatus,
    PaginatedFaceMatchesResponse,
)

router = APIRouter(
    prefix="/faces",
    tags=["faces"],
    responses={418: {"description": "I'm a teapot"}},
    lifespan=model_lifespan,
)


class DetectedFace(BaseModel):
    """A face detected in an uploaded photo, not yet persisted."""

    bounding_box: FaceBoundingBox
    landmarks: list[FaceLandmark]
    confidence: float = Field(ge=0, le=1)
    embedding: FaceEmbedding


class FaceMatchResolution(BaseModel):
    """Analyst decision on a candidate match; `reviewed_by` is filled in server-side."""

    status: FaceMatchStatus
    review_note: str | None = None


@router.get(
    "/matches",
    summary="List candidate face-to-person matches",
    response_model=PaginatedFaceMatchesResponse,
    response_model_by_alias=True,
)
async def get_face_matches(
    params: Annotated[FaceMatchSearchParameters, Depends()], datastore: FaceMatchDatastoreDep
):
    """List candidate matches, e.g. a face's pending 'potential matches' for review."""
    return await datastore.list_matches(request=params)


@router.patch(
    "/matches/{id}",
    summary="Resolve a candidate match (confirm or reject)",
    response_model=FaceMatch,
    response_model_by_alias=True,
)
async def resolve_face_match(
    id: str, resolution: FaceMatchResolution, user: CurrentUserDep, datastore: FaceMatchDatastoreDep
):
    """Confirm or reject a candidate match. Confirming assigns the face to the person."""
    match = await datastore.resolve_match(
        match_id=id,
        review=FaceMatchReview(
            status=resolution.status, reviewed_by=user.id, review_note=resolution.review_note
        ),
    )
    if match is None:
        raise HTTPException(status_code=404, detail=f"Face match not found: {id}")
    return match


@router.get("/{id}", summary="Get face by ID", response_model=Face)
async def get_face_by_id(id: str, datastore: FaceDatastoreDep):
    """Get a single face by its ID."""
    face = await datastore.get_face_by_id(face_id=id)
    if face is None:
        raise HTTPException(status_code=404, detail=f"Face not found: {id}")
    return face


@router.get("/{id}/view", summary="Download the source image a face was detected in")
async def download_face_source_image(id: str, datastore: FaceDatastoreDep):
    """Download the source image a face was detected in."""
    uri_info = await datastore.get_face_uri(face_id=id)
    if uri_info is None:
        raise HTTPException(status_code=404, detail=f"Face not found: {id}")
    file_bytes = download_uri(uri_info.uri)
    return Response(content=file_bytes, media_type=uri_info.mime_type)


@router.post(
    "",
    summary="Get paginated list of faces",
    response_model=PaginatedFacesResponse,
    response_model_by_alias=True,
)
async def get_faces(params: BaseFaceSearchParameters, datastore: FaceDatastoreDep):
    """Get all faces, optionally filtered by image/person/quality, with pagination."""
    return await datastore.search_faces(request=params)


@router.get(
    "/search/{id}",
    summary="Find faces similar to an existing face by ID",
    response_model=PaginatedFaceSimilarityResponse,
    response_model_by_alias=True,
)
async def similarity_search_faces_by_id(
    id: str,
    params: Annotated[FaceSimilaritySearchParameters, Depends()],
    datastore: FaceDatastoreDep,
):
    """Find faces similar to an existing face, e.g. to propose identity clusters."""
    request = FaceIdKnnSearchRequest(face_id=id, **params.model_dump())
    return await datastore.search_similar_faces(request=request)


@router.post(
    "/detect",
    summary="Detect faces in an uploaded photo without persisting anything",
    response_model=list[DetectedFace],
    response_model_by_alias=True,
)
async def detect_faces_in_upload(file: UploadFile, model: FaceModelDep):
    """Detect all faces in an uploaded photo, ranked by descending confidence.

    Used to let the caller pick which face to act on (search/create-person)
    before committing to it, when more than one face is found.
    """
    img_bytes = await file.read()
    img = PILImage.open(BytesIO(img_bytes)).convert("RGB")
    annotations = await model.infer_async(img)

    detected = []
    for annotation in annotations:
        face_create = face_annotation_to_face_create(annotation, image_id="")
        detected.append(
            DetectedFace(
                bounding_box=face_create.bounding_box,
                landmarks=face_create.landmarks,
                confidence=face_create.detection_confidence,
                embedding=face_create.embedding,
            )
        )
    detected.sort(key=lambda f: f.confidence, reverse=True)
    return detected


@router.post(
    "/search/embedding",
    summary="Find faces similar to a raw embedding vector",
    response_model=PaginatedFaceSimilarityResponse,
    response_model_by_alias=True,
)
async def similarity_search_faces_by_embedding(
    request: FaceSimilaritySearchRequest, datastore: FaceDatastoreDep
):
    """Find faces similar to an embedding, e.g. one chosen from /faces/detect."""
    return await datastore.search_similar_faces(request=request)


@router.post(
    "/search/image",
    summary="Find faces similar to an uploaded photo",
    response_model=PaginatedFaceSimilarityResponse,
    response_model_by_alias=True,
)
async def similarity_search_faces_by_upload(
    file: UploadFile,
    params: FaceSimilaritySearchFormParametersDep,
    datastore: FaceDatastoreDep,
    model: FaceModelDep,
):
    """Detect the most prominent face in an uploaded photo and find similar faces."""
    img_bytes = await file.read()
    img = PILImage.open(BytesIO(img_bytes)).convert("RGB")
    annotations = await model.infer_async(img)
    if not annotations:
        raise HTTPException(status_code=404, detail="No face detected in uploaded image")

    best = max(annotations, key=lambda a: a["confidence"])
    request = FaceSimilaritySearchRequest.model_validate(
        {**params.model_dump(exclude_none=True), "embedding": best["embedding"]}
    )
    return await datastore.search_similar_faces(request=request)


@router.patch("/{id}/assign", summary="Assign (or unassign) a face to a person", response_model=Face)
async def assign_face(id: str, assignment: FaceAssignment, datastore: FaceDatastoreDep):
    """Assign a face to a person, or clear its assignment when person_id is None."""
    face = await datastore.assign_person(face_id=id, assignment=assignment)
    if face is None:
        raise HTTPException(status_code=404, detail=f"Face not found: {id}")
    return face


@router.patch(
    "/{id}/representative",
    summary="Mark or unmark a face as representative/primary for its person",
    response_model=Face,
)
async def set_face_representative(id: str, data: FaceRepresentativeUpdate, datastore: FaceDatastoreDep):
    """Curate which of a person's assigned faces are used as reference faces."""
    try:
        face = await datastore.set_representative(face_id=id, data=data)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if face is None:
        raise HTTPException(status_code=404, detail=f"Face not found or not assigned to a person: {id}")
    return face


@router.delete("/{id}", summary="Delete face by ID")
async def delete_face(id: str, datastore: FaceDatastoreDep) -> bool:
    """Delete a face by its ID."""
    return await datastore.delete_face(face_id=id)
