import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.analyzers.filters import infer_seniority
from app.analyzers.skills import extract_skills, match_skills
from app.analyzers.visa import TextVisaSignals, classify_text
from app.core.enums import RoleCategory


class LLMJobAnalysis(BaseModel):
    role_category: str = RoleCategory.UNKNOWN.value
    seniority: str = "unknown"
    years_required: int | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    visa_status: str = "unknown"
    relocation_status: str = "unknown"
    remote_type: str = "unknown"
    employment_type: str = "unknown"
    salary: str | None = None
    positive_signals: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


@dataclass
class AnalysisResult:
    role_category: str
    seniority: str
    years_required: int | None
    required_skills: list[str]
    preferred_skills: list[str]
    visa: TextVisaSignals
    remote_type: str
    employment_type: str
    salary: str | None
    positive_signals: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    resume_variant: str = "SENIOR_SOFTWARE_ENGINEER"
    skill_score: float = 0.0
    matched_skills: list[str] = field(default_factory=list)
    model: str | None = None
    prompt_version: str | None = None


def analyze_deterministically(
    *,
    title: str,
    description: str,
    remote_type: str,
    employment_type: str,
    salary: str | None,
    candidate_skills: list[str],
) -> AnalysisResult:
    visa = classify_text(f"{title}\n{description}")
    skills = extract_skills(f"{title}\n{description}")
    match = match_skills(skills, candidate_skills, title)
    years = _years_required(description)
    red_flags = list(visa.snippets) if visa.visa_status.value in {"no", "unlikely"} else []
    positives = []
    if match.matched:
        positives.append("Matched skills: " + ", ".join(match.matched[:8]))
    if visa.claims:
        positives.extend(claim.value.replace("_", " ") for claim in visa.claims if "no_" not in claim.value)
    return AnalysisResult(
        role_category=match.role_category,
        seniority=infer_seniority(title, description),
        years_required=years,
        required_skills=skills,
        preferred_skills=[],
        visa=visa,
        remote_type=remote_type,
        employment_type=employment_type,
        salary=salary,
        positive_signals=positives,
        red_flags=red_flags,
        resume_variant=match.resume_variant,
        skill_score=match.score,
        matched_skills=match.matched,
        model=None,
        prompt_version="deterministic-v1",
    )


def merge_llm(base: AnalysisResult, llm: LLMJobAnalysis, job_text: str) -> AnalysisResult:
    allowed = {skill.lower() for skill in extract_skills(job_text)}
    required = [skill for skill in llm.required_skills if skill.lower() in allowed or skill in base.required_skills]
    preferred = [skill for skill in llm.preferred_skills if skill.lower() in allowed]
    if required:
        base.required_skills = required
    if preferred:
        base.preferred_skills = preferred
    if llm.role_category and llm.role_category != RoleCategory.UNKNOWN.value:
        base.role_category = llm.role_category
    if llm.years_required:
        base.years_required = llm.years_required
    if llm.salary:
        base.salary = llm.salary
    base.positive_signals = list(dict.fromkeys(base.positive_signals + llm.positive_signals))
    base.red_flags = list(dict.fromkeys(base.red_flags + llm.red_flags))
    base.model = "openai"
    base.prompt_version = "job-analysis-v1"
    return base


def _years_required(text: str) -> int | None:
    match = re.search(r"(\d+)\+?\s*\+?\s*years", text, re.I)
    if not match:
        return None
    return int(match.group(1))
