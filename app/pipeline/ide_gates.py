"""Hard exclusion gate evaluation for the Investment Decision Engine (§3.5, §5).

Five deterministic gates (H1–H5). No LLM calls. Evaluated in order — the first
gate that triggers returns immediately. Each gate operates on the IDEContext
produced by ide_collector. Returns a GateResult; if triggered=True the
orchestrator writes a not_recommended verdict and skips all further stages."""

from __future__ import annotations

from app.providers.base.search_data import DomainMetrics
from app.schemas.opportunities import GateResult, HardExclusionGate, IDEContext

# ── Gate evaluation order ─────────────────────────────────────────────────────
# H3 first (cheapest signal, catches malware before crawling more pages).
# H1 next (prohibited content detected in crawled pages).
# H2 (deindexed/penalized — requires traffic + backlink signals).
# H4 (language impossibility — crawl required).
# H5 (manual action indicators — requires traffic history).
_GATE_ORDER = ["H3", "H1", "H2", "H4", "H5"]


def evaluate_gates(ctx: IDEContext) -> GateResult:
    """Evaluate all hard exclusion gates in order. Returns at the first trigger."""
    for gate_id in _GATE_ORDER:
        result = _GATE_CHECKS[gate_id](ctx)
        if result.triggered:
            return result
    return GateResult(triggered=False)


# ── Individual gate checks ────────────────────────────────────────────────────

def _check_h3_malware(ctx: IDEContext) -> GateResult:
    """H3 — Malware or phishing flag.

    Triggers when: DataForSEO spam signals indicate a malware / phishing pattern,
    OR the domain's spam_risk score is at the absolute floor (0.0 after inversion),
    which in DataForSEO terms means a spam_score of 100.

    Without a dedicated Safe Browsing API call (not in MVP scope), this gate
    uses the available spam_risk signal as a proxy. A spam_risk of 0.0 means the
    provider returned maximum spam — treat as a malware/phishing indicator."""
    if ctx.domain_metrics is None:
        return GateResult(triggered=False)

    dm: DomainMetrics = ctx.domain_metrics
    if dm.spam_risk is not None and dm.spam_risk == 0.0:
        return GateResult(
            triggered=True,
            gate=HardExclusionGate.H3_MALWARE,
            reason=(
                "Domain spam risk signal is at maximum (0.0 clean score), indicating "
                "a malware or phishing pattern. Investment not recommended."
            ),
        )
    return GateResult(triggered=False)


def _check_h1_prohibited_content(ctx: IDEContext) -> GateResult:
    """H1 — Prohibited content: adult, escort, illegal, scam sites.

    Checks crawled page titles and content for prohibited category signals.
    This is a heuristic keyword scan over the crawled content. The LLM Call 1
    provides a more nuanced assessment via D4 (editorial integrity), but this
    gate catches obvious cases before any LLM call runs."""
    _PROHIBITED_PATTERNS = [
        "escort", "adult dating", "porn", "xxx", "gambling casino",
        "buy followers", "buy fake", "get rich quick", "miracle cure",
        "darkweb", "dark web market",
    ]
    all_crawls = _all_crawls(ctx)
    if not all_crawls:
        return GateResult(triggered=False)

    for crawl in all_crawls:
        text = _crawl_text(crawl).lower()
        for pattern in _PROHIBITED_PATTERNS:
            if pattern in text:
                return GateResult(
                    triggered=True,
                    gate=HardExclusionGate.H1_PROHIBITED_CONTENT,
                    reason=(
                        f"Prohibited content pattern detected in crawled pages: '{pattern}'. "
                        "This site category is not eligible for link investment."
                    ),
                )
    return GateResult(triggered=False)


def _check_h2_deindexed(ctx: IDEContext) -> GateResult:
    """H2 — Deindexed or algorithmically penalized site.

    Triggers when: domain traffic is 'minimal' (< 100/mo estimated) AND the
    domain has a meaningful backlink profile (≥ 20 referring domains). This
    combination — established links but near-zero traffic — is a strong signal
    of a Google penalty or deindex affecting the whole domain."""
    dm: DomainMetrics | None = ctx.domain_metrics
    bm = ctx.backlink_metrics

    if dm is None or bm is None:
        return GateResult(triggered=False)

    if dm.traffic_tier == "minimal" and bm.referring_domains is not None and bm.referring_domains >= 20:
        return GateResult(
            triggered=True,
            gate=HardExclusionGate.H2_DEINDEXED_PENALIZED,
            reason=(
                f"Domain shows near-zero organic traffic (tier: minimal) despite "
                f"{bm.referring_domains} referring domains — consistent with a Google "
                "algorithmic penalty or deindex. Investment not recommended."
            ),
        )
    return GateResult(triggered=False)


def _check_h4_language_impossible(ctx: IDEContext) -> GateResult:
    """H4 — Complete language impossibility: zero audience overlap.

    Triggers when all crawled pages are in a language incompatible with any
    plausible target audience for the prospect URL, AND the domain TLD is
    country-specific and non-overlapping. We detect language from crawled
    content character sets — this is a coarse check for obvious mismatches
    (e.g., a Japanese-only site evaluated for an English SEO guide)."""
    all_crawls = _all_crawls(ctx)
    if not all_crawls:
        return GateResult(triggered=False)

    # Detect obvious non-Latin scripts that indicate a non-overlapping language
    _INCOMPATIBLE_SCRIPTS = [
        "一",  # CJK Unified Ideographs (Chinese/Japanese/Korean block start)
        "؀",  # Arabic block start
        "ऀ",  # Devanagari (Hindi) block start
        "Ѐ",  # Cyrillic block start
        "฀",  # Thai block start
    ]
    # Only trigger if ALL crawled pages show incompatible script
    incompatible_count = 0
    for crawl in all_crawls:
        text = _crawl_text(crawl)
        if any(char in text for char in _INCOMPATIBLE_SCRIPTS):
            incompatible_count += 1

    if incompatible_count == len(all_crawls) and len(all_crawls) >= 2:
        return GateResult(
            triggered=True,
            gate=HardExclusionGate.H4_LANGUAGE_IMPOSSIBLE,
            reason=(
                "All crawled pages appear to be in a script incompatible with the "
                "target audience language. Zero audience overlap — investment not viable."
            ),
        )
    return GateResult(triggered=False)


def _check_h5_manual_action(ctx: IDEContext) -> GateResult:
    """H5 — Manual action indicators: severe traffic loss with link profile intact.

    Triggers when: traffic trajectory is 'declining' AND the domain had a
    meaningful backlink profile. A sharp traffic decline despite an established
    link profile suggests a manual penalty rather than organic decline."""
    dm: DomainMetrics | None = ctx.domain_metrics
    bm = ctx.backlink_metrics

    if dm is None:
        return GateResult(triggered=False)

    # Traffic must be actively declining (not just 'minimal')
    if dm.traffic_trajectory != "declining":
        return GateResult(triggered=False)

    # Backlink profile must be established (manual actions usually affect linked sites)
    if bm is None or bm.referring_domains is None or bm.referring_domains < 50:
        return GateResult(triggered=False)

    # Spam risk must still be acceptable (if spam is also high, H3 or H2 fires first)
    if dm.spam_risk is not None and dm.spam_risk < 0.30:
        return GateResult(triggered=False)

    return GateResult(
        triggered=True,
        gate=HardExclusionGate.H5_MANUAL_ACTION,
        reason=(
            f"Domain traffic is sharply declining despite {bm.referring_domains} referring domains — "
            "pattern consistent with a Google manual action. "
            "Investment not recommended until traffic recovers."
        ),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _all_crawls(ctx: IDEContext) -> list:
    """Collect all available crawled pages from the context."""
    result = []
    if ctx.placement_page_crawl is not None:
        result.append(ctx.placement_page_crawl)
    result.extend(c for c in ctx.sampled_article_crawls if c is not None)
    result.extend(c for c in ctx.domain_sample_crawls if c is not None)
    return result


def _crawl_text(crawl) -> str:
    """Extract available text from a CrawlResult."""
    parts = []
    if hasattr(crawl, "title") and crawl.title:
        parts.append(crawl.title)
    if hasattr(crawl, "markdown") and crawl.markdown:
        parts.append(crawl.markdown[:2000])
    return " ".join(parts)


_GATE_CHECKS = {
    "H3": _check_h3_malware,
    "H1": _check_h1_prohibited_content,
    "H2": _check_h2_deindexed,
    "H4": _check_h4_language_impossible,
    "H5": _check_h5_manual_action,
}
