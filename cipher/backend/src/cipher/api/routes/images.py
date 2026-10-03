from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from loguru import logger
from setfitcv.api.deps import ImageEmbeddingModelDep, model_lifespan

from cipher.api.deps.access import DatasetAccessDep, require_content_access
from cipher.api.deps.postgres import (
    FileDatastoreDep,
    ImageDatastoreDep,
    ImageSimilaritySearchFormParametersDep,
)
from cipher.api.utils import download_uri
from cipher.schemas._base.common import SortOrder
from cipher.schemas.content.image import (
    BaseImageSearchParameters,
    Image,
    ImageAnnotateRequest,
    ImagePublic,
    ImageSimilaritySearchParameters,
    ImageSimilaritySearchRequest,
    ImageTagRequest,
    ImageTagResult,
    ImageUpdate,
    PaginatedImageSimilarityResponse,
    PaginatedImagesResponse,
    TextImageKnnSearchRequest,
)
from cipher.schemas.ingestion.file import File

router = APIRouter(
    prefix="/images",
    tags=["images"],
    responses={418: {"description": "I'm a teapot"}},
    lifespan=model_lifespan,
)


@router.get(
    "/filetypes",
    summary="Get the distinct file types present among images",
    response_model=list[str],
)
async def get_image_filetypes(datastore: ImageDatastoreDep):
    """Get the distinct set of file types actually present among images."""
    return await datastore.get_filetypes()


@router.get("/{id}", summary="Get image by ID", response_model=Image)
async def get_image_by_id(
    id: str, access: DatasetAccessDep, file_datastore: FileDatastoreDep, datastore: ImageDatastoreDep
):
    """Get a single image by its ID."""
    await require_content_access(sha256s=[id], access=access, file_datastore=file_datastore)
    image = await datastore.get_image_by_id(image_id=id)
    if image is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")
    return image


@router.get(
    "/{id}/files",
    summary="List the files this image was found in",
    response_model=list[File],
    response_model_by_alias=True,
)
async def get_image_files(id: str, access: DatasetAccessDep, datastore: ImageDatastoreDep):
    """List every file whose content is this image (matched on sha256), in datasets the user can see."""
    files = [f for f in await datastore.get_files_for_image(image_id=id) if access.allows(f.dataset_id)]
    if not files:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")
    return files


@router.get("/{id}/view", summary="Download image by ID")
async def download_image_by_id(
    id: str, access: DatasetAccessDep, file_datastore: FileDatastoreDep, datastore: ImageDatastoreDep
):
    """Download a single image by its ID."""
    await require_content_access(sha256s=[id], access=access, file_datastore=file_datastore)
    uri_info = await datastore.get_image_uri(image_id=id)
    if uri_info is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")
    file_bytes = download_uri(uri_info.uri)
    return Response(content=file_bytes, media_type=uri_info.mime_type)


@router.get(
    "/search/{id}",
    summary="Perform image similarity search by image ID",
    response_model=PaginatedImageSimilarityResponse,
    response_model_by_alias=True,
)
async def similarity_search_images_by_id(
    id: str,
    # Query() (not Depends()) so list-valued filters (datasets, filetypes) are
    # parsed from repeated query params -- Depends() silently drops them.
    params: Annotated[ImageSimilaritySearchParameters, Query()],
    access: DatasetAccessDep,
    file_datastore: FileDatastoreDep,
    datastore: ImageDatastoreDep,
):
    """Get all images, optionally filtered by a search query, with pagination."""
    await require_content_access(sha256s=[id], access=access, file_datastore=file_datastore)
    params.datasets = access.scope(params.datasets)
    embedding = await datastore.get_embedding_by_image_id(image_id=id)
    if embedding is None:
        if await datastore.get_image_by_id(image_id=id) is None:
            raise HTTPException(status_code=404, detail=f"Image not found: {id}")
        raise HTTPException(status_code=422, detail=f"Image has not been embedded yet: {id}")

    # dont need to validate again
    search_request = ImageSimilaritySearchRequest.model_validate(
        {**params.model_dump(exclude_none=True), "embedding": embedding}
    )
    return await datastore.search_similar_images(request=search_request)


@router.post(
    "/search/text",
    summary="Perform image similarity search by image ID",
    response_model=PaginatedImageSimilarityResponse,
    response_model_by_alias=True,
)
async def similarity_search_images_by_text(
    params: TextImageKnnSearchRequest,
    access: DatasetAccessDep,
    datastore: ImageDatastoreDep,
    model: ImageEmbeddingModelDep,
):
    """Get all images, optionally filtered by a search query, with pagination."""
    params.datasets = access.scope(params.datasets)
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
    access: DatasetAccessDep,
    datastore: ImageDatastoreDep,
):
    """Get all images, optionally filtered by a search query, with pagination."""
    params.datasets = access.scope(params.datasets)
    return await datastore.search_images(request=params)


@router.post(
    "/search/image",
    summary="Perform image similarity search by uploading an image",
    response_model=PaginatedImageSimilarityResponse,
    response_model_by_alias=True,
)
async def similarity_search_images_by_upload(
    file: UploadFile,
    params: ImageSimilaritySearchFormParametersDep,
    access: DatasetAccessDep,
    datastore: ImageDatastoreDep,
    model: ImageEmbeddingModelDep,
):
    """Get all images, optionally filtered by a search query, with pagination."""
    params.datasets = access.scope(params.datasets)
    img_bytes = await file.read()
    embedding = await model.infer_image(image_bytes=img_bytes)

    if embedding is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")

    search_request = ImageSimilaritySearchRequest.model_validate(
        {**params.model_dump(exclude_none=True), "embedding": embedding}
    )
    return await datastore.search_similar_images(request=search_request)


@router.post(
    "/tag",
    summary="Label a set of images with a positive or negative tag, or clear it",
    response_model=ImageTagResult,
    response_model_by_alias=True,
)
async def tag_images(
    body: ImageTagRequest, access: DatasetAccessDep, file_datastore: FileDatastoreDep, datastore: ImageDatastoreDep
):
    """Bulk label: `positive` goes in `tags`, `negative` in `negativeTags`; no `type` clears the label.

    This is also how a predicted tag (`tagScores`) is accepted or rejected.
    """
    await require_content_access(sha256s=body.image_ids, access=access, file_datastore=file_datastore)
    return await datastore.tag_images(
        image_ids=body.image_ids, tag=body.tag, tag_type=body.type, user_id=access.user.id
    )


@router.post(
    "/annotate",
    summary="Save one tag's positive, negative and cleared labels for many images at once",
    response_model=ImageTagResult,
    response_model_by_alias=True,
)
async def annotate_images(
    body: ImageAnnotateRequest,
    access: DatasetAccessDep,
    file_datastore: FileDatastoreDep,
    datastore: ImageDatastoreDep,
):
    """A bulk annotation pass in one transaction -- the save step of a label-many-then-save workflow."""
    image_ids = [*body.positive, *body.negative, *body.cleared]
    if not image_ids:
        return ImageTagResult()
    await require_content_access(sha256s=image_ids, access=access, file_datastore=file_datastore)
    return await datastore.annotate_images(
        tag=body.tag, positive=body.positive, negative=body.negative, cleared=body.cleared, user_id=access.user.id
    )


@router.patch(
    "/{id}",
    summary="Update an image (e.g. tags)",
    response_model=ImagePublic,
    response_model_by_alias=True,
)
async def update_image(
    id: str, data: ImageUpdate, access: DatasetAccessDep, file_datastore: FileDatastoreDep, datastore: ImageDatastoreDep
):
    """Partially update an image (e.g. tags)."""
    await require_content_access(sha256s=[id], access=access, file_datastore=file_datastore)
    image = await datastore.update_image(image_id=id, data=data, user_id=access.user.id)
    if image is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {id}")
    return image


@router.delete("/{id}", summary="Delete image by ID")
async def delete_image(
    id: str, access: DatasetAccessDep, file_datastore: FileDatastoreDep, datastore: ImageDatastoreDep
) -> bool:
    """Delete a image by its ID."""
    await require_content_access(sha256s=[id], access=access, file_datastore=file_datastore)
    return await datastore.delete_image(image_id=id)


@router.post(
    "/search/test-upload",
    summary="Perform image similarity search by uploading an image",
)
async def test_similarity_search_images_by_upload(
    file: UploadFile,
    access: DatasetAccessDep,
    image_datastore: ImageDatastoreDep,
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
        datasets=access.scope(None),
    )
    response = await image_datastore.search_similar_images(request=search_request)
    if not response.data:
        raise HTTPException(status_code=404, detail="Failed test. No similar images found")

    best_img = response.data[0]
    uri_info = await image_datastore.get_image_uri(image_id=best_img.id)
    if uri_info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Failed test. File metadata not found for image ID: {best_img.id}",
        )

    image_path = uri_info.uri.replace("file://", "")
    logger.info(f"Test upload best match image path: {image_path}")
    return Response(
        content=Path(image_path).read_bytes(),
        media_type=uri_info.mime_type,
    )
