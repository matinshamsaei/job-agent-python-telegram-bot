import httpx
import pytest

from app.collectors.ashby import AshbyCollector
from app.collectors.base import CollectionOutcome, CollectorTarget, MissingTokenError
from app.collectors.detect import (
    ProbeBudget,
    board_matches_company,
    candidate_tokens,
    detect_company,
    extract_hints,
)
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.personio import PersonioXmlCollector
from app.collectors.registry import (
    ADAPTERS,
    build_collector,
    missing_adapter_reason,
    strategy_for,
    supported_ats_types,
)
from app.collectors.runner import classify_http_error, collect_source
from app.collectors.smartrecruiters import SmartRecruitersCollector
from app.collectors.teamtailor import TeamtailorCollector
from app.collectors.workable import WorkableCollector
from app.collectors.workday import WorkdayCollector
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStatus, CollectionStrategy


def settings() -> Settings:
    return Settings(http_timeout_seconds=5, collector_pause_seconds=0)


def target(ats_type: str, **kwargs) -> CollectorTarget:
    return CollectorTarget(
        company_slug=kwargs.pop("slug", "acme"),
        company_name=kwargs.pop("name", "Acme"),
        ats_type=ats_type,
        **kwargs,
    )


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- registry ---------------------------------------------------------------


def test_registry_covers_phase_one_and_two_adapters() -> None:
    assert supported_ats_types() >= {
        AtsType.GREENHOUSE.value,
        AtsType.LEVER.value,
        AtsType.PERSONIO_XML.value,
        AtsType.ASHBY.value,
        AtsType.SMARTRECRUITERS.value,
        AtsType.WORKABLE.value,
        AtsType.RECRUITEE.value,
        AtsType.TEAMTAILOR.value,
        AtsType.WORKDAY.value,
    }


def test_every_adapter_declares_its_ats_type() -> None:
    for ats_type, factory in ADAPTERS.items():
        assert factory.ats_type == ats_type
        assert factory.strategy in set(CollectionStrategy)


def test_career_page_has_no_adapter_but_has_a_reason() -> None:
    assert build_collector(AtsType.CAREER_PAGE.value, None, settings()) is None
    assert "browser" in missing_adapter_reason(AtsType.CAREER_PAGE.value)
    assert strategy_for(AtsType.CAREER_PAGE.value) == CollectionStrategy.BROWSER.value


async def test_unsupported_ats_reports_adapter_missing_not_a_silent_skip() -> None:
    outcome = await collect_source(
        target(AtsType.CAREER_PAGE.value), client_for(lambda request: None), settings()
    )
    assert outcome.status is CollectionStatus.ADAPTER_MISSING
    assert outcome.jobs == []
    assert outcome.detail
    assert not outcome.ok


# --- status classification --------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (401, CollectionStatus.AUTH_REQUIRED),
        (403, CollectionStatus.AUTH_REQUIRED),
        (429, CollectionStatus.BLOCKED),
        (404, CollectionStatus.FEED_UNAVAILABLE),
        (410, CollectionStatus.FEED_UNAVAILABLE),
        (503, CollectionStatus.FEED_UNAVAILABLE),
        (418, CollectionStatus.INVALID_SOURCE),
    ],
)
def test_http_errors_map_to_explaining_statuses(code: int, expected: CollectionStatus) -> None:
    request = httpx.Request("GET", "https://example.test/jobs")
    error = httpx.HTTPStatusError("", request=request, response=httpx.Response(code, request=request))
    status, detail = classify_http_error(error)
    assert status is expected
    assert detail


async def test_missing_token_is_reported_as_needs_token() -> None:
    outcome = await collect_source(
        target(AtsType.GREENHOUSE.value), client_for(lambda request: None), settings()
    )
    assert outcome.status is CollectionStatus.NEEDS_TOKEN


async def test_reachable_but_empty_feed_is_no_jobs_not_a_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": []})

    outcome = await collect_source(
        target(AtsType.GREENHOUSE.value, board_token="acme"), client_for(handler), settings()
    )
    assert outcome.status is CollectionStatus.NO_JOBS
    assert outcome.ok


async def test_malformed_payload_is_invalid_source() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    outcome = await collect_source(
        target(AtsType.GREENHOUSE.value, board_token="acme"), client_for(handler), settings()
    )
    assert outcome.status is CollectionStatus.INVALID_SOURCE


def test_collection_outcome_ok_only_for_reachable_feeds() -> None:
    assert CollectionOutcome(status=CollectionStatus.COLLECTED).ok
    assert CollectionOutcome(status=CollectionStatus.NO_JOBS).ok
    assert not CollectionOutcome(status=CollectionStatus.BLOCKED).ok


# --- adapters ---------------------------------------------------------------


async def test_greenhouse_parses_list_and_enriches_description() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jobs"):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 42,
                            "title": "Senior Software Engineer",
                            "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
                            "location": {"name": "Berlin, Germany"},
                            "updated_at": "2026-08-01T10:00:00Z",
                            "company_name": "Acme",
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"content": "<p>Build <b>React</b> apps</p>"})

    collector = GreenhouseCollector(client_for(handler), settings())
    source = target(AtsType.GREENHOUSE.value, board_token="acme")
    jobs = await collector.collect(source)
    assert [job.title for job in jobs] == ["Senior Software Engineer"]
    assert jobs[0].location == "Berlin, Germany"
    assert jobs[0].posted_at is not None

    enriched = await collector.enrich(source, jobs[0])
    assert enriched.description == "Build React apps"


async def test_ashby_skips_unlisted_jobs_and_keeps_compensation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "a1",
                        "title": "Frontend Engineer",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/a1",
                        "location": "Remote",
                        "descriptionPlain": "Ship UI",
                        "employmentType": "FullTime",
                        "isListed": True,
                        "compensation": {"compensationTierSummary": "EUR 80k - 100k"},
                        "secondaryLocations": [{"location": "Berlin"}],
                    },
                    {"id": "a2", "title": "Hidden", "isListed": False},
                ]
            },
        )

    jobs = await AshbyCollector(client_for(handler), settings()).collect(
        target(AtsType.ASHBY.value, board_token="acme")
    )
    assert len(jobs) == 1
    assert jobs[0].salary_text == "EUR 80k - 100k"
    assert jobs[0].extra["secondary_locations"] == ["Berlin"]


async def test_smartrecruiters_paginates_until_total_is_reached() -> None:
    pages = {
        0: {"totalFound": 3, "content": [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}]},
        2: {"totalFound": 3, "content": [{"id": "3", "name": "C"}]},
    }
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        calls.append(offset)
        return httpx.Response(200, json=pages[offset])

    collector = SmartRecruitersCollector(client_for(handler), settings())
    collector_module = __import__("app.collectors.smartrecruiters", fromlist=["PAGE_SIZE"])
    original = collector_module.PAGE_SIZE
    collector_module.PAGE_SIZE = 2
    try:
        jobs = await collector.collect(target(AtsType.SMARTRECRUITERS.value, board_token="Acme"))
    finally:
        collector_module.PAGE_SIZE = original

    assert [job.title for job in jobs] == ["A", "B", "C"]
    assert calls == [0, 2]


async def test_smartrecruiters_builds_location_when_full_location_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "totalFound": 1,
                "content": [
                    {"id": "1", "name": "Engineer", "location": {"city": "Amsterdam", "country": "nl"}}
                ],
            },
        )

    jobs = await SmartRecruitersCollector(client_for(handler), settings()).collect(
        target(AtsType.SMARTRECRUITERS.value, board_token="Acme")
    )
    assert jobs[0].location == "Amsterdam, NL"


async def test_workable_merges_description_requirements_and_benefits() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "name": "Acme",
                "jobs": [
                    {
                        "title": "Full Stack Engineer",
                        "shortcode": "XYZ1",
                        "url": "https://apply.workable.com/acme/j/XYZ1/",
                        "employment_type": "Full-time",
                        "city": "Helsinki",
                        "country": "Finland",
                        "description": "<p>Role</p>",
                        "requirements": "<p>TypeScript</p>",
                        "benefits": "<p>Relocation</p>",
                        "published_on": "2026-08-20",
                    }
                ],
            },
        )

    jobs = await WorkableCollector(client_for(handler), settings()).collect(
        target(AtsType.WORKABLE.value, board_token="acme")
    )
    assert jobs[0].external_id == "XYZ1"
    assert jobs[0].location == "Helsinki, Finland"
    assert "TypeScript" in jobs[0].description
    assert "Relocation" in jobs[0].description


async def test_personio_uses_feed_and_builds_job_url() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <workzag-jobs>
      <position>
        <id>987</id>
        <name>Senior Frontend Engineer</name>
        <office>Munich</office>
        <employmentType>permanent</employmentType>
        <jobDescriptions>
          <jobDescription><name>Tasks</name><value>&lt;p&gt;Build UI&lt;/p&gt;</value></jobDescription>
        </jobDescriptions>
      </position>
    </workzag-jobs>"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=xml)

    jobs = await PersonioXmlCollector(client_for(handler), settings()).collect(
        target(AtsType.PERSONIO_XML.value, board_token="acme")
    )
    assert jobs[0].url == "https://acme.jobs.personio.de/job/987"
    assert "Tasks: Build UI" in jobs[0].description


async def test_teamtailor_reads_rss_namespaced_location() -> None:
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:tt="https://teamtailor.com/locations" version="2.0">
      <channel>
        <item>
          <title>Software Engineer</title>
          <description>&lt;p&gt;Join us&lt;/p&gt;</description>
          <link>https://career.acme.com/jobs/1</link>
          <guid>abc</guid>
          <pubDate>Fri, 24 Jul 2026 13:57:16 +0200</pubDate>
          <remoteStatus>hybrid</remoteStatus>
          <tt:locations>Stockholm</tt:locations>
          <tt:department>Engineering</tt:department>
        </item>
      </channel>
    </rss>"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=rss)

    jobs = await TeamtailorCollector(client_for(handler), settings()).collect(
        target(AtsType.TEAMTAILOR.value, feed_url="https://career.acme.com/jobs.rss")
    )
    assert jobs[0].location == "Stockholm"
    assert jobs[0].extra["remote_status"] == "hybrid"
    assert jobs[0].posted_at is not None


# --- workday ----------------------------------------------------------------


def test_workday_derives_cxs_endpoint_from_public_careers_url() -> None:
    collector = WorkdayCollector(None, settings())
    endpoint = collector.feed_url(
        target(
            AtsType.WORKDAY.value,
            feed_url="https://acme.wd3.myworkdayjobs.com/en-US/Acme_Careers",
        )
    )
    assert endpoint == "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/Acme_Careers/jobs"


def test_workday_accepts_the_cxs_url_directly() -> None:
    collector = WorkdayCollector(None, settings())
    endpoint = collector.feed_url(
        target(
            AtsType.WORKDAY.value,
            feed_url="https://acme.wd3.myworkdayjobs.com/wday/cxs/acmetenant/Acme_Careers",
        )
    )
    assert endpoint == "https://acme.wd3.myworkdayjobs.com/wday/cxs/acmetenant/Acme_Careers/jobs"


def test_workday_without_a_feed_url_needs_configuration() -> None:
    collector = WorkdayCollector(None, settings())
    with pytest.raises(MissingTokenError):
        collector.feed_url(target(AtsType.WORKDAY.value))


async def test_workday_collects_postings_and_builds_public_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Software Engineer",
                        "externalPath": "/job/Eindhoven/Software-Engineer_JR1",
                        "locationsText": "Eindhoven",
                        "bulletFields": ["JR1"],
                    }
                ],
            },
        )

    jobs = await WorkdayCollector(client_for(handler), settings()).collect(
        target(AtsType.WORKDAY.value, feed_url="https://acme.wd3.myworkdayjobs.com/en-US/Acme_Careers")
    )
    assert jobs[0].external_id == "JR1"
    assert jobs[0].url == (
        "https://acme.wd3.myworkdayjobs.com/Acme_Careers/job/Eindhoven/Software-Engineer_JR1"
    )


# --- detection --------------------------------------------------------------


def test_extract_hints_finds_tokens_for_each_known_ats() -> None:
    html = """
    <a href="https://boards.greenhouse.io/acmegh">GH</a>
    <a href="https://jobs.lever.co/acmelever">Lever</a>
    <a href="https://jobs.ashbyhq.com/acme.ashby">Ashby</a>
    <a href="https://jobs.smartrecruiters.com/AcmeSR">SR</a>
    <a href="https://apply.workable.com/acmework/">Workable</a>
    <a href="https://acmep.jobs.personio.de/">Personio</a>
    <a href="https://acme.wd3.myworkdayjobs.com/en-US/Acme_Careers">Workday</a>
    """
    found = {(hint.ats_type, hint.board_token or hint.feed_url) for hint in extract_hints(html)}
    assert (AtsType.GREENHOUSE.value, "acmegh") in found
    assert (AtsType.LEVER.value, "acmelever") in found
    assert (AtsType.ASHBY.value, "acme.ashby") in found
    assert (AtsType.SMARTRECRUITERS.value, "AcmeSR") in found
    assert (AtsType.WORKABLE.value, "acmework") in found
    assert (AtsType.PERSONIO_XML.value, "acmep") in found
    assert (
        AtsType.WORKDAY.value,
        "https://acme.wd3.myworkdayjobs.com/en-US/Acme_Careers",
    ) in found


def test_extract_hints_ignores_generic_subdomains() -> None:
    hints = extract_hints('<a href="https://www.workable.com/">Workable marketing site</a>')
    assert [hint.board_token for hint in hints] == []


def test_extract_hints_returns_nothing_for_a_plain_careers_page() -> None:
    assert extract_hints("<html><body>We are hiring!</body></html>") == []


def test_candidate_tokens_are_derived_and_deduplicated() -> None:
    tokens = candidate_tokens("property-finder", "Property Finder")
    assert tokens[0] == "property-finder"
    assert "propertyfinder" in tokens
    assert len(tokens) == len(set(tokens))


def test_board_matching_rejects_a_name_collision() -> None:
    class FakeJob:
        def __init__(self, company_name: str) -> None:
            self.extra = {"company_name": company_name}

    assert board_matches_company([FakeJob("Acme Group")], "Acme")
    assert not board_matches_company([FakeJob("Totally Different Co")], "Acme")


def test_board_matching_passes_when_the_feed_says_nothing() -> None:
    class FakeJob:
        extra: dict = {}

    assert board_matches_company([FakeJob()], "Acme")


# --- detection must not mistake a block for an absence ----------------------


async def test_a_blocked_probe_is_reported_as_blocked_not_as_no_ats() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "myworkdayjobs" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(429, text="rate limited")

    result = await detect_company(
        "acme", "Acme", "https://acme.test/careers", client_for(handler), settings()
    )
    assert result.status is CollectionStatus.BLOCKED
    assert not result.verified
    assert "Retry later" in (result.detail or "")


async def test_probe_budget_stops_hammering_a_platform_that_blocked_us() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(429)

    budget = ProbeBudget()
    client = client_for(handler)
    await detect_company("acme", "Acme", None, client, settings(), budget=budget)
    first_round = len(calls)
    assert budget.strikes

    await detect_company("beta", "Beta", None, client, settings(), budget=budget)
    # Second company skips platforms already on cooldown after repeated strikes.
    assert len(calls) >= first_round


async def test_detection_finds_the_token_named_on_the_careers_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "acme.test":
            return httpx.Response(
                200, text='<a href="https://boards.greenhouse.io/acmeboard">Jobs</a>'
            )
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 1,
                        "title": "Engineer",
                        "absolute_url": "https://boards.greenhouse.io/acmeboard/jobs/1",
                        "location": {"name": "Berlin"},
                    }
                ]
            },
        )

    result = await detect_company(
        "acme", "Acme", "https://acme.test/careers", client_for(handler), settings()
    )
    assert result.ats_type == AtsType.GREENHOUSE.value
    assert result.board_token == "acmeboard"
    assert result.origin == "signature"
    assert result.verified


async def test_a_probed_token_belonging_to_another_company_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "boards-api.greenhouse.io" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 1,
                            "title": "Engineer",
                            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                            "location": {"name": "Berlin"},
                            "company_name": "Some Unrelated Corp",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    result = await detect_company("acme", "Acme", None, client_for(handler), settings())
    assert not result.verified
    assert result.board_token is None
