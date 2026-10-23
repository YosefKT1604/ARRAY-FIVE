import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.db.seed import seed_if_empty
from app.errors import register_error_handlers
from app.routers import health, resource, dependency, job, supplier, delivery, disruption, recovery_plan, ai, whatsapp

@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_if_empty()
    yield

app = FastAPI(title="Orbyte Backend", lifespan=lifespan) # change the name of the project later on
register_error_handlers(app)
app.include_router(health.router, prefix="/api/v1")
app.include_router(resource.router, prefix="/api/v1")
app.include_router(dependency.router, prefix="/api/v1")
app.include_router(job.router, prefix="/api/v1")
app.include_router(supplier.router, prefix="/api/v1")
app.include_router(delivery.router, prefix="/api/v1")
app.include_router(disruption.router, prefix="/api/v1")
app.include_router(recovery_plan.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(whatsapp.router, prefix="/api/v1")

# Serve the built frontend from the same server (one URL on Replit). Registered AFTER every API route and
# after /docs and /openapi.json, so those win. If frontend/dist is missing, the API works as before.
FRONTEND_DIST = Path(os.environ.get("SCDC_FRONTEND_DIST") or Path(__file__).resolve().parents[3] / "frontend" / "dist")

if (FRONTEND_DIST / "index.html").is_file():
    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such API route.")
        target = (FRONTEND_DIST / path).resolve()
        if path and target.is_file() and target.is_relative_to(FRONTEND_DIST.resolve()):
            return FileResponse(target)
        # Single-page app: any other path is a screen the React router handles.
        return FileResponse(FRONTEND_DIST / "index.html")
