"""Report how much of the target list is actually collectable.

The goal is not that every company has an API, but that every company has a
known collection strategy — and that the gaps are visible and ranked.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.registry import missing_adapter_reason, supported_ats_types
from app.core.enums import CollectionStatus
from app.models import CompanyJobSource, TargetCompany

VERIFIED_STATUSES = {CollectionStatus.COLLECTED.value, CollectionStatus.NO_JOBS.value}


@dataclass
class AtsCoverage:
    ats_type: str
    supported: bool
    companies: set[str] = field(default_factory=set)
    sources: int = 0
    verified: int = 0
    jobs_last_run: int = 0
    statuses: dict[str, int] = field(default_factory=dict)


@dataclass
class CoverageReport:
    by_ats: dict[str, AtsCoverage]
    total_companies: int
    companies_with_supported_source: set[str]
    companies_with_jobs: set[str]

    @property
    def rows(self) -> list[AtsCoverage]:
        return sorted(
            self.by_ats.values(),
            key=lambda row: (not row.supported, -len(row.companies), row.ats_type),
        )

    def print(self) -> None:
        print(f"Target companies (enabled): {self.total_companies}")
        print(f"Companies with a supported source: {len(self.companies_with_supported_source)}")
        print(f"Companies that returned jobs on the last run: {len(self.companies_with_jobs)}\n")

        header = f"{'ATS':18} {'Companies':>9} {'Sources':>7} {'Adapter':>8} {'Verified':>8} {'Jobs':>6}"
        print(header)
        print("-" * len(header))
        for row in self.rows:
            adapter = "yes" if row.supported else "no"
            print(
                f"{row.ats_type:18} {len(row.companies):>9} {row.sources:>7} "
                f"{adapter:>8} {row.verified:>8} {row.jobs_last_run:>6}"
            )

        missing = [row for row in self.rows if not row.supported and row.companies]
        if missing:
            print("\nWhere the next adapter pays off most:")
            for row in missing:
                print(
                    f"  {row.ats_type:18} {len(row.companies):>3} companies"
                    f"  ({missing_adapter_reason(row.ats_type)})"
                )

        statuses: dict[str, int] = {}
        for row in self.by_ats.values():
            for status, count in row.statuses.items():
                statuses[status] = statuses.get(status, 0) + count
        if statuses:
            print("\nLast status per source:")
            for status, count in sorted(statuses.items(), key=lambda kv: -kv[1]):
                print(f"  {status:20} {count}")

        unsupported = self.total_companies - len(self.companies_with_supported_source)
        if unsupported:
            print(
                f"\n{unsupported} companies have no supported source yet. "
                "Run `python -m app.jobs discover-sources` to look for their real ATS."
            )


async def build_report(session: AsyncSession) -> CoverageReport:
    supported = supported_ats_types()
    pairs = (
        await session.execute(
            select(TargetCompany, CompanyJobSource)
            .join(CompanyJobSource, CompanyJobSource.company_id == TargetCompany.id)
            .where(TargetCompany.enabled.is_(True))
        )
    ).all()
    enabled_slugs = set(
        (
            await session.scalars(
                select(TargetCompany.slug).where(TargetCompany.enabled.is_(True))
            )
        ).all()
    )

    by_ats: dict[str, AtsCoverage] = {}
    with_supported: set[str] = set()
    with_jobs: set[str] = set()
    for company, source in pairs:
        row = by_ats.get(source.ats_type)
        if row is None:
            row = AtsCoverage(ats_type=source.ats_type, supported=source.ats_type in supported)
            by_ats[source.ats_type] = row
        row.companies.add(company.slug)
        row.sources += 1
        row.jobs_last_run += source.last_job_count
        row.statuses[source.status] = row.statuses.get(source.status, 0) + 1
        if source.status in VERIFIED_STATUSES:
            row.verified += 1
        if source.ats_type in supported:
            with_supported.add(company.slug)
        if source.last_job_count:
            with_jobs.add(company.slug)

    return CoverageReport(
        by_ats=by_ats,
        total_companies=len(enabled_slugs),
        companies_with_supported_source=with_supported,
        companies_with_jobs=with_jobs,
    )


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Show ATS adapter coverage across the target company list."
    )


async def _run() -> None:
    from app.core.config import Settings
    from app.core.logging import configure_logging
    from app.db.session import dispose_engine, init_engine

    settings = Settings()
    configure_logging(settings)
    factory = init_engine(settings)
    try:
        async with factory() as session:
            report = await build_report(session)
            report.print()
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
