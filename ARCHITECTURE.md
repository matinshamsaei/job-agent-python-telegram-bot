# Architecture

Personal Job Search & Immigration Assistant.

This is a **single-user modular monolith**. It discovers software engineering jobs, filters for realistic visa/relocation fit, ranks opportunities, notifies via Telegram, tracks applications, generates cover letters on demand, and learns from outcomes. It never auto-applies.

## Current repository state

Greenfield. Phase 1 is the runnable foundation (API, settings, PostgreSQL, Redis, Alembic, structured logging, health checks, Docker Compose). Domain models and collectors start in later phases.

## Success metrics

The system is successful if it improves:

- relevant jobs discovered
- wasted applications avoided
- high-quality applications submitted
- recruiter responses
- interviews
- offers
- country/company yield over time

AI sophistication is not a success metric.

## High-level design

```
Job collectors  →  normalize/dedupe  →  hard filters  →  AI analysis (cached)
        →  visa intelligence  →  skill match  →  scoring/ranking
        →  Telegram (decision)  →  optional cover letter
        →  manual apply  →  application/outcome tracking
        →  preference learning  →  funnel analytics
```

Cheap deterministic work always runs before LLM calls.

## Modular monolith

One FastAPI process, one PostgreSQL database, one Redis instance, Dramatiq workers (from Phase 3+), APScheduler in-process (from Phase 3+).

Domain packages stay independently testable. They communicate through typed models and service functions, not shared mutable state.

Planned package layout (`backend/app/`):

| Package | Responsibility | First phase |
|---|---|---|
| `api/` | HTTP routes | 1 |
| `core/` | settings, logging | 1 |
| `db/` | engine, sessions, Redis client | 1 |
| `models/` / `schemas/` / `repositories/` | persistence and API contracts | 2 |
| `collectors/` | Greenhouse, Lever, career pages | 3 |
| `analyzers/` | deterministic extract + LLM analysis | 4 |
| `scoring/` | pure scoring engine | 5 |
| `notifications/` | Telegram bot | 7 |
| `applications/` | application + event tracking | 8 |
| `cover_letters/` | on-demand generation and versioning | 9 |
| `learning/` | transparent preference model | 10 |
| `analytics/` | funnel and bottleneck insights | 11 |
| `workers/` / `scheduler/` | Dramatiq actors, APScheduler jobs | 3+ |

Frontend (`frontend/`) is a Next.js dashboard. It is not a second backend.

## Core invariants

1. **Never auto-apply.** Telegram `APPLY` means "intended to apply" and opens the original job URL.
2. **Never invent facts.** No fabricated company evidence, skills, or candidate experience.
3. **Visa claims need evidence.** Store timestamped `CompanyEvidence`, not a naked boolean.
4. **Evidence decays.** Historical sponsorship does not imply current sponsorship.
5. **Unknown is valid.** Missing visa information is `UNKNOWN`, not a guess.
6. **Explain every score.** Weights, breakdown, reasons, and risks are stored and shown.
7. **Cover letters are on demand only.** Generated when the user asks, never in the discovery loop.
8. **One collector failure cannot stop a search run.**

## Data model (Phase 2)

Minimum entities: `CandidateProfile`, `CandidateResume`, `TargetCompany`, `CompanyAlias`, `CompanyEvidence`, `JobSource`, `Job`, `JobAnalysis`, `JobScore`, `JobDecision`, `Application`, `ApplicationEvent`, `CoverLetter`, `Notification`, `LearningFeedback`, `SearchRun`, `VerificationRun`.

Dedup:

- preferred: `source + external_id`
- fallback: normalized company + title + location + description hash

## Job sources

Preference order: official API → ATS JSON → RSS/feed → static HTML → Playwright.

V1 collectors: Greenhouse, Lever, company career pages.

Do not scrape LinkedIn. Do not bypass auth, CAPTCHA, rate limits, robots.txt, or anti-bot systems. Skip sources that cannot be accessed reliably and legally.

## Scoring (Phase 5)

Configurable weights, defaulting to:

| Component | Weight |
|---|---|
| Technical fit | 25% |
| Visa fit | 20% |
| Experience fit | 15% |
| Relocation fit | 10% |
| Country fit | 10% |
| Role/seniority fit | 10% |
| Company fit | 5% |
| International hiring | 5% |

Recommendations: `APPLY` 80–100, `REVIEW` 60–79, `SKIP` 0–59.

Learning (Phase 10) adjusts a transparent preference model from accumulated decisions. It does not rewrite global weights after a single click.

## Tradeoffs

**Modular monolith vs microservices.** One deployable, one database, local transactions. Independent Python packages preserve testability without network boundaries. Microservices would add ops cost with no user benefit.

**Async FastAPI + later Dramatiq.** HTTP and I/O stay async. Dramatiq actors are typically sync; collectors will use sync httpx (or `asyncio.run` for isolated async calls) inside workers. This is simpler than an async-native queue and is enough for a personal crawler.

**Deterministic filters before LLMs.** Saves money, keeps skips explainable, and avoids analyzing intern or local-only roles. The risk is over-filtering; filters must be conservative (only drop explicit disqualifiers).

**Evidence-based visa vs boolean flags.** More schema and verification work, but the product is useless if it recommends companies that do not sponsor. Stale positive evidence is treated as weak, not confirmatory.

**Transparent preference model vs ML.** Immediate, inspectable, and honest ("your preferences changed because…"). Feature snapshots on every decision keep the door open for learning-to-rank later.

**Telegram as the action surface.** Fast decisions on ranked jobs. The dashboard owns search, evidence timelines, funnel analytics, and cover-letter editing.

**Playwright last.** It is the least reliable and most expensive collector. ATS JSON boards are preferred.

**No multi-user auth.** This is a personal system. Network exposure should stay local/Docker.

## Risks

| Risk | Mitigation |
|---|---|
| ATS HTML/JSON changes break collectors | Pluggable collectors, per-source error isolation, `SearchRun` metrics |
| Stale or wrong visa evidence wastes applications | Timestamped evidence, freshness decay, mixed-evidence tests, `UNKNOWN` default |
| LLM cost on noisy discovery | Hard filters first, analysis cache keyed on description hash |
| Cover letter hallucinates experience | Pydantic output, candidate-profile-only facts, tests for invented experience |
| Career pages inconsistent | Company-specific adapters only when Greenhouse/Lever are absent |
| Telegram message limits for cover letters | Send a preview + dashboard deep link |
| Over-filtering good jobs | Conservative hard filters; `REVIEW` band for uncertain visa |
| Under-filtering sponsorship theater | Job-posting claims are evidence, not confirmation; government/official sources rank higher |
| Single-machine Redis/Postgres failure | Docker healthchecks; API readiness endpoint |

## Implementation plan

| Phase | Scope |
|---|---|
| **1 Foundation** | uv, FastAPI, PostgreSQL, Redis, SQLAlchemy, Alembic, settings, Docker, health, structured logging |
| **2 Database** | models, migrations, seed companies/profile/resumes/evidence |
| **3 Job discovery** | collector protocol, Greenhouse, Lever, career pages, normalize, dedupe |
| **4 Job intelligence** | hard filters, AI analysis, visa intelligence, skill taxonomy matching |
| **5 Scoring** | explainable scoring engine, ranking, recommendations |
| **6 Dashboard** | Next.js jobs/companies/filters/detail views |
| **7 Telegram** | bot, notifications, stateful job actions |
| **8 Application tracking** | statuses, events, follow-up reminders |
| **9 Cover letters** | on-demand generation, versioning, Telegram flow |
| **10 Learning** | decision feedback, preference model, outcome tracking |
| **11 Analytics** | funnel, country/company yield, bottleneck insights |

Phase 1 explicitly does **not** include collectors, OpenAI, Telegram, Dramatiq, Playwright, or the dashboard.

## Local runtime (Phase 1)

```
Docker Compose:  PostgreSQL 16  +  Redis 8
Host (or api container):  FastAPI / uvicorn
Alembic:  migration runner (no domain tables until Phase 2)
```

Default host ports (chosen to avoid common local clashes):

- API: `8000`
- PostgreSQL: `5434` → container `5432`
- Redis: `6380` → container `6379`

## Configuration

See `.env.example`. Settings are loaded via Pydantic Settings. Secrets are never committed.
