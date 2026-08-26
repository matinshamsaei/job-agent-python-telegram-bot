from datetime import UTC, datetime

import httpx
import structlog

from app.collectors.base import RawJob
from app.collectors.greenhouse import html_to_text
from app.core.config import Settings
from app.models import TargetCompany

logger = structlog.get_logger(__name__)


class LeverCollector:
    name = "lever"

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def collect(self, company: TargetCompany) -> list[RawJob]:
        token = company.board_token
        if not token:
            return []
        url = f"https://api.lever.co/v0/postings/{token}"
        response = await self.client.get(
            url,
            params={"mode": "json"},
            timeout=self.settings.http_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        jobs: list[RawJob] = []
        for item in payload:
            categories = item.get("categories") or {}
            location = categories.get("location") or item.get("country")
            html = item.get("description") or ""
            plain = item.get("descriptionPlain") or html_to_text(html)
            created = item.get("createdAt")
            posted_at = None
            if isinstance(created, (int, float)):
                posted_at = datetime.fromtimestamp(created / 1000, tz=UTC)
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=str(item.get("id") or item.get("id")),
                    title=item.get("text") or "",
                    url=item.get("hostedUrl") or item.get("applyUrl") or "",
                    location=location,
                    description=plain,
                    description_html=html,
                    employment_type=categories.get("commitment"),
                    posted_at=posted_at,
                    extra={"team": categories.get("team")},
                )
            )
        logger.info("lever_collected", company=company.slug, count=len(jobs))
        return jobs

    async def enrich(self, company: TargetCompany, raw: RawJob) -> RawJob:
        return raw
