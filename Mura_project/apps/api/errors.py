"""One canonical application error envelope.

Every application error leaves the process as::

    {"error": {"code": ..., "message": ..., "retryable": ..., "request_id": ...}}

Messages are looked up from a fixed table keyed by code and are never built from
exception content, so a pydantic input value, a database URL, a provider
response body, a transcript or a name cannot reach the client through an error.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mura.deepseek import DeepSeekError
from mura.domain.models import StrictModel
from mura.validation import ContractValidationError

REQUEST_ID_HEADER = "X-Request-ID"

BAD_REQUEST = "bad_request"
UNAUTHORIZED = "unauthorized"
FORBIDDEN = "forbidden"
NOT_FOUND = "not_found"
CONFLICT = "conflict"
METHOD_NOT_ALLOWED = "method_not_allowed"
PAYLOAD_TOO_LARGE = "payload_too_large"
UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
VALIDATION_FAILED = "validation_failed"
RATE_LIMITED = "rate_limited"
INTERNAL_ERROR = "internal_error"
UPSTREAM_PROVIDER_FAILED = "upstream_provider_failed"
PIPELINE_OUTPUT_INVALID = "pipeline_output_invalid"
SERVICE_UNAVAILABLE = "service_unavailable"
UPSTREAM_TIMEOUT = "upstream_timeout"

# Authorization codes. A raise site may select one of these so a client can
# distinguish "log in" from "ask an owner"; the message still comes from the
# table below, so no exception text ever escapes.
AUTHENTICATION_REQUIRED = "authentication_required"
INVALID_TOKEN = "invalid_token"
FAMILY_NOT_FOUND = "family_not_found"
INSUFFICIENT_FAMILY_ROLE = "insufficient_family_role"
SOLE_OWNER_REQUIRED = "sole_owner_required"

#: Codes a route may request explicitly via HTTPException(detail=...).
SELECTABLE_CODES = frozenset(
    {
        AUTHENTICATION_REQUIRED,
        INVALID_TOKEN,
        FAMILY_NOT_FOUND,
        INSUFFICIENT_FAMILY_ROLE,
        SOLE_OWNER_REQUIRED,
    }
)

_MESSAGE_BY_CODE: dict[str, str] = {
    BAD_REQUEST: "The request could not be understood.",
    UNAUTHORIZED: "Authentication is required.",
    FORBIDDEN: "This operation is not permitted.",
    NOT_FOUND: "The requested resource was not found.",
    METHOD_NOT_ALLOWED: "That method is not allowed on this resource.",
    CONFLICT: "The resource is not in a state that allows this operation.",
    PAYLOAD_TOO_LARGE: "The uploaded file is larger than the configured limit.",
    UNSUPPORTED_MEDIA_TYPE: "The uploaded file format is not supported.",
    VALIDATION_FAILED: "The request did not match the expected contract.",
    RATE_LIMITED: "Too many requests.",
    INTERNAL_ERROR: "The service could not complete the request.",
    UPSTREAM_PROVIDER_FAILED: "The model provider returned an unusable response.",
    PIPELINE_OUTPUT_INVALID: "The extraction output failed contract validation.",
    SERVICE_UNAVAILABLE: "The service is not available.",
    UPSTREAM_TIMEOUT: "The upstream provider did not respond in time.",
    AUTHENTICATION_REQUIRED: "Authentication is required.",
    INVALID_TOKEN: "Authentication is required.",
    FAMILY_NOT_FOUND: "The requested resource was not found.",
    INSUFFICIENT_FAMILY_ROLE: "This operation is not permitted for your role.",
    SOLE_OWNER_REQUIRED: "A family must always retain at least one owner.",
}

# Plain integers: Starlette renames several of these constants across versions,
# and the wire contract is the number.
_CODE_BY_STATUS: dict[int, str] = {
    400: BAD_REQUEST,
    401: UNAUTHORIZED,
    403: FORBIDDEN,
    404: NOT_FOUND,
    # Without this a wrong verb answered "internal_error", reporting a caller
    # routing mistake as a server fault and masking real 500s in monitoring.
    405: METHOD_NOT_ALLOWED,
    409: CONFLICT,
    413: PAYLOAD_TOO_LARGE,
    415: UNSUPPORTED_MEDIA_TYPE,
    422: VALIDATION_FAILED,
    429: RATE_LIMITED,
    500: INTERNAL_ERROR,
    502: UPSTREAM_PROVIDER_FAILED,
    503: SERVICE_UNAVAILABLE,
    504: UPSTREAM_TIMEOUT,
}

# Retryable means the same request may succeed later without the caller
# changing anything. Client contract errors are never retryable.
_RETRYABLE_CODES = frozenset(
    {RATE_LIMITED, UPSTREAM_PROVIDER_FAILED, SERVICE_UNAVAILABLE, UPSTREAM_TIMEOUT}
)


class ErrorBody(StrictModel):
    code: str
    message: str
    retryable: bool
    request_id: str


class ErrorEnvelope(StrictModel):
    error: ErrorBody


def request_id_of(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) and value else "req_unassigned"


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    retryable: bool | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=_MESSAGE_BY_CODE.get(code, _MESSAGE_BY_CODE[INTERNAL_ERROR]),
            retryable=code in _RETRYABLE_CODES if retryable is None else retryable,
            request_id=request_id_of(request),
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers={REQUEST_ID_HEADER: envelope.error.request_id},
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    status_code = exc.status_code if isinstance(exc, StarletteHTTPException) else 500
    # A raise site may select a known code; anything else is discarded, since
    # details have historically carried structured payloads and interpolated text.
    detail = getattr(exc, "detail", None)
    code = (
        detail
        if isinstance(detail, str) and detail in SELECTABLE_CODES
        else _CODE_BY_STATUS.get(status_code, INTERNAL_ERROR)
    )
    return error_response(request, status_code=status_code, code=code)


async def handle_validation_error(request: Request, _exc: Exception) -> JSONResponse:
    return error_response(
        request,
        status_code=422,
        code=VALIDATION_FAILED,
    )


async def handle_deepseek_error(request: Request, _exc: Exception) -> JSONResponse:
    return error_response(
        request,
        status_code=502,
        code=UPSTREAM_PROVIDER_FAILED,
    )


async def handle_contract_validation_error(request: Request, _exc: Exception) -> JSONResponse:
    return error_response(
        request,
        status_code=502,
        code=PIPELINE_OUTPUT_INVALID,
        retryable=False,
    )


def register_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(StarletteHTTPException, handle_http_exception)
    application.add_exception_handler(RequestValidationError, handle_validation_error)
    application.add_exception_handler(DeepSeekError, handle_deepseek_error)
    application.add_exception_handler(ContractValidationError, handle_contract_validation_error)
