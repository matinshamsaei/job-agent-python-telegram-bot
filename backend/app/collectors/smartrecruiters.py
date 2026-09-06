import httpx
import structlog

from app.collectors.base import CollectorTarget, MissingTokenError, RawJob
from app.collectors.greenhouse import html_to_text, parse_dt
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

logger = structlog.get_logger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 10
SECTION_ORDER = ("jobDescription", "qualifications", "additionalInformation")


class SmartRecruitersCollector:
    """SmartRecruiters public postings API.

    The list endpoint is paginated and description-free, so `enrich` fetches
    the per-posting job ad sections.
    """

    name = "smartrecruiters"
    ats_type = AtsType.SMARTRECRUITERS.value
    strategy = CollectionStrategy.API.value

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def _base(self, target: CollectorTarget) -> str:
        if not target.board_token:
            raise MissingTokenError("smartrecruiters requires a company identifier")
        return f"https://api.smartrecruiters.com/v1/companies/{target.board_token}/postings"

    def feed_url(self, target: CollectorTarget) -> str:
        return target.feed_url or self._base(target)

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        base = self._base(target)
        jobs: list[RawJob] = []
        offset = 0
        for _ in range(MAX_PAGES):
            response = await self.client.get(base, params={"limit": PAGE_SIZE, "offset": offset})
            response.raise_for_status()
            payload = response.json()
            content = payload.get("content") or []
            for item in content:
                jobs.append(_to_raw_job(self.name, item))
            offset += len(content)
            if not content or offset >= int(payload.get("totalFound") or 0):
                break
        logger.info("smartrecruiters_collected", company=target.company_slug, count=len(jobs))
        return jobs

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        if not target.board_token or not raw.external_id:
            return raw
        url = f"{self._base(target)}/{raw.external_id}"
        response = await self.client.get(url)
        response.raise_for_status()
        item = response.json()
        sections = ((item.get("jobAd") or {}).get("sections")) or {}
        blocks: list[str] = []
        for key in SECTION_ORDER:
            text = html_to_text(((sections.get(key) or {}).get("text")) or "")
            if text:
                blocks.append(text)
        if blocks:
            raw.description = "\n\n".join(blocks)
        raw.url = item.get("postingUrl") or item.get("applyUrl") or raw.url
        return raw


def _to_raw_job(source: str, item: dict) -> RawJob:
    location = item.get("location") or {}
    employment = item.get("typeOfEmployment") or {}
    return RawJob(
        source=source,
        external_id=str(item.get("id") or ""),
        title=item.get("name") or "",
        url=item.get("postingUrl") or item.get("applyUrl") or "",
        location=location.get("fullLocation") or _join_location(location),
        employment_type=employment.get("label"),
        posted_at=parse_dt(item.get("releasedDate")),
        extra={
            "department": (item.get("department") or {}).get("label"),
            "function": (item.get("function") or {}).get("label"),
            "experience_level": (item.get("experienceLevel") or {}).get("label"),
            "remote": location.get("remote"),
            "hybrid": location.get("hybrid"),
            "ref_number": item.get("refNumber"),
        },
    )


def _join_location(location: dict) -> str | None:
    parts = [location.get("city"), (location.get("country") or "").upper() or None]
    joined = ", ".join(part for part in parts if part)
    return joined or None
