from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GSCKeywordRow:
    keyword: str
    clicks: int
    impressions: int
    ctr: float
    position: float


@dataclass
class GSCPageMetrics:
    url: str
    keywords: list[GSCKeywordRow] = field(default_factory=list)
    total_clicks: int = 0
    total_impressions: int = 0


@dataclass
class GSCProperty:
    property_uri: str  # e.g. "https://example.com/" or "sc-domain:example.com"
    permission_level: str  # "siteOwner" | "siteFullUser" | "siteRestrictedUser"


@dataclass
class GSCAuthUrl:
    url: str
    state: str


class GSCProvider(ABC):
    """Abstract interface for Google Search Console data. Implementations
    handle OAuth token management and API calls. Business logic never
    imports a concrete GSC client directly."""

    @abstractmethod
    def get_auth_url(self, state: str) -> GSCAuthUrl:
        """Return the OAuth2 authorization URL to redirect the user to."""

    @abstractmethod
    async def exchange_code(self, code: str) -> dict:
        """Exchange an authorization code for OAuth tokens. Returns the raw
        token dict to be stored on the user record."""

    @abstractmethod
    async def list_properties(self, tokens: dict) -> list[GSCProperty]:
        """List all GSC properties the authenticated user has access to."""

    @abstractmethod
    async def get_page_metrics(
        self,
        tokens: dict,
        property_uri: str,
        page_url: str,
        days: int = 90,
        row_limit: int = 5,
    ) -> GSCPageMetrics:
        """Fetch keyword performance data for a specific page URL.
        Returns the top `row_limit` keywords by impressions over `days` days."""


class GSCError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"GSC request failed: {reason}")
