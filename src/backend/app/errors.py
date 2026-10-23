from enum import StrEnum
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.problem import Problem

class ErrorCode(StrEnum):
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    DUPLICATE_DISRUPTION = "DUPLICATE_DISRUPTION"
    STALE_PLAN_VERSION = "STALE_PLAN_VERSION"
    PLAN_INFEASIBLE = "PLAN_INFEASIBLE"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"

# Used when an error is raised without an explicit code.
DEFAULT_CODE = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
    500: ErrorCode.INTERNAL_ERROR,
}

# For errors where the status alone is ambiguous (several kinds of 409). It subclasses Starlette's
# HTTPException so the existing http_error handler picks it up without a handler of its own.
class ApiError(StarletteHTTPException):
    def __init__(self, status_code: int, code: ErrorCode, detail: str):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code

def problem_response(problem: Problem, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=problem.status,
        headers=headers,
        media_type="application/problem+json",
    )

def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        problem = Problem(
            title=HTTPStatus(exc.status_code).phrase,
            status=exc.status_code,
            detail=exc.detail,
            instance=request.url.path,
            code=getattr(exc, "code", None) or DEFAULT_CODE.get(exc.status_code, ErrorCode.BAD_REQUEST),
        )
        return problem_response(problem, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        problem = Problem(
            title="Unprocessable Content",
            status=422,
            detail="Request validation failed.",
            instance=request.url.path,
            errors=[{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()],
            code=ErrorCode.VALIDATION_ERROR,
        )
        return problem_response(problem)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        problem = Problem(
            title="Internal Server Error",
            status=500,
            detail="An unexpected error occurred.",
            instance=request.url.path,
            code=ErrorCode.INTERNAL_ERROR,
        )
        return problem_response(problem)