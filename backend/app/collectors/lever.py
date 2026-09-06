from datetime import UTC, datetime

import httpx
import structlog

from app.collectors.base import CollectorTarget, MissingTokenError, RawJob
from app.collectors.greenhouse import html_to_text
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

logger = structlog.get_logger(__name__)


class LeverCollector:
    name = "lever"
    ats_type = AtsType.LEVER.value
    strategy = CollectionStrategy.API.value

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def feed_url(self, target: CollectorTarget) -> str:
        if target.feed_url:
            return target.feed_url
        if not target.board_token:
            raise MissingTokenError("lever requires a site token")
        return f"https://api.lever.co/v0/postings/{target.board_token}"

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        response = await self.client.get(self.feed_url(target), params={"mode": "json"})
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
                    external_id=str(item.get("id") or ""),
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
        logger.info("lever_collected", company=target.company_slug, count=len(jobs))
        return jobs

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        return raw
