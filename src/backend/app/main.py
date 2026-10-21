from fastapi import FastAPI

from app.errors import register_error_handlers
from app.routers import health, item

app = FastAPI(title="Orbyte Backend") # change the name of the project later on
register_error_handlers(app)
app.include_router(health.router, prefix="/api/v1")
app.include_router(item.router, prefix="/api/v1")