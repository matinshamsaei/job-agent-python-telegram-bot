from __future__ import annotations

import argparse
import asyncio
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the job discovery pipeline once and exit. Never auto-applies."
    )
    parser.add_argument("--limit", type=int, default=10, help="Maximum discovered jobs to process")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from app.jobs.pipeline import run_pipeline

    asyncio.run(run_pipeline(limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
