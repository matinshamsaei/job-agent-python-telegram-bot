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

Phase 1 is the foundation only: FastAPI, PostgreSQL, Redis, Alembic, settings, structured logging, health checks, Docker Compose.

See [ARCHITECTURE.md](ARCHITECTURE.md) for design, tradeoffs, risks, and the phase plan.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose
- (later phases) OpenAI API key, Telegram bot token

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
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health checks:

- http://localhost:8000/health/live — process is up
- http://localhost:8000/health/ready — PostgreSQL + Redis
- http://localhost:8000/health — combined status
- http://localhost:8000/docs — OpenAPI

## Run everything in Docker

```powershell
copy .env.example .env
docker compose up --build
```

The API container overrides `DATABASE_URL` and `REDIS_URL` so they point at the Compose service names.

## Database

Alembic lives in `backend/`. There are no domain tables in Phase 1; `upgrade head` applies the baseline revision so the migration toolchain is verified.

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

## Redis

Used in Phase 1 for the readiness check. Later: Dramatiq broker/queue and cache.

Host port `6380` avoids clashing with other local Redis instances. Inside Compose the service still listens on `6379`.

```
redis://localhost:6380/0
```

## Environment variables

Copy `.env.example` to `.env`. Never commit `.env`.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy async PostgreSQL URL |
| `REDIS_URL` | Redis URL |
| `OPENAI_API_KEY` | Reserved; unused in Phase 1 |
| `TELEGRAM_BOT_TOKEN` | Reserved; unused in Phase 1 |
| `TELEGRAM_CHAT_ID` | Reserved; unused in Phase 1 |
| `APP_ENV` | `development` / `production` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_JSON` | `true` for JSON logs |

## Workers and scheduler

Not started in Phase 1. Dramatiq workers and APScheduler jobs arrive with job discovery (Phase 3).

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
backend/app/     FastAPI application
backend/alembic/  migrations
frontend/        Next.js dashboard (Phase 6+)
tests/           pytest suite
scripts/         operational scripts
```
