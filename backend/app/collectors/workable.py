import httpx
import structlog

from app.collectors.base import CollectorTarget, MissingTokenError, RawJob
from app.collectors.greenhouse import html_to_text, parse_dt
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

logger = structlog.get_logger(__name__)


class WorkableCollector:
    """Workable public account feed.

    `https://www.workable.com/api/accounts/{token}?details=true` returns every
    published job with its HTML description in one response.
    """

    name = "workable"
    ats_type = AtsType.WORKABLE.value
    strategy = CollectionStrategy.API.value

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def feed_url(self, target: CollectorTarget) -> str:
        if target.feed_url:
            return target.feed_url
        if not target.board_token:
            raise MissingTokenError("workable requires an account subdomain")
        return f"https://www.workable.com/api/accounts/{target.board_token}"

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        response = await self.client.get(self.feed_url(target), params={"details": "true"})
        response.raise_for_status()
        payload = response.json()
        jobs: list[RawJob] = []
        for item in payload.get("jobs") or []:
            html = "\n".join(
                block
                for block in (item.get("description"), item.get("requirements"), item.get("benefits"))
                if block
            )
            shortcode = item.get("shortcode") or ""
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=str(shortcode or item.get("id") or item.get("title") or ""),
                    title=item.get("title") or "",
                    url=item.get("url") or item.get("application_url") or "",
                    location=_location(item),
                    description=html_to_text(html),
                    description_html=html,
                    employment_type=item.get("employment_type"),
                    posted_at=parse_dt(item.get("published_on") or item.get("created_at")),
                    extra={
                        "department": item.get("department"),
                        "telecommuting": item.get("telecommuting"),
                    },
                )
            )
        logger.info("workable_collected", company=target.company_slug, count=len(jobs))
        return jobs

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        return raw


def _location(item: dict) -> str | None:
    location = item.get("location")
    if isinstance(location, dict):
        parts = [location.get("city"), location.get("region"), location.get("country")]
    else:
        parts = [item.get("city"), item.get("state"), item.get("country")]
    joined = ", ".join(part for part in parts if part)
    return joined or None
