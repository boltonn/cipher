from fastapi import APIRouter, HTTPException, Response
from pyparse.parsers.email import EmlParser

from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.deps.postgres import FileDatastoreDep, ImageDatastoreDep
from cipher.api.utils import download_uri
from cipher.schemas.base import BaseModel
from cipher.schemas.email import EmailBase
from cipher.schemas.file import File
from cipher.schemas.image import ImagePublic

router = APIRouter(
    prefix="/files",
    tags=["files"],
    responses={418: {"description": "I'm a teapot"}},
)


@router.get("/{id}", summary="Get file by ID", response_model=File)
async def get_file(id: str, datastore: FileDatastoreDep):
    """Get a single file by its ID."""
    file = await datastore.get_file_by_id(file_id=id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File not found: {id}")
    return file


@router.get("/{id}/view", summary="Download file by ID")
async def download_file_by_id(id: str, datastore: FileDatastoreDep):
    """Download a single file's raw bytes by its ID."""
    file = await datastore.get_file_by_id(file_id=id)
    if file is None or file.uri is None:
        raise HTTPException(status_code=404, detail=f"File not found: {id}")
    file_bytes = download_uri(file.uri)
    return Response(
        content=file_bytes,
        media_type=file.mime_type,
        headers={"Content-Disposition": f"attachment; filename={file.filename}"},
    )


@router.get(
    "/{id}/email",
    summary="Parse an ingested email file by ID",
    response_model=EmailBase,
)
async def get_file_email(id: str, datastore: FileDatastoreDep):
    """Parse a stored email file on demand and return its structured representation for display."""
    file = await datastore.get_file_by_id(file_id=id)
    if file is None or file.uri is None:
        raise HTTPException(status_code=404, detail=f"File not found: {id}")
    if file.filetype != "eml":
        raise HTTPException(status_code=400, detail=f"Unsupported email filetype: {file.filetype}")
    return EmlParser().parse(download_uri(file.uri))


@router.get(
    "/{id}/image",
    summary="Get the Image record for a file, if the images pipeline has processed it",
    response_model=ImagePublic,
)
async def get_file_image(id: str, image_datastore: ImageDatastoreDep):
    """Look up the Image entity (EXIF metadata, embedding-backed similarity) for a file."""
    image = await image_datastore.get_image_by_file_id(file_id=id)
    if image is None:
        raise HTTPException(status_code=404, detail=f"No image record found for file: {id}")
    return image


class FileText(BaseModel):
    """Reconstructed extracted text for a file, from its indexed search chunks."""

    text: str
    chunk_count: int


@router.get(
    "/{id}/text",
    summary="Get a file's extracted text, reconstructed from its indexed chunks",
    response_model=FileText,
)
async def get_file_text(id: str, file_datastore: FileDatastoreDep, chunk_datastore: TextChunkDatastoreDep):
    """Concatenate a file's indexed text chunks, in original document order."""
    file = await file_datastore.get_file_by_id(file_id=id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File not found: {id}")

    chunks = await chunk_datastore.list_by_file_id(file_id=id)
    if not chunks:
        raise HTTPException(status_code=404, detail=f"No extracted text found for file: {id}")

    ordered = sorted(chunks, key=lambda chunk: chunk.chunk_index)
    return FileText(
        text="\n\n".join(chunk.text for chunk in ordered),
        chunk_count=len(ordered),
    )
