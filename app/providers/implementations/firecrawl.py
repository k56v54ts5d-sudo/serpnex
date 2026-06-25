import asyncio

import httpx

from app.providers.base.crawler import CrawlError, CrawlResult, CrawlerProvider


class FirecrawlCrawlerProvider(CrawlerProvider):
    """CrawlerProvider backed by the Firecrawl managed crawling API.
    Handles JS rendering, bot detection avoidance, and returns clean markdown."""

    _BASE_URL = "https://api.firecrawl.dev/v1"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY is not configured")
        self._api_key = api_key
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def crawl(self, url: str) -> CrawlResult:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._BASE_URL}/scrape",
                headers=self._headers,
                json={"url": url, "formats": ["markdown", "html"]},
            )

        if response.status_code != 200:
            raise CrawlError(url, f"Firecrawl returned HTTP {response.status_code}")

        data = response.json()
        if not data.get("success"):
            raise CrawlError(url, data.get("error", "unknown error"))

        page = data.get("data", {})
        metadata = page.get("metadata", {})

        return CrawlResult(
            url=url,
            status_code=metadata.get("statusCode", 200),
            markdown=page.get("markdown", ""),
            html=page.get("html", ""),
            title=metadata.get("title"),
            meta_description=metadata.get("description"),
        )

    async def crawl_many(self, urls: list[str]) -> list[CrawlResult]:
        tasks = [self.crawl(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: list[CrawlResult] = []
        for url, result in zip(urls, results):
            if isinstance(result, CrawlError):
                raise result
            if isinstance(result, BaseException):
                raise CrawlError(url, str(result))
            processed.append(result)

        return processed
