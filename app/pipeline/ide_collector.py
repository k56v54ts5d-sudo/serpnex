"""Investment Decision Engine data collection (§3.5).

Responsibilities:
1. Mode detection — classify the input URL as Mode A, B/category, or B/domain
2. Section inference — for Mode B/domain, find the best matching site section
3. Parallel data collection — crawl pages + fetch domain signals

Mode detection does not use an LLM. It is a deterministic URL and HTTP
response classifier. Section inference uses a lightweight Haiku call."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from app.providers.base.crawler import CrawlError, CrawlResult
from app.providers.base.search_data import BacklinkMetrics, DomainMetrics
from app.providers.registry import get_crawler_provider, get_llm_provider, get_search_data_provider
from app.schemas.opportunities import IDEContext

# Signals in page content that indicate a single article (vs a listing/category)
_ARTICLE_SIGNALS = [
    "published", "author", "byline", "date", "posted on",
    "written by", "updated", "share this", "reading time",
]

# URL path patterns that strongly indicate a category/listing page
_CATEGORY_PATH_PATTERNS = [
    "/category/", "/categories/", "/tag/", "/tags/",
    "/topic/", "/topics/", "/section/", "/archive/",
    "/blog/", "/articles/", "/resources/", "/learn/",
    "/news/", "/insights/", "/guides/",
]


async def collect_ide(
    prospect_url: str,
    target_topic: str | None = None,
    target_audience: str | None = None,
) -> IDEContext:
    """Entry point. Detect mode, then collect all signals for the IDE pipeline."""
    parsed = urlparse(prospect_url)
    domain = _extract_domain(parsed.netloc)

    ctx = IDEContext(
        prospect_url=prospect_url,
        prospect_domain=domain,
        target_topic=target_topic,
        target_audience=target_audience,
    )

    # ── Phase 1: Mode detection ───────────────────────────────────────────────
    mode, mode_b_subtype, note = await _detect_mode(prospect_url, parsed)
    ctx.mode = mode
    ctx.mode_b_subtype = mode_b_subtype
    ctx.mode_detection_note = note

    # ── Phase 2: Section inference (Mode B/domain only) ───────────────────────
    if mode == "guest_post_opportunity" and mode_b_subtype == "domain_inferred":
        inferred = await _infer_section(domain, target_topic)
        ctx.inferred_section = inferred

    # ── Phase 3: Parallel data collection ────────────────────────────────────
    await _collect_data(ctx, prospect_url, parsed, domain)

    return ctx


# ── Mode detection ────────────────────────────────────────────────────────────

async def _detect_mode(url: str, parsed) -> tuple[str, str | None, str | None]:
    """Classify the URL as Mode A or Mode B (and sub-type) using HTTP + heuristics.

    Returns (mode, mode_b_subtype, note)."""
    path = parsed.path.rstrip("/")
    is_root = path == "" or path == "/"

    if is_root:
        return "guest_post_opportunity", "domain_inferred", "Bare domain or root path — section inference required."

    # Check URL path for category patterns before fetching
    path_lower = path.lower()
    if any(pattern in path_lower for pattern in _CATEGORY_PATH_PATTERNS):
        return "guest_post_opportunity", "category_url", f"Category URL pattern detected in path: {path}"

    # Fetch the page to check content signals
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.head(url)
            if response.status_code in (405, 501):
                response = await client.get(url, headers={"Range": "bytes=0-5000"})
    except Exception:
        # Cannot reach — default to Mode B/domain to at least evaluate the domain
        return (
            "guest_post_opportunity",
            "domain_inferred",
            "Could not fetch prospect URL — defaulting to domain-level evaluation.",
        )

    if response.status_code >= 400:
        # URL not reachable — evaluate the domain instead
        return (
            "guest_post_opportunity",
            "domain_inferred",
            f"Prospect URL returned HTTP {response.status_code} — evaluating domain instead.",
        )

    # For GET responses: check content for article signals
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return "guest_post_opportunity", "category_url", "Non-HTML response — treating as section."

    # Try to detect article signals in a small content sample
    body_sample = ""
    if hasattr(response, "text"):
        body_sample = response.text[:3000].lower()

    article_signal_count = sum(1 for sig in _ARTICLE_SIGNALS if sig in body_sample)
    if article_signal_count >= 2:
        return "specific_placement", None, None

    # Default ambiguous paths to category_url (safer than domain_inferred for paths with depth)
    if path.count("/") >= 2:
        return (
            "guest_post_opportunity",
            "category_url",
            f"Ambiguous path depth ≥ 2 with {article_signal_count} article signals — treating as category.",
        )

    return (
        "guest_post_opportunity",
        "domain_inferred",
        f"Ambiguous URL — {article_signal_count} article signals found. Defaulting to domain evaluation.",
    )


# ── Section inference (Mode B/domain) ────────────────────────────────────────

async def _infer_section(domain: str, target_topic: str | None) -> str | None:
    """Infer the best matching content section for the target topic via Haiku."""
    if not target_topic:
        return None

    base_url = f"https://{domain}"
    crawler = get_crawler_provider()
    llm = get_llm_provider()

    # Fetch homepage and sitemap concurrently
    homepage_task = asyncio.create_task(_safe_crawl(crawler, base_url))
    sitemap_task = asyncio.create_task(_safe_crawl(crawler, f"{base_url}/sitemap.xml"))
    homepage, sitemap = await asyncio.gather(homepage_task, sitemap_task, return_exceptions=True)

    # Extract candidate section URLs from homepage links and sitemap
    sections = _extract_candidate_sections(domain, homepage, sitemap)
    if not sections:
        return None

    section_list = "\n".join(f"- {s}" for s in sections[:20])
    prompt = (
        f"Given the following content sections from {domain}, which section "
        f"is most likely to publish articles related to '{target_topic}'?\n\n"
        f"{section_list}\n\n"
        "Return only the URL of the best matching section, or 'none' if no section matches."
    )

    try:
        from app.providers.base.llm import LLMMessage
        messages = [LLMMessage(role="user", content=prompt)]
        response = await llm.complete(messages, max_tokens=100)
        text = (response.content or "").strip()
        if text.startswith("http") and domain in text:
            return text.split()[0]  # take first token if model returns extra text
    except Exception:
        pass

    return sections[0] if sections else None


def _extract_candidate_sections(domain: str, homepage, sitemap) -> list[str]:
    """Extract plausible section URLs from a homepage crawl and sitemap."""
    candidates = set()

    for source in [homepage, sitemap]:
        if not isinstance(source, CrawlResult) or not source.markdown:
            continue
        # Extract URLs from markdown links that look like section roots
        import re
        urls = re.findall(r'https?://[^\s\)\"]+', source.markdown)
        for url in urls:
            parsed = urlparse(url)
            if parsed.netloc and domain in parsed.netloc:
                path = parsed.path.rstrip("/")
                if path and path.count("/") == 1:  # top-level paths only
                    candidates.add(url.split("?")[0].split("#")[0])

    return list(candidates)[:15]


# ── Data collection ───────────────────────────────────────────────────────────

async def _collect_data(ctx: IDEContext, prospect_url: str, parsed, domain: str) -> None:
    """Collect crawled content and domain signals in parallel."""
    crawler = get_crawler_provider()
    search = get_search_data_provider()

    # Determine which URLs to crawl based on mode
    if ctx.mode == "specific_placement":
        primary_url = prospect_url
        secondary_urls = await _pick_domain_samples(domain, prospect_url)
        tasks = {
            "placement": asyncio.create_task(_safe_crawl(crawler, primary_url)),
            "domain_samples": asyncio.create_task(_crawl_many(crawler, secondary_urls)),
            "backlinks": asyncio.create_task(_safe_backlinks(search, prospect_url)),
            "domain_metrics": asyncio.create_task(_safe_domain_metrics(search, domain)),
        }
    else:
        # Mode B: crawl articles from section or inferred section
        section_url = ctx.inferred_section or prospect_url
        article_urls = await _extract_article_urls(crawler, section_url, limit=4)
        domain_sample_urls = await _pick_domain_samples(domain, section_url)
        tasks = {
            "articles": asyncio.create_task(_crawl_many(crawler, article_urls)),
            "domain_samples": asyncio.create_task(_crawl_many(crawler, domain_sample_urls)),
            "backlinks": asyncio.create_task(_safe_backlinks(search, domain)),
            "domain_metrics": asyncio.create_task(_safe_domain_metrics(search, domain)),
        }

    results = {}
    for key, task in tasks.items():
        try:
            results[key] = await task
        except Exception as exc:
            ctx.crawl_errors.append(f"{key}: {exc}")
            results[key] = None

    if ctx.mode == "specific_placement":
        ctx.placement_page_crawl = results.get("placement")
    else:
        articles = results.get("articles") or []
        ctx.sampled_article_crawls = [c for c in articles if isinstance(c, CrawlResult)]
        ctx.sampled_article_urls = [c.url for c in ctx.sampled_article_crawls]

    domain_samples = results.get("domain_samples") or []
    ctx.domain_sample_crawls = [c for c in domain_samples if isinstance(c, CrawlResult)]
    ctx.backlink_metrics = results.get("backlinks")
    ctx.domain_metrics = results.get("domain_metrics")


async def _extract_article_urls(crawler, section_url: str, limit: int = 4) -> list[str]:
    """Crawl a section/category page and extract article URLs."""
    try:
        section_crawl = await crawler.crawl(section_url)
        if not isinstance(section_crawl, CrawlResult) or not section_crawl.markdown:
            return []
    except Exception:
        return []

    import re
    parsed_section = urlparse(section_url)
    domain = parsed_section.netloc
    urls = re.findall(r'https?://[^\s\)\"\']+', section_crawl.markdown)
    seen = set()
    articles = []
    for url in urls:
        clean = url.split("?")[0].split("#")[0].rstrip("/")
        parsed = urlparse(clean)
        if parsed.netloc == domain and parsed.path.count("/") >= 2 and clean not in seen:
            seen.add(clean)
            articles.append(clean)
        if len(articles) >= limit:
            break
    return articles


async def _pick_domain_samples(domain: str, exclude_url: str) -> list[str]:
    """Return up to 3 domain sample URLs (homepage + top-level paths)."""
    base = f"https://{domain}"
    samples = [base]
    # Add a few common section paths as fallback samples
    for path in ["/about", "/blog", "/resources", "/articles"]:
        if len(samples) >= 3:
            break
        url = f"{base}{path}"
        if url != exclude_url:
            samples.append(url)
    return samples[:3]


async def _safe_crawl(crawler, url: str) -> CrawlResult | None:
    try:
        result = await crawler.crawl(url)
        return result if isinstance(result, CrawlResult) else None
    except Exception:
        return None


async def _crawl_many(crawler, urls: list[str]) -> list[CrawlResult]:
    tasks = [asyncio.create_task(_safe_crawl(crawler, url)) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, CrawlResult)]


async def _safe_backlinks(search, url: str) -> BacklinkMetrics | None:
    try:
        return await search.get_backlink_metrics(url)
    except Exception:
        return None


async def _safe_domain_metrics(search, domain: str) -> DomainMetrics | None:
    try:
        return await search.get_domain_metrics(domain)
    except Exception:
        return None


def _extract_domain(netloc: str) -> str:
    """Strip www. prefix and port from a netloc."""
    domain = netloc.split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.lower()
