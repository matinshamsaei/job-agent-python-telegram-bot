import httpx
import structlog
from sqlalchemy import select

from app.core.config import Settings
from app.core.enums import ApplicationStatus, CoverLetterStatus, DecisionType, ResumeVariant
from app.core.logging import configure_logging
from app.cover_letters.generator import generate_cover_letter
from app.db.session import dispose_engine, init_engine
from app.db import session as db_session
from app.models import (
    Application,
    ApplicationEvent,
    CandidateProfile,
    CandidateResume,
    CoverLetter,
    Job,
    JobAnalysis,
    JobDecision,
    TargetCompany,
)

logger = structlog.get_logger(__name__)


async def handle_callback(settings: Settings, client: httpx.AsyncClient, callback: dict) -> None:
    data = callback.get("data") or ""
    callback_id = callback.get("id")
    chat_id = callback.get("message", {}).get("chat", {}).get("id")
    if not data or ":" not in data or db_session.SessionLocal is None:
        return
    action, _, raw_id = data.partition(":")
    try:
        job_id = int(raw_id)
    except ValueError:
        return

    async with db_session.SessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            await _answer(client, settings, callback_id, "Job not found.")
            return
        company = await session.get(TargetCompany, job.company_id)
        if action == "apply":
            await _mark_intended(session, job)
            await session.commit()
            await _answer(client, settings, callback_id, "Marked as intended. Open the job page to apply manually.")
            await _send(client, settings, chat_id, f"Apply manually:\n{job.url}")
            return
        if action == "skip":
            session.add(JobDecision(job_id=job.id, decision=DecisionType.SKIP.value, job_features=_features(job)))
            await session.commit()
            await _answer(client, settings, callback_id, "Skipped.")
            await delete_suggested_message(client, settings, callback)
            return
        if action == "reject":
            session.add(
                JobDecision(
                    job_id=job.id,
                    decision=DecisionType.REJECT.value,
                    reason="other",
                    job_features=_features(job),
                )
            )
            await session.commit()
            await _answer(client, settings, callback_id, "Rejected.")
            await delete_suggested_message(client, settings, callback)
            return
        if action == "cover":
            await _answer(client, settings, callback_id, "Generating a tailored cover letter...")
            try:
                letter = await _generate(session, settings, job, company)
                await session.commit()
                await _send(
                    client,
                    settings,
                    chat_id,
                    f"Your cover letter is ready.\n\nSubject: {letter.subject}\n\n{letter.cover_letter}",
                )
            except Exception as exc:
                logger.warning("cover_letter_failed", error=str(exc))
                await _send(client, settings, chat_id, "Could not generate a cover letter. Check OPENAI_API_KEY.")
            return


async def poll_forever() -> None:
    settings = Settings()
    configure_logging(settings)
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    init_engine(settings)
    offset = 0
    timeout = httpx.Timeout(settings.http_timeout_seconds + 40)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            logger.info("telegram_bot_started")
            while True:
                response = await client.get(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
                    params={"timeout": 30, "offset": offset},
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    offset = update["update_id"] + 1
                    callback = update.get("callback_query")
                    if callback:
                        await handle_callback(settings, client, callback)
    finally:
        await dispose_engine()


async def _generate(session, settings: Settings, job: Job, company: TargetCompany | None) -> CoverLetter:
    if company is None:
        raise RuntimeError("Company missing")
    profile = await session.scalar(select(CandidateProfile).limit(1))
    if profile is None:
        raise RuntimeError("Candidate profile missing")
    analysis = await session.scalar(select(JobAnalysis).where(JobAnalysis.job_id == job.id))
    variant = (analysis.extra or {}).get("resume_variant") if analysis else ResumeVariant.SENIOR_SOFTWARE_ENGINEER.value
    resume = await session.scalar(
        select(CandidateResume).where(CandidateResume.variant == variant)
    ) or await session.scalar(select(CandidateResume).where(CandidateResume.is_default.is_(True)))
    if resume is None:
        raise RuntimeError("No resume variant found")
    output = await generate_cover_letter(settings, profile=profile, resume=resume, job=job, company=company)
    row = CoverLetter(
        job_id=job.id,
        candidate_resume_id=resume.id,
        content=output.cover_letter,
        subject=output.subject,
        model=settings.openai_model,
        prompt_version="cover-v1",
        status=CoverLetterStatus.DRAFT.value,
    )
    session.add(row)
    await session.flush()
    return row


async def _mark_intended(session, job: Job) -> None:
    existing = await session.scalar(select(Application).where(Application.job_id == job.id))
    if existing is None:
        application = Application(
            job_id=job.id,
            company_id=job.company_id,
            status=ApplicationStatus.INTENDED.value,
            application_url=job.url,
        )
        session.add(application)
        await session.flush()
        session.add(
            ApplicationEvent(
                application_id=application.id,
                event_type=ApplicationStatus.INTENDED.value,
                notes="Marked from Telegram. Application was not submitted.",
                source="telegram",
            )
        )
    session.add(
        JobDecision(
            job_id=job.id,
            decision=DecisionType.APPLY_INTENDED.value,
            notes="Telegram APPLY. Manual submission required.",
            job_features=_features(job),
        )
    )


def suggested_message_coords(callback: dict) -> tuple[object, object]:
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    return chat_id, message.get("message_id")


async def delete_suggested_message(client: httpx.AsyncClient, settings: Settings, callback: dict) -> None:
    chat_id, message_id = suggested_message_coords(callback)
    if not chat_id or not message_id or not settings.telegram_bot_token:
        return
    base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
    response = await client.post(
        f"{base}/deleteMessage",
        json={"chat_id": chat_id, "message_id": message_id},
    )
    payload = {}
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code < 400 and payload.get("ok", True):
        logger.info("telegram_message_deleted", chat_id=chat_id, message_id=message_id)
        return
    logger.warning(
        "telegram_delete_failed",
        status=response.status_code,
        body=str(payload or response.text)[:300],
    )
    await client.post(
        f"{base}/editMessageReplyMarkup",
        json={"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}},
    )


def _features(job: Job) -> dict:
    return {
        "title": job.title,
        "country": job.country,
        "company_id": job.company_id,
        "source": job.source,
    }


async def _answer(client: httpx.AsyncClient, settings: Settings, callback_id: str | None, text: str) -> None:
    if not callback_id:
        return
    await client.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerCallbackQuery",
        json={"callback_query_id": callback_id, "text": text, "show_alert": False},
    )


async def _send(client: httpx.AsyncClient, settings: Settings, chat_id, text: str) -> None:
    if not chat_id:
        return
    await client.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
    )


def main() -> None:
    import asyncio

    asyncio.run(poll_forever())


if __name__ == "__main__":
    main()
