from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import gsc, health

app = FastAPI(
    title="Serpnex",
    description="Link intelligence platform API",
    version="0.1.0",
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(gsc.router, prefix="/api/v1")


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Provider registry raises ValueError when a required API key is not configured.
    Surface this as 503 Service Unavailable rather than letting it crash as a 500."""
    return JSONResponse(
        status_code=503,
        content={"detail": f"Service not configured: {exc}"},
    )
