"""Identify which ATS a company uses and verify the feed is really readable.

Two independent signals are combined:

1. **Signatures** — the careers page (after redirects) almost always links to
   the real board, so ATS URLs in the HTML give a token directly.
2. **Probing** — a candidate token is only accepted once the adapter's own feed
   URL returns a usable payload.

Nothing is guessed: a token that fails its probe is reported, never stored as
if it worked.
"""

import asyncio
import re
from dataclasses import dataclass, field

import httpx
import structlog

from app.collectors.base import CollectorTarget, MissingTokenError
from app.collectors.known_ats import KNOWN_ATS_BY_SLUG
from app.collectors.registry import build_collector, strategy_for
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStatus
from app.collectors.runner import collect_source

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AtsHint:
    """A candidate ATS configuration, not yet verified."""

    ats_type: str
    board_token: str | None = None
    feed_url: str | None = None
    origin: str = "signature"


COOLDOWN_COMPANIES = 10


@dataclass
class ProbeBudget:
    """Circuit breaker shared across a detection run.

    When an ATS rate-limits or blocks us, probing it again is both rude and
    misleading — a 403 looks identical to "this company has no board". The
    platform is put on cooldown for the next few companies rather than dropped
    for the whole run, so one early 429 does not poison every later company.
    """

    cooldown: dict[str, int] = field(default_factory=dict)
    blocked: set[str] = field(default_factory=set)
    strikes: dict[str, int] = field(default_factory=dict)

    def is_blocked(self, ats_type: str) -> bool:
        return self.cooldown.get(ats_type, 0) > 0

    def record_strike(self, ats_type: str) -> None:
        """One 429/403 on a platform; cooldown only after repeated strikes."""
        count = self.strikes.get(ats_type, 0) + 1
        self.strikes[ats_type] = count
        if count >= 2:
            if not self.is_blocked(ats_type):
                logger.warning("ats_probe_cooldown", ats_type=ats_type, companies=COOLDOWN_COMPANIES)
            self.cooldown[ats_type] = COOLDOWN_COMPANIES
            self.blocked.add(ats_type)

    def next_company(self) -> None:
        for ats_type, remaining in list(self.cooldown.items()):
            if remaining > 0:
                self.cooldown[ats_type] = remaining - 1


@dataclass
class DetectionResult:
    slug: str
    ats_type: str = AtsType.UNKNOWN.value
    board_token: str | None = None
    feed_url: str | None = None
    status: CollectionStatus = CollectionStatus.DISCOVERED
    detail: str | None = None
    job_count: int = 0
    origin: str = "none"
    hints: list[AtsHint] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return self.status in {CollectionStatus.COLLECTED, CollectionStatus.NO_JOBS}


# (compiled pattern, ats type, group holding the token). A group of 0 means the
# whole match is the feed identifier rather than a token.
SIGNATURES: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)", re.I), AtsType.GREENHOUSE.value, 1),
    (re.compile(r"job-boards\.greenhouse\.io/([\w-]+)", re.I), AtsType.GREENHOUSE.value, 1),
    (re.compile(r"boards\.greenhouse\.io/embed/job_board\?for=([\w-]+)", re.I), AtsType.GREENHOUSE.value, 1),
    (re.compile(r"boards\.greenhouse\.io/([\w-]+)", re.I), AtsType.GREENHOUSE.value, 1),
    (re.compile(r"api\.lever\.co/v0/postings/([\w-]+)", re.I), AtsType.LEVER.value, 1),
    (re.compile(r"jobs\.(?:eu\.)?lever\.co/([\w-]+)", re.I), AtsType.LEVER.value, 1),
    (re.compile(r"([\w-]+)\.jobs\.personio\.(?:de|com)", re.I), AtsType.PERSONIO_XML.value, 1),
    (re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([\w.-]+)", re.I), AtsType.ASHBY.value, 1),
    (re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)", re.I), AtsType.ASHBY.value, 1),
    (re.compile(r"api\.smartrecruiters\.com/v1/companies/([\w-]+)", re.I), AtsType.SMARTRECRUITERS.value, 1),
    (re.compile(r"jobs\.smartrecruiters\.com/([\w-]+)", re.I), AtsType.SMARTRECRUITERS.value, 1),
    (re.compile(r"careers\.smartrecruiters\.com/([\w-]+)", re.I), AtsType.SMARTRECRUITERS.value, 1),
    (re.compile(r"apply\.workable\.com/([\w-]+)", re.I), AtsType.WORKABLE.value, 1),
    (re.compile(r"([\w-]+)\.workable\.com", re.I), AtsType.WORKABLE.value, 1),
    (re.compile(r"([\w-]+)\.recruitee\.com", re.I), AtsType.RECRUITEE.value, 1),
    (re.compile(r"([\w-]+)\.teamtailor\.com", re.I), AtsType.TEAMTAILOR.value, 1),
    (
        re.compile(r"https://[\w-]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[\w-]+", re.I),
        AtsType.WORKDAY.value,
        0,
    ),
    (re.compile(r"jobs\.jobvite\.com/([\w-]+)", re.I), AtsType.JOBVITE.value, 1),
    (re.compile(r"([\w-]+)\.icims\.com", re.I), AtsType.ICIMS.value, 1),
    (re.compile(r"comeet\.com/jobs/([\w-]+)", re.I), AtsType.COMEET.value, 1),
    (re.compile(r"([\w-]+)\.bamboohr\.com", re.I), AtsType.BAMBOOHR.value, 1),
    (re.compile(r"([\w-]+)\.taleo\.net", re.I), AtsType.TALEO.value, 1),
    (re.compile(r"([\w-]+)\.successfactors\.(?:com|eu)", re.I), AtsType.SUCCESSFACTORS.value, 1),
]

# Subdomains that show up in ATS URLs but are never a real board token.
TOKEN_BLOCKLIST = frozenset({"www", "jobs", "careers", "career", "apply", "boards", "job", "api", "embed"})

# ATS types worth probing with a guessed token, most common first. Workday and
# Teamtailor are excluded because their feeds need a site id or custom domain
# that cannot be guessed from a company name. Personio is excluded from probes
# because wrong-subdomain probes trip its rate limiter and poison the run;
# Personio companies are found via careers-page signatures instead.
PROBEABLE = (
    AtsType.GREENHOUSE.value,
    AtsType.LEVER.value,
    AtsType.ASHBY.value,
    AtsType.SMARTRECRUITERS.value,
    AtsType.WORKABLE.value,
    AtsType.RECRUITEE.value,
)

# Platforms that must stay reachable for a "no board" conclusion to be honest.
# Cooldown on a secondary platform must not mark every later company as blocked.
PRIMARY_PROBEABLE = frozenset(
    {
        AtsType.GREENHOUSE.value,
        AtsType.LEVER.value,
        AtsType.ASHBY.value,
        AtsType.SMARTRECRUITERS.value,
    }
)


def extract_hints(text: str) -> list[AtsHint]:
    """Pull candidate ATS configurations out of careers-page HTML."""
    hints: list[AtsHint] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for pattern, ats_type, group in SIGNATURES:
        for match in pattern.finditer(text):
            if group == 0:
                hint = AtsHint(ats_type=ats_type, feed_url=match.group(0))
            else:
                token = match.group(group)
                if not token or token.lower() in TOKEN_BLOCKLIST:
                    continue
                hint = AtsHint(ats_type=ats_type, board_token=token)
            key = (hint.ats_type, hint.board_token, hint.feed_url)
            if key in seen:
                continue
            seen.add(key)
            hints.append(hint)
    return hints


def _dedupe(tokens: list[str]) -> list[str]:
    ordered: list[str] = []
    for token in tokens:
        if token and token not in ordered:
            ordered.append(token)
    return ordered


def candidate_tokens(slug: str, name: str) -> list[str]:
    """Plausible board tokens derived from the company slug and name."""
    plain = re.sub(r"[^a-z0-9]", "", name.lower())
    return _dedupe([slug, slug.replace("-", ""), plain])


def probe_tokens(ats_type: str, slug: str, name: str) -> list[str]:
    """Tokens worth trying for one ATS.

    Greenhouse boards are the only ones where the `<name>jobs` style suffix is
    common enough to be worth the extra request.
    """
    tokens = candidate_tokens(slug, name)
    if ats_type == AtsType.GREENHOUSE.value:
        plain = re.sub(r"[^a-z0-9]", "", name.lower())
        tokens = tokens + [f"{plain}jobs", f"{plain}careers"]
    return _dedupe(tokens)


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def board_matches_company(outcome_jobs: list, name: str) -> bool:
    """Reject a guessed token whose board clearly belongs to another company.

    Some feeds echo the owning company name. When they do and it disagrees with
    ours, the token was a name collision rather than a find.
    """
    expected = normalize_name(name)
    reported = {
        normalize_name(job.extra.get("company_name") or "")
        for job in outcome_jobs
        if job.extra.get("company_name")
    }
    if not reported or not expected:
        return True
    return any(
        expected in candidate or candidate in expected
        for candidate in reported
        if candidate
    )


async def verify_hint(
    hint: AtsHint,
    slug: str,
    name: str,
    client: httpx.AsyncClient,
    settings: Settings,
) -> tuple[CollectionStatus, str | None, int]:
    """Run the real adapter against a hint and report what happened."""
    target = CollectorTarget(
        company_slug=slug,
        company_name=name,
        ats_type=hint.ats_type,
        board_token=hint.board_token,
        feed_url=hint.feed_url,
    )
    if build_collector(hint.ats_type, client, settings) is None:
        return CollectionStatus.ADAPTER_MISSING, "no adapter implemented", 0
    outcome = await collect_source(target, client, settings)
    if (
        hint.origin == "probe"
        and outcome.status is CollectionStatus.COLLECTED
        and not board_matches_company(outcome.jobs, name)
    ):
        return (
            CollectionStatus.INVALID_SOURCE,
            f"board '{hint.board_token}' reports a different company name",
            0,
        )
    return outcome.status, outcome.detail, len(outcome.jobs)


async def fetch_careers_html(url: str, client: httpx.AsyncClient) -> str:
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        logger.info("careers_fetch_failed", url=url, error=f"{type(exc).__name__}: {exc}")
        return ""
    if response.status_code >= 400:
        return ""
    return response.text


BLOCKING_STATUSES = frozenset({CollectionStatus.BLOCKED, CollectionStatus.AUTH_REQUIRED})


async def detect_company(
    slug: str,
    name: str,
    careers_url: str | None,
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    probe_guesses: bool = True,
    budget: ProbeBudget | None = None,
) -> DetectionResult:
    """Detect and verify a company's ATS, preferring evidence over guesses."""
    result = DetectionResult(slug=slug)
    tracker = budget if budget is not None else ProbeBudget()

    catalog = KNOWN_ATS_BY_SLUG.get(slug)
    if catalog:
        hint = AtsHint(
            ats_type=str(catalog["ats_type"]),
            board_token=catalog.get("board_token"),
            feed_url=catalog.get("feed_url"),
            origin="catalog",
        )
        status, detail, count = await verify_hint(hint, slug, name, client, settings)
        if status in {CollectionStatus.COLLECTED, CollectionStatus.NO_JOBS}:
            return _accept(result, hint, status, detail, count)
        if build_collector(hint.ats_type, client, settings) is None:
            result.ats_type = hint.ats_type
            result.board_token = hint.board_token
            result.feed_url = hint.feed_url
            result.status = CollectionStatus.ATS_DETECTED
            result.detail = f"catalog lists {hint.ats_type} but no adapter is implemented"
            result.origin = "catalog"
            return result

    hints: list[AtsHint] = []
    if careers_url:
        hints = extract_hints(await fetch_careers_html(careers_url, client))
        result.hints = list(hints)

    for hint in hints:
        status, detail, count = await verify_hint(hint, slug, name, client, settings)
        if status in {CollectionStatus.COLLECTED, CollectionStatus.NO_JOBS}:
            return _accept(result, hint, status, detail, count)
        await _pause(settings)

    # The page named an ATS we cannot read. That is still a real finding.
    if hints:
        best = hints[0]
        result.ats_type = best.ats_type
        result.board_token = best.board_token
        result.feed_url = best.feed_url
        result.status = CollectionStatus.ATS_DETECTED
        result.detail = f"detected {best.ats_type} on careers page but feed was not readable"
        result.origin = "signature"

    if not probe_guesses:
        return result

    # Probe one ATS at a time and stop at the first hit. Parallel probes caused
    # rate limits that looked like "no board exists".
    primary_blocked_now: set[str] = set()
    for ats_type in PROBEABLE:
        if tracker.is_blocked(ats_type):
            if ats_type in PRIMARY_PROBEABLE:
                primary_blocked_now.add(ats_type)
            continue
        for token in probe_tokens(ats_type, slug, name):
            hint = AtsHint(ats_type=ats_type, board_token=token, origin="probe")
            status, _detail, count = await verify_hint(hint, slug, name, client, settings)
            if status is CollectionStatus.COLLECTED:
                return _accept(result, hint, status, None, count)
            if status in BLOCKING_STATUSES:
                tracker.record_strike(ats_type)
                if ats_type in PRIMARY_PROBEABLE:
                    primary_blocked_now.add(ats_type)
                break
            await _pause(settings, settings.detect_pause_seconds)

    # When every primary platform refused this company, do not call it "no ATS".
    if primary_blocked_now == PRIMARY_PROBEABLE and result.status is CollectionStatus.DISCOVERED:
        result.status = CollectionStatus.BLOCKED
        result.detail = (
            "all primary ATS platforms rate limited or blocked us for this company. "
            "Retry later before concluding there is no board."
        )
        return result

    # Mid-run cooldown on a platform means later companies skip it honestly.
    unreachable = sorted(ats for ats in PRIMARY_PROBEABLE if tracker.is_blocked(ats))
    if unreachable and result.status is CollectionStatus.DISCOVERED:
        result.status = CollectionStatus.BLOCKED
        result.detail = (
            f"could not finish probing: {', '.join(unreachable)} rate limited or blocked us. "
            "Retry later before concluding there is no board."
        )
    return result


async def _pause(settings: Settings, seconds: float | None = None) -> None:
    delay = settings.detect_pause_seconds if seconds is None else seconds
    if delay > 0:
        await asyncio.sleep(delay)


def _accept(
    result: DetectionResult,
    hint: AtsHint,
    status: CollectionStatus,
    detail: str | None,
    count: int,
) -> DetectionResult:
    result.ats_type = hint.ats_type
    result.board_token = hint.board_token
    result.feed_url = hint.feed_url
    result.status = status
    result.detail = detail
    result.job_count = count
    result.origin = hint.origin
    logger.info(
        "ats_verified",
        company=result.slug,
        ats_type=hint.ats_type,
        board_token=hint.board_token,
        feed_url=hint.feed_url,
        origin=hint.origin,
        jobs=count,
    )
    return result


def strategy_for_result(result: DetectionResult) -> str:
    return strategy_for(result.ats_type)


__all__ = [
    "AtsHint",
    "DetectionResult",
    "MissingTokenError",
    "candidate_tokens",
    "detect_company",
    "extract_hints",
    "probe_tokens",
    "strategy_for_result",
    "verify_hint",
]
