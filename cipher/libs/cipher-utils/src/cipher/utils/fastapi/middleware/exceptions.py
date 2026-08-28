import sys
import traceback

from loguru import logger

from cipher.schemas.exceptions import EntityAlreadyExistsError, EntityNotFoundError
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def get_error_response(exc) -> dict:
    """Generic error handling function."""
    error_response = {
        "error": True,
        "message": str(exc),
        "error_type": exc.__class__.__name__,
    }

    # Add detailed traceback if in debug mode
    exc_trb, exc_type, exc_value = sys.exc_info()

    # Return traceback info if debug mode is on
    error_response["traceback"] = "".join(
        traceback.format_exception(exc_trb, exc_type, exc_value)
    )

    return error_response


async def entity_exists_handler(request: Request, exc: EntityAlreadyExistsError):
    """Handles entity already exists errors."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,  # 409 is better for "already exists"
        content={"detail": str(exc)},
    )


async def entity_not_found_handler(request: Request, exc: EntityNotFoundError):
    """Handles entity not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handling error in validating requests."""
    logger.exception(exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=get_error_response(exc),
    )


async def python_exception_handler(request: Request, exc: Exception):
    """Handling any internal error."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=get_error_response(exc),
    )
