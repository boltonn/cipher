from datetime import datetime
from enum import StrEnum
from typing import Annotated, NotRequired, TypedDict

import numpy as np
from pydantic import Field, field_serializer

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PageParams, PaginatedResponse, Sex
from cipher.schemas._base.detection import BoundingBox

FACE_EMBEDDING_DIMENSION = 512

FaceEmbedding = Annotated[
    list[float],
    Field(min_length=FACE_EMBEDDING_DIMENSION, max_length=FACE_EMBEDDING_DIMENSION),
]

DEFAULT_FACE_MATCH_SIMILARITY = 0.61
"""Datastore-wide default for 'this counts as a match': the floor used
whenever similarity search runs without an analyst-chosen threshold (e.g.
the background matching pipeline), and the UI's default slider position."""

DEFAULT_FACE_REJECT_SIMILARITY = 0.64
"""Floor for auto-rejecting a face as 'not a face': an unassigned face at least
this similar to one an analyst manually rejected (e.g. the same cat) is
rejected automatically, flagged `rejection_method=automatic` so it can be undone."""


class FaceAssignmentMethod(StrEnum):
    """How a face came to be linked to a person."""

    MANUAL = "manual"
    AUTOMATIC = "automatic"


class FaceSortField(StrEnum):
    DATE_CREATED = "date_created"
    QUALITY = "quality_score"
    DETECTION_CONFIDENCE = "detection_confidence"
    SIMILARITY = "similarity"


class FaceStatus(StrEnum):
    """At-a-glance triage status for a face.

    Combines assignment, pending candidate matches, and the assigned
    person's verification state.

    UNMATCHED: no person assigned, no pending candidates either.
    MATCHED: either assigned to a person who isn't yet verified, or not
        assigned but has one or more pending `FaceMatch` candidates.
    VERIFIED: assigned to a person who has been verified.
    REJECTED: not a face (detector false positive, e.g. a pet), marked by an
        analyst or auto-rejected by similarity to one an analyst marked.
    """

    UNMATCHED = "unmatched"
    MATCHED = "matched"
    VERIFIED = "verified"
    REJECTED = "rejected"


class FaceBoundingBox(BaseModel):
    """Face location within an image, normalized to image width/height."""

    x: float = Field(ge=0, le=1, description="Normalized left edge")
    y: float = Field(ge=0, le=1, description="Normalized top edge")
    width: float = Field(gt=0, le=1, description="Normalized width")
    height: float = Field(gt=0, le=1, description="Normalized height")


class FaceLandmark(BaseModel):
    """A single facial keypoint, normalized to image width/height.

    Unlike the bounding box, landmarks are not clamped to [0, 1] by the
    detector: an occluded or near-edge keypoint is still estimated, and
    that estimate can fall slightly outside the frame.
    """

    x: float
    y: float
    label: str | None = Field(default=None, description="Keypoint name, e.g. 'left_eye', 'nose_tip'")


class FacePose(BaseModel):
    """Head pose relative to the camera, in degrees."""

    yaw: float = Field(description="Left/right rotation")
    pitch: float = Field(description="Up/down rotation")
    roll: float = Field(description="Tilt rotation")


class FaceBase(BaseModel):
    """Base face schema."""

    bounding_box: FaceBoundingBox
    landmarks: list[FaceLandmark] = Field(default_factory=list)
    detector_model: str | None = Field(default=None, description="Face detector model name")
    detection_confidence: float | None = Field(
        default=None, ge=0, le=1, description="Detector's confidence this is a face"
    )
    quality_score: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Usability of this face for recognition (pose/blur/occlusion)",
    )
    pose: FacePose | None = Field(default=None, description="Head pose, if estimated")
    embedding_model: str | None = Field(default=None, description="Face embedding model name")


class FaceCreate(FaceBase):
    """Face creation schema, produced by a face detection/embedding job."""

    image_id: str
    embedding: FaceEmbedding | None = Field(default=None)


class FaceUpdate(BaseModel):
    """Face update schema for revising detection metadata."""

    quality_score: float | None = Field(default=None)
    embedding: FaceEmbedding | None = Field(default=None)
    embedding_model: str | None = Field(default=None)


class FaceAssignment(BaseModel):
    """Schema for linking (or relinking) a face to a person."""

    person_id: str | None = Field(default=None, description="Person to assign; None clears the assignment")
    assignment_method: FaceAssignmentMethod = Field(default=FaceAssignmentMethod.MANUAL)
    assignment_confidence: float | None = Field(default=None, ge=0, le=1)


class FaceRejection(BaseModel):
    """Mark (or unmark) a set of faces as not a face.

    Rejecting unassigns each face, rejects its pending matches, and -- unless
    `reject_similar` is off -- auto-rejects unassigned faces at least
    `min_similarity` similar to them (e.g. more photos of the same cat).
    """

    face_ids: list[str] = Field(min_length=1, max_length=1000)
    reject_similar: bool = Field(default=True)
    min_similarity: float = Field(default=DEFAULT_FACE_REJECT_SIMILARITY, ge=0, le=1)


class FaceRejectionResult(BaseModel):
    """Outcome of a reject/unreject call."""

    updated: int = Field(default=0, description="Faces whose rejection state changed as asked")
    auto_rejected: int = Field(default=0, description="Similar faces auto-rejected alongside")


class FaceRepresentativeUpdate(BaseModel):
    """Schema for curating a person's representative (reference) faces.

    A person has no single centroid embedding; instead, one or more of
    their assigned faces are marked representative and matched against
    directly. `is_primary` marks the one used for display (e.g. thumbnail)
    and implies `is_representative`; only one face per person may be
    primary at a time.
    """

    is_representative: bool = Field(default=True)
    is_primary: bool = Field(default=False)


class Face(FaceBase):
    """Face model for API responses, includes the embedding."""

    id: str
    image_id: str
    person_id: str | None = Field(default=None)
    assignment_method: FaceAssignmentMethod | None = Field(default=None)
    assignment_confidence: float | None = Field(default=None)
    is_representative: bool = Field(default=False, description="Used as a reference face when matching this person")
    is_primary: bool = Field(default=False, description="This person's primary/display face")
    date_rejected: datetime | None = Field(default=None, description="When this was marked not a face")
    rejection_method: FaceAssignmentMethod | None = Field(default=None)
    rejection_confidence: float | None = Field(
        default=None, description="Similarity to the analyst-rejected face that triggered an automatic rejection"
    )
    embedding: FaceEmbedding | None = Field(default=None)
    date_created: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "imageId": "123e4567-e89b-12d3-a456-426614174001",
                "personId": None,
                "boundingBox": {"x": 0.32, "y": 0.18, "width": 0.22, "height": 0.3},
                "landmarks": [{"x": 0.38, "y": 0.28, "label": "left_eye"}],
                "detectorModel": "retinaface",
                "detectionConfidence": 0.99,
                "qualityScore": 0.87,
                "pose": {"yaw": 4.2, "pitch": -1.5, "roll": 0.3},
                "embeddingModel": "arcface-r100",
                "isRepresentative": False,
                "isPrimary": False,
                "dateCreated": "2024-01-01T12:00:00Z",
            }
        },
    }

    @field_serializer("embedding")
    def serialize_embedding(self, v):
        """Convert numpy array embeddings to lists for JSON serialization."""
        if isinstance(v, np.ndarray):
            return v.tolist()
        return v


class FacePublic(FaceBase):
    """Face model for public API responses (excludes embedding).

    Carries the underlying file's `uri` denormalized in, so a frontend
    rendering a page of face thumbnails doesn't need a follow-up request
    per face just to find the image to crop from. Also carries a computed
    `status` (and, when relevant, the top pending-match candidate) so a grid
    of face cards doesn't need a per-card follow-up request either.
    """

    id: str
    image_id: str
    uri: str = Field(description="URI of the image file this face was detected in")
    person_id: str | None = Field(default=None)
    person_name: str | None = Field(
        default=None, description="Assigned person's name, denormalized so a face grid needn't fetch it per card"
    )
    assignment_method: FaceAssignmentMethod | None = Field(default=None)
    is_representative: bool = Field(default=False)
    is_primary: bool = Field(default=False)
    date_rejected: datetime | None = Field(default=None)
    rejection_method: FaceAssignmentMethod | None = Field(default=None)
    rejection_confidence: float | None = Field(default=None)
    status: FaceStatus = Field(default=FaceStatus.UNMATCHED)
    candidate_person_id: str | None = Field(
        default=None, description="Top pending-match candidate's person id, when not yet assigned"
    )
    candidate_person_name: str | None = Field(default=None)

    model_config = {"from_attributes": True}


class BaseFaceSearchParameters(PageParams):
    """Base parameters for face search."""

    image_id: str | None = Field(default=None, description="Filter to faces in this image")
    datasets: list[str] | None = Field(default=None, description="Filter to faces in images from these datasets")
    person_id: str | None = Field(default=None, description="Filter to faces of this person")
    unassigned_only: bool = Field(default=False, description="Only return faces with no person assigned")
    representative_only: bool = Field(default=False, description="Only return representative faces")
    rejected_only: bool = Field(
        default=False, description="Only return faces marked not a face (otherwise they're excluded)"
    )
    min_quality: float | None = Field(default=None, ge=0, le=1)
    min_size: int | None = Field(
        default=None,
        ge=0,
        description="Minimum face crop size in pixels (shorter of width/height, using the source image's resolution)",
    )
    person_ids: list[str] | None = Field(
        default=None,
        description="Filter to faces assigned to, or with a pending match for, any of these persons",
    )
    limit: int = Field(default=10, ge=1, le=100)
    sort_by: FaceSortField = Field(default=FaceSortField.DETECTION_CONFIDENCE)


class FaceSimilaritySearchParameters(BaseFaceSearchParameters):
    """Parameters for similarity-based face search."""

    sort_by: FaceSortField = Field(default=FaceSortField.SIMILARITY)
    min_similarity: float | None = Field(default=DEFAULT_FACE_MATCH_SIMILARITY, ge=0, le=1)


class FaceSimilaritySearchRequest(FaceSimilaritySearchParameters):
    """Search request using an embedding vector directly."""

    embedding: FaceEmbedding = Field(description="Embedding vector to search")


class FaceIdKnnSearchRequest(FaceSimilaritySearchParameters):
    """Search request for faces similar to an existing face (e.g. for clustering)."""

    face_id: str = Field(description="ID of face to find similar faces for")


class PaginatedFacesResponse(PaginatedResponse):
    """Paginated response for faces."""

    data: list[FacePublic] = Field(description="List of faces")


class FaceSimilarityResult(FacePublic):
    """A face returned from a KNN search, carrying its similarity to the query."""

    similarity_score: float = Field(ge=0, le=1, description="Similarity to the query embedding")


class PaginatedFaceSimilarityResponse(PaginatedResponse):
    """Paginated response for face similarity search."""

    data: list[FaceSimilarityResult] = Field(description="List of faces with similarity scores")


class FaceLandmarks5(BaseModel):
    """Raw 5-point facial landmarks in InsightFace's flat field order.

    Field order defines the contract that model output is zipped onto (see
    `cipher.schemas._base.detection.BoundingBox`); convert to `list[FaceLandmark]`
    before persisting.
    """

    lefteye_x: float
    lefteye_y: float
    righteye_x: float
    righteye_y: float
    nose_x: float
    nose_y: float
    leftmouth_x: float
    leftmouth_y: float
    rightmouth_x: float
    rightmouth_y: float


class FaceAnnotation(TypedDict):
    """Raw output of a face detection/embedding model for a single face.

    `pose`/`age`/`sex` are only present when the producing model was
    constructed with the corresponding `get_pose`/`get_age_and_sex` flag.
    """

    bbox: dict[str, float]
    confidence: float
    landmarks: dict[str, float]
    embedding: list[float] | None
    pose: NotRequired[dict[str, float]]
    age: NotRequired[float]
    sex: NotRequired[Sex]


def face_annotation_to_face_create(
    annotation: FaceAnnotation,
    image_id: str,
    detector_model: str | None = None,
    embedding_model: str | None = None,
) -> FaceCreate:
    """Convert a raw model annotation into the schema used for persistence.

    `age`/`sex`, if present on the annotation, aren't persisted: `FaceCreate`
    has no field for them today.
    """
    bbox = BoundingBox(**annotation["bbox"])
    landmarks = FaceLandmarks5(**annotation["landmarks"])
    pose = annotation.get("pose")

    return FaceCreate(
        image_id=image_id,
        bounding_box=FaceBoundingBox(
            x=bbox.xmin,
            y=bbox.ymin,
            width=bbox.xmax - bbox.xmin,
            height=bbox.ymax - bbox.ymin,
        ),
        landmarks=[
            FaceLandmark(x=landmarks.lefteye_x, y=landmarks.lefteye_y, label="left_eye"),
            FaceLandmark(x=landmarks.righteye_x, y=landmarks.righteye_y, label="right_eye"),
            FaceLandmark(x=landmarks.nose_x, y=landmarks.nose_y, label="nose_tip"),
            FaceLandmark(x=landmarks.leftmouth_x, y=landmarks.leftmouth_y, label="left_mouth"),
            FaceLandmark(x=landmarks.rightmouth_x, y=landmarks.rightmouth_y, label="right_mouth"),
        ],
        detector_model=detector_model,
        detection_confidence=annotation["confidence"],
        pose=FacePose(**pose) if pose else None,
        embedding=annotation["embedding"],
        embedding_model=embedding_model,
    )
