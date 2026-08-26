import re
from dataclasses import dataclass

from app.core.enums import EmploymentType, Seniority, VisaStatus

ENGINEERING_TITLE = re.compile(
    r"\b(software|engineer|developer|frontend|front-end|backend|back-end|"
    r"full[\s-]?stack|typescript|javascript|react|node)\b",
    re.I,
)
BLOCKED_TITLE = re.compile(
    r"\b(intern|internship|junior|graduate|working student|werkstudent|"
    r"apprentice|driver|warehouse|accountant|counsel|lawyer|sales executive|"
    r"account executive|recruiter|talent acquisition)\b",
    re.I,
)
SENIOR_OK = re.compile(r"\b(senior|staff|principal|lead|head of)\b", re.I)
FRONTEND_TITLE = re.compile(r"\b(frontend|front-end|front end)\b", re.I)
FULLSTACK_TITLE = re.compile(r"\bfull[\s-]?stack\b", re.I)
BACKEND_ONLY_TITLE = re.compile(r"\b(backend|back-end|back end|server[- ]side)\b", re.I)
SPECIALTY_BLOCK = re.compile(
    r"\b(security|infosec|infrastructure|site reliability|\bsre\b|devops|"
    r"platform engineer|data engineer|data scientist|machine learning|"
    r"ml engineer|ai engineer|ai/?ml|presales|pre-sales|solutions engineer|"
    r"sales engineer|android|ios\b|mobile engineer|firmware|embedded|"
    r"qa engineer|quality assurance|test engineer|support engineer|"
    r"network engineer|sysadmin|reliability engineer)\b",
    re.I,
)
TARGET_STACK = re.compile(
    r"\b(react|next\.?js|vue|nuxt|typescript|javascript|frontend|front-end|"
    r"full[\s-]?stack|node\.?js|nodejs|nestjs|express)\b",
    re.I,
)
OTHER_STACK = re.compile(
    r"\b(java|kotlin|scala|golang|\.net|c#|php|ruby|rails|c\+\+)\b",
    re.I,
)


@dataclass(frozen=True)
class FilterResult:
    rejected: bool
    reason: str | None = None


def looks_like_engineering_role(title: str) -> bool:
    if BLOCKED_TITLE.search(title) and not SENIOR_OK.search(title):
        return False
    return bool(ENGINEERING_TITLE.search(title))


def looks_like_target_role(title: str) -> bool:
    """Frontend, full-stack, or generic software engineer — not backend/specialty."""
    if not looks_like_engineering_role(title):
        return False
    if SPECIALTY_BLOCK.search(title):
        return False
    if BACKEND_ONLY_TITLE.search(title) and not (FRONTEND_TITLE.search(title) or FULLSTACK_TITLE.search(title)):
        return False
    if OTHER_STACK.search(title) and not TARGET_STACK.search(title):
        return False
    return True


def target_role_rank(title: str) -> int:
    if FRONTEND_TITLE.search(title):
        return 0
    if FULLSTACK_TITLE.search(title):
        return 1
    return 2


def incompatible_stack(title: str, description: str) -> bool:
    blob = f"{title}\n{description}"
    if TARGET_STACK.search(blob):
        return False
    return bool(OTHER_STACK.search(blob))


def apply_hard_filters(
    *,
    title: str,
    description: str,
    country: str | None,
    target_countries: list[str],
    visa_status: str,
    employment_type: str,
    remote_type: str,
    role_category: str | None = None,
) -> FilterResult:
    blob = f"{title}\n{description}"
    if BLOCKED_TITLE.search(title) and not SENIOR_OK.search(title):
        return FilterResult(True, "incompatible_seniority")
    if not looks_like_target_role(title):
        if not looks_like_engineering_role(title):
            return FilterResult(True, "unrelated_role")
        if BACKEND_ONLY_TITLE.search(title):
            return FilterResult(True, "too_backend")
        return FilterResult(True, "wrong_role")
    if role_category == "backend":
        return FilterResult(True, "too_backend")
    if incompatible_stack(title, description):
        return FilterResult(True, "wrong_stack")
    if employment_type == EmploymentType.INTERNSHIP.value:
        return FilterResult(True, "incompatible_seniority")
    if visa_status == VisaStatus.NO.value:
        return FilterResult(True, "explicit_no_sponsorship")
    if country and country not in target_countries and remote_type != "remote":
        return FilterResult(True, "impossible_location")
    lowered = blob.lower()
    if re.search(r"\blocal candidates only\b", lowered) and remote_type != "remote":
        return FilterResult(True, "explicit_local_only")
    return FilterResult(False, None)


def infer_seniority(title: str, description: str) -> str:
    from_title = _seniority_from_text(title)
    if from_title != Seniority.UNKNOWN.value:
        return from_title
    return _seniority_from_text(description)


def _seniority_from_text(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(intern|internship|working student)\b", lowered):
        return Seniority.INTERN.value
    if re.search(r"\bjunior\b", lowered):
        return Seniority.JUNIOR.value
    if re.search(r"\bprincipal\b", lowered):
        return Seniority.PRINCIPAL.value
    if re.search(r"\bstaff\b", lowered):
        return Seniority.STAFF.value
    if re.search(r"\b(tech lead|team lead|lead)\b", lowered):
        return Seniority.LEAD.value
    if re.search(r"\bsenior\b", lowered):
        return Seniority.SENIOR.value
    if re.search(r"\bmid[\s-]?level\b", lowered):
        return Seniority.MID.value
    return Seniority.UNKNOWN.value
