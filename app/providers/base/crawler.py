from __future__ import annotations

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
        """Crawl a single URL. Raises CrawlError on failure."""

    @abstractmethod
    async def crawl_many(self, urls: list[str]) -> list[CrawlResult | CrawlError]:
        """Crawl multiple URLs concurrently. Returns one entry per URL in the
        same order — a CrawlResult on success, a CrawlError on failure.
        Never raises; callers inspect each entry to handle partial failures."""


class CrawlError(Exception):
    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Crawl failed for {url}: {reason}")
