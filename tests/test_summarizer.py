"""Tests for the content summarization stage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.summarizer import _extract_metadata, summarize_page
from app.providers.base.crawler import CrawlResult
from app.providers.base.llm import LLMResponse
from app.schemas.verdicts import FormatLabel, PageSummary


def _make_crawl(url="https://example.com/page", title="Test Page", markdown="") -> CrawlResult:
    return CrawlResult(url=url, title=title, markdown=markdown, html="", meta_description=None, status_code=200)


class TestExtractMetadata:
    def test_extracts_h1_from_markdown(self):
        crawl = _make_crawl(markdown="# My Page Title\n\nSome content here.")
        meta = _extract_metadata(crawl)
        assert meta["h1"] == "My Page Title"

    def test_extracts_h2_list(self):
        crawl = _make_crawl(markdown="# Title\n\n## Section One\n\n## Section Two\n\nContent.")
        meta = _extract_metadata(crawl)
        assert "Section One" in meta["h2_list"]
        assert "Section Two" in meta["h2_list"]

    def test_word_count_approximate(self):
        words = " ".join(["word"] * 50)
        crawl = _make_crawl(markdown=f"# Title\n\n{words}")
        meta = _extract_metadata(crawl)
        assert meta["word_count"] > 40

    def test_truncates_at_2200_words(self):
        long_text = " ".join(["word"] * 3000)
        crawl = _make_crawl(markdown=f"# Title\n\n{long_text}")
        meta = _extract_metadata(crawl)
        assert "[truncated]" in meta["markdown_body"]

    def test_strips_footer_patterns(self):
        crawl = _make_crawl(markdown="# Title\n\nContent.\n\n© 2024 Company")
        meta = _extract_metadata(crawl)
        assert "©" not in meta["markdown_body"]

    def test_no_h1_returns_none_str(self):
        crawl = _make_crawl(markdown="Just some content without a heading.")
        meta = _extract_metadata(crawl)
        assert meta["h1"] == "none"

    def test_empty_markdown(self):
        crawl = _make_crawl(markdown="")
        meta = _extract_metadata(crawl)
        assert meta["word_count"] == 0
        assert meta["h1"] == "none"


class TestSummarizePage:
    @pytest.mark.asyncio
    async def test_summarize_page_returns_page_summary(self):
        crawl = _make_crawl(markdown="# SEO Guide\n\n## Why SEO matters\n\nContent here about SEO.")
        tool_input = {
            "topic_and_angle": "A guide to SEO fundamentals",
            "format_label": "guide",
            "heading_structure": "H1 + 1 H2 subheading",
            "intent_alignment": "Informational intent, matches guide format",
            "notable_elements": ["Numbered steps"],
            "visible_content_gaps": ["No case studies"],
        }
        mock_response = LLMResponse(
            tool_name="summarize_page",
            tool_input=tool_input,
            input_tokens=100,
            output_tokens=50,
        )
        mock_llm = AsyncMock()
        mock_llm.call_with_tool = AsyncMock(return_value=mock_response)

        with patch("app.pipeline.summarizer.get_llm_provider", return_value=mock_llm):
            result = await summarize_page(crawl)

        assert isinstance(result, PageSummary)
        assert result.format_label == FormatLabel.GUIDE
        assert "SEO" in result.topic_and_angle

    @pytest.mark.asyncio
    async def test_summarize_page_retries_on_validation_failure(self):
        crawl = _make_crawl(markdown="# Page\n\nContent.")
        bad_response = LLMResponse(
            tool_name="summarize_page",
            tool_input={"bad": "data"},
            input_tokens=100,
            output_tokens=50,
        )
        good_tool_input = {
            "topic_and_angle": "A guide to SEO",
            "format_label": "guide",
            "heading_structure": "H1 only",
            "intent_alignment": "Informational",
            "notable_elements": [],
            "visible_content_gaps": [],
        }
        good_response = LLMResponse(
            tool_name="summarize_page",
            tool_input=good_tool_input,
            input_tokens=100,
            output_tokens=50,
        )
        mock_llm = AsyncMock()
        mock_llm.call_with_tool = AsyncMock(side_effect=[bad_response, good_response])

        with patch("app.pipeline.summarizer.get_llm_provider", return_value=mock_llm):
            result = await summarize_page(crawl)

        assert isinstance(result, PageSummary)
        assert mock_llm.call_with_tool.call_count == 2
