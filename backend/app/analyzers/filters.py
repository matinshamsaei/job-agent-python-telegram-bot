import re
from dataclasses import dataclass

from app.analyzers.location import parse_location
from app.core.enums import EmploymentType, Seniority, VisaStatus

ENGINEERING_TITLE = re.compile(
    r"\b(software|engineer|developer|frontend|front-end|backend|back-end|"
    r"full[\s-]?stack|typescript|javascript|react|node)\b",
    re.I,
)
BLOCKED_TITLE = re.compile(
    r"\b(intern|internship|junior|graduate|working student|werkstudent|"
    r"apprentice|driver|warehouse|accountant|counsel|lawyer|sales executive|"
    r"account executive|recruiter|talent acquisition|trainee|accelerator program|"
    r"accelerator programm|bootcamp)\b",
    re.I,
)
SENIOR_OK = re.compile(r"\b(senior|staff|principal|lead|head of)\b", re.I)
FRONTEND_TITLE = re.compile(r"\b(frontend|front-end|front end|ui engineer|web engineer|web developer)\b", re.I)
FULLSTACK_TITLE = re.compile(r"\bfull[\s-]?stack\b", re.I)
PRODUCT_TITLE = re.compile(r"\b(product engineer|product developer|web|ui)\b", re.I)
SOFTWARE_TITLE = re.compile(
    r"\b(software|developer|typescript|javascript|react|vue|angular|node(\.?js)?)\b",
    re.I,
)
# "Senior Engineer", "Principal Engineer", "Engineer II - Payments" with nothing narrowing it.
GENERIC_ENGINEER_TITLE = re.compile(
    r"^\W*(?:(?:senior|sr\.?|staff|principal|lead)\s+)?engineer\b(?:\s+(?:i{1,3}|iv|[1-4]))?\s*(?:$|[-–,|(:])",
    re.I,
)
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
# "Engineer" titles that are not product software development.
NON_DEV_ENGINEER = re.compile(
    r"\b(implementation|gtm|go[- ]to[- ]market|forward[\s-]deployed|solutions? engineer|analytics engineer|"
    r"it|systems engineer|value engineer|av engineer|identity engineer|technical office|"
    r"deployment engineer|field engineer|customer engineer|developer relations|devrel|cloud engineer|"
    r"automation engineer|hardware|electrical|mechanical|civil|process engineer|manufacturing|"
    r"integration engineer|technical account|validation engineer|verification engineer|rf|optical|"
    r"silicon|asic|fpga|robotics|aosp|kernel|compiler|database engineer|quant|research engineer|"
    r"prompt engineer|quality engineer|test automation|sdet|mobile|graphics)\b",
    re.I,
)
# Vendor-platform roles (configuring someone else's product) and management tracks.
ALWAYS_BLOCK = re.compile(
    r"\b(salesforce|servicenow|netsuite|okta|dynamics 365|"
    r"director|vice president|vp|chief|cto|manager)\b",
    re.I,
)
TARGET_STACK = re.compile(
    r"\b(react|next\.?js|vue|nuxt|typescript|javascript|frontend|front-end|"
    r"full[\s-]?stack|node\.?js|nodejs|nestjs|express)\b",
    re.I,
)
OTHER_STACK = re.compile(
    r"(?<![\w.#+])(java|kotlin|scala|golang|\.net|c#|php|ruby|rails|c\+\+|rust|elixir)(?![\w#+])",
    re.I,
)
TITLE_SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead)\b", re.I)
TITLE_LEVEL = re.compile(r"\b(?:engineer|developer)\s+(i{1,3}|iv|[1-4])\b", re.I)
WORLDWIDE = re.compile(r"\b(anywhere|worldwide|global|emea|europe|eu)\b", re.I)


@dataclass(frozen=True)
class FilterResult:
    rejected: bool
    reason: str | None = None


def looks_like_engineering_role(title: str) -> bool:
    if BLOCKED_TITLE.search(title) and not SENIOR_OK.search(title):
        return False
    return bool(ENGINEERING_TITLE.search(title))


def _explicit_target_title(title: str) -> bool:
    return bool(FRONTEND_TITLE.search(title) or FULLSTACK_TITLE.search(title))


def looks_like_target_role(title: str) -> bool:
    """Frontend, full-stack, or generic software engineer — not backend/specialty."""
    if not looks_like_engineering_role(title):
        return False
    if ALWAYS_BLOCK.search(title):
        return False
    explicit = _explicit_target_title(title)
    if not explicit and (SPECIALTY_BLOCK.search(title) or NON_DEV_ENGINEER.search(title)):
        return False
    if BACKEND_ONLY_TITLE.search(title) and not explicit:
        return False
    if OTHER_STACK.search(title) and not TARGET_STACK.search(title):
        return False
    return bool(
        explicit
        or PRODUCT_TITLE.search(title)
        or SOFTWARE_TITLE.search(title)
        or GENERIC_ENGINEER_TITLE.search(title.strip())
    )


def target_role_rank(title: str) -> int:
    """Lower is more relevant: role family first, then seniority."""
    if FRONTEND_TITLE.search(title):
        family = 0
    elif FULLSTACK_TITLE.search(title):
        family = 1
    elif PRODUCT_TITLE.search(title):
        family = 2
    elif SOFTWARE_TITLE.search(title):
        family = 3
    else:
        family = 4
    seniority = _seniority_from_title(title)
    if seniority in {Seniority.SENIOR.value, Seniority.STAFF.value, Seniority.LEAD.value}:
        level = 0
    elif seniority in {Seniority.PRINCIPAL.value, Seniority.UNKNOWN.value}:
        level = 1
    else:
        level = 2
    return family * 3 + level


def incompatible_stack(title: str, description: str) -> bool:
    blob = f"{title}\n{description}"
    if TARGET_STACK.search(blob):
        return False
    return bool(OTHER_STACK.search(blob))


def location_is_reachable(
    *,
    country: str | None,
    location: str | None,
    remote_type: str,
    target_countries: list[str],
) -> bool:
    """False when the job is tied to a country the candidate cannot relocate to.

    Countries named in the location string win over `country`, which may only be
    the company's headquarters fallback. Any target country among several
    listed locations is enough.
    """
    named = parse_location(location).countries
    if named:
        if any(code in target_countries for code in named):
            return True
        return remote_type == "remote" and bool(WORLDWIDE.search(location or ""))
    if not country or country in target_countries:
        return True
    return remote_type == "remote"


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
    location: str | None = None,
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
    if role_category == "backend" and (BACKEND_ONLY_TITLE.search(title) or not TARGET_STACK.search(blob)):
        return FilterResult(True, "too_backend")
    if incompatible_stack(title, description):
        return FilterResult(True, "wrong_stack")
    if employment_type == EmploymentType.INTERNSHIP.value:
        return FilterResult(True, "incompatible_seniority")
    if visa_status == VisaStatus.NO.value:
        return FilterResult(True, "explicit_no_sponsorship")
    if not location_is_reachable(
        country=country,
        location=location,
        remote_type=remote_type,
        target_countries=target_countries,
    ):
        return FilterResult(True, "impossible_location")
    lowered = blob.lower()
    if re.search(r"\blocal candidates only\b", lowered) and remote_type != "remote":
        return FilterResult(True, "explicit_local_only")
    return FilterResult(False, None)


def infer_seniority(title: str, description: str, years_required: int | None = None) -> str:
    from_title = _seniority_from_title(title)
    if from_title != Seniority.UNKNOWN.value:
        return from_title
    return _seniority_from_body(description, years_required)


def _seniority_from_title(title: str) -> str:
    lowered = title.lower()
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
    if TITLE_SENIOR.search(lowered):
        return Seniority.SENIOR.value
    if re.search(r"\bmid[\s-]?level\b", lowered):
        return Seniority.MID.value
    level = TITLE_LEVEL.search(lowered)
    if level:
        token = level.group(1)
        if token in {"i", "1"}:
            return Seniority.JUNIOR.value
        if token in {"ii", "2"}:
            return Seniority.MID.value
        return Seniority.SENIOR.value
    return Seniority.UNKNOWN.value


def _seniority_from_body(description: str, years_required: int | None) -> str:
    """Body text mentions "lead", "staff" and "junior" in passing, so only trust strong signals."""
    if years_required is not None:
        if years_required >= 5:
            return Seniority.SENIOR.value
        if years_required >= 3:
            return Seniority.MID.value
        return Seniority.JUNIOR.value
    if re.search(
        r"\b(senior|sr\.?)\s+(software|frontend|front-end|full[\s-]?stack|web|product)?\s*(engineer|developer)\b",
        description,
        re.I,
    ):
        return Seniority.SENIOR.value
    if re.search(r"\bmid[\s-]?level\b", description, re.I):
        return Seniority.MID.value
    return Seniority.UNKNOWN.value
