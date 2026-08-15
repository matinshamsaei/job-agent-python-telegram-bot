from typing import Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["ok", "error", "skipped"]
OverallStatus = Literal["ok", "degraded"]


class HealthChecks(BaseModel):
    api: CheckStatus = "ok"
    database: CheckStatus
    redis: CheckStatus


class HealthResponse(BaseModel):
    status: OverallStatus
    service: str
    version: str
    environment: str
    checks: HealthChecks
    errors: dict[str, str] = Field(default_factory=dict)
