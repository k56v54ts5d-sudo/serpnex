"""FirecrawlCrawlerProvider: verify crawl_many partial-failure contract.
Uses pytest-httpx to mock HTTP without making real network calls."""

import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock

from app.providers.base.crawler import CrawlError, CrawlResult
from app.providers.implementations.firecrawl import FirecrawlCrawlerProvider

_API_KEY = "test-key"
_BASE = "https://api.firecrawl.dev/v1"


def _ok_response(url: str) -> dict:
    return {
        "success": True,
        "data": {
            "markdown": f"# Content for {url}",
            "html": f"<h1>Content for {url}</h1>",
            "metadata": {
                "statusCode": 200,
                "title": f"Page {url}",
                "description": None,
            },
        },
    }


def _err_response(message: str) -> dict:
    return {"success": False, "error": message}


@pytest.fixture
def provider() -> FirecrawlCrawlerProvider:
    return FirecrawlCrawlerProvider(api_key=_API_KEY)


@pytest.mark.asyncio
async def test_crawl_success(httpx_mock: HTTPXMock, provider: FirecrawlCrawlerProvider) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/scrape",
        json=_ok_response("https://example.com"),
    )
    result = await provider.crawl("https://example.com")
    assert isinstance(result, CrawlResult)
    assert result.url == "https://example.com"
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_crawl_http_error_raises(httpx_mock: HTTPXMock, provider: FirecrawlCrawlerProvider) -> None:
    httpx_mock.add_response(method="POST", url=f"{_BASE}/scrape", status_code=403)
    with pytest.raises(CrawlError) as exc_info:
        await provider.crawl("https://blocked.com")
    assert "403" in str(exc_info.value)


@pytest.mark.asyncio
async def test_crawl_api_error_raises(httpx_mock: HTTPXMock, provider: FirecrawlCrawlerProvider) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/scrape",
        json=_err_response("Page blocked by robots.txt"),
    )
    with pytest.raises(CrawlError) as exc_info:
        await provider.crawl("https://blocked.com")
    assert "robots" in str(exc_info.value)


@pytest.mark.asyncio
async def test_crawl_many_all_success(httpx_mock: HTTPXMock, provider: FirecrawlCrawlerProvider) -> None:
    urls = ["https://a.com", "https://b.com", "https://c.com"]
    for url in urls:
        httpx_mock.add_response(method="POST", url=f"{_BASE}/scrape", json=_ok_response(url))

    results = await provider.crawl_many(urls)
    assert len(results) == 3
    assert all(isinstance(r, CrawlResult) for r in results)


@pytest.mark.asyncio
async def test_crawl_many_partial_failure_does_not_raise(
    httpx_mock: HTTPXMock, provider: FirecrawlCrawlerProvider
) -> None:
    """When one URL fails, crawl_many must return a CrawlError in that slot
    rather than raising. This is critical for the pipeline: a blocked competitor
    page must not abort the entire analysis."""
    httpx_mock.add_response(method="POST", url=f"{_BASE}/scrape", json=_ok_response("https://a.com"))
    httpx_mock.add_response(method="POST", url=f"{_BASE}/scrape", status_code=403)
    httpx_mock.add_response(method="POST", url=f"{_BASE}/scrape", json=_ok_response("https://c.com"))

    results = await provider.crawl_many(["https://a.com", "https://blocked.com", "https://c.com"])

    assert len(results) == 3
    assert isinstance(results[0], CrawlResult)
    assert isinstance(results[1], CrawlError)
    assert isinstance(results[2], CrawlResult)
    assert results[1].url == "https://blocked.com"


@pytest.mark.asyncio
async def test_crawl_many_all_failures_returns_errors(
    httpx_mock: HTTPXMock, provider: FirecrawlCrawlerProvider
) -> None:
    for _ in range(2):
        httpx_mock.add_response(method="POST", url=f"{_BASE}/scrape", status_code=403)

    results = await provider.crawl_many(["https://a.com", "https://b.com"])
    assert all(isinstance(r, CrawlError) for r in results)
