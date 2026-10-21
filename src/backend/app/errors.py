from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.problem import Problem


def problem_response(problem: Problem, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(problem.model_dump(exclude_none=True),
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
        )
        return problem_response(problem)
