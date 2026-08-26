from app.analyzers.filters import (
    apply_hard_filters,
    infer_seniority,
    looks_like_engineering_role,
    looks_like_target_role,
    target_role_rank,
)
from app.analyzers.normalize import detect_employment_type, fingerprint, hash_text
from app.jobs.pipeline import select_round_robin
from app.analyzers.visa import classify_text, decayed_confidence
from app.core.enums import VisaStatus
from app.core.config import Settings
from app.db.session import init_engine
from app.jobs.run_once import build_parser
from app.scoring.engine import score_job


def test_senior_title_not_intern_from_description_boilerplate() -> None:
    title = "Senior Software Engineer (Java)"
    body = "We also run an internship and hire junior engineers."
    assert detect_employment_type("Full-time", title, body) != "internship"
    assert infer_seniority(title, body) == "senior"


def test_intern_title_still_detected() -> None:
    assert detect_employment_type(None, "Software Engineering Intern", "") == "internship"
    assert infer_seniority("Software Engineering Intern", "") == "intern"


def test_round_robin_mixes_companies() -> None:
    buckets = [
        [("careem", "a"), ("careem", "b")],
        [("adyen", "c"), ("adyen", "d"), ("adyen", "e")],
        [("n26", "f")],
    ]
    selected = select_round_robin(buckets, 4)
    companies = [item[0] for item in selected]
    assert companies == ["careem", "adyen", "n26", "careem"]
    assert looks_like_engineering_role("Senior Software Engineer")
    assert not looks_like_engineering_role("Warehouse Associate")
    assert not looks_like_engineering_role("Junior Developer")


def test_target_roles_keep_frontend_fullstack_software_engineer() -> None:
    assert looks_like_target_role("Senior Software Engineer")
    assert looks_like_target_role("Senior Frontend Engineer")
    assert looks_like_target_role("Senior Full-Stack Engineer")
    assert looks_like_target_role("Staff Software Engineer")
    assert not looks_like_target_role("Senior Backend Engineer")
    assert not looks_like_target_role("Senior Software Engineer (Java)")
    assert not looks_like_target_role("AI Infrastructure Engineer")
    assert not looks_like_target_role("Application Security Engineer")
    assert not looks_like_target_role("Lead PreSales Solutions Engineer")
    assert target_role_rank("Senior Frontend Engineer") < target_role_rank("Senior Software Engineer")


def test_hard_filter_rejects_backend_and_java_stack() -> None:
    backend = apply_hard_filters(
        title="Senior Backend Engineer",
        description="Build APIs in Node.js",
        country="DE",
        target_countries=["DE"],
        visa_status=VisaStatus.UNKNOWN.value,
        employment_type="full_time",
        remote_type="hybrid",
        role_category="backend",
    )
    assert backend.rejected is True
    assert backend.reason == "too_backend"
    java = apply_hard_filters(
        title="Senior Software Engineer",
        description="You will write Java and Kotlin microservices. Spring Boot required.",
        country="NL",
        target_countries=["NL"],
        visa_status=VisaStatus.UNKNOWN.value,
        employment_type="full_time",
        remote_type="onsite",
    )
    assert java.rejected is True
    assert java.reason == "wrong_stack"
    react = apply_hard_filters(
        title="Senior Software Engineer",
        description="React, TypeScript, and Node.js. Some Java services exist.",
        country="NL",
        target_countries=["NL"],
        visa_status=VisaStatus.UNKNOWN.value,
        employment_type="full_time",
        remote_type="hybrid",
    )
    assert react.rejected is False


def test_hard_filter_rejects_no_sponsorship() -> None:
    result = apply_hard_filters(
        title="Senior Software Engineer",
        description="Must have right to work. No visa sponsorship.",
        country="DE",
        target_countries=["DE"],
        visa_status=VisaStatus.NO.value,
        employment_type="full_time",
        remote_type="hybrid",
    )
    assert result.rejected is True
    assert result.reason == "explicit_no_sponsorship"


def test_hard_filter_rejects_wrong_country() -> None:
    result = apply_hard_filters(
        title="Senior Software Engineer",
        description="Build APIs in Node.js",
        country="US",
        target_countries=["DE", "NL"],
        visa_status=VisaStatus.UNKNOWN.value,
        employment_type="full_time",
        remote_type="onsite",
    )
    assert result.rejected is True
    assert result.reason == "impossible_location"


def test_visa_confirmed_from_posting() -> None:
    signals = classify_text("Visa sponsorship available. Relocation assistance provided.")
    assert signals.visa_status == VisaStatus.CONFIRMED
    assert signals.relocation_status.value == "supported"


def test_visa_no_from_right_to_work() -> None:
    signals = classify_text("Applicants must already have the right to work in Germany.")
    assert signals.visa_status == VisaStatus.NO


def test_visa_unknown_when_silent() -> None:
    signals = classify_text("We are hiring a Senior Software Engineer in Berlin.")
    assert signals.visa_status == VisaStatus.UNKNOWN


def test_old_evidence_loses_confidence() -> None:
    from datetime import UTC, datetime, timedelta

    observed = datetime.now(UTC) - timedelta(days=180)
    assert abs(decayed_confidence(1.0, observed, 180) - 0.5) < 0.02


def test_dedup_fingerprint_stable() -> None:
    first = fingerprint("N26", "Senior Engineer", "Berlin", "Build Node.js services")
    second = fingerprint("N26", "Senior Engineer", "Berlin", "Build   Node.js services")
    assert first == second
    assert hash_text("A") != hash_text("B")


def test_scoring_apply_band() -> None:
    result = score_job(
        technical_fit=0.95,
        years_experience=7,
        years_required=5,
        visa_status=VisaStatus.CONFIRMED.value,
        relocation_status="supported",
        country="DE",
        seniority="senior",
        company_priority=96,
        international_hiring=True,
        matched_skills=["TypeScript", "Node.js"],
        missing_skills=[],
    )
    assert result.overall_score >= 80
    assert result.recommendation == "apply"
    assert result.positive_reasons


def test_scoring_skip_band() -> None:
    result = score_job(
        technical_fit=0.1,
        years_experience=7,
        years_required=12,
        visa_status=VisaStatus.NO.value,
        relocation_status="no",
        country="US",
        seniority="junior",
        company_priority=10,
        international_hiring=False,
        matched_skills=[],
        missing_skills=["Java", "Kotlin"],
    )
    assert result.overall_score < 60
    assert result.recommendation == "skip"


def test_run_once_parser_limit() -> None:
    args = build_parser().parse_args(["--limit", "10"])
    assert args.limit == 10


def test_init_engine_returns_session_factory() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://jobagent:jobagent@localhost:5434/jobagent"
    )
    factory = init_engine(settings)
    assert factory is not None
    assert callable(factory)


def test_parse_nordic_and_canada_locations() -> None:
    from app.analyzers.location import parse_location

    assert parse_location("Stockholm, Sweden").country == "SE"
    assert parse_location("Copenhagen").country == "DK"
    assert parse_location("Helsinki, Finland").country == "FI"
    assert parse_location("Oslo, Norway").country == "NO"
    assert parse_location("Toronto, Canada").country == "CA"


def test_target_company_seed_json() -> None:
    from app.db.seed import load_target_companies

    rows = load_target_companies()
    assert len(rows) == 93
    assert {row["country"] for row in rows} >= {"AE", "DE", "NL", "IE", "SA", "SE", "DK", "FI", "NO"}
    assert all(row["visa_status"] != "confirmed" for row in rows)
    by_slug = {row["slug"]: row for row in rows}
    assert by_slug["careem"]["ats_type"] == "greenhouse"
    assert by_slug["adyen"]["board_token"] == "adyen"
    assert by_slug["hubspot"]["ats_type"] == "greenhouse"
    assert by_slug["hubspot"]["board_token"] == "hubspotjobs"
    assert by_slug["n26"]["ats_type"] == "greenhouse"
    assert by_slug["personio"]["ats_type"] == "personio_xml"
    assert any(
        item["claim"] == "recognized_sponsor" for item in by_slug["adyen"]["evidence"]
    )


def test_skip_callback_reads_message_coords() -> None:
    from app.notifications.bot import suggested_message_coords

    chat_id, message_id = suggested_message_coords(
        {"message": {"message_id": 42, "chat": {"id": 99}}}
    )
    assert chat_id == 99
    assert message_id == 42
