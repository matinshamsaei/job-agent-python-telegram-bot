from datetime import datetime

import httpx
import structlog
from bs4 import BeautifulSoup

from app.collectors.base import CollectorTarget, MissingTokenError, RawJob
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

logger = structlog.get_logger(__name__)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(" ", strip=True)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class GreenhouseCollector:
    name = "greenhouse"
    ats_type = AtsType.GREENHOUSE.value
    strategy = CollectionStrategy.API.value

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def feed_url(self, target: CollectorTarget) -> str:
        if target.feed_url:
            return target.feed_url
        if not target.board_token:
            raise MissingTokenError("greenhouse requires a board token")
        return f"https://boards-api.greenhouse.io/v1/boards/{target.board_token}/jobs"

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        response = await self.client.get(self.feed_url(target))
        response.raise_for_status()
        payload = response.json()
        jobs: list[RawJob] = []
        for item in payload.get("jobs", []):
            location = None
            if isinstance(item.get("location"), dict):
                location = item["location"].get("name")
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=str(item["id"]),
                    title=item.get("title") or "",
                    url=item.get("absolute_url") or "",
                    location=location,
                    posted_at=parse_dt(item.get("updated_at") or item.get("first_published")),
                    extra={"company_name": item.get("company_name")},
                )
            )
        logger.info("greenhouse_collected", company=target.company_slug, count=len(jobs))
        return jobs

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        if not target.board_token:
            return raw
        url = (
            f"https://boards-api.greenhouse.io/v1/boards/"
            f"{target.board_token}/jobs/{raw.external_id}"
        )
        response = await self.client.get(url)
        response.raise_for_status()
        item = response.json()
        html = item.get("content") or ""
        raw.description_html = html
        raw.description = html_to_text(html)
        if isinstance(item.get("location"), dict) and item["location"].get("name"):
            raw.location = item["location"]["name"]
        return raw
