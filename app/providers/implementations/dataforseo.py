import base64

import httpx

from app.providers.base.search_data import (
    BacklinkMetrics,
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
