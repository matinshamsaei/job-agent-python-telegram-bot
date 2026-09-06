import httpx
import structlog

from app.collectors.base import CollectorTarget, MissingTokenError, RawJob
from app.collectors.greenhouse import html_to_text, parse_dt
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

logger = structlog.get_logger(__name__)


class RecruiteeCollector:
    """Recruitee public careers offers feed."""

    name = "recruitee"
    ats_type = AtsType.RECRUITEE.value
    strategy = CollectionStrategy.API.value

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def feed_url(self, target: CollectorTarget) -> str:
        if target.feed_url:
            return target.feed_url
        if not target.board_token:
            raise MissingTokenError("recruitee requires a company subdomain")
        return f"https://{target.board_token}.recruitee.com/api/offers/"

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        response = await self.client.get(self.feed_url(target))
        response.raise_for_status()
        payload = response.json()
        jobs: list[RawJob] = []
        for item in payload.get("offers") or []:
            html = item.get("description") or ""
            requirements = item.get("requirements") or ""
            combined = "\n".join(block for block in (html, requirements) if block)
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=str(item.get("id") or item.get("slug") or ""),
                    title=item.get("title") or "",
                    url=item.get("careers_url") or item.get("careers_apply_url") or "",
                    location=_location(item),
                    description=html_to_text(combined),
                    description_html=combined,
                    employment_type=item.get("employment_type_code") or item.get("employment_type"),
                    posted_at=parse_dt(item.get("published_at") or item.get("created_at")),
                    extra={"department": item.get("department"), "remote": item.get("remote")},
                )
            )
        logger.info("recruitee_collected", company=target.company_slug, count=len(jobs))
        return jobs

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        return raw


def _location(item: dict) -> str | None:
    parts = [item.get("city"), item.get("state_name") or item.get("state_code"), item.get("country")]
    joined = ", ".join(part for part in parts if part)
    return joined or item.get("location") or None
