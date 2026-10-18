from pydantic import BaseModel, Field, field_validator
from typing import Optional

class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=20000)
    required_skills: list[str] = Field(default_factory=list, max_length=100)
    preferred_skills: list[str] = Field(default_factory=list, max_length=100)
    min_years: float = Field(default=0, ge=0, le=60)
    domain_keywords: list[str] = Field(default_factory=list, max_length=100)
    education_keywords: list[str] = Field(default_factory=list, max_length=100)
    @field_validator("title")
    @classmethod
    def clean_title(cls, v): return v.strip()
