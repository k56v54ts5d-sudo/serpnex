import asyncio
import base64
from datetime import datetime, timezone

import httpx

from app.providers.base.search_data import (
    BacklinkMetrics,
    DomainMetrics,
    OrganicResult,
    SearchDataError,
    SearchDataProvider,
    SerpResult,
)


class DataForSEOSearchDataProvider(SearchDataProvider):
    """SearchDataProvider backed by the DataForSEO API (SERP + Backlinks endpoints)."""

    _BASE_URL = "https://api.dataforseo.com/v3"

    def __init__(self, login: str, password: str) -> None:
        if not login or not password:
            raise ValueError("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD are not configured")
        credentials = base64.b64encode(f"{login}:{password}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

    async def get_serp(self, keyword: str, location_code: int = 2840) -> SerpResult:
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": "en",
                "depth": 10,
            }
        ]
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._BASE_URL}/serp/google/organic/live/regular",
                headers=self._headers,
                json=payload,
            )

        if response.status_code != 200:
            raise SearchDataError(f"DataForSEO SERP returned HTTP {response.status_code}")

        body = response.json()
        task = self._extract_task(body, "SERP")
        result = (task.get("result") or [{}])[0]

        organic_items = [
            item for item in (result.get("items") or []) if item.get("type") == "organic"
        ]
        features = [
            item["type"]
            for item in (result.get("items") or [])
            if item.get("type") != "organic"
        ]

        return SerpResult(
            keyword=keyword,
            total_results=result.get("se_results_count", 0),
            organic=[
                OrganicResult(
                    position=item.get("rank_absolute", idx + 1),
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("description"),
                )
                for idx, item in enumerate(organic_items)
            ],
            features=list(set(features)),
        )

    async def get_backlink_metrics(self, url: str) -> BacklinkMetrics:
        payload = [{"target": url, "limit": 5, "order_by": ["referring_domains,desc"]}]
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._BASE_URL}/backlinks/summary/live",
                headers=self._headers,
                json=payload,
            )

        if response.status_code != 200:
            raise SearchDataError(f"DataForSEO Backlinks returned HTTP {response.status_code}")

        body = response.json()
        task = self._extract_task(body, "Backlinks")
        result = (task.get("result") or [{}])[0]

        anchors_raw = result.get("anchor_summary", {}).get("anchors", [])
        top_anchors = [
            {"anchor": a.get("anchor", ""), "count": a.get("backlinks", 0)}
            for a in anchors_raw[:5]
        ]

        return BacklinkMetrics(
            url=url,
            referring_domains=result.get("referring_domains", 0),
            domain_rating=result.get("domain_rank"),
            spam_score=result.get("spam_score"),
            top_anchors=top_anchors,
        )

    async def get_domain_metrics(self, domain: str) -> DomainMetrics:
        """Fetch domain-level traffic, trajectory, authority, spam risk, and maturity.

        Maps DataForSEO Domain Overview (organic traffic) and Backlinks Summary
        responses to the provider-agnostic DomainMetrics model.

        Traffic tier thresholds: high ≥ 10k/mo; medium 1k–10k; low 100–1k;
        minimal < 100. Trajectory derived from 12-month organic traffic trend:
        growing > +15%; declining < -15%; stable otherwise.
        Spam risk is the inverse of DataForSEO's spam_score percentage (0–100 → 1.0–0.0)."""

        # DataForSEO Domain Overview endpoint for traffic signals
        traffic_payload = [{"target": domain, "location_code": 2840, "language_code": "en"}]
        backlink_payload = [{"target": domain, "limit": 1}]

        async with httpx.AsyncClient(timeout=30.0) as client:
            traffic_resp, backlink_resp = await asyncio.gather(
                client.post(
                    f"{self._BASE_URL}/dataforseo_labs/google/domain_intersection/live",
                    headers=self._headers,
                    json=traffic_payload,
                ),
                client.post(
                    f"{self._BASE_URL}/backlinks/summary/live",
                    headers=self._headers,
                    json=backlink_payload,
                ),
                return_exceptions=True,
            )

        # ── Traffic signals ────────────────────────────────────────────────────
        traffic_tier: str = "unknown"
        traffic_trajectory: str = "unknown"
        maturity_years: float | None = None

        if not isinstance(traffic_resp, Exception) and traffic_resp.status_code == 200:
            try:
                body = traffic_resp.json()
                task = self._extract_task(body, "DomainOverview")
                result = (task.get("result") or [{}])[0]
                metrics = result.get("metrics", {}).get("organic", {})

                monthly_traffic = metrics.get("etv", 0) or 0
                if monthly_traffic >= 10_000:
                    traffic_tier = "high"
                elif monthly_traffic >= 1_000:
                    traffic_tier = "medium"
                elif monthly_traffic >= 100:
                    traffic_tier = "low"
                else:
                    traffic_tier = "minimal"

                # Trajectory: compare current vs 12-month-ago estimate if available
                historical = result.get("historical_bulk_traffic", [])
                if len(historical) >= 2:
                    current = historical[-1].get("organic_etv") or 0
                    past = historical[0].get("organic_etv") or 0
                    if past > 0:
                        change = (current - past) / past
                        if change > 0.15:
                            traffic_trajectory = "growing"
                        elif change < -0.15:
                            traffic_trajectory = "declining"
                        else:
                            traffic_trajectory = "stable"

                # Domain age from creation date if available
                created_date = result.get("domain_info", {}).get("creation_date")
                if created_date:
                    try:
                        created = datetime.fromisoformat(created_date.replace("Z", "+00:00"))
                        now = datetime.now(timezone.utc)
                        maturity_years = round((now - created).days / 365.25, 1)
                    except (ValueError, TypeError):
                        pass
            except (SearchDataError, KeyError, IndexError):
                pass

        # ── Authority + spam signals ───────────────────────────────────────────
        referring_domains: int | None = None
        spam_risk: float | None = None

        if not isinstance(backlink_resp, Exception) and backlink_resp.status_code == 200:
            try:
                body = backlink_resp.json()
                task = self._extract_task(body, "BacklinksSummary")
                result = (task.get("result") or [{}])[0]
                referring_domains = result.get("referring_domains") or None
                raw_spam = result.get("spam_score")
                # DataForSEO spam_score is 0–100 (higher = spammier).
                # Invert and normalise to 0–1 (1.0 = clean).
                if raw_spam is not None:
                    spam_risk = round(1.0 - (raw_spam / 100.0), 3)
            except (SearchDataError, KeyError, IndexError):
                pass

        return DomainMetrics(
            domain=domain,
            traffic_tier=traffic_tier,
            traffic_trajectory=traffic_trajectory,
            referring_domains=referring_domains,
            spam_risk=spam_risk,
            maturity_years=maturity_years,
        )

    @staticmethod
    def _extract_task(body: dict, label: str) -> dict:
        tasks = body.get("tasks") or []
        if not tasks:
            raise SearchDataError(f"DataForSEO {label} response contained no tasks")
        task = tasks[0]
        if task.get("status_code") != 20000:
            raise SearchDataError(
                f"DataForSEO {label} task error: {task.get('status_message', 'unknown')}"
            )
        return task
