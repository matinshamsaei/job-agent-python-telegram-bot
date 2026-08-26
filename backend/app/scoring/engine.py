from dataclasses import dataclass

from app.core.enums import Recommendation, RelocationStatus, Seniority, VisaStatus

DEFAULT_WEIGHTS = {
    "technical_fit": 0.25,
    "experience_fit": 0.15,
    "visa_fit": 0.20,
    "relocation_fit": 0.10,
    "country_fit": 0.10,
    "role_seniority_fit": 0.10,
    "company_fit": 0.05,
    "international_hiring": 0.05,
}

COUNTRY_PRIORITY = {
    "AE": 1.0,
    "DE": 0.92,
    "NL": 0.85,
    "SE": 0.82,
    "IE": 0.78,
    "DK": 0.76,
    "SA": 0.70,
    "FI": 0.68,
    "NO": 0.68,
    "EE": 0.62,
    "PT": 0.55,
    "CA": 0.48,
}

VISA_SCORES = {
    VisaStatus.CONFIRMED.value: 1.0,
    VisaStatus.LIKELY.value: 0.75,
    VisaStatus.UNKNOWN.value: 0.40,
    VisaStatus.UNLIKELY.value: 0.15,
    VisaStatus.NO.value: 0.0,
}

RELOCATION_SCORES = {
    RelocationStatus.SUPPORTED.value: 1.0,
    RelocationStatus.UNKNOWN.value: 0.45,
    RelocationStatus.UNLIKELY.value: 0.15,
    RelocationStatus.NO.value: 0.0,
}

SENIORITY_SCORES = {
    Seniority.SENIOR.value: 1.0,
    Seniority.STAFF.value: 0.95,
    Seniority.LEAD.value: 0.95,
    Seniority.PRINCIPAL.value: 0.8,
    Seniority.MID.value: 0.45,
    Seniority.UNKNOWN.value: 0.55,
    Seniority.JUNIOR.value: 0.1,
    Seniority.INTERN.value: 0.0,
}


@dataclass(frozen=True)
class ScoreResult:
    overall_score: float
    breakdown: dict[str, float]
    positive_reasons: list[str]
    negative_reasons: list[str]
    risks: list[str]
    recommendation: str
    weights: dict[str, float]


def score_job(
    *,
    technical_fit: float,
    years_experience: int,
    years_required: int | None,
    visa_status: str,
    relocation_status: str,
    country: str | None,
    seniority: str,
    company_priority: int,
    international_hiring: bool,
    matched_skills: list[str],
    missing_skills: list[str],
    apply_threshold: int = 80,
    review_threshold: int = 60,
    weights: dict[str, float] | None = None,
) -> ScoreResult:
    used_weights = dict(weights or DEFAULT_WEIGHTS)
    experience = _experience_fit(years_experience, years_required)
    visa = VISA_SCORES.get(visa_status, 0.4)
    relocation = RELOCATION_SCORES.get(relocation_status, 0.45)
    country_fit = COUNTRY_PRIORITY.get(country or "", 0.2)
    seniority_fit = SENIORITY_SCORES.get(seniority, 0.5)
    company_fit = min(max(company_priority, 0), 100) / 100
    international = 1.0 if international_hiring else 0.35

    components = {
        "technical_fit": _clamp(technical_fit),
        "experience_fit": experience,
        "visa_fit": visa,
        "relocation_fit": relocation,
        "country_fit": country_fit,
        "role_seniority_fit": seniority_fit,
        "company_fit": company_fit,
        "international_hiring": international,
    }
    overall = 100 * sum(components[key] * used_weights[key] for key in used_weights)

    positives: list[str] = []
    negatives: list[str] = []
    risks: list[str] = []
    if matched_skills:
        positives.append("Strong skill overlap: " + ", ".join(matched_skills[:6]))
    if visa_status == VisaStatus.CONFIRMED.value:
        positives.append("Visa sponsorship confirmed in current posting/evidence")
    if visa_status == VisaStatus.LIKELY.value:
        positives.append("International hiring / likely sponsorship signals")
    if relocation_status == RelocationStatus.SUPPORTED.value:
        positives.append("Relocation support mentioned")
    if country in COUNTRY_PRIORITY:
        positives.append(f"Country fit: {country}")
    if seniority in {Seniority.SENIOR.value, Seniority.STAFF.value, Seniority.LEAD.value}:
        positives.append("Seniority matches")
    if missing_skills:
        negatives.append("Missing listed skills: " + ", ".join(missing_skills[:6]))
    if visa_status == VisaStatus.UNKNOWN.value:
        risks.append("Visa status unknown")
    if visa_status in {VisaStatus.NO.value, VisaStatus.UNLIKELY.value}:
        negatives.append("Weak or negative visa signal")
    if years_required and years_required > years_experience + 2:
        negatives.append(f"Posting asks for {years_required}+ years")

    if overall >= apply_threshold:
        recommendation = Recommendation.APPLY.value
    elif overall >= review_threshold:
        recommendation = Recommendation.REVIEW.value
    else:
        recommendation = Recommendation.SKIP.value

    breakdown = {key: round(value * 100, 1) for key, value in components.items()}
    return ScoreResult(
        overall_score=round(overall, 1),
        breakdown=breakdown,
        positive_reasons=positives,
        negative_reasons=negatives,
        risks=risks,
        recommendation=recommendation,
        weights=used_weights,
    )


def _experience_fit(actual: int, required: int | None) -> float:
    if required is None:
        return 0.8 if actual >= 5 else 0.55
    if actual >= required:
        return 1.0
    gap = required - actual
    if gap <= 1:
        return 0.75
    if gap <= 2:
        return 0.5
    return 0.2


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
