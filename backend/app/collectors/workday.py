import re
from urllib.parse import urlparse

import httpx
import structlog

from app.collectors.base import CollectorTarget, MissingTokenError, RawJob
from app.collectors.greenhouse import html_to_text, parse_dt
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStrategy

logger = structlog.get_logger(__name__)

PAGE_SIZE = 20
MAX_PAGES = 10

# Matches both the candidate-facing URL and the internal cxs endpoint, e.g.
# https://asml.wd3.myworkdayjobs.com/en-US/ASML_Careers
CXS_PATTERN = re.compile(
    r"https://(?P<host>[\w.-]+\.myworkdayjobs\.com)/"
    r"(?:wday/cxs/(?P<tenant>[\w-]+)/)?"
    r"(?:[a-z]{2}-[A-Z]{2}/)?"
    r"(?P<site>[\w-]+)",
)


class WorkdayCollector:
    """Workday CXS job search API.

    Workday needs a tenant *and* a site id that cannot be derived from a
    company name, so this adapter is driven by `feed_url` — either the public
    careers URL or the cxs endpoint itself.
    """

    name = "workday"
    ats_type = AtsType.WORKDAY.value
    strategy = CollectionStrategy.API.value

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    def _endpoint(self, target: CollectorTarget) -> tuple[str, str]:
        """Return the (jobs endpoint, site base url) pair for this source."""
        source_url = target.feed_url or target.board_token
        if not source_url:
            raise MissingTokenError("workday requires a feed_url with tenant and site id")
        match = CXS_PATTERN.match(source_url)
        if match is None:
            raise MissingTokenError(f"workday feed_url is not a myworkdayjobs URL: {source_url}")
        host = match.group("host")
        site = match.group("site")
        tenant = match.group("tenant") or host.split(".")[0]
        base = f"https://{host}/wday/cxs/{tenant}/{site}"
        return f"{base}/jobs", base

    def feed_url(self, target: CollectorTarget) -> str:
        return self._endpoint(target)[0]

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        endpoint, base = self._endpoint(target)
        jobs: list[RawJob] = []
        offset = 0
        for _ in range(MAX_PAGES):
            response = await self.client.post(
                endpoint,
                json={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            postings = payload.get("jobPostings") or []
            for item in postings:
                path = item.get("externalPath") or ""
                bullets = item.get("bulletFields") or []
                jobs.append(
                    RawJob(
                        source=self.name,
                        external_id=str(bullets[0] if bullets else path),
                        title=item.get("title") or "",
                        url=_public_url(base, path),
                        location=item.get("locationsText"),
                        extra={"external_path": path, "posted_on": item.get("postedOn")},
                    )
                )
            offset += len(postings)
            if not postings or offset >= int(payload.get("total") or 0):
                break
        logger.info("workday_collected", company=target.company_slug, count=len(jobs))
        return jobs

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        path = raw.extra.get("external_path")
        if not path:
            return raw
        _, base = self._endpoint(target)
        response = await self.client.get(f"{base}{path}", headers={"Accept": "application/json"})
        response.raise_for_status()
        info = (response.json() or {}).get("jobPostingInfo") or {}
        html = info.get("jobDescription") or ""
        raw.description_html = html
        raw.description = html_to_text(html)
        raw.location = info.get("location") or raw.location
        raw.employment_type = info.get("timeType") or raw.employment_type
        raw.posted_at = parse_dt(info.get("startDate")) or raw.posted_at
        raw.url = info.get("externalUrl") or raw.url
        return raw


def _public_url(cxs_base: str, path: str) -> str:
    """Turn a cxs base plus external path into the candidate-facing job URL."""
    parsed = urlparse(cxs_base)
    site = parsed.path.rsplit("/", 1)[-1]
    return f"{parsed.scheme}://{parsed.netloc}/{site}{path}"
