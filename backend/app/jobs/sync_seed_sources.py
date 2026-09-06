"""Write verified company job sources from the database back into seed JSON.

Discovery stores findings in PostgreSQL. This command makes them survive a
database reset by updating `target_companies.json` in place.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.enums import AtsType
from app.db.seed import DATA_PATH, load_target_companies
from app.models import CompanyJobSource, TargetCompany

KEEP_STATUSES = {
    "feed_available",
    "collected",
    "no_jobs",
    "ats_detected",
    "adapter_missing",
    "needs_token",
    "feed_unavailable",
    "blocked",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync verified ATS sources from the database into target_companies.json."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_PATH,
        help="JSON path to rewrite (default: seed data path)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the updates without writing the file",
    )
    return parser


async def sync_seed(output: Path, *, dry_run: bool) -> int:
    from app.core.config import Settings
    from app.core.logging import configure_logging
    from app.db.session import dispose_engine, init_engine

    settings = Settings()
    configure_logging(settings)
    factory = init_engine(settings)
    try:
        async with factory() as session:
            pairs = (
                await session.execute(
                    select(TargetCompany, CompanyJobSource)
                    .join(CompanyJobSource, CompanyJobSource.company_id == TargetCompany.id)
                    .where(CompanyJobSource.label == "primary")
                )
            ).all()
    finally:
        await dispose_engine()

    by_slug = {
        company.slug: source
        for company, source in pairs
        if source.status in KEEP_STATUSES
        and source.ats_type not in {AtsType.CAREER_PAGE.value, AtsType.UNKNOWN.value}
    }
    rows = load_target_companies()
    updated = 0
    for row in rows:
        source = by_slug.get(row["slug"])
        if source is None:
            continue
        changed = (
            row.get("ats_type") != source.ats_type
            or row.get("board_token") != source.board_token
            or (source.feed_url and row.get("extra", {}).get("feed_url") != source.feed_url)
        )
        if not changed and row.get("sources"):
            continue
        row["ats_type"] = source.ats_type
        row["board_token"] = source.board_token
        entry = {
            "ats_type": source.ats_type,
            "board_token": source.board_token,
            "collection_strategy": source.collection_strategy,
            "status": source.status,
        }
        if source.feed_url:
            entry["feed_url"] = source.feed_url
        if source.job_url_pattern:
            entry["job_url_pattern"] = source.job_url_pattern
        row["sources"] = [entry]
        updated += 1
        print(
            f"{row['slug']:34} -> {source.ats_type:16} "
            f"{source.board_token or source.feed_url or '-'}"
        )

    print(f"\n{updated} companies updated")
    if dry_run or updated == 0:
        return updated
    output.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    return updated


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(sync_seed(args.output, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
