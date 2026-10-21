from fastapi import FastAPI

from app.errors import register_error_handlers
from app.routers import health, resource, dependency, job, supplier, delivery, disruption, recovery_plan

app = FastAPI(title="Orbyte Backend") # change the name of the project later on
register_error_handlers(app)
app.include_router(health.router, prefix="/api/v1")
app.include_router(resource.router, prefix="/api/v1")
app.include_router(dependency.router, prefix="/api/v1")
app.include_router(job.router, prefix="/api/v1")
app.include_router(supplier.router, prefix="/api/v1")
app.include_router(delivery.router, prefix="/api/v1")
app.include_router(disruption.router, prefix="/api/v1")
app.include_router(recovery_plan.router, prefix="/api/v1")