import structlog
from openai import AsyncOpenAI

from app.analyzers.job_analysis import LLMJobAnalysis
from app.core.config import Settings

logger = structlog.get_logger(__name__)
PROMPT_VERSION = "job-analysis-v1"


class OpenAIProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.openai_api_key)

    async def analyze_job(self, *, title: str, company: str, description: str) -> LLMJobAnalysis | None:
        if self.client is None:
            return None
        prompt = (
            "Extract structured hiring signals from this software-engineering job. "
            "Never invent skills that are not in the text. "
            "If visa/relocation is not stated, use unknown.\n\n"
            f"Company: {company}\nTitle: {title}\n\n{description[:12000]}"
        )
        try:
            response = await self.client.chat.completions.parse(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract job requirements. Do not invent experience or skills.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format=LLMJobAnalysis,
                temperature=0,
            )
            return response.choices[0].message.parsed
        except Exception as exc:
            logger.warning("openai_analyze_failed", error=str(exc))
            return None
