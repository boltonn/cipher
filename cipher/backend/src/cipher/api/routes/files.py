from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Annotated

from clir.api.deps import TextEmbeddingModelDep
from fastapi import APIRouter, Body, HTTPException, Query, Response
from filetyper.models.magic import MagicNumberFilterTyper
from pydantic import Field
from pyparse.parsers.email import SUPPORTED_FILETYPES as SUPPORTED_EMAIL_FILETYPES, EmailOptions, parse_email
from pyparse.parsers.email.quotes import find_quoted_blocks
from pyparse.parsers.email.subjects import subject_key

from cipher.api.deps.access import DatasetAccess, DatasetAccessDep
from cipher.api.deps.authentication import AdminOnly, CurrentUserDep
from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.deps.postgres import (
    EnrichmentDatastoreDep,
    ExtractedTextDatastoreDep,
    FileDatastoreDep,
    ImageDatastoreDep,
)
from cipher.api.utils import download_uri
from cipher.datastores.postgres.repositories.file import PostgresFileRepository
from cipher.datastores.postgres.tables.file import FileTable
from cipher.orchestration.quoted_copies import QuotingEmail, linked_by_quotes, quoting_email
from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import ModelTagType, TagRequest, TagsUpdate
from cipher.schemas.content.document import DocumentMetadata
from cipher.schemas.content.email import (
    ConversationEmail,
    ConversationSource,
    EmailBase,
    EmailConversation,
    EmailMetadata,
)
from cipher.schemas.content.image import ImagePublic
from cipher.schemas.content.search import FileSummary
from cipher.schemas.content.text_correction import TextCorrectionRequest, TextCorrectionSummary
from cipher.schemas.ingestion.file import File, FilesTagRequest
from cipher.schemas.interaction.tag import TagSource

router = APIRouter(
    prefix="/files",
    tags=["files"],
    responses={418: {"description": "I'm a teapot"}},
)


async def get_accessible_file(*, file_id: str, datastore: PostgresFileRepository, access: DatasetAccess) -> File:
    """The file, if it exists (404) and is in a dataset the user can see (403)."""
    file = await datastore.get_file_by_id(file_id=file_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
    access.require(file.dataset_id)
    return file


@router.post("/tag", summary="Tag many files at once", status_code=204)
async def tag_files(body: FilesTagRequest, access: DatasetAccessDep, datastore: FileDatastoreDep) -> None:
    """Label every listed file's content with `tag` as yours (every copy of the bytes follows)."""
    for file_id in dict.fromkeys(body.file_ids):
        await get_accessible_file(file_id=file_id, datastore=datastore, access=access)
    await datastore.tag_files(
        file_ids=body.file_ids, tag=body.tag, label=ModelTagType.POSITIVE, source=TagSource.user(access.user.id)
    )


@router.get("/{id}", summary="Get file by ID", response_model=File)
async def get_file(id: str, access: DatasetAccessDep, datastore: FileDatastoreDep):
    """Get a single file by its ID."""
    return await get_accessible_file(file_id=id, datastore=datastore, access=access)


@router.get("/{id}/children", summary="Files found inside a file", response_model=list[File])
async def get_file_children(
    id: str,
    access: DatasetAccessDep,
    datastore: FileDatastoreDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
):
    """An email's attachments or an archive's members, in path order."""
    await get_accessible_file(file_id=id, datastore=datastore, access=access)
    return await datastore.list_children(parent_id=id, limit=limit)


@router.patch("/{id}/tag", summary="Toggle a positive or negative tag on a file", response_model=File)
async def toggle_file_tag(
    id: str, tag_data: Annotated[TagRequest, Body(...)], access: DatasetAccessDep, datastore: FileDatastoreDep
):
    """Toggle a tag: `positive` goes in `tags`, `negative` in `negativeTags`; a tag is in at most one."""
    await get_accessible_file(file_id=id, datastore=datastore, access=access)
    file = await datastore.toggle_tag(file_id=id, tag=tag_data.tag, tag_type=tag_data.type, user_id=access.user.id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return file


@router.put("/{id}/tags", summary="Set a file's tags", response_model=File)
async def set_file_tags(
    id: str, data: Annotated[TagsUpdate, Body(...)], access: DatasetAccessDep, datastore: FileDatastoreDep
):
    """Set the positive tags of the file's content (every copy shares them); changes are recorded as yours."""
    await get_accessible_file(file_id=id, datastore=datastore, access=access)
    return await datastore.set_tags(file_id=id, tags=data.tags, user_id=access.user.id)


_summary_runner = None


def _runner():
    """One prompt runner for the app's lifetime (same `LLM__*` settings as chat)."""
    global _summary_runner
    if _summary_runner is None:
        from pyprompt import PromptRunner, Settings

        _summary_runner = PromptRunner(Settings())
    return _summary_runner


def _summary(chunk) -> FileSummary:
    return FileSummary(
        chunk_id=chunk.id,
        sha256=chunk.sha256,
        text=chunk.text,
        generated_by=chunk.generated_by,
        date_created=chunk.date_created,
    )


@router.get("/{id}/summary", summary="A file's cached AI summary", response_model=FileSummary)
async def get_file_summary(id: str, access: DatasetAccessDep, datastore: FileDatastoreDep):
    """404 until the file (or a content-identical one in the dataset) has been summarized."""
    from cipher.orchestration.summarize import existing_summary

    await get_accessible_file(file_id=id, datastore=datastore, access=access)
    file = await datastore.session.get(FileTable, id)
    chunk = await existing_summary(datastore.session, file)
    if chunk is None:
        raise HTTPException(status_code=404, detail="Not summarized yet")
    return _summary(chunk)


@router.post(
    "/{id}/summary", summary="Summarize a file with the LLM (cached as a summary chunk)", response_model=FileSummary
)
async def summarize_file(
    id: str,
    access: DatasetAccessDep,
    datastore: FileDatastoreDep,
    model: TextEmbeddingModelDep,
    force: Annotated[bool, Query(description="Write a fresh summary even if one is cached")] = False,
):
    """Return the file's summary, writing one first if its content has none (or `force`).

    Stored as a summary chunk (embedded now, so it's searchable straight away) and shared by
    content-identical files; another dataset's summary is reused. 422 when there's nothing to read yet.
    """
    from cipher.orchestration.summarize import summarize_file as summarize

    async def embed(text: str) -> list[float]:
        return await model.infer(text=text, task="retrieval", is_query=False)

    await get_accessible_file(file_id=id, datastore=datastore, access=access)
    chunk = await summarize(datastore.session, _runner(), id, embed=embed, force=force)
    if chunk is None:
        raise HTTPException(status_code=422, detail="Nothing to summarize yet: extract its text or map the table first")
    return _summary(chunk)


_file_typer = MagicNumberFilterTyper()


class FiletypeUpdate(BaseModel):
    """A corrected filetype, by registry name (e.g. `wmv`); group and MIME type follow from the registry."""

    filetype: str


@router.patch("/{id}/filetype", summary="Correct a file's filetype", response_model=File, dependencies=[AdminOnly])
async def set_file_filetype(
    id: str,
    data: Annotated[FiletypeUpdate, Body(...)],
    access: DatasetAccessDep,
    datastore: FileDatastoreDep,
    enrichments: EnrichmentDatastoreDep,
):
    """Admin: correct a misdetected filetype on every copy of the file's content.

    Unfinished enrichment rows (queued or failed under the wrong type) are dropped, so each
    step's next run re-queues the file only if it fits the corrected type.
    """
    file = await get_accessible_file(file_id=id, datastore=datastore, access=access)
    info = _file_typer.get_filetype_info(data.filetype)
    if info is None:
        raise HTTPException(status_code=400, detail=f"Unknown filetype: {data.filetype}")
    file_ids = await datastore.set_filetype(
        sha256=file.sha256,
        filetype=info["filetype"],
        filetype_group=info["filetype_group"],
        mime_type=info["mime_type"],
    )
    await datastore.session.commit()
    await enrichments.delete_unfinished_for_files(file_ids=file_ids)
    await enrichments.session.commit()
    return await datastore.get_file_by_id(file_id=id)


@router.get("/{id}/view", summary="Download file by ID")
async def download_file_by_id(id: str, access: DatasetAccessDep, datastore: FileDatastoreDep):
    """Download a single file's raw bytes by its ID."""
    file = await get_accessible_file(file_id=id, datastore=datastore, access=access)
    if file.uri is None:
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
    access: DatasetAccessDep,
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

    file = await get_accessible_file(file_id=id, datastore=datastore, access=access)
    if file.uri is None:
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


class EmailView(EmailBase):
    """A parsed email plus the other files that are copies of the same message."""

    copy_file_ids: list[str] = Field(
        default=[], description="Other email files with the same meaningful hash, in datasets you can see"
    )


@router.get(
    "/{id}/email",
    summary="Parse an ingested email file by ID",
    response_model=EmailView,
)
async def get_file_email(
    id: str,
    access: DatasetAccessDep,
    datastore: FileDatastoreDep,
    extracted_text_datastore: ExtractedTextDatastoreDep,
):
    """Parse a stored email file on demand and return its structured representation for display."""
    file = await get_accessible_file(file_id=id, datastore=datastore, access=access)
    if file.uri is None:
        raise HTTPException(status_code=404, detail=f"File not found: {id}")
    if file.filetype not in SUPPORTED_EMAIL_FILETYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported email filetype: {file.filetype}")
    email = parse_email(download_uri(file.uri), filetype=file.filetype, options=EmailOptions(embed_inline_images=True))
    if email.plain and not email.metadata.quoted_blocks:
        email.metadata.quoted_blocks = find_quoted_blocks(email.plain)
    copies = (
        await extracted_text_datastore.get_email_copies(
            meaningful_hash=email.metadata.meaningful_hash, exclude_file_id=id, dataset_ids=access.dataset_ids
        )
        if email.metadata.meaningful_hash
        else []
    )
    return EmailView(**email.model_dump(), copy_file_ids=copies)


LINK_WINDOW = timedelta(days=30)
PREVIEW_CHARS = 160


def _quoting(email: ConversationEmail, content: str) -> tuple[QuotingEmail, str]:
    """The email ready for quote matching, and its preview: the opening of the text it adds."""
    blocks = find_quoted_blocks(content)
    own_text = content[: blocks[0].start_offset] if blocks else content
    quoting = quoting_email(file_id=email.file_id, content=content, blocks=blocks, from_address=email.from_address)
    return quoting, " ".join(own_text.split())[:PREVIEW_CHARS]


def link_conversation(
    members: list[tuple[ConversationEmail, str]], candidates: list[tuple[ConversationEmail, str]], title: str | None
) -> tuple[list[ConversationEmail], bool]:
    """The conversation's emails in date order, plus whether quoted text linked any beyond `members`.

    A candidate joins when its subject matches `title` once Re: / Fwd: are removed and it quotes, or is
    quoted by, an email already in the conversation (followed through the chain).
    """
    key = subject_key(title)
    member_ids = {email.file_id for email, _ in members}
    prepared = {
        email.file_id: (email, *_quoting(email, content))
        for email, content in [*members, *candidates]
        if email.file_id in member_ids or subject_key(email.title) == key
    }
    linked = linked_by_quotes(
        members=[quoting for file_id, (_, quoting, _) in prepared.items() if file_id in member_ids],
        candidates=[quoting for file_id, (_, quoting, _) in prepared.items() if file_id not in member_ids],
    )
    kept = member_ids | {quoting.message.file_id for quoting in linked}
    emails = [
        email.model_copy(update={"preview": preview})
        for file_id, (email, _, preview) in prepared.items()
        if file_id in kept
    ]
    emails.sort(key=lambda email: (email.date_sent is None, email.date_sent or datetime.min.replace(tzinfo=UTC)))
    return emails, bool(linked)


@router.get(
    "/{id}/conversation",
    summary="The emails in an email file's conversation",
    response_model=EmailConversation,
)
async def get_file_conversation(
    id: str,
    access: DatasetAccessDep,
    datastore: FileDatastoreDep,
    extracted_text_datastore: ExtractedTextDatastoreDep,
):
    """The emails sharing this email's `conversation_id`, plus same-subject emails within 30 days linked by quoted text."""
    file = await get_accessible_file(file_id=id, datastore=datastore, access=access)
    extracted = await extracted_text_datastore.get_by_file_id(id)
    if extracted is None or not isinstance(extracted.metadata, EmailMetadata):
        raise HTTPException(status_code=404, detail=f"No extracted email for file: {id}")
    metadata = extracted.metadata
    members = (
        await extracted_text_datastore.get_conversation_emails(
            conversation_id=metadata.conversation_id, file_id=id, dataset_ids=access.dataset_ids
        )
        if metadata.conversation_id
        else []
    )
    if not any(email.file_id == id for email, _ in members):
        members.append(
            (ConversationEmail(file_id=id, title=metadata.title, date_sent=metadata.date_sent), extracted.content)
        )
    key = subject_key(metadata.title)
    candidates = (
        await extracted_text_datastore.get_subject_candidates(
            subject_key=key,
            file_id=id,
            date_from=metadata.date_sent - LINK_WINDOW,
            date_to=metadata.date_sent + LINK_WINDOW,
            dataset_id=file.dataset_id,
        )
        if key and metadata.date_sent
        else []
    )
    emails, is_linked = link_conversation(members=members, candidates=candidates, title=metadata.title)
    return EmailConversation(
        conversation_id=metadata.conversation_id,
        source=ConversationSource.QUOTED_TEXT if is_linked else ConversationSource.HEADERS,
        emails=emails,
    )


@router.get(
    "/{id}/image",
    summary="Get the Image record for a file, if the images pipeline has processed it",
    response_model=ImagePublic,
)
async def get_file_image(
    id: str, access: DatasetAccessDep, datastore: FileDatastoreDep, image_datastore: ImageDatastoreDep
):
    """Look up the Image entity (EXIF metadata, embedding-backed similarity) for a file."""
    await get_accessible_file(file_id=id, datastore=datastore, access=access)
    image = await image_datastore.get_image_by_file_id(file_id=id)
    if image is None:
        raise HTTPException(status_code=404, detail=f"No image record found for file: {id}")
    return image


class FileText(BaseModel):
    """A file's extracted text plus how many search chunks it was indexed into."""

    extracted_text_id: str
    text: str
    chunk_count: int
    image_pages: list[int] = Field(default=[], description="Pages with no usable text layer (scanned)")
    ocr_pages: list[int] = Field(default=[], description="Pages whose text came from OCR")
    ocr_model: str | None = Field(default=None, description="OCR engine/model that produced `ocr_pages`")
    is_content_corrected: bool = Field(default=False, description="An analyst corrected this text")
    content_corrected_by: str | None = Field(default=None, description="Who last corrected it")
    corrected_ranges: list[tuple[int, int]] = Field(default=[], description="Stretches of the text a person wrote")


@router.get(
    "/{id}/text",
    summary="Get a file's extracted text",
    response_model=FileText,
)
async def get_file_text(
    id: str,
    access: DatasetAccessDep,
    datastore: FileDatastoreDep,
    extracted_text_datastore: ExtractedTextDatastoreDep,
    chunk_datastore: TextChunkDatastoreDep,
):
    """Return the stored extractor output verbatim.

    Served from the `extracted_text` table rather than rejoined from indexed
    chunks -- chunk `start_offset`/`end_offset` are offsets into this exact
    string, so any reconstruction would break highlighting (and would drop
    content wherever a chunk is missing from the index).
    """
    await get_accessible_file(file_id=id, datastore=datastore, access=access)
    extracted = await extracted_text_datastore.get_by_file_id(file_id=id)
    if extracted is None:
        raise HTTPException(status_code=404, detail=f"No extracted text found for file: {id}")

    chunk_count = len(await chunk_datastore.spans_for_file(id))
    metadata = extracted.metadata if isinstance(extracted.metadata, DocumentMetadata) else None
    return FileText(
        extracted_text_id=extracted.id,
        text=extracted.content,
        chunk_count=chunk_count,
        image_pages=metadata.image_pages if metadata else [],
        ocr_pages=metadata.ocr_pages if metadata else [],
        ocr_model=metadata.ocr_model if metadata else None,
        is_content_corrected=extracted.is_content_corrected,
        content_corrected_by=extracted.content_corrected_by,
        corrected_ranges=extracted.corrected_ranges or [],
    )


@router.put(
    "/{id}/text",
    summary="Correct a file's extracted text",
    response_model=TextCorrectionSummary,
    dependencies=[AdminOnly],
)
async def correct_file_text(
    id: str,
    body: Annotated[TextCorrectionRequest, Body(...)],
    access: DatasetAccessDep,
    user: CurrentUserDep,
    datastore: FileDatastoreDep,
    extracted_text_datastore: ExtractedTextDatastoreDep,
    chunk_datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Admin: replace an OCR'd text on every copy of the file's content, moving its mentions and chunks along.

    Nothing is re-run unless `rerun` names steps (from a dry run's `rerunnable`). `dryRun` reports what
    would happen (mentions renamed or lost) without writing. 409 while a step that reads the text is
    running on these files.
    """
    from cipher.orchestration.correct_text import correct_text

    await get_accessible_file(file_id=id, datastore=datastore, access=access)
    extracted = await extracted_text_datastore.get_by_file_id(file_id=id)
    if extracted is None:
        raise HTTPException(status_code=404, detail=f"No extracted text found for file: {id}")
    metadata = extracted.metadata if isinstance(extracted.metadata, DocumentMetadata) else None
    if not (metadata and metadata.ocr_pages):
        raise HTTPException(status_code=422, detail="Only text read by OCR can be corrected")
    try:
        summary = await correct_text(
            chunk_datastore.session,
            file_id=id,
            content=body.content,
            corrected_by=user.id,
            chunk_store=chunk_datastore,
            rerun=body.rerun,
            embed=model.encode_passages,
            tokenizer=model.tokenizer,
            dry_run=body.dry_run,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not body.dry_run and summary.file_count and not summary.is_saved:
        running = ", ".join(step.value.replace("_", " ") for step in summary.running)
        raise HTTPException(status_code=409, detail=f"Not saved: {running} is running on this file; try again after")
    return summary


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
async def get_file_table(
    id: str, access: DatasetAccessDep, datastore: FileDatastoreDep, extracted_text_datastore: ExtractedTextDatastoreDep
):
    """Return structured tables extracted from a file (csv/tsv/json/jsonl/xlsx/...), if any.

    Each sheet is capped at `MAX_TABLE_ROWS`; `truncated`/`total_rows` tell the
    client when it's only seeing a prefix of the full table.
    """
    await get_accessible_file(file_id=id, datastore=datastore, access=access)
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
