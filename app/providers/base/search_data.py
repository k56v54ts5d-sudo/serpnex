from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class OrganicResult:
    position: int
    url: str
    title: str
    description: str | None


@dataclass
class SerpResult:
    keyword: str
    total_results: int
    organic: list[OrganicResult] = field(default_factory=list)
    features: list[str] = field(default_factory=list)  # e.g. ["featured_snippet", "paa"]


@dataclass
class BacklinkMetrics:
    url: str
    referring_domains: int
    domain_rating: float | None
    spam_score: float | None
    top_anchors: list[dict] = field(default_factory=list)  # [{"anchor": str, "count": int}]


class SearchDataProvider(ABC):
    """Abstract interface for SERP and backlink data. Implementations wrap
    third-party data vendors. Business logic never imports a concrete
    search data provider directly."""

    @abstractmethod
    async def get_serp(self, keyword: str, location_code: int = 2840) -> SerpResult:
        """Fetch organic SERP results for a keyword. location_code follows
        DataForSEO location codes (2840 = United States)."""

    @abstractmethod
    async def get_backlink_metrics(self, url: str) -> BacklinkMetrics:
        """Fetch referring domain count, domain rating, spam score, and
        top anchor texts for a URL or domain."""


class SearchDataError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Search data fetch failed: {reason}")
