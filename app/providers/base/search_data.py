from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


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


@dataclass
class DomainMetrics:
    """Provider-agnostic domain intelligence model.

    Represents what the application needs to know about a prospect domain,
    expressed in business concepts. Provider implementations are responsible
    for mapping their API-specific responses to these fields. The model must
    remain stable across provider changes — never add provider-specific field
    names or API response structures here.

    Used by the Investment Decision Engine (§3.5) for signals P3, D3, and D8.
    """

    domain: str

    # Traffic authority — is this domain attracting meaningful organic search traffic?
    # Assess based on estimated monthly visits from any organic traffic data source.
    # "high" ≥ 10k/mo; "medium" 1k–10k/mo; "low" 100–1k/mo;
    # "minimal" < 100/mo; "unknown" if no data available.
    traffic_tier: Literal["high", "medium", "low", "minimal", "unknown"]

    # Traffic trajectory — is organic traffic trending up, stable, or declining?
    # Assessed over a meaningful historical window (implementation-defined, typically 12 months).
    # "growing": meaningful upward trend; "stable": flat ±15%;
    # "declining": meaningful downward trend; "unknown" if insufficient history.
    traffic_trajectory: Literal["growing", "stable", "declining", "unknown"]

    # Link authority — how many unique referring domains link to this domain?
    # None if unavailable from the provider.
    referring_domains: int | None

    # Spam risk — likelihood the domain is engaged in manipulative link practices.
    # 0.0 = high spam risk; 1.0 = completely clean.
    # Provider implementations must normalize their native spam scores to this scale.
    # None if the provider does not supply this signal.
    spam_risk: float | None

    # Domain maturity — approximate age of the domain in years.
    # Derived from registration date or earliest indexed content.
    # None if unavailable.
    maturity_years: float | None


class SearchDataProvider(ABC):
    """Abstract interface for SERP, backlink, and domain intelligence data.

    Implementations wrap third-party data vendors (DataForSEO, Semrush, Ahrefs, etc.).
    Business logic never imports a concrete search data provider directly — always
    depend on this ABC and access instances via the provider registry."""

    @abstractmethod
    async def get_serp(self, keyword: str, location_code: int = 2840) -> SerpResult:
        """Fetch organic SERP results for a keyword. location_code follows
        DataForSEO location codes (2840 = United States)."""

    @abstractmethod
    async def get_backlink_metrics(self, url: str) -> BacklinkMetrics:
        """Fetch referring domain count, domain rating, spam score, and
        top anchor texts for a URL or domain."""

    @abstractmethod
    async def get_domain_metrics(self, domain: str) -> DomainMetrics:
        """Fetch domain-level traffic, trajectory, authority, spam risk, and
        maturity signals for a prospect domain.

        The implementation is responsible for translating provider-specific API
        responses into the provider-agnostic DomainMetrics model. When a signal
        is unavailable, return None for that field rather than raising.

        Used by the Investment Decision Engine for P3, D3, and D8 signals."""


class SearchDataError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Search data fetch failed: {reason}")
