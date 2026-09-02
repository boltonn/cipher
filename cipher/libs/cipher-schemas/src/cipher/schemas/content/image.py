from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

import numpy as np
from pydantic import BeforeValidator, Field, field_serializer

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PageParams, PaginatedResponse

IMAGE_EMBEDDING_DIMENSION = 512


class ImageSortField(StrEnum):
    SIMILARITY = "similarity"
    DATE_TAKEN = "date_taken"


def _coerce_embedding(v: Any) -> Any:
    """Convert a numpy array to a plain list before `list[float]` validation.

    Pgvector's `Vector` column type deserializes to a numpy array, whose truthiness is
    ambiguous for pydantic's `list[float]` validator.
    """
    return v.tolist() if isinstance(v, np.ndarray) else v


ImageEmbedding = Annotated[
    list[float],
    BeforeValidator(_coerce_embedding),
    Field(min_length=IMAGE_EMBEDDING_DIMENSION, max_length=IMAGE_EMBEDDING_DIMENSION),
]


class ImageBase(BaseModel):
    """Base image schema."""

    width: int = Field(ge=0, description="Width of the image in pixels")
    height: int = Field(ge=0, description="Height of the image in pixels")
    camera_make: str | None = Field(None, description="Camera manufacturer")
    camera_model: str | None = Field(None, description="Camera model")
    focal_length: float | None = Field(None, description="Lens focal length in millimeters")
    aperture: float | None = Field(None, description="Lens aperture (f-number)")
    iso: int | None = Field(None, description="Camera sensor sensitivity")
    date_taken: datetime | None = Field(None, description="Image capture timestamp")
    gps_latitude: float | None = Field(None, ge=-90, le=90, description="EXIF GPS latitude")
    gps_longitude: float | None = Field(None, ge=-180, le=180, description="EXIF GPS longitude")
    gps_altitude: float | None = Field(None, description="Altitude in meters")
    tags: list[str] = Field(default_factory=list, description="Image tags")
    embedding_model: str | None = Field(None, description="Embedding model name")


class ImageCreate(ImageBase):
    """Image creation schema.

    `id` is the sha256 of the image content -- shared by every file with identical
    bytes, so identical images are only ever embedded/stored once.
    """

    id: str
    embedding: ImageEmbedding | None = None


class ImageUpdate(BaseModel):
    """Image update schema."""

    tags: list[str] | None = None
    embedding: ImageEmbedding | None = None
    embedding_model: str | None = None


class Image(ImageBase):
    """Image model for API responses with embedding.

    `id` (the sha256) identifies the image *content*, which is stored once no matter how
    many files share it. `file_id` identifies which occurrence this particular response is
    about -- it's resolved by the caller/repository at read time (any file with this
    content is an equally valid representative), not stored on the image row itself.
    """

    id: str = Field(description="sha256 of the image content")
    file_id: str = Field(description="A file with this content -- picked at read time, not a stored link")
    embedding: ImageEmbedding | None = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "e3b0c44298fc1c149afbfc8996fb92427ae41e4649b934ca495991b7852b855",
                "file_id": "abc123",
                "width": 1080,
                "height": 2400,
                "camera_make": "Apple",
                "camera_model": "iPhone 14 Pro",
                "focal_length": 6.9,
                "aperture": 1.8,
                "iso": 125,
                "date_taken": "2024-07-17T11:38:55Z",
                "gps_altitude": 12.3,
                "tags": ["portrait", "outdoor"],
                "embedding_model": "clip-vit-base-patch16",
            }
        },
    }

    @field_serializer("embedding")
    def serialize_embedding(self, v):
        """Convert numpy array embeddings to lists for JSON serialization."""
        if isinstance(v, np.ndarray):
            return v.tolist()
        return v


class ImagePublic(ImageBase):
    """Image model for public API responses (excludes embedding).

    Search/list responses identify an image only by `id` (its sha256) -- content is
    deduplicated across files, and the set of files an image belongs to is fetched
    separately via `GET /images/{id}/files`. `file_id` is populated only when a
    single occurrence is the subject of the response (e.g. `GET /files/{id}/image`).
    """

    id: str = Field(description="sha256 of the image content")
    file_id: str | None = Field(
        default=None, description="A file with this content -- set only for single-occurrence responses"
    )

    model_config = {"from_attributes": True}


class BaseImageSearchParameters(PageParams):
    """Base parameters for image search."""

    date_from: datetime | None = Field(None, description="Filter images after this date")
    date_to: datetime | None = Field(None, description="Filter images before this date")
    datasets: list[str] | None = Field(None, description="Dataset IDs to filter")
    filetypes: list[str] | None = Field(None, description="File types to filter")
    tags: list[str] | None = Field(None, description="Tags to filter")
    limit: int = Field(10, description="Number of results to return", ge=1, le=100)
    sort_by: ImageSortField = Field(ImageSortField.DATE_TAKEN, description="Sort field")

    model_config = {
        "json_schema_extra": {
            "example": {
                "page": 1,
                "sortBy": "date_taken",
                "sortOrder": "desc",
                "limit": 10,
            }
        }
    }


class ImageSimilaritySearchParameters(BaseImageSearchParameters):
    """Parameters for similarity-based image search."""

    sort_by: ImageSortField = Field(ImageSortField.SIMILARITY, description="Sort field")
    min_similarity: float | None = Field(
        None,
        description="Minimum cosine similarity threshold (0 to 1)",
        ge=0.0,
        le=1.0,
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "page": 1,
                "sortBy": "similarity",
                "minSimilarity": 0,
                "sortOrder": "desc",
                "limit": 10,
            }
        }
    }


class ImageUploadKnnSearchRequest(ImageSimilaritySearchParameters):
    """Search request using uploaded image file."""

    pass


class ImageSimilaritySearchRequest(ImageSimilaritySearchParameters):
    """Search request using embedding vector."""

    embedding: ImageEmbedding = Field(..., description="Embedding vector to search")


class TextImageKnnSearchRequest(ImageSimilaritySearchParameters):
    """Search request using text query."""

    query: str = Field(..., description="Text query to search for similar images")

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "A scenic view of mountains during sunrise",
                "page": 1,
                "sortBy": "similarity",
                "minSimilarity": 0,
                "sortOrder": "desc",
                "limit": 10,
            }
        }
    }


class ImageIdKnnSearchRequest(ImageSimilaritySearchParameters):
    """Search request using image ID."""

    image_id: str = Field(..., description="ID of image to find similar images")

    model_config = {
        "json_schema_extra": {
            "example": {
                "imageId": "123e4567-e89b-12d3-a456-426614174000",
                "page": 1,
                "sortBy": "similarity",
                "minSimilarity": 0,
                "sortOrder": "desc",
                "limit": 10,
            }
        }
    }


class PaginatedImagesResponse(PaginatedResponse):
    """Paginated response for images."""

    data: list[ImagePublic] = Field(..., description="List of images")


class ImageSimilarityResult(ImagePublic):
    """An image returned from a KNN search, carrying its similarity to the query."""

    similarity_score: float = Field(ge=0, le=1, description="Similarity to the query embedding")


class PaginatedImageSimilarityResponse(PaginatedResponse):
    """Paginated response for image similarity search."""

    data: list[ImageSimilarityResult] = Field(description="List of images with similarity scores")
