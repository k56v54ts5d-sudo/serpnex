"""GSC OAuth endpoints: connect and callback."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_gsc_connect_unconfigured_returns_503() -> None:
    """Without Google credentials configured, the registry raises ValueError.
    The app exception handler must translate this to 503 Service Unavailable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/gsc/connect")
    # No Google credentials in the test environment → 503
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_gsc_callback_with_error_param_returns_400() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/gsc/callback",
            params={"code": "ignored", "state": "ignored", "error": "access_denied"},
        )
    assert response.status_code == 400
    assert "access_denied" in response.json()["detail"]


@pytest.mark.asyncio
async def test_gsc_callback_missing_code_returns_422() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/gsc/callback",
            params={"state": "some-state"},
        )
    assert response.status_code == 422
