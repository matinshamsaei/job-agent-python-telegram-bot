import xml.etree.ElementTree as ET

import httpx
import structlog

from app.collectors.base import RawJob
from app.collectors.greenhouse import html_to_text
from app.core.config import Settings
from app.models import TargetCompany

logger = structlog.get_logger(__name__)


class PersonioXmlCollector:
    name = "personio_xml"

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def collect(self, company: TargetCompany) -> list[RawJob]:
        token = company.board_token
        if not token:
            return []
        url = f"https://{token}.jobs.personio.de/xml?language=en"
        response = await self.client.get(url, timeout=self.settings.http_timeout_seconds)
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
            description = "\n\n".join(descriptions)
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=job_id or title,
                    title=title,
                    url=f"https://{token}.jobs.personio.de/job/{job_id}",
                    location=office or None,
                    description=description,
                    employment_type=employment or None,
                )
            )
        logger.info("personio_collected", company=company.slug, count=len(jobs))
        return jobs

    async def enrich(self, company: TargetCompany, raw: RawJob) -> RawJob:
        return raw
