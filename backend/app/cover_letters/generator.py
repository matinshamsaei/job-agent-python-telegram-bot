from app.analyzers.ai import OpenAIProvider
from app.core.config import Settings
from app.cover_letters.schema import CoverLetterOutput
from app.models import CandidateProfile, CandidateResume, Job, TargetCompany


async def generate_cover_letter(
    settings: Settings,
    *,
    profile: CandidateProfile,
    resume: CandidateResume,
    job: Job,
    company: TargetCompany,
) -> CoverLetterOutput:
    provider = OpenAIProvider(settings)
    if provider.client is None:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    prompt = (
        "Write a concise cover letter for a senior engineer. "
        "150-300 words. Professional, natural, confident. "
        "Do not invent employers, projects, or skills. "
        "Use only the candidate facts provided. "
        "Do not start with 'I am writing to express my interest'.\n\n"
        f"Candidate: {profile.name}, {profile.current_title}, {profile.years_experience} years.\n"
        f"Resume variant: {resume.variant}\n"
        f"Resume:\n{resume.content}\n\n"
        f"Company: {company.name} ({company.country})\n"
        f"Role: {job.title}\n"
        f"Location: {job.location}\n"
        f"Description:\n{job.description[:8000]}"
    )
    response = await provider.client.chat.completions.parse(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "You write honest, specific cover letters. Never invent experience.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format=CoverLetterOutput,
        temperature=0.4,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Cover letter model returned no structured output")
    parsed.resume_variant = resume.variant
    return parsed
