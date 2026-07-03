from fastapi import APIRouter, UploadFile
from pyparse.parsers.email import EmlParser

router = APIRouter(
    prefix="/emails",
    tags=["emails"],
    responses={418: {"description": "I'm a teapot"}},
)


@router.post(
    "/parse",
    summary="Parse an email file",
)
async def parse_email(
    file: UploadFile,
):
    """Parse an email file and return its structured representation for display."""
    email_bytes = await file.read()
    parser = EmlParser()
    email = parser.parse(email_bytes)
    return email
