import httpx
import structlog

from app.collectors.base import CollectorTarget, MissingTokenError, RawJob
from app.collectors.greenhouse import html_to_text, parse_dt
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

logger = structlog.get_logger(__name__)


class AshbyCollector:
    """Ashby public job board API.

    `https://api.ashbyhq.com/posting-api/job-board/{token}` returns the full
    posting list including descriptions, so `enrich` is a no-op.
    """

    name = "ashby"
    ats_type = AtsType.ASHBY.value
    strategy = CollectionStrategy.API.value

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def feed_url(self, target: CollectorTarget) -> str:
        if target.feed_url:
            return target.feed_url
        if not target.board_token:
            raise MissingTokenError("ashby requires a job board name")
        return f"https://api.ashbyhq.com/posting-api/job-board/{target.board_token}"

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        response = await self.client.get(
            self.feed_url(target),
            params={"includeCompensation": "true"},
        )
        response.raise_for_status()
        payload = response.json()
        jobs: list[RawJob] = []
        for item in payload.get("jobs", []):
            if item.get("isListed") is False:
                continue
            html = item.get("descriptionHtml") or ""
            plain = item.get("descriptionPlain") or html_to_text(html)
            secondary = [
                entry.get("location")
                for entry in item.get("secondaryLocations") or []
                if entry.get("location")
            ]
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=str(item.get("id") or ""),
                    title=item.get("title") or "",
                    url=item.get("jobUrl") or item.get("applyUrl") or "",
                    location=item.get("location"),
                    description=plain,
                    description_html=html,
                    employment_type=item.get("employmentType"),
                    posted_at=parse_dt(item.get("publishedAt") or item.get("updatedAt")),
                    salary_text=_compensation_text(item),
                    extra={
                        "department": item.get("department"),
                        "team": item.get("team"),
                        "is_remote": item.get("isRemote"),
                        "secondary_locations": secondary,
                    },
                )
            )
        logger.info("ashby_collected", company=target.company_slug, count=len(jobs))
        return jobs

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        return raw


def _compensation_text(item: dict) -> str | None:
    compensation = item.get("compensation")
    if not isinstance(compensation, dict):
        return None
    summary = compensation.get("compensationTierSummary")
    return summary if isinstance(summary, str) and summary else None
