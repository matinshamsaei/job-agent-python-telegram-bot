import httpx
import structlog

from app.core.config import Settings
from app.core.enums import NotificationChannel, NotificationStatus, RelocationStatus, VisaStatus
from app.models import Job, JobScore, Notification, TargetCompany
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

VISA_LABEL = {
    VisaStatus.CONFIRMED.value: "Confirmed",
    VisaStatus.LIKELY.value: "Likely",
    VisaStatus.UNKNOWN.value: "Unknown",
    VisaStatus.UNLIKELY.value: "Unlikely",
    VisaStatus.NO.value: "No",
}
VISA_ICON = {
    VisaStatus.CONFIRMED.value: "🟢",
    VisaStatus.LIKELY.value: "🟡",
    VisaStatus.UNKNOWN.value: "⚪",
    VisaStatus.UNLIKELY.value: "🟠",
    VisaStatus.NO.value: "🔴",
}


def build_job_message(
    *,
    job: Job,
    company: TargetCompany,
    score: JobScore,
    visa_status: str,
    relocation_status: str,
) -> str:
    reasons = "\n".join(f"+ {item}" for item in (score.positive_reasons or [])[:4]) or "+ See dashboard"
    risks = "\n".join(f"- {item}" for item in (score.risks or score.negative_reasons or [])[:4]) or "- None listed"
    relocation = "Supported" if relocation_status == RelocationStatus.SUPPORTED.value else relocation_status.title()
    tech = score.breakdown.get("technical_fit", 0)
    exp = score.breakdown.get("experience_fit", 0)
    return (
        f"🟢 HIGH PRIORITY JOB\n\n"
        f"{job.title}\n\n"
        f"Company:\n{company.name}\n\n"
        f"Location:\n{job.location or company.city or company.country}\n\n"
        f"Score:\n{int(round(score.overall_score))}/100\n\n"
        f"Visa:\n{VISA_ICON.get(visa_status, '⚪')} {VISA_LABEL.get(visa_status, visa_status)}\n\n"
        f"Relocation:\n{'🟢 ' if relocation_status == RelocationStatus.SUPPORTED.value else ''}{relocation}\n\n"
        f"Technical fit:\n{int(tech)}\n\n"
        f"Experience fit:\n{int(exp)}\n\n"
        f"Why:\n{reasons}\n\n"
        f"Risks:\n{risks}"
    )


def build_keyboard(job: Job) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "VIEW JOB", "url": job.url}],
            [
                {"text": "APPLY", "callback_data": f"apply:{job.id}"},
                {"text": "SKIP", "callback_data": f"skip:{job.id}"},
            ],
            [
                {"text": "REJECT", "callback_data": f"reject:{job.id}"},
                {"text": "GENERATE COVER LETTER", "callback_data": f"cover:{job.id}"},
            ],
        ]
    }


async def send_job_notification(
    session: AsyncSession,
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    job: Job,
    company: TargetCompany,
    score: JobScore,
    visa_status: str,
    relocation_status: str,
) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("telegram_skipped", reason="missing_token_or_chat_id")
        session.add(
            Notification(
                job_id=job.id,
                channel=NotificationChannel.TELEGRAM.value,
                status=NotificationStatus.SKIPPED.value,
                error="missing telegram credentials",
            )
        )
        return False

    text = build_job_message(
        job=job,
        company=company,
        score=score,
        visa_status=visa_status,
        relocation_status=relocation_status,
    )
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    response = await client.post(
        url,
        json={
            "chat_id": settings.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": True,
            "reply_markup": build_keyboard(job),
        },
        timeout=settings.http_timeout_seconds,
    )
    if response.status_code >= 400:
        logger.warning("telegram_send_failed", status=response.status_code, body=response.text[:300])
        session.add(
            Notification(
                job_id=job.id,
                channel=NotificationChannel.TELEGRAM.value,
                status=NotificationStatus.FAILED.value,
                error=response.text[:500],
                payload={"text": text[:500]},
            )
        )
        return False

    payload = response.json()
    message_id = str(payload.get("result", {}).get("message_id", ""))
    session.add(
        Notification(
            job_id=job.id,
            channel=NotificationChannel.TELEGRAM.value,
            status=NotificationStatus.SENT.value,
            external_id=message_id,
            payload={"score": score.overall_score},
        )
    )
    logger.info("telegram_sent", job_id=job.id, company=company.slug)
    return True
