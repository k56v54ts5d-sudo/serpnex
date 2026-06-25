import secrets

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.providers.base.gsc import GSCError
from app.providers.registry import get_gsc_provider

router = APIRouter(prefix="/auth/gsc", tags=["gsc"])


class AuthUrlResponse(BaseModel):
    auth_url: str
    state: str


@router.get("/connect", response_model=AuthUrlResponse)
async def get_gsc_auth_url() -> AuthUrlResponse:
    """Return the Google OAuth2 authorization URL for GSC connection.
    The client should redirect the user to auth_url."""
    provider = get_gsc_provider()
    state = secrets.token_urlsafe(32)
    result = provider.get_auth_url(state=state)
    return AuthUrlResponse(auth_url=result.url, state=result.state)


@router.get("/callback")
async def gsc_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(default=None),
) -> dict:
    """OAuth2 callback endpoint. Exchanges the authorization code for tokens.
    In Sprint 2 this will be wired to a user session and persisted to the database."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    try:
        provider = get_gsc_provider()
        tokens = await provider.exchange_code(code=code)
        # Token persistence to user record is wired in Sprint 2 when auth is implemented.
        return {"status": "connected", "token_received": True}
    except GSCError as exc:
        raise HTTPException(status_code=502, detail=exc.reason) from exc
