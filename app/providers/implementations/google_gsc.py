import asyncio
import json
from datetime import date, timedelta

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.providers.base.gsc import (
    GSCAuthUrl,
    GSCError,
    GSCKeywordRow,
    GSCPageMetrics,
    GSCProperty,
    GSCProvider,
)

_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class GoogleGSCProvider(GSCProvider):
    """GSCProvider backed by the Google Search Console API via OAuth2.

    All synchronous googleapiclient calls are dispatched to a thread pool
    via asyncio.to_thread() so they do not block the event loop."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        if not client_id or not client_secret:
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not configured")
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def _build_flow(self) -> Flow:
        client_config = {
            "web": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uris": [self._redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=_SCOPES,
            redirect_uri=self._redirect_uri,
        )

    def get_auth_url(self, state: str) -> GSCAuthUrl:
        flow = self._build_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent",
        )
        return GSCAuthUrl(url=auth_url, state=state)

    async def exchange_code(self, code: str) -> dict:
        def _sync_exchange() -> dict:
            flow = self._build_flow()
            flow.fetch_token(code=code)
            return json.loads(flow.credentials.to_json())

        try:
            return await asyncio.to_thread(_sync_exchange)
        except Exception as exc:
            raise GSCError(f"Token exchange failed: {exc}") from exc

    async def list_properties(self, tokens: dict) -> list[GSCProperty]:
        def _sync_list() -> list[GSCProperty]:
            creds = Credentials.from_authorized_user_info(tokens, scopes=_SCOPES)
            service = build("searchconsole", "v1", credentials=creds)
            result = service.sites().list().execute()
            return [
                GSCProperty(
                    property_uri=site["siteUrl"],
                    permission_level=site.get("permissionLevel", "unknown"),
                )
                for site in result.get("siteEntry", [])
            ]

        try:
            return await asyncio.to_thread(_sync_list)
        except Exception as exc:
            raise GSCError(f"list_properties failed: {exc}") from exc

    async def get_page_metrics(
        self,
        tokens: dict,
        property_uri: str,
        page_url: str,
        days: int = 90,
        row_limit: int = 5,
    ) -> GSCPageMetrics:
        def _sync_fetch() -> GSCPageMetrics:
            creds = Credentials.from_authorized_user_info(tokens, scopes=_SCOPES)
            service = build("webmasters", "v3", credentials=creds)

            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=days)).isoformat()

            request_body = {
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["query"],
                "dimensionFilterGroups": [
                    {
                        "filters": [
                            {
                                "dimension": "page",
                                "operator": "equals",
                                "expression": page_url,
                            }
                        ]
                    }
                ],
                "rowLimit": row_limit,
                "orderBy": [{"fieldName": "impressions", "sortOrder": "DESCENDING"}],
            }

            response = (
                service.searchanalytics()
                .query(siteUrl=property_uri, body=request_body)
                .execute()
            )

            rows = response.get("rows", [])
            keywords = [
                GSCKeywordRow(
                    keyword=row["keys"][0],
                    clicks=int(row.get("clicks", 0)),
                    impressions=int(row.get("impressions", 0)),
                    ctr=float(row.get("ctr", 0.0)),
                    position=float(row.get("position", 0.0)),
                )
                for row in rows
            ]

            return GSCPageMetrics(
                url=page_url,
                keywords=keywords,
                total_clicks=sum(k.clicks for k in keywords),
                total_impressions=sum(k.impressions for k in keywords),
            )

        try:
            return await asyncio.to_thread(_sync_fetch)
        except Exception as exc:
            raise GSCError(f"get_page_metrics failed: {exc}") from exc
