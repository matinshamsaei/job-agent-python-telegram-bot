from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from app.models import TargetCompany


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


class JobCollector(Protocol):
    name: str

    async def collect(self, company: TargetCompany) -> list[RawJob]:
        ...

    async def enrich(self, company: TargetCompany, raw: RawJob) -> RawJob:
        ...
