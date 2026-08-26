from pydantic import BaseModel, Field


class CoverLetterOutput(BaseModel):
    subject: str
    cover_letter: str
    key_points_used: list[str] = Field(default_factory=list)
    resume_variant: str
    warnings: list[str] = Field(default_factory=list)
