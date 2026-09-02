from io import BytesIO

from fastapi import APIRouter, HTTPException, Query, Response
from pyparse.parsers.email import EmlParser

from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.deps.postgres import ExtractedTextDatastoreDep, FileDatastoreDep, ImageDatastoreDep
from cipher.api.utils import download_uri
from cipher.schemas._base.base import BaseModel
from cipher.schemas.content.document import DocumentMetadata
from cipher.schemas.content.email import EmailBase
from cipher.schemas.content.image import ImagePublic
from cipher.schemas.content.search import ChunkFilters
from cipher.schemas.ingestion.file import File

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


@router.get("/{id}/preview", summary="Browser-displayable JPEG for an image file")
async def preview_image_file(
    id: str,
    datastore: FileDatastoreDep,
    max_dim: int = Query(default=1600, ge=64, le=4096, alias="max"),
):
    """Return a resized inline JPEG for an image file (HEIC/HEIF included, via pillow-heif).

    Works for any image `File` -- no `Image` pipeline row required -- so the map
    and file viewer can show a live preview immediately after ingestion.
    """
    from PIL import Image, ImageOps

    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except ImportError:  # pragma: no cover - HEIC just won't decode
        pass

    file = await datastore.get_file_by_id(file_id=id)
    if file is None or file.uri is None:
        raise HTTPException(status_code=404, detail=f"File not found: {id}")
    if file.filetype_group != "image":
        raise HTTPException(status_code=415, detail=f"Not an image file: {file.filetype}")

    try:
        img = Image.open(BytesIO(download_uri(file.uri)))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((max_dim, max_dim))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
    except Exception as exc:  # noqa: BLE001 - surface any decode failure as 415
        raise HTTPException(status_code=415, detail=f"Could not decode image: {exc}") from exc

    return Response(
        content=buf.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
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
    """A file's extracted text plus how many search chunks it was indexed into."""

    extracted_text_id: str
    text: str
    chunk_count: int


@router.get(
    "/{id}/text",
    summary="Get a file's extracted text",
    response_model=FileText,
)
async def get_file_text(
    id: str,
    extracted_text_datastore: ExtractedTextDatastoreDep,
    chunk_datastore: TextChunkDatastoreDep,
):
    """Return the stored extractor output verbatim.

    Served from the `extracted_text` table rather than rejoined from indexed
    chunks -- chunk `start_offset`/`end_offset` are offsets into this exact
    string, so any reconstruction would break highlighting (and would drop
    content wherever a chunk is missing from the index).
    """
    extracted = await extracted_text_datastore.get_by_file_id(file_id=id)
    if extracted is None:
        raise HTTPException(status_code=404, detail=f"No extracted text found for file: {id}")

    chunk_count = await chunk_datastore.count(filters=ChunkFilters(file_id=id))
    return FileText(extracted_text_id=extracted.id, text=extracted.content, chunk_count=chunk_count)


# Caps the rows returned per sheet regardless of how large the underlying table
# is -- extraction stores the full table (a huge CSV can produce millions of
# rows), and without this cap a single request could ship a multi-hundred-MB
# JSON payload and force the client to parse and hold it all in memory. This
# is a last-resort ceiling, not a pagination window -- the client's table
# viewer virtualizes rendering, so it comfortably handles this many rows in
# memory without needing incremental fetches.
MAX_TABLE_ROWS = 100_000


class FileTableSheet(BaseModel):
    """One extracted table's cells, split into a header row and (possibly capped) data rows."""

    columns: list[str]
    rows: list[list[str]]
    total_rows: int
    truncated: bool


class FileTables(BaseModel):
    """A file's structured tables, if extraction found any (e.g. csv/tsv/xlsx/json)."""

    sheets: list[FileTableSheet]


@router.get(
    "/{id}/table",
    summary="Get a file's structured table data",
    response_model=FileTables,
)
async def get_file_table(id: str, extracted_text_datastore: ExtractedTextDatastoreDep):
    """Return structured tables extracted from a file (csv/tsv/json/jsonl/xlsx/...), if any.

    Each sheet is capped at `MAX_TABLE_ROWS`; `truncated`/`total_rows` tell the
    client when it's only seeing a prefix of the full table.
    """
    extracted = await extracted_text_datastore.get_by_file_id(file_id=id)
    tables = extracted.metadata.tables if extracted and isinstance(extracted.metadata, DocumentMetadata) else None
    if not tables:
        raise HTTPException(status_code=404, detail=f"No table data found for file: {id}")

    sheets = []
    for table in tables:
        if not table.cells:
            continue
        columns, *rows = table.cells
        sheets.append(
            FileTableSheet(
                columns=columns,
                rows=rows[:MAX_TABLE_ROWS],
                total_rows=len(rows),
                truncated=len(rows) > MAX_TABLE_ROWS,
            )
        )
    if not sheets:
        raise HTTPException(status_code=404, detail=f"No table data found for file: {id}")
    return FileTables(sheets=sheets)
