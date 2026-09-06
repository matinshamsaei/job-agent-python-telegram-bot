import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx
import structlog

from app.collectors.base import CollectorTarget, MissingTokenError, RawJob
from app.collectors.greenhouse import html_to_text
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

logger = structlog.get_logger(__name__)

LOCATIONS_NS = "{https://teamtailor.com/locations}"


class TeamtailorCollector:
    """Teamtailor public jobs RSS feed.

    Career-site domains are custom (`career.<brand>.com` as often as
    `<brand>.teamtailor.com`), so a source may set `feed_url` directly.
    """

    name = "teamtailor"
    ats_type = AtsType.TEAMTAILOR.value
    strategy = CollectionStrategy.XML.value

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def feed_url(self, target: CollectorTarget) -> str:
        if target.feed_url:
            return target.feed_url
        if not target.board_token:
            raise MissingTokenError("teamtailor requires a career-site subdomain or feed_url")
        return f"https://{target.board_token}.teamtailor.com/jobs.rss"

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        response = await self.client.get(self.feed_url(target))
        response.raise_for_status()
        root = ET.fromstring(response.text)
        jobs: list[RawJob] = []
        for item in root.findall("./channel/item"):
            html = item.findtext("description") or ""
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or "").strip()
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=guid or link,
                    title=(item.findtext("title") or "").strip(),
                    url=link,
                    location=(item.findtext(f"{LOCATIONS_NS}locations") or "").strip() or None,
                    description=html_to_text(html),
                    description_html=html,
                    posted_at=_parse_rfc2822(item.findtext("pubDate")),
                    extra={
                        "remote_status": (item.findtext("remoteStatus") or "").strip() or None,
                        "department": (item.findtext(f"{LOCATIONS_NS}department") or "").strip() or None,
                    },
                )
            )
        logger.info("teamtailor_collected", company=target.company_slug, count=len(jobs))
        return jobs

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        return raw


def _parse_rfc2822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
