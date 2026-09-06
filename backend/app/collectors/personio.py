import xml.etree.ElementTree as ET

import httpx
import structlog

from app.collectors.base import CollectorTarget, MissingTokenError, RawJob
from app.collectors.greenhouse import html_to_text
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

logger = structlog.get_logger(__name__)


class PersonioXmlCollector:
    name = "personio_xml"
    ats_type = AtsType.PERSONIO_XML.value
    strategy = CollectionStrategy.XML.value

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def feed_url(self, target: CollectorTarget) -> str:
        if target.feed_url:
            return target.feed_url
        if not target.board_token:
            raise MissingTokenError("personio requires a subdomain token")
        return f"https://{target.board_token}.jobs.personio.de/xml?language=en"

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        base = f"https://{target.board_token}.jobs.personio.de"
        response = await self.client.get(self.feed_url(target))
        response.raise_for_status()
        root = ET.fromstring(response.text)
        jobs: list[RawJob] = []
        for position in root.findall("position"):
            job_id = (position.findtext("id") or "").strip()
            title = (position.findtext("name") or "").strip()
            office = (position.findtext("office") or "").strip()
            employment = (position.findtext("employmentType") or "").strip()
            descriptions = []
            for block in position.findall("./jobDescriptions/jobDescription"):
                name = (block.findtext("name") or "").strip()
                value = html_to_text(block.findtext("value") or "")
                if value:
                    descriptions.append(f"{name}: {value}" if name else value)
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=job_id or title,
                    title=title,
                    url=f"{base}/job/{job_id}",
                    location=office or None,
                    description="\n\n".join(descriptions),
                    employment_type=employment or None,
                )
            )
        logger.info("personio_collected", company=target.company_slug, count=len(jobs))
        return jobs

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        return raw
