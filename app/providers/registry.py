from functools import lru_cache

from app.config import settings
from app.providers.base.crawler import CrawlerProvider
from app.providers.base.gsc import GSCProvider
from app.providers.base.llm import LLMProvider
from app.providers.base.search_data import SearchDataProvider


@lru_cache(maxsize=1)
def get_crawler_provider() -> CrawlerProvider:
    if settings.crawler_provider == "firecrawl":
        from app.providers.implementations.firecrawl import FirecrawlCrawlerProvider

        return FirecrawlCrawlerProvider(api_key=settings.firecrawl_api_key)
    raise ValueError(f"Unknown crawler provider: {settings.crawler_provider!r}")


@lru_cache(maxsize=1)
def get_search_data_provider() -> SearchDataProvider:
    if settings.search_data_provider == "dataforseo":
        from app.providers.implementations.dataforseo import DataForSEOSearchDataProvider

        return DataForSEOSearchDataProvider(
            login=settings.dataforseo_login,
            password=settings.dataforseo_password,
        )
    raise ValueError(f"Unknown search data provider: {settings.search_data_provider!r}")


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "anthropic":
        from app.providers.implementations.anthropic import AnthropicLLMProvider

        return AnthropicLLMProvider(api_key=settings.anthropic_api_key)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")


@lru_cache(maxsize=1)
def get_gsc_provider() -> GSCProvider:
    if settings.gsc_provider == "google":
        from app.providers.implementations.google_gsc import GoogleGSCProvider

        return GoogleGSCProvider(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=settings.google_redirect_uri,
        )
    raise ValueError(f"Unknown GSC provider: {settings.gsc_provider!r}")
