from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzers.ai import OpenAIProvider
from app.analyzers.filters import apply_hard_filters, looks_like_target_role, target_role_rank
from app.analyzers.job_analysis import analyze_deterministically, merge_llm
from app.analyzers.normalize import normalized_job_fields
from app.analyzers.skills import match_skills
from app.analyzers.visa import combine_visa_status, decayed_confidence
from app.collectors.registry import collector_for
from app.core.config import Settings
from app.core.enums import EvidenceClaim, EvidenceType, NotificationStatus
from app.core.logging import configure_logging
from app.db.seed import seed_if_needed
from app.db.session import dispose_engine, init_engine
from app.models import (
    CandidateProfile,
    CompanyEvidence,
    Job,
    JobAnalysis,
    JobScore,
    Notification,
    SearchRun,
    TargetCompany,
)
from app.notifications.telegram import send_job_notification
from app.scoring.engine import score_job

logger = structlog.get_logger(__name__)

MAX_NOTIFY_PER_COMPANY = 2


@dataclass
class PipelineSummary:
    discovered: int = 0
    new: int = 0
    duplicates: int = 0
    rejected: int = 0
    ai_analyzed: int = 0
    high_score: int = 0
    telegram_notifications: int = 0
    errors: int = 0
    highest_score: float = 0.0
    notified_by_company: dict[str, int] = field(default_factory=dict)
    error_details: list[str] = field(default_factory=list)

    def print(self) -> None:
        print(
            f"Discovered: {self.discovered}\n"
            f"New: {self.new}\n"
            f"Duplicates: {self.duplicates}\n"
            f"Rejected: {self.rejected}\n"
            f"AI analyzed: {self.ai_analyzed}\n"
            f"High score: {self.high_score}\n"
            f"Highest score: {self.highest_score}\n"
            f"Telegram notifications: {self.telegram_notifications}\n"
            f"Errors: {self.errors}"
        )


async def run_pipeline(limit: int = 10) -> PipelineSummary:
    settings = Settings()
    configure_logging(settings)
    if not settings.openai_api_key:
        logger.warning("openai_disabled", reason="OPENAI_API_KEY is empty; using deterministic analysis only")
    chat_id = settings.telegram_chat_id.strip()
    if chat_id and not chat_id.lstrip("-").isdigit():
        logger.warning(
            "telegram_chat_id_not_numeric",
            hint="TELEGRAM_CHAT_ID must be your numeric user id from @userinfobot, not the bot username",
        )
    session_factory = init_engine(settings)
    summary = PipelineSummary()
    try:
        async with session_factory() as session:
            await seed_if_needed(session)
            await _execute(session, settings, summary, limit)
    finally:
        await dispose_engine()
    summary.print()
    return summary


async def _execute(
    session: AsyncSession,
    settings: Settings,
    summary: PipelineSummary,
    limit: int,
) -> None:
    profile = await session.scalar(select(CandidateProfile).limit(1))
    if profile is None:
        raise RuntimeError("Candidate profile is missing. Seed the database first.")

    companies = (
        await session.scalars(
            select(TargetCompany)
            .where(TargetCompany.enabled.is_(True))
            .order_by(TargetCompany.priority.desc())
        )
    ).all()

    run = SearchRun(source="run_once", started_at=datetime.now(UTC))
    session.add(run)
    await session.flush()

    headers = {"User-Agent": "job-agent/0.1 (personal job-search assistant)"}
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    ai = OpenAIProvider(settings)

    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        buckets: list[list[tuple[TargetCompany, object]]] = []
        for company in companies:
            collector = collector_for(company, client, settings)
            try:
                raw_jobs = await collector.collect(company)
            except Exception as exc:
                _record_error(summary, run, f"{company.slug} collect: {exc}")
                continue
            engineering = [
                (company, raw)
                for raw in raw_jobs
                if looks_like_target_role(raw.title)
            ]
            engineering.sort(key=lambda item: target_role_rank(item[1].title))
            if engineering:
                buckets.append(engineering)
            await _pause(settings)

        selected = select_round_robin(buckets, limit)
        summary.discovered = len(selected)

        for company, raw in selected:
            collector = collector_for(company, client, settings)
            try:
                if not raw.description:
                    raw = await collector.enrich(company, raw)
                    await _pause(settings)
                await _process_job(
                    session,
                    client,
                    settings,
                    ai,
                    profile,
                    company,
                    raw,
                    summary,
                    run,
                )
            except Exception as exc:
                _record_error(summary, run, f"{company.slug} {raw.title}: {exc}")

    run.finished_at = datetime.now(UTC)
    run.jobs_found = summary.discovered
    run.jobs_created = summary.new
    run.jobs_updated = 0
    run.jobs_skipped = summary.duplicates + summary.rejected
    run.summary = {
        "discovered": summary.discovered,
        "new": summary.new,
        "duplicates": summary.duplicates,
        "rejected": summary.rejected,
        "ai_analyzed": summary.ai_analyzed,
        "high_score": summary.high_score,
        "highest_score": summary.highest_score,
        "telegram_notifications": summary.telegram_notifications,
        "errors": summary.errors,
    }
    await session.commit()


async def _process_job(
    session: AsyncSession,
    client: httpx.AsyncClient,
    settings: Settings,
    ai: OpenAIProvider,
    profile: CandidateProfile,
    company: TargetCompany,
    raw,
    summary: PipelineSummary,
    run: SearchRun,
) -> None:
    existing = await session.scalar(
        select(Job).where(Job.source == raw.source, Job.external_id == raw.external_id)
    )
    fields = normalized_job_fields(company, raw)
    if existing is None:
        existing = await session.scalar(select(Job).where(Job.fingerprint == fields["fingerprint"]))
    if existing is not None:
        summary.duplicates += 1
        return

    job = Job(**fields)
    session.add(job)
    await session.flush()
    summary.new += 1

    analysis = analyze_deterministically(
        title=job.title,
        description=job.description,
        remote_type=job.remote_type,
        employment_type=job.employment_type,
        salary=job.salary,
        candidate_skills=list(profile.skills or []),
    )
    hard = apply_hard_filters(
        title=job.title,
        description=job.description,
        country=job.country,
        target_countries=list(profile.target_countries or []),
        visa_status=analysis.visa.visa_status.value,
        employment_type=job.employment_type,
        remote_type=job.remote_type,
        role_category=analysis.role_category,
    )
    if hard.rejected:
        summary.rejected += 1
        logger.info("job_rejected", job_id=job.id, reason=hard.reason, title=job.title)
        await _store_analysis(session, job, analysis, used_ai=False)
        return

    used_ai = False
    if ai.enabled:
        llm = await ai.analyze_job(title=job.title, company=company.name, description=job.description)
        if llm is not None:
            analysis = merge_llm(analysis, llm, f"{job.title}\n{job.description}")
            used_ai = True
            summary.ai_analyzed += 1
            match = match_skills(analysis.required_skills, list(profile.skills or []), job.title)
            analysis.skill_score = match.score
            analysis.matched_skills = match.matched
            analysis.resume_variant = match.resume_variant

    evidence_rows = (
        await session.scalars(select(CompanyEvidence).where(CompanyEvidence.company_id == company.id))
    ).all()
    evidence_tuples = [
        (
            row.type,
            row.claim,
            decayed_confidence(row.confidence, row.observed_at, settings.evidence_half_life_days),
        )
        for row in evidence_rows
    ]
    visa_status = combine_visa_status(analysis.visa, evidence_tuples).value
    await _store_posting_evidence(session, company, job, analysis)

    hard = apply_hard_filters(
        title=job.title,
        description=job.description,
        country=job.country,
        target_countries=list(profile.target_countries or []),
        visa_status=visa_status,
        employment_type=job.employment_type,
        remote_type=job.remote_type,
        role_category=analysis.role_category,
    )
    stored = await _store_analysis(session, job, analysis, used_ai=used_ai, visa_status=visa_status)
    if hard.rejected:
        summary.rejected += 1
        logger.info("job_rejected", job_id=job.id, reason=hard.reason, title=job.title)
        return

    international = any(
        claim == EvidenceClaim.INTERNATIONAL_HIRING
        or claim == EvidenceClaim.SPONSORSHIP_AVAILABLE
        for claim in analysis.visa.claims
    ) or visa_status in {"confirmed", "likely"}

    result = score_job(
        technical_fit=analysis.skill_score,
        years_experience=profile.years_experience,
        years_required=analysis.years_required,
        visa_status=visa_status,
        relocation_status=analysis.visa.relocation_status.value,
        country=job.country,
        seniority=analysis.seniority,
        company_priority=company.priority,
        international_hiring=international,
        matched_skills=analysis.matched_skills,
        missing_skills=[skill for skill in analysis.required_skills if skill not in analysis.matched_skills],
        apply_threshold=settings.score_apply_threshold,
        review_threshold=settings.score_review_threshold,
    )
    score = JobScore(
        job_id=job.id,
        overall_score=result.overall_score,
        breakdown=result.breakdown,
        positive_reasons=result.positive_reasons,
        negative_reasons=result.negative_reasons,
        risks=result.risks,
        recommendation=result.recommendation,
        weights=result.weights,
    )
    session.add(score)
    await session.flush()
    summary.highest_score = max(summary.highest_score, result.overall_score)

    if result.overall_score >= settings.score_notify_threshold:
        summary.high_score += 1
        if summary.notified_by_company.get(company.slug, 0) >= MAX_NOTIFY_PER_COMPANY:
            logger.info("telegram_capped", company=company.slug, job_id=job.id)
            return
        already = await session.scalar(
            select(Notification.id).where(
                Notification.job_id == job.id,
                Notification.status == NotificationStatus.SENT.value,
            )
        )
        if already is None:
            sent = await send_job_notification(
                session,
                client,
                settings,
                job=job,
                company=company,
                score=score,
                visa_status=visa_status,
                relocation_status=stored.relocation_status,
            )
            if sent:
                summary.telegram_notifications += 1
                summary.notified_by_company[company.slug] = (
                    summary.notified_by_company.get(company.slug, 0) + 1
                )


def select_round_robin(buckets: list[list], limit: int) -> list:
    selected: list = []
    index = 0
    while len(selected) < limit:
        progressed = False
        for bucket in buckets:
            if index < len(bucket):
                selected.append(bucket[index])
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        index += 1
    return selected


async def _store_analysis(
    session: AsyncSession,
    job: Job,
    analysis,
    *,
    used_ai: bool,
    visa_status: str | None = None,
) -> JobAnalysis:
    row = JobAnalysis(
        job_id=job.id,
        role_category=analysis.role_category,
        seniority=analysis.seniority,
        years_required=analysis.years_required,
        required_skills=analysis.required_skills,
        preferred_skills=analysis.preferred_skills,
        location=job.location,
        remote_type=analysis.remote_type,
        visa_status=visa_status or analysis.visa.visa_status.value,
        relocation_status=analysis.visa.relocation_status.value,
        salary=analysis.salary,
        employment_type=analysis.employment_type,
        positive_signals=analysis.positive_signals,
        red_flags=analysis.red_flags,
        description_hash=job.description_hash,
        model=analysis.model if used_ai else None,
        prompt_version=analysis.prompt_version,
        extra={"resume_variant": analysis.resume_variant},
    )
    session.add(row)
    await session.flush()
    return row


async def _store_posting_evidence(session: AsyncSession, company: TargetCompany, job: Job, analysis) -> None:
    for claim in analysis.visa.claims:
        exists = await session.scalar(
            select(CompanyEvidence.id).where(
                CompanyEvidence.company_id == company.id,
                CompanyEvidence.claim == claim.value,
                CompanyEvidence.source_url == job.url,
            )
        )
        if exists is not None:
            continue
        session.add(
            CompanyEvidence(
                company_id=company.id,
                type=EvidenceType.JOB_POSTING.value,
                source_url=job.url,
                source_name="job_posting",
                claim=claim.value,
                confidence=0.7,
                observed_at=datetime.now(UTC),
                extra={"job_id": job.id, "snippets": analysis.visa.snippets},
            )
        )


def _record_error(summary: PipelineSummary, run: SearchRun, message: str) -> None:
    summary.errors += 1
    summary.error_details.append(message)
    errors = list(run.errors or [])
    errors.append(message)
    run.errors = errors
    logger.warning("pipeline_error", error=message)


async def _pause(settings: Settings) -> None:
    import asyncio

    if settings.collector_pause_seconds > 0:
        await asyncio.sleep(settings.collector_pause_seconds)
