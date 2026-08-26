from enum import StrEnum


class AtsType(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    PERSONIO_XML = "personio_xml"
    CAREER_PAGE = "career_page"
    UNKNOWN = "unknown"


class VisaStatus(StrEnum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    UNKNOWN = "unknown"
    UNLIKELY = "unlikely"
    NO = "no"


class RelocationStatus(StrEnum):
    SUPPORTED = "supported"
    UNKNOWN = "unknown"
    UNLIKELY = "unlikely"
    NO = "no"


class RemoteType(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    UNKNOWN = "unknown"


class Seniority(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    LEAD = "lead"
    UNKNOWN = "unknown"


class RoleCategory(StrEnum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    FULL_STACK = "full_stack"
    MOBILE = "mobile"
    DATA = "data"
    DEVOPS = "devops"
    OTHER = "other"
    UNKNOWN = "unknown"


class Recommendation(StrEnum):
    APPLY = "apply"
    REVIEW = "review"
    SKIP = "skip"


class EvidenceType(StrEnum):
    OFFICIAL = "official"
    GOVERNMENT = "government"
    JOB_POSTING = "job_posting"
    RECRUITER = "recruiter"
    EMPLOYEE = "employee"
    COMMUNITY = "community"
    THIRD_PARTY = "third_party"


class EvidenceClaim(StrEnum):
    SPONSORSHIP_AVAILABLE = "sponsorship_available"
    NO_SPONSORSHIP = "no_sponsorship"
    RELOCATION_AVAILABLE = "relocation_available"
    NO_RELOCATION = "no_relocation"
    INTERNATIONAL_HIRING = "international_hiring"
    LOCAL_ONLY = "local_only"
    RECOGNIZED_SPONSOR = "recognized_sponsor"


class ResumeVariant(StrEnum):
    SENIOR_SOFTWARE_ENGINEER = "SENIOR_SOFTWARE_ENGINEER"
    SENIOR_FRONTEND_ENGINEER = "SENIOR_FRONTEND_ENGINEER"
    FULL_STACK_ENGINEER = "FULL_STACK_ENGINEER"


class DecisionType(StrEnum):
    APPROVE = "approve"
    SKIP = "skip"
    REJECT = "reject"
    APPLY_INTENDED = "apply_intended"


class RejectionReason(StrEnum):
    NO_SPONSORSHIP = "no_sponsorship"
    LOW_SALARY = "low_salary"
    WRONG_COUNTRY = "wrong_country"
    WRONG_SENIORITY = "wrong_seniority"
    WRONG_STACK = "wrong_stack"
    TOO_FRONTEND = "too_frontend"
    TOO_BACKEND = "too_backend"
    REMOTE_RESTRICTION = "remote_restriction"
    COMPANY_NOT_INTERESTING = "company_not_interesting"
    JOB_MISMATCH = "job_mismatch"
    OTHER = "other"


class ApplicationStatus(StrEnum):
    INTENDED = "intended"
    APPLIED = "applied"
    RECRUITER_RESPONSE = "recruiter_response"
    PHONE_SCREEN = "phone_screen"
    TECHNICAL_INTERVIEW = "technical_interview"
    ONSITE = "onsite"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    NO_RESPONSE = "no_response"


class NotificationChannel(StrEnum):
    TELEGRAM = "telegram"


class NotificationStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class CoverLetterStatus(StrEnum):
    DRAFT = "draft"
    EDITED = "edited"
    USED = "used"
    DISCARDED = "discarded"
