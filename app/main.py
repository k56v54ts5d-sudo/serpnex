from fastapi import FastAPI

from app.api.v1 import health, gsc

app = FastAPI(
    title="Serpnex",
    description="Link intelligence platform API",
    version="0.1.0",
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(gsc.router, prefix="/api/v1")
