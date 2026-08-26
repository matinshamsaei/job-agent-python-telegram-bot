import hashlib
import re

from app.analyzers.location import parse_location
from app.collectors.base import RawJob
from app.core.enums import EmploymentType, RemoteType
from app.models import TargetCompany


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def hash_text(value: str) -> str:
    return hashlib.sha256(normalize_whitespace(value).lower().encode("utf-8")).hexdigest()


def detect_remote_type(location: str | None, description: str) -> str:
    text = f"{location or ''} {description}".lower()
    if "hybrid" in text:
        return RemoteType.HYBRID.value
    if any(token in text for token in ("fully remote", "remote-first", "work from home")):
        return RemoteType.REMOTE.value
    if "remote" in text and "not remote" not in text:
        return RemoteType.REMOTE.value
    if any(token in text for token in ("on-site", "onsite", "in office", "office-based")):
        return RemoteType.ONSITE.value
    return RemoteType.UNKNOWN.value


def detect_employment_type(value: str | None, title: str, description: str = "") -> str:
    """Intern/contract must come from the ATS field or title, not job-body boilerplate."""
    header = f"{value or ''} {title}".lower()
    if re.search(r"\b(intern|internship|working student|werkstudent|apprentice)\b", header):
        if not re.search(r"\b(senior|staff|principal|lead)\b", title, re.I):
            return EmploymentType.INTERNSHIP.value
    if re.search(r"\b(contract|contractor)\b", header):
        return EmploymentType.CONTRACT.value
    if re.search(r"\bpart[\s-]?time\b", header):
        return EmploymentType.PART_TIME.value
    if re.search(r"\b(full[\s-]?time|permanent)\b", header):
        return EmploymentType.FULL_TIME.value
    body = description.lower()
    if re.search(r"\b(full[\s-]?time|permanent)\b", body):
        return EmploymentType.FULL_TIME.value
    if re.search(r"\bpart[\s-]?time\b", body):
        return EmploymentType.PART_TIME.value
    return EmploymentType.UNKNOWN.value


def fingerprint(company_name: str, title: str, location: str | None, description: str) -> str:
    basis = "|".join(
        [
            normalize_whitespace(company_name).lower(),
            normalize_whitespace(title).lower(),
            normalize_whitespace(location or "").lower(),
            hash_text(description),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def normalized_job_fields(company: TargetCompany, raw: RawJob) -> dict:
    parsed = parse_location(raw.location)
    description = normalize_whitespace(raw.description)
    return {
        "company_id": company.id,
        "source": raw.source,
        "external_id": raw.external_id,
        "title": normalize_whitespace(raw.title),
        "location": raw.location,
        "country": parsed.country or company.country,
        "city": parsed.city or company.city,
        "remote_type": detect_remote_type(raw.location, description),
        "employment_type": detect_employment_type(raw.employment_type, raw.title, description),
        "description": description,
        "description_hash": hash_text(description),
        "salary": raw.salary_text,
        "posted_at": raw.posted_at,
        "url": raw.url,
        "fingerprint": fingerprint(company.name, raw.title, raw.location, description),
    }
