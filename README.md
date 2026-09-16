# Job Search & Immigration Assistant

Personal system for finding realistic software engineering roles with visa sponsorship / relocation support.

It is **not** an auto-apply bot. Applications are always submitted by the candidate.

## What this is

A modular monolith that:

1. Discovers jobs from official/ATS sources
2. Filters and ranks them against the candidate profile
3. Scores visa/relocation evidence without fabricating claims
4. Notifies via Telegram for a human decision
5. Generates cover letters **on demand**
6. Tracks applications and outcomes
7. Learns from decisions to improve future ranking

Phase 1 is the foundation. Discovery, scoring, and Telegram notifications are available via the one-shot runner.

See [ARCHITECTURE.md](ARCHITECTURE.md) for design, tradeoffs, risks, and the phase plan.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose
- OpenAI API key
- Telegram bot token and chat id

Install uv on Windows:

```powershell
python -m pip install uv
```

Or: https://docs.astral.sh/uv/getting-started/installation/

## Quick start

```powershell
cd f:\Programming\job-agent
copy .env.example .env
docker compose up -d postgres redis
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.jobs run-once --limit 10
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health checks:

- http://localhost:8000/health/live — process is up
- http://localhost:8000/health/ready — PostgreSQL (Redis only if `REDIS_URL` is set)
- http://localhost:8000/health — combined status
- http://localhost:8000/docs — OpenAPI

## Run everything in Docker

```powershell
copy .env.example .env
docker compose up --build
```

The API container overrides `DATABASE_URL` and `REDIS_URL` so they point at the Compose service names.

## Database

Alembic lives in `backend/`. Domain tables (jobs, companies, scores, notifications) are created by migrations after the baseline revision.

```powershell
cd backend
uv run alembic upgrade head
uv run alembic revision -m "describe change"
uv run alembic downgrade -1
```

PostgreSQL connection (local Compose defaults). Host port `5434` avoids clashing with other local Postgres instances; inside Compose the service still listens on `5432`.

```
postgresql+asyncpg://jobagent:jobagent@localhost:5434/jobagent
```

A raw `postgres://` / `postgresql://` URI from Supabase also works; settings convert it to `postgresql+asyncpg://`, enable SSL for `*.supabase.co` / `*.supabase.com`, and disable prepared statements on the transaction pooler (port `6543`).

Prefer the **session** pooler (port `5432`) or the direct `db.<ref>.supabase.co` host for Alembic. Apply production migrations with `DATABASE_URL` pointing at Supabase:

```powershell
cd backend
uv run alembic upgrade head
```

Or dispatch `.github/workflows/migrate.yml` after setting the `DATABASE_URL` GitHub Actions secret.

Target companies are upserted from `backend/app/db/data/target_companies.json` (Europe/MENA 2026 research list). Re-seed after changing that file, or on the next `run-once` (seed always upserts):

```powershell
cd backend
uv run python -m app.db.seed
```

Workbook changes can be converted again with `scripts/import_target_companies.py`. Sponsorship from that workbook is stored as `likely` / `unknown`, never `confirmed`. Nordic countries (SE, DK, FI, NO) are included in the candidate target list so those jobs are not location-filtered out.

### Companies vs job sources

A company does not know how it is collected. Identity and research live on `target_companies`; the ATS configuration lives on `company_job_sources`, one row per collectable feed. A company may have several:

```json
{
  "slug": "acme",
  "name": "Acme",
  "careers_url": "https://acme.com/careers",
  "sources": [
    { "ats_type": "greenhouse", "board_token": "acme" },
    {
      "label": "corporate",
      "ats_type": "workday",
      "feed_url": "https://acme.wd3.myworkdayjobs.com/en-US/Acme_Careers"
    }
  ]
}
```

If a company has no `sources` array, one `primary` source is derived from the legacy `ats_type` / `board_token` fields, so older seed files keep working.

## Redis

Optional. Locally it is used for the readiness check and later Dramatiq. On Vercel, omit `REDIS_URL`; `/health/ready` then only requires Postgres.

Host port `6380` avoids clashing with other local Redis instances. Inside Compose the service still listens on `6379`.

```
redis://localhost:6380/0
```

## Environment variables

Copy `.env.example` to `.env`. Never commit `.env`.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy/libpq PostgreSQL URL (asyncpg; Supabase URIs accepted) |
| `REDIS_URL` | Redis URL (optional) |
| `OPENAI_API_KEY` | Job analysis and on-demand cover letters |
| `OPENAI_MODEL` | OpenAI model, default `gpt-4o-mini` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat that receives job cards |
| `TELEGRAM_WEBHOOK_SECRET` | Shared secret Telegram sends as `X-Telegram-Bot-Api-Secret-Token` |
| `PUBLIC_BASE_URL` | Public HTTPS origin for `python -m app.notifications.webhook set` |
| `SCORE_NOTIFY_THRESHOLD` | Minimum score for Telegram (default 80) |
| `APP_ENV` | `development` / `production` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_JSON` | `true` for JSON logs |

## One-shot discovery (no scheduler)

Runs the real pipeline once against PostgreSQL, OpenAI, and Telegram, then exits. It never submits applications and never generates cover letters unless you click the Telegram button later.

```powershell
cd f:\Programming\job-agent\backend
uv run python -m app.jobs run-once --limit 10
```

Equivalent:

```powershell
uv run python -m app.jobs.run_once --limit 10
```

To handle APPLY / SKIP / REJECT / GENERATE COVER LETTER buttons in production, Telegram calls `POST /telegram/webhook`. Register it once (stop the polling bot first):

```powershell
cd backend
uv run python -m app.notifications.webhook set --url https://your-app.vercel.app
```

Locally you can still poll:

```powershell
uv run python -m app.notifications.bot
```

Do not run polling and the webhook at the same time.

## Which ATS platforms are collected

Jobs are read from public ATS feeds only. Careers-page HTML is never scraped.

| ATS | Strategy | Configured with |
|---|---|---|
| Greenhouse | API | board token |
| Lever | API | site token |
| Personio | XML | subdomain |
| Ashby | API | job board name |
| SmartRecruiters | API | company identifier |
| Workable | API | account subdomain |
| Recruitee | API | company subdomain |
| Teamtailor | RSS | subdomain or `feed_url` |
| Workday | API | `feed_url` (needs tenant **and** site id) |

Comeet, Jobvite, BambooHR, iCIMS, Taleo, SuccessFactors and bespoke career pages are recognised but have no adapter yet. They are reported as `adapter_missing` rather than skipped silently.

### Why a company can return zero jobs

Every collection attempt stores a status on its source, so there is always a reason:

| Status | Meaning |
|---|---|
| `collected` | feed read, postings returned |
| `no_jobs` | feed read, zero open postings |
| `needs_token` | ATS known, board token or feed url missing |
| `adapter_missing` | ATS known, no adapter implemented yet |
| `feed_unavailable` | wrong token, or the feed is down |
| `auth_required` | feed needs credentials |
| `blocked` | rate limited |
| `invalid_source` | feed responded but could not be parsed |
| `ats_detected` | ATS found on the careers page but its feed was not readable |
| `discovered` | not investigated yet |

## Find each company's real ATS

Most careers pages are JavaScript-rendered, so a board token has to be discovered and verified rather than assumed. This command inspects each careers page for ATS links, then probes tokens derived from the company slug and name against the real feeds:

```powershell
cd backend
uv run python -m app.jobs discover-sources
```

A source is stored **only** after the live feed returns a usable payload, and a probed token whose board reports a different company name is rejected as a name collision. `extra.detected_via` records whether the match came from a page signature or a probe.

```powershell
uv run python -m app.jobs discover-sources --dry-run                 # report only
uv run python -m app.jobs discover-sources --only-unsupported        # skip solved companies
uv run python -m app.jobs discover-sources --slug adyen --slug wolt  # specific companies
uv run python -m app.jobs discover-sources --no-probe                # trust page links only
uv run python -m app.jobs discover-sources --report findings.json
```

Verified findings live in PostgreSQL. Write them back into the seed file so they survive a database reset:

```powershell
uv run python -m app.jobs sync-seed-sources
uv run python -m app.jobs sync-seed-sources --dry-run
```

## Adapter coverage

Shows how much of the target list is collectable and ranks the missing adapters by how many companies they would unlock. The goal is not that every company has an API — it is that every company has a known strategy.

```powershell
cd backend
uv run python -m app.jobs coverage
```

## Workers and scheduler

The one-shot command above is the local end-to-end path. Dramatiq/APScheduler are not required to discover and notify.

## Production (Vercel + Supabase)

The API deploys from the repo root as FastAPI on Vercel (`api/index.py` / `backend.app.main:app`). Python 3.13. Set at least:

- `DATABASE_URL` — Supabase URI (session pooler or direct)
- `APP_ENV=production`
- `LOG_JSON=true`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET` — for job buttons
- `PUBLIC_BASE_URL` — production origin, used to register the webhook

Redis, OpenAI, and Telegram are not required for health checks.

```powershell
vercel link
vercel env add DATABASE_URL
vercel --prod
```

GitHub Actions: `.github/workflows/test.yml` on push; `.github/workflows/migrate.yml` is manual.

## Frontend

Not started in Phase 1. Next.js dashboard is Phase 6.

```powershell
# later
cd frontend
npm install
npm run dev
```

## Tests

From `backend/`:

```powershell
cd backend
uv run pytest
```

Integration tests that need Postgres/Redis are marked `integration` and skipped unless those services are reachable (or `RUN_INTEGRATION_TESTS=1` is set).

```powershell
uv run pytest -m integration
```

## Project layout

```
api/index.py     Vercel FastAPI entrypoint
backend/app/     FastAPI application
backend/alembic/  migrations
frontend/        Next.js dashboard (later)
tests/           pytest suite
scripts/         operational scripts
```
