from fastapi import APIRouter, HTTPException

from cipher.api.deps.postgres import FileDatastoreDep
from cipher.schemas.file import File

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
