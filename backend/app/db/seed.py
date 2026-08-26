from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AtsType, VisaStatus
from app.db.seed_data import CANDIDATE, COMPANIES, JOB_SOURCES, RESUMES
from app.models import CandidateProfile, CandidateResume, CompanyAlias, CompanyEvidence, JobSource, TargetCompany

logger = structlog.get_logger(__name__)

DATA_PATH = Path(__file__).resolve().parent / "data" / "target_companies.json"
VERIFIED_ATS = {AtsType.GREENHOUSE.value, AtsType.LEVER.value, AtsType.PERSONIO_XML.value}
SEED_EVIDENCE_SOURCES = {
    "europe_mena_target_companies_2026",
    "verified_example_2026",
    "IND recognised sponsor list (as recorded 2026 dataset)",
}
COMPANY_COLUMNS = (
    "name",
    "country",
    "city",
    "ats_type",
    "board_token",
    "careers_url",
    "linkedin_url",
    "extra",
    "priority",
    "enabled",
    "visa_status",
)
ALIASES_BY_SLUG = {row["slug"]: list(row.get("aliases") or []) for row in COMPANIES}


def load_target_companies() -> list[dict]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


async def seed_if_needed(session: AsyncSession) -> None:
    await seed_all(session, replace_evidence=False)


async def seed_all(session: AsyncSession, replace_evidence: bool = True) -> None:
    companies = load_target_companies()
    await _seed_sources(session)
    await _seed_candidate(session)
    await _upsert_companies(session, companies, replace_evidence=replace_evidence)
    await session.commit()
    logger.info("seed_completed", companies=len(companies), replace_evidence=replace_evidence)


async def _seed_sources(session: AsyncSession) -> None:
    for source in JOB_SOURCES:
        if await session.scalar(select(JobSource.id).where(JobSource.name == source["name"])):
            continue
        session.add(JobSource(**source))


async def _seed_candidate(session: AsyncSession) -> None:
    profile = await session.scalar(select(CandidateProfile).limit(1))
    if profile is None:
        profile = CandidateProfile(**CANDIDATE)
        session.add(profile)
        await session.flush()
        for resume in RESUMES:
            session.add(CandidateResume(profile_id=profile.id, **resume))
        return
    profile.target_countries = list(CANDIDATE["target_countries"])
    profile.preferred_countries = list(CANDIDATE["preferred_countries"])
    profile.target_roles = list(CANDIDATE["target_roles"])


async def _upsert_companies(
    session: AsyncSession,
    rows: list[dict],
    replace_evidence: bool,
) -> None:
    json_slugs = {row["slug"] for row in rows}
    existing = {company.slug: company for company in (await session.scalars(select(TargetCompany))).all()}

    for row in rows:
        payload = dict(row)
        evidence = payload.pop("evidence", [])
        aliases = list(payload.pop("aliases", [])) + ALIASES_BY_SLUG.get(payload["slug"], [])
        if payload.get("visa_status") == VisaStatus.CONFIRMED.value:
            payload["visa_status"] = VisaStatus.LIKELY.value
        payload.setdefault("enabled", True)

        company = existing.get(payload["slug"])
        if company is not None and company.ats_type in VERIFIED_ATS and payload.get("ats_type") not in VERIFIED_ATS:
            payload["ats_type"] = company.ats_type
            payload["board_token"] = company.board_token

        if company is None:
            company = TargetCompany(**{key: payload.get(key) for key in ("slug", *COMPANY_COLUMNS)})
            session.add(company)
            await session.flush()
            existing[company.slug] = company
        else:
            for key in COMPANY_COLUMNS:
                setattr(company, key, payload.get(key))

        await _sync_seed_evidence(session, company, evidence, replace=replace_evidence)
        for alias in aliases:
            exists = await session.scalar(
                select(CompanyAlias.id).where(
                    CompanyAlias.company_id == company.id,
                    CompanyAlias.alias == alias,
                )
            )
            if exists is None:
                session.add(CompanyAlias(company_id=company.id, alias=alias))

    for slug, company in existing.items():
        if slug not in json_slugs:
            company.enabled = False


async def _sync_seed_evidence(
    session: AsyncSession,
    company: TargetCompany,
    evidence: list[dict],
    replace: bool,
) -> None:
    current = (
        await session.scalars(select(CompanyEvidence).where(CompanyEvidence.company_id == company.id))
    ).all()
    if replace:
        for row in current:
            if row.source_name in SEED_EVIDENCE_SOURCES:
                await session.delete(row)
        current = [row for row in current if row.source_name not in SEED_EVIDENCE_SOURCES]
    existing_keys = {(row.source_name, row.claim, row.source_url) for row in current}
    for item in evidence:
        key = (item.get("source_name"), item.get("claim") or "international_hiring", item.get("source_url"))
        if not replace and key in existing_keys:
            continue
        extra = dict(item.get("extra") or {})
        if item.get("text"):
            extra["text"] = item["text"]
        session.add(
            CompanyEvidence(
                company_id=company.id,
                type=item.get("type") or "third_party",
                source_url=item.get("source_url"),
                source_name=item.get("source_name"),
                claim=item.get("claim") or "international_hiring",
                confidence=float(item.get("confidence") or 0.5),
                extra=extra,
            )
        )


async def _cli() -> None:
    from app.core.config import Settings
    from app.core.logging import configure_logging
    from app.db.session import dispose_engine, init_engine

    settings = Settings()
    configure_logging(settings)
    factory = init_engine(settings)
    try:
        async with factory() as session:
            await seed_all(session)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_cli())
