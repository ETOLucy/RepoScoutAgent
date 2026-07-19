from typing import Literal

from pydantic import BaseModel, Field


class RequirementItem(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=240)
    required: bool = True


class SearchIntent(BaseModel):
    goal: str
    requirements: list[RequirementItem] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list, max_length=8)
    language: str | None = None
    minimum_stars: int = Field(default=0, ge=0)
    licenses: list[str] = Field(default_factory=list)
    active_within_days: int | None = Field(default=None, ge=1)
    clarification_questions: list[str] = Field(default_factory=list, max_length=1)


class SearchQuery(BaseModel):
    query: str
    keywords: list[str]
    fingerprint: str


class SearchPlan(BaseModel):
    queries: list[SearchQuery]
    max_results: int = 20
    max_documents_per_repository: int = 6
    max_repositories_to_analyze: int = 8


class CriterionMatch(BaseModel):
    requirement_id: str
    status: Literal["satisfied", "violated", "unknown"]
    evidence: str | None = None
    source_path: str | None = None


class RepositoryAssessment(BaseModel):
    summary: str
    criteria: list[CriterionMatch]
