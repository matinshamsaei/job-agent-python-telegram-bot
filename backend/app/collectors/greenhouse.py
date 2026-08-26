from datetime import datetime

import httpx
import structlog
from bs4 import BeautifulSoup

from app.collectors.base import RawJob
from app.core.config import Settings
from app.models import TargetCompany

logger = structlog.get_logger(__name__)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(" ", strip=True)


class GreenhouseCollector:
    name = "greenhouse"

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def collect(self, company: TargetCompany) -> list[RawJob]:
        token = company.board_token
        if not token:
            return []
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        response = await self.client.get(url, timeout=self.settings.http_timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        jobs: list[RawJob] = []
        for item in payload.get("jobs", []):
            location = None
            if isinstance(item.get("location"), dict):
                location = item["location"].get("name")
            posted = _parse_dt(item.get("updated_at") or item.get("first_published"))
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=str(item["id"]),
                    title=item.get("title") or "",
                    url=item.get("absolute_url") or "",
                    location=location,
                    posted_at=posted,
                    extra={"company_name": item.get("company_name")},
                )
            )
        logger.info("greenhouse_collected", company=company.slug, count=len(jobs))
        return jobs

    async def enrich(self, company: TargetCompany, raw: RawJob) -> RawJob:
        token = company.board_token
        if not token:
            return raw
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{raw.external_id}"
        response = await self.client.get(url, timeout=self.settings.http_timeout_seconds)
        response.raise_for_status()
        item = response.json()
        html = item.get("content") or ""
        raw.description_html = html
        raw.description = html_to_text(html)
        if isinstance(item.get("location"), dict) and item["location"].get("name"):
            raw.location = item["location"]["name"]
        return raw


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
