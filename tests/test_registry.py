"""Provider registry: verify correct provider types are returned when configured,
and ValueError is raised for unconfigured or unknown providers."""

import pytest

from app.providers.base.crawler import CrawlerProvider
from app.providers.base.gsc import GSCProvider
from app.providers.base.llm import LLMProvider
from app.providers.base.search_data import SearchDataProvider


def _make_registry(overrides: dict):
    """Return a fresh registry module with settings overridden."""
    from unittest.mock import patch

    import app.providers.registry as reg_module
    from functools import lru_cache

    # Clear lru_cache so each call in this test is fresh
    reg_module.get_crawler_provider.cache_clear()
    reg_module.get_search_data_provider.cache_clear()
    reg_module.get_llm_provider.cache_clear()
    reg_module.get_gsc_provider.cache_clear()

    return reg_module, overrides


def test_unconfigured_crawler_raises() -> None:
    import app.providers.registry as reg
    reg.get_crawler_provider.cache_clear()

    from unittest.mock import patch
    import app.config as cfg_module

    mock_settings = cfg_module.Settings(
        crawler_provider="firecrawl",
        firecrawl_api_key="",  # empty = not configured
    )
    with patch.object(reg, "settings", mock_settings):
        with pytest.raises(ValueError, match="FIRECRAWL_API_KEY"):
            reg.get_crawler_provider()


def test_unknown_crawler_provider_raises() -> None:
    import app.providers.registry as reg
    reg.get_crawler_provider.cache_clear()

    from unittest.mock import patch
    import app.config as cfg_module

    mock_settings = cfg_module.Settings(crawler_provider="nonexistent")
    with patch.object(reg, "settings", mock_settings):
        with pytest.raises(ValueError, match="nonexistent"):
            reg.get_crawler_provider()


def test_unconfigured_search_data_raises() -> None:
    import app.providers.registry as reg
    reg.get_search_data_provider.cache_clear()

    from unittest.mock import patch
    import app.config as cfg_module

    mock_settings = cfg_module.Settings(
        search_data_provider="dataforseo",
        dataforseo_login="",
        dataforseo_password="",
    )
    with patch.object(reg, "settings", mock_settings):
        with pytest.raises(ValueError, match="DATAFORSEO"):
            reg.get_search_data_provider()


def test_unconfigured_llm_raises() -> None:
    import app.providers.registry as reg
    reg.get_llm_provider.cache_clear()

    from unittest.mock import patch
    import app.config as cfg_module

    mock_settings = cfg_module.Settings(llm_provider="anthropic", anthropic_api_key="")
    with patch.object(reg, "settings", mock_settings):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            reg.get_llm_provider()


def test_unconfigured_gsc_raises() -> None:
    import app.providers.registry as reg
    reg.get_gsc_provider.cache_clear()

    from unittest.mock import patch
    import app.config as cfg_module

    mock_settings = cfg_module.Settings(
        gsc_provider="google",
        google_client_id="",
        google_client_secret="",
    )
    with patch.object(reg, "settings", mock_settings):
        with pytest.raises(ValueError, match="GOOGLE_CLIENT"):
            reg.get_gsc_provider()


def test_configured_providers_return_correct_types() -> None:
    import app.providers.registry as reg
    from unittest.mock import patch
    import app.config as cfg_module

    reg.get_crawler_provider.cache_clear()
    reg.get_search_data_provider.cache_clear()
    reg.get_llm_provider.cache_clear()
    reg.get_gsc_provider.cache_clear()

    mock_settings = cfg_module.Settings(
        crawler_provider="firecrawl",
        firecrawl_api_key="test-fc-key",
        search_data_provider="dataforseo",
        dataforseo_login="test-login",
        dataforseo_password="test-pass",
        llm_provider="anthropic",
        anthropic_api_key="test-anthropic-key",
        gsc_provider="google",
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
        google_redirect_uri="http://localhost/callback",
    )
    with patch.object(reg, "settings", mock_settings):
        reg.get_crawler_provider.cache_clear()
        reg.get_search_data_provider.cache_clear()
        reg.get_llm_provider.cache_clear()
        reg.get_gsc_provider.cache_clear()

        assert isinstance(reg.get_crawler_provider(), CrawlerProvider)
        assert isinstance(reg.get_search_data_provider(), SearchDataProvider)
        assert isinstance(reg.get_llm_provider(), LLMProvider)
        assert isinstance(reg.get_gsc_provider(), GSCProvider)

    # Clean up so other tests are not affected by cached instances
    reg.get_crawler_provider.cache_clear()
    reg.get_search_data_provider.cache_clear()
    reg.get_llm_provider.cache_clear()
    reg.get_gsc_provider.cache_clear()
