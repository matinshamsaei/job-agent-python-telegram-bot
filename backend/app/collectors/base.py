from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from app.core.enums import CollectionStatus
from app.models import CompanyJobSource, TargetCompany


class RawJob(BaseModel):
    source: str
    external_id: str
    title: str
    url: str
    location: str | None = None
    description: str = ""
    description_html: str = ""
    employment_type: str | None = None
    posted_at: datetime | None = None
    salary_text: str | None = None
    extra: dict = Field(default_factory=dict)


@dataclass(frozen=True)
class CollectorTarget:
    """Everything an adapter needs to read one feed.

    Deliberately plain data rather than an ORM row so adapters stay testable
    and a company can own several differently-configured sources.
    """

    company_slug: str
    company_name: str
    ats_type: str
    board_token: str | None = None
    feed_url: str | None = None
    job_url_pattern: str | None = None
    careers_url: str | None = None
    label: str = "primary"
    extra: dict = dataclass_field(default_factory=dict)


def target_from(company: TargetCompany, source: CompanyJobSource) -> CollectorTarget:
    return CollectorTarget(
        company_slug=company.slug,
        company_name=company.name,
        ats_type=source.ats_type,
        board_token=source.board_token,
        feed_url=source.feed_url,
        job_url_pattern=source.job_url_pattern,
        careers_url=company.careers_url,
        label=source.label,
        extra=dict(source.extra or {}),
    )


@dataclass
class CollectionOutcome:
    """Result of one collection attempt, always with an explaining status."""

    status: CollectionStatus
    jobs: list[RawJob] = dataclass_field(default_factory=list)
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {CollectionStatus.COLLECTED, CollectionStatus.NO_JOBS}


class MissingTokenError(Exception):
    """Raised when a source is configured for an ATS but has no usable token."""


class JobCollector(Protocol):
    name: str
    ats_type: str
    strategy: str

    async def collect(self, target: CollectorTarget) -> list[RawJob]:
        ...

    async def enrich(self, target: CollectorTarget, raw: RawJob) -> RawJob:
        ...
