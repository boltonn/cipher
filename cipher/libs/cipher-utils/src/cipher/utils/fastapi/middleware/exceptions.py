import sys
import traceback
from enum import StrEnum

from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from cipher.schemas._base.exceptions import EntityAlreadyExistsError, EntityNotFoundError
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    """Machine-readable `code` on every error body; clients switch on it, never on `detail` text. Wire-only, so camelCase."""

    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "notFound"
    CONFLICT = "conflict"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    SERVER_ERROR = "serverError"
    ERROR = "error"


_CODE_BY_STATUS = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_422_UNPROCESSABLE_CONTENT: ErrorCode.INVALID,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.UNAVAILABLE,
}


def error_code_for(status_code: int) -> ErrorCode:
    """The `ErrorCode` for an HTTP status."""
    if status_code in _CODE_BY_STATUS:
        return _CODE_BY_STATUS[status_code]
    return ErrorCode.SERVER_ERROR if status_code >= 500 else ErrorCode.ERROR


def get_error_response(exc) -> dict:
    """Generic error handling function."""
    error_response = {
        "error": True,
        "code": ErrorCode.INVALID if isinstance(exc, RequestValidationError) else ErrorCode.SERVER_ERROR,
        "message": str(exc),
        "error_type": exc.__class__.__name__,
    }

    # Add detailed traceback if in debug mode
    exc_trb, exc_type, exc_value = sys.exc_info()

    # Return traceback info if debug mode is on
    error_response["traceback"] = "".join(traceback.format_exception(exc_trb, exc_type, exc_value))

    return error_response


async def entity_exists_handler(request: Request, exc: EntityAlreadyExistsError):
    """Handles entity already exists errors."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,  # 409 is better for "already exists"
        content={"code": ErrorCode.CONFLICT, "detail": str(exc)},
    )


async def entity_not_found_handler(request: Request, exc: EntityNotFoundError):
    """Handles entity not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "code": ErrorCode.NOT_FOUND,
            "detail": str(exc),
            "entityName": exc.entity_name,
            "identifier": exc.identifier,
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """`HTTPException`s get the same `{code, detail}` body as the typed errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": error_code_for(exc.status_code), "detail": exc.detail},
        headers=getattr(exc, "headers", None),
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
