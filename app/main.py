from fastapi import FastAPI

from app.routers import health

app = FastAPI(title="Orbyte Backend") # change the name of the project later on
app.include_router(health.router, prefix="/api/v1")