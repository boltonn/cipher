from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from loguru import logger
from setfitcv.api.deps import ImageEmbeddingModelDep, model_lifespan

from cipher.api.deps.postgres import (
    FileDatastoreDep,
    ImageDatastoreDep,
    ImageSimilaritySearchFormParametersDep,
)
from cipher.api.utils import download_uri
from cipher.schemas.common import SortOrder
from cipher.schemas.image import (
    BaseImageSearchParameters,
    Image,
    ImageSimilaritySearchParameters,
    ImageSimilaritySearchRequest,
    PaginatedImagesResponse,
    TextImageKnnSearchRequest,
)

router = APIRouter(
    prefix="/images",
    tags=["images"],
    responses={418: {"description": "I'm a teapot"}},
    lifespan=model_lifespan,
)


@router.get("/{id}", summary="Get image by ID", response_model=Image)
async def get_image_by_id(id: str, datastore: ImageDatastoreDep):
    """Get a single image by its ID."""
    image = await datastore.get_image_by_id(image_id=id)
    if image is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")
    return image


@router.get("/{id}/view", summary="Download image by ID")
async def download_image_by_id(id: str, datastore: ImageDatastoreDep):
    """Download a single image by its ID."""
    uri_info = await datastore.get_image_uri(image_id=id)
    if uri_info is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")
    file_bytes = download_uri(uri_info.uri)
    return Response(content=file_bytes, media_type=uri_info.mime_type)


@router.get(
    "/search/{id}",
    summary="Perform image similarity search by image ID",
    response_model=PaginatedImagesResponse,
    response_model_by_alias=True,
)
async def similarity_search_images_by_id(
    id: str,
    params: Annotated[ImageSimilaritySearchParameters, Depends()],
    datastore: ImageDatastoreDep,
):
    """Get all images, optionally filtered by a search query, with pagination."""
    embedding = await datastore.get_embedding_by_image_id(image_id=id)
    if embedding is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")

    # dont need to validate again
    search_request = ImageSimilaritySearchRequest.model_validate(
        {**params.model_dump(exclude_none=True), "embedding": embedding}
    )
    return await datastore.search_similar_images(request=search_request)


@router.post(
    "/search/text",
    summary="Perform image similarity search by image ID",
    response_model=PaginatedImagesResponse,
    response_model_by_alias=True,
)
async def similarity_search_images_by_text(
    params: TextImageKnnSearchRequest,
    datastore: ImageDatastoreDep,
    model: ImageEmbeddingModelDep,
):
    """Get all images, optionally filtered by a search query, with pagination."""
    embedding = await model.infer_text(text=params.query)
    if embedding is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")

    search_request = ImageSimilaritySearchRequest.model_validate(
        {**params.model_dump(exclude_none=True), "embedding": embedding}
    )
    return await datastore.search_similar_images(request=search_request)


@router.post(
    "",
    summary="Get paginated list of images",
    response_model=PaginatedImagesResponse,
    response_model_by_alias=True,
)
async def get_images(
    params: BaseImageSearchParameters,
    datastore: ImageDatastoreDep,
):
    """Get all images, optionally filtered by a search query, with pagination."""
    return await datastore.search_images(request=params)


@router.post(
    "/search/image",
    summary="Perform image similarity search by uploading an image",
    response_model=PaginatedImagesResponse,
    response_model_by_alias=True,
)
async def similarity_search_images_by_upload(
    file: UploadFile,
    params: ImageSimilaritySearchFormParametersDep,
    datastore: ImageDatastoreDep,
    model: ImageEmbeddingModelDep,
):
    """Get all images, optionally filtered by a search query, with pagination."""
    img_bytes = await file.read()
    embedding = await model.infer_image(image_bytes=img_bytes)

    if embedding is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")

    search_request = ImageSimilaritySearchRequest.model_validate(
        {**params.model_dump(exclude_none=True), "embedding": embedding}
    )
    return await datastore.search_similar_images(request=search_request)


@router.delete("/{id}", summary="Delete image by ID")
async def delete_image(id: str, datastore: ImageDatastoreDep) -> bool:
    """Delete a image by its ID."""
    return await datastore.delete_image(image_id=id)


@router.post(
    "/search/test-upload",
    summary="Perform image similarity search by uploading an image",
)
async def test_similarity_search_images_by_upload(
    file: UploadFile,
    image_datastore: ImageDatastoreDep,
    file_datastore: FileDatastoreDep,
    model: ImageEmbeddingModelDep,
):
    """Get all images, optionally filtered by a search query, with pagination."""
    img_bytes = await file.read()
    embedding = await model.infer_image(image_bytes=img_bytes)

    if embedding is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")

    search_request = ImageSimilaritySearchRequest(
        embedding=embedding,
        page=1,
        limit=10,
        sort_by="similarity",
        sort_order=SortOrder.DESC,
    )
    response = await image_datastore.search_similar_images(request=search_request)
    if not response.data:
        raise HTTPException(
            status_code=404, detail="Failed test. No similar images found"
        )

    best_img = response.data[0]
    file_example = await file_datastore.get_file_by_id(
        file_id=best_img.file_id,
    )
    if file_example is None:
        raise HTTPException(
            status_code=404,
            detail=f"Failed test. File metadata not found for file ID: {best_img.file_id}",
        )

    image_path = file_example.uri.replace("file://", "")
    logger.info(f"Test upload best match image path: {image_path}")
    return Response(
        content=Path(image_path).read_bytes(),
        media_type=file_example.mime_type,
    )
