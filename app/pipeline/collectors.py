"""Data collection phase (§3.2).

Runs all external data fetches in parallel where possible. Returns an
AnalysisContext with raw collected data and a data_quality map. Contains
no business logic — it only fetches, caches, and reports availability."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.pipeline.cache import get_cache
from app.providers.base.crawler import CrawlError, CrawlResult
from app.providers.base.gsc import GSCPageMetrics
from app.providers.base.search_data import BacklinkMetrics, SerpResult
from app.providers.registry import get_crawler_provider, get_gsc_provider, get_search_data_provider


@dataclass
class AnalysisContext:
    """All raw data collected for a single page analysis run."""

    page_url: str

    # Page crawl
    page_crawl: CrawlResult | None = None
    page_crawl_error: str | None = None

    # GSC data
    gsc_metrics: GSCPageMetrics | None = None
    gsc_connected: bool = False

    # SERP + competitors
    serp_result: SerpResult | None = None
    primary_keyword: str | None = None
    competitor_crawls: list[CrawlResult | CrawlError] = field(default_factory=list)
    competitor_urls: list[str] = field(default_factory=list)

    # Backlinks
    target_backlinks: BacklinkMetrics | None = None
    competitor_backlinks: list[BacklinkMetrics | None] = field(default_factory=list)

    @property
    def data_quality(self) -> dict[str, bool]:
        """Signal availability map consumed by the confidence scoring model."""
        successful_competitor_crawls = sum(
            1 for c in self.competitor_crawls if isinstance(c, CrawlResult)
        )
        competitor_backlinks_available = sum(
            1 for b in self.competitor_backlinks if b is not None
        )
        return {
            "page_crawled": self.page_crawl is not None,
            "gsc_connected": self.gsc_connected,
            "gsc_data": self.gsc_metrics is not None,
            "serp_available": self.serp_result is not None,
            "competitor_count": successful_competitor_crawls,
            "target_backlinks": self.target_backlinks is not None,
            "competitor_backlinks_count": competitor_backlinks_available,
        }


async def collect(
    page_url: str,
    *,
    gsc_tokens: dict | None,
    gsc_property: str | None,
) -> AnalysisContext:
    """Orchestrate data collection for a full page analysis (§3.2).

    Phase 1 runs in parallel: page crawl + GSC fetch.
    Phase 2 is sequential: keyword identification → SERP → competitors + backlinks.
    Cache is checked before every external call."""

    ctx = AnalysisContext(page_url=page_url)
    cache = get_cache()
    crawler = get_crawler_provider()
    search = get_search_data_provider()

    # ── Phase 1: page crawl + GSC (parallel) ─────────────────────────────────
    crawl_task = _fetch_crawl(crawler, cache, page_url)
    gsc_task = _fetch_gsc(cache, page_url, gsc_tokens, gsc_property)

    crawl_result, gsc_result = await asyncio.gather(crawl_task, gsc_task, return_exceptions=True)

    if isinstance(crawl_result, CrawlResult):
        ctx.page_crawl = crawl_result
    elif isinstance(crawl_result, Exception):
        ctx.page_crawl_error = str(crawl_result)

    if isinstance(gsc_result, GSCPageMetrics):
        ctx.gsc_metrics = gsc_result
        ctx.gsc_connected = True
    # gsc_result may be None (not connected) or an exception — both mean no GSC data

    # ── Phase 2: keyword identification ──────────────────────────────────────
    keyword = _identify_keyword(ctx)
    if keyword is None:
        # No keyword = no SERP = no competitors; analysis can still run with lower confidence
        return ctx
    ctx.primary_keyword = keyword

    # ── Phase 3: SERP (sequential — competitor URLs depend on this) ───────────
    serp = await _fetch_serp(search, cache, keyword)
    ctx.serp_result = serp

    if serp is None:
        return ctx

    ctx.competitor_urls = [r.url for r in serp.organic[:3]]

    # ── Phase 4: competitor crawls + target and competitor backlinks (parallel)
    competitor_crawl_task = crawler.crawl_many(ctx.competitor_urls)
    target_backlink_task = _fetch_backlinks(search, cache, page_url, namespace="backlinks_target")
    competitor_backlink_tasks = [
        _fetch_backlinks(search, cache, url, namespace="backlinks_target")
        for url in ctx.competitor_urls
    ]

    results = await asyncio.gather(
        competitor_crawl_task,
        target_backlink_task,
        *competitor_backlink_tasks,
        return_exceptions=True,
    )

    competitor_crawls = results[0]
    target_backlinks = results[1]
    comp_backlinks = results[2:]

    ctx.competitor_crawls = competitor_crawls if isinstance(competitor_crawls, list) else []
    ctx.target_backlinks = target_backlinks if isinstance(target_backlinks, BacklinkMetrics) else None
    ctx.competitor_backlinks = [
        b if isinstance(b, BacklinkMetrics) else None for b in comp_backlinks
    ]

    return ctx


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _fetch_crawl(crawler, cache, url: str) -> CrawlResult | None:
    cached = await cache.get("crawl", url)
    if cached:
        from app.providers.base.crawler import CrawlResult as CR
        return CR(**cached)
    result = await crawler.crawl(url)
    await cache.set("crawl", result.__dict__, url)
    return result


async def _fetch_gsc(
    cache,
    page_url: str,
    tokens: dict | None,
    gsc_property: str | None,
) -> GSCPageMetrics | None:
    if not tokens or not gsc_property:
        return None
    cached = await cache.get("gsc", gsc_property, page_url)
    if cached:
        from app.providers.base.gsc import GSCPageMetrics as GM, GSCKeywordRow
        rows = [GSCKeywordRow(**r) for r in cached.get("keywords", [])]
        return GM(
            url=cached["url"],
            keywords=rows,
            total_clicks=cached["total_clicks"],
            total_impressions=cached["total_impressions"],
        )
    provider = get_gsc_provider()
    metrics = await provider.get_page_metrics(tokens, gsc_property, page_url)
    kw_dicts = [
        {"keyword": k.keyword, "clicks": k.clicks, "impressions": k.impressions,
         "ctr": k.ctr, "position": k.position}
        for k in metrics.keywords
    ]
    await cache.set("gsc", {
        "url": metrics.url,
        "keywords": kw_dicts,
        "total_clicks": metrics.total_clicks,
        "total_impressions": metrics.total_impressions,
    }, gsc_property, page_url)
    return metrics


async def _fetch_serp(search, cache, keyword: str) -> SerpResult | None:
    cached = await cache.get("serp", keyword)
    if cached:
        from app.providers.base.search_data import SerpResult as SR, OrganicResult
        organic = [OrganicResult(**o) for o in cached.get("organic", [])]
        return SR(
            keyword=keyword,
            total_results=cached["total_results"],
            organic=organic,
            features=cached.get("features", []),
        )
    try:
        result = await search.get_serp(keyword)
        payload = {
            "keyword": result.keyword,
            "total_results": result.total_results,
            "organic": [o.__dict__ for o in result.organic],
            "features": result.features,
        }
        await cache.set("serp", payload, keyword)
        return result
    except Exception:
        return None


async def _fetch_backlinks(search, cache, url: str, namespace: str) -> BacklinkMetrics | None:
    cached = await cache.get(namespace, url)
    if cached:
        from app.providers.base.search_data import BacklinkMetrics as BM
        return BM(**cached)
    try:
        metrics = await search.get_backlink_metrics(url)
        await cache.set(namespace, metrics.__dict__, url)
        return metrics
    except Exception:
        return None


def _identify_keyword(ctx: AnalysisContext) -> str | None:
    """Identify the primary keyword for SERP lookup (§2.3).

    Priority: GSC top impression keyword → page title inference.
    Returns None if no keyword can be identified."""
    if ctx.gsc_metrics and ctx.gsc_metrics.keywords:
        # GSC keywords are already ordered by impressions descending
        return ctx.gsc_metrics.keywords[0].keyword

    if ctx.page_crawl and ctx.page_crawl.title:
        # Fallback: use the page title as a keyword proxy
        return ctx.page_crawl.title.strip()

    return None
