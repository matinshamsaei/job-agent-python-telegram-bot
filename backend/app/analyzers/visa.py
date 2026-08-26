import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.enums import EvidenceClaim, EvidenceType, RelocationStatus, VisaStatus

NEGATIVE_VISA = [
    r"no visa sponsorship",
    r"not (able|going) to sponsor",
    r"cannot sponsor",
    r"will not sponsor",
    r"does not sponsor",
    r"must (already )?have (the )?right to work",
    r"must be (a )?citizen",
    r"work authorization (already )?required",
    r"applicants must be authorized to work",
    r"without the need for (visa )?sponsorship",
]
NEGATIVE_RELOCATION = [
    r"no relocation",
    r"relocation (is )?not (provided|available|offered)",
    r"local candidates only",
    r"must (already )?reside",
    r"must be (currently )?based in",
]
POSITIVE_VISA = [
    r"visa sponsorship (is )?(available|provided|offered)",
    r"sponsorship available",
    r"we (can |will |do )?sponsor",
    r"visa support",
    r"international applicants (are )?welcome",
]
POSITIVE_RELOCATION = [
    r"relocation (assistance|support|package) (is )?(available|provided|offered)?",
    r"we (help|assist) with relocation",
    r"relocation support",
]
INTERNATIONAL = [
    r"international hiring",
    r"candidates worldwide",
    r"willing to relocate",
]


@dataclass(frozen=True)
class TextVisaSignals:
    visa_status: VisaStatus
    relocation_status: RelocationStatus
    claims: list[EvidenceClaim]
    snippets: list[str]


def classify_text(text: str) -> TextVisaSignals:
    blob = text.lower()
    claims: list[EvidenceClaim] = []
    snippets: list[str] = []

    neg_visa = _first_match(NEGATIVE_VISA, blob)
    pos_visa = _first_match(POSITIVE_VISA, blob)
    neg_rel = _first_match(NEGATIVE_RELOCATION, blob)
    pos_rel = _first_match(POSITIVE_RELOCATION, blob)
    intl = _first_match(INTERNATIONAL, blob)

    if neg_visa:
        claims.append(EvidenceClaim.NO_SPONSORSHIP)
        snippets.append(neg_visa)
        visa = VisaStatus.NO
    elif pos_visa:
        claims.append(EvidenceClaim.SPONSORSHIP_AVAILABLE)
        snippets.append(pos_visa)
        visa = VisaStatus.CONFIRMED
    else:
        visa = VisaStatus.UNKNOWN

    if neg_rel:
        claims.append(EvidenceClaim.NO_RELOCATION)
        snippets.append(neg_rel)
        relocation = RelocationStatus.NO
    elif pos_rel:
        claims.append(EvidenceClaim.RELOCATION_AVAILABLE)
        snippets.append(pos_rel)
        relocation = RelocationStatus.SUPPORTED
    else:
        relocation = RelocationStatus.UNKNOWN

    if intl and EvidenceClaim.NO_SPONSORSHIP not in claims:
        claims.append(EvidenceClaim.INTERNATIONAL_HIRING)
        snippets.append(intl)
        if visa == VisaStatus.UNKNOWN:
            visa = VisaStatus.LIKELY

    if EvidenceClaim.NO_SPONSORSHIP in claims:
        visa = VisaStatus.NO
    if EvidenceClaim.LOCAL_ONLY in claims or EvidenceClaim.NO_RELOCATION in claims:
        if relocation != RelocationStatus.NO:
            relocation = RelocationStatus.UNLIKELY

    return TextVisaSignals(visa, relocation, claims, snippets)


def decayed_confidence(
    confidence: float,
    observed_at: datetime,
    half_life_days: int,
    now: datetime | None = None,
) -> float:
    current = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    age_days = max((current - observed_at).total_seconds() / 86400, 0)
    if half_life_days <= 0:
        return confidence
    return confidence * (0.5 ** (age_days / half_life_days))


EVIDENCE_PRIORITY = {
    EvidenceType.GOVERNMENT: 7,
    EvidenceType.OFFICIAL: 6,
    EvidenceType.JOB_POSTING: 5,
    EvidenceType.RECRUITER: 4,
    EvidenceType.EMPLOYEE: 3,
    EvidenceType.COMMUNITY: 2,
    EvidenceType.THIRD_PARTY: 1,
}


def combine_visa_status(
    posting: TextVisaSignals,
    evidence: list[tuple[str, str, float]],
) -> VisaStatus:
    """evidence tuples: (type, claim, decayed_confidence)."""
    if posting.visa_status == VisaStatus.NO:
        return VisaStatus.NO
    ranked = sorted(
        evidence,
        key=lambda item: (EVIDENCE_PRIORITY.get(EvidenceType(item[0]), 0), item[2]),
        reverse=True,
    )
    for _type, claim, confidence in ranked:
        if confidence < 0.25:
            continue
        if claim == EvidenceClaim.NO_SPONSORSHIP.value:
            return VisaStatus.NO
        if claim == EvidenceClaim.SPONSORSHIP_AVAILABLE.value:
            return VisaStatus.CONFIRMED if confidence >= 0.6 else VisaStatus.LIKELY
        if claim == EvidenceClaim.RECOGNIZED_SPONSOR.value:
            return VisaStatus.LIKELY
        if claim == EvidenceClaim.INTERNATIONAL_HIRING.value and posting.visa_status == VisaStatus.UNKNOWN:
            return VisaStatus.LIKELY
        if claim == EvidenceClaim.LOCAL_ONLY.value:
            return VisaStatus.UNLIKELY
    return posting.visa_status


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0)
    return None
