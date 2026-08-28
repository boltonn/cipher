import traceback
from collections.abc import Callable
from secrets import token_urlsafe
from time import time

from loguru import logger

from cipher.utils.fastapi.settings import BaseServiceSettings
from fastapi import Request, Response
from fastapi.responses import JSONResponse

settings = BaseServiceSettings()
DEBUG = True


async def log_middleware(request: Request, call_next: Callable) -> Response:
    """Log requests with unique ID and handle exceptions."""
    start_time = time()
    request_id = token_urlsafe(8)
    exception = None

    with logger.contextualize(request_id=request_id):
        try:
            response = await call_next(request)
        except Exception as exc:
            exception = exc
            logger.exception("Exception occurred during request processing")  # Add this
            response = _create_error_response(exc, request_id)

        elapsed = time() - start_time
        _log_request(request, response, elapsed, exception)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Processed-Time"] = f"{elapsed:.3f}"

        return response


def _create_error_response(exc: Exception, request_id: str) -> JSONResponse:
    """Create error response based on debug mode."""
    error_data = {
        "error": "Internal Server Error",
        "request_id": request_id,
    }

    if DEBUG:
        error_data.update(
            {
                "message": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc().split("\n"),
            }
        )
    else:
        error_data["message"] = (
            "An unexpected error occurred. Please contact support with the request ID."
        )

    return JSONResponse(content=error_data, status_code=500)


def _log_request(
    request: Request,
    response: Response,
    elapsed: float,
    exception: Exception | None,
) -> None:
    """Log request with appropriate level and format."""
    log_data = {
        "method": request.method,
        "url": str(request.url),
        "status": response.status_code,
        "elapsed_ms": round(elapsed * 1000, 2),
    }

    # Choose log level
    if exception:
        log_level = logger.error
        message = "Request failed with exception"
    elif response.status_code >= 500:
        log_level = logger.error
        message = "Server error"
    elif response.status_code >= 400:
        log_level = logger.warning
        message = "Client error"
    else:
        log_level = logger.info
        message = "Request completed"

    # Log based on format preference
    if settings.log.to_json:
        log_level(message, **log_data, exc_info=exception)
    else:
        log_msg = f"{message}: {request.method} {request.url} - {response.status_code} ({log_data['elapsed_ms']}ms)"
        log_level(log_msg, exc_info=exception) if exception else log_level(log_msg)
