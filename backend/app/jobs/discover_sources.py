"""Find and verify the real ATS behind each target company's careers page.

This is the step that turns "no public feed" into an actual answer. For every
company it inspects the careers page for ATS links, verifies each candidate
against the live adapter, and only then writes the source configuration.

Nothing is written for a guessed token unless the live feed responds. ATS types
detected on the careers page (even without a working adapter) are stored with
status `ats_detected` so the coverage report stays honest.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.detect import DetectionResult, ProbeBudget, detect_company
from app.collectors.registry import strategy_for, supported_ats_types
from app.core.config import Settings
from app.core.enums import AtsType, CollectionStatus
from app.models import CompanyJobSource, TargetCompany

logger = structlog.get_logger(__name__)

USER_AGENT = "job-agent/0.1 (personal job-search assistant)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect and verify each company's ATS, then store the working sources."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only inspect the first N companies (0 means all)",
    )
    parser.add_argument(
        "--slug",
        action="append",
        default=[],
        help="Restrict to specific company slugs (repeatable)",
    )
    parser.add_argument(
        "--only-unsupported",
        action="store_true",
        help="Skip companies that already have a source with a working adapter",
    )
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="Only trust ATS links found on the careers page, never guess tokens",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report findings without writing to the database",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write the findings to this JSON path",
    )
    parser.add_argument(
        "--sync-seed",
        action="store_true",
        help="After discovery, write verified sources back into target_companies.json",
    )
    return parser


async def discover(
    session: AsyncSession,
    settings: Settings,
    *,
    limit: int = 0,
    slugs: list[str] | None = None,
    only_unsupported: bool = False,
    probe_guesses: bool = True,
    dry_run: bool = False,
) -> list[DetectionResult]:
    supported = supported_ats_types()
    query = select(TargetCompany).where(TargetCompany.enabled.is_(True))
    if slugs:
        query = query.where(TargetCompany.slug.in_(slugs))
    companies = (await session.scalars(query.order_by(TargetCompany.priority.desc()))).all()

    sources_by_company: dict[int, list[CompanyJobSource]] = {}
    for source in (await session.scalars(select(CompanyJobSource))).all():
        sources_by_company.setdefault(source.company_id, []).append(source)

    if only_unsupported:
        # Skip companies that already have a concrete ATS (even without an adapter).
        unresolved = {AtsType.CAREER_PAGE.value, AtsType.UNKNOWN.value}
        companies = [
            company
            for company in companies
            if not any(
                source.ats_type not in unresolved
                for source in sources_by_company.get(company.id, [])
            )
        ]
    if limit > 0:
        companies = companies[:limit]

    results: list[DetectionResult] = []
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(settings.detect_timeout_seconds),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=settings.detect_concurrency * 2),
    ) as client:
        budget = ProbeBudget()
        for index, company in enumerate(companies, start=1):
            budget.next_company()
            result = await detect_company(
                company.slug,
                company.name,
                company.careers_url,
                client,
                settings,
                probe_guesses=probe_guesses,
                budget=budget,
            )
            results.append(result)
            print(
                f"[{index}/{len(companies)}] {company.slug:26} "
                f"{result.ats_type:16} {result.status.value:16} "
                f"{result.board_token or result.feed_url or '-'}"
            )
            if not dry_run and _should_store(result):
                _store(company, result, sources_by_company.get(company.id, []), session)
                # Commit per company so an aborted run keeps verified finds.
                await session.commit()
            if settings.collector_pause_seconds > 0:
                await asyncio.sleep(settings.collector_pause_seconds)

    if budget.blocked:
        print(
            "\nThese platforms stopped answering mid-run and were skipped: "
            f"{', '.join(sorted(budget.blocked))}. "
            "Their companies are marked `blocked`, not `no ATS`. Retry later."
        )
    return results


def _should_store(result: DetectionResult) -> bool:
    """Persist verified feeds and ATS detections that explain a missing adapter."""
    return result.verified or result.status is CollectionStatus.ATS_DETECTED


def _store(
    company: TargetCompany,
    result: DetectionResult,
    sources: list[CompanyJobSource],
    session: AsyncSession,
) -> None:
    """Attach the detected configuration to the company's primary source."""
    now = datetime.now(UTC)
    source = next((row for row in sources if row.label == "primary"), None)
    if source is None:
        source = CompanyJobSource(company_id=company.id, label="primary")
        session.add(source)
        sources.append(source)

    source.ats_type = result.ats_type
    source.board_token = result.board_token
    source.feed_url = result.feed_url
    source.collection_strategy = strategy_for(result.ats_type)
    source.enabled = True
    if result.verified:
        source.status = CollectionStatus.FEED_AVAILABLE.value
        source.last_verified_at = now
        source.last_job_count = result.job_count
    else:
        source.status = result.status.value
    source.status_detail = result.detail
    source.extra = {
        **dict(source.extra or {}),
        "detected_via": result.origin,
        "verified_job_count": result.job_count,
        "verified_at": now.isoformat() if result.verified else None,
    }

    # Keep the flat columns in step so existing reports stay meaningful.
    company.ats_type = result.ats_type
    company.board_token = result.board_token


def summarize(results: list[DetectionResult]) -> dict:
    by_status: dict[str, int] = {}
    by_ats: dict[str, int] = {}
    for result in results:
        by_status[result.status.value] = by_status.get(result.status.value, 0) + 1
        if result.verified:
            by_ats[result.ats_type] = by_ats.get(result.ats_type, 0) + 1
    return {
        "inspected": len(results),
        "verified": sum(1 for result in results if result.verified),
        "by_status": by_status,
        "verified_by_ats": by_ats,
    }


def as_json(results: list[DetectionResult]) -> list[dict]:
    return [
        {
            "slug": result.slug,
            "ats_type": result.ats_type,
            "board_token": result.board_token,
            "feed_url": result.feed_url,
            "collection_strategy": strategy_for(result.ats_type),
            "status": result.status.value,
            "detail": result.detail,
            "job_count": result.job_count,
            "verified": result.verified,
            "detected_via": result.origin,
        }
        for result in results
    ]


async def _run(args: argparse.Namespace) -> None:
    from app.core.logging import configure_logging
    from app.db.session import dispose_engine, init_engine

    settings = Settings()
    configure_logging(settings)
    factory = init_engine(settings)
    try:
        async with factory() as session:
            results = await discover(
                session,
                settings,
                limit=args.limit,
                slugs=args.slug,
                only_unsupported=args.only_unsupported,
                probe_guesses=not args.no_probe,
                dry_run=args.dry_run,
            )
    finally:
        await dispose_engine()

    summary = summarize(results)
    print("\n" + json.dumps(summary, indent=2))
    if args.report:
        args.report.write_text(json.dumps(as_json(results), indent=2), encoding="utf-8")
        print(f"Wrote {args.report}")
    if args.sync_seed and not args.dry_run:
        from app.db.seed import DATA_PATH
        from app.jobs.sync_seed_sources import sync_seed

        await sync_seed(DATA_PATH, dry_run=False)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
