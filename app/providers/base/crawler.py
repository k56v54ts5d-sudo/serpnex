from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CrawlResult:
    url: str
    status_code: int
    markdown: str
    html: str
    title: str | None
    meta_description: str | None


class CrawlerProvider(ABC):
    """Abstract interface for page crawling. Implementations handle rendering,
    rate limiting, and content extraction. Business logic never imports a
    concrete crawler directly."""

    @abstractmethod
    async def crawl(self, url: str) -> CrawlResult:
        """Crawl a URL and return rendered content. Raises CrawlError on failure."""

    @abstractmethod
    async def crawl_many(self, urls: list[str]) -> list[CrawlResult]:
        """Crawl multiple URLs concurrently. Returns results in the same order.
        Failed individual URLs raise CrawlError within their result slot."""


class CrawlError(Exception):
    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Crawl failed for {url}: {reason}")
