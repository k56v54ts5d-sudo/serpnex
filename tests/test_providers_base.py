"""Verify that provider interfaces are properly abstract and cannot be
instantiated directly. This ensures no business logic accidentally bypasses
the abstraction layer."""

import pytest

from app.providers.base.crawler import CrawlerProvider
from app.providers.base.gsc import GSCProvider
from app.providers.base.llm import LLMProvider
from app.providers.base.search_data import SearchDataProvider


def test_crawler_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        CrawlerProvider()  # type: ignore[abstract]


def test_search_data_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        SearchDataProvider()  # type: ignore[abstract]


def test_llm_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]


def test_gsc_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        GSCProvider()  # type: ignore[abstract]
