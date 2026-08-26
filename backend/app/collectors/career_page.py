import structlog

from app.collectors.base import RawJob
from app.models import TargetCompany

logger = structlog.get_logger(__name__)


class CareerPageCollector:
    name = "career_page"

    async def collect(self, company: TargetCompany) -> list[RawJob]:
        logger.info(
            "career_page_skipped",
            company=company.slug,
            reason="no_public_ats_json_or_xml_feed",
            careers_url=company.careers_url,
        )
        return []

    async def enrich(self, company: TargetCompany, raw: RawJob) -> RawJob:
        return raw
