from typing import Literal

from pydantic import BaseModel, Field


class RequirementItem(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=240)
    required: bool = True
    retrieval_terms: list[str] = Field(default_factory=list, max_length=8)
    evidence_sources: list[str] = Field(default_factory=list, max_length=6)


class SearchStrategy(BaseModel):
    strategy_type: str = Field(min_length=1, max_length=60)
    terms: list[str] = Field(min_length=1, max_length=3)
    rationale: str = Field(min_length=1, max_length=240)
    hypothesis: str = Field(default="", max_length=400)
    expected_signals: list[str] = Field(default_factory=list, max_length=6)
    verifies: list[str] = Field(default_factory=list, max_length=8)


class ComponentRole(BaseModel):
    role: str = Field(min_length=1, max_length=60)
    purpose: str = Field(min_length=1, max_length=240)
    search_terms: list[str] = Field(min_length=1, max_length=4)
    compatibility_interfaces: list[str] = Field(default_factory=list, max_length=8)
    fulfills: list[str] = Field(default_factory=list, max_length=8)


class SearchIntent(BaseModel):
    goal: str
    requirements: list[RequirementItem] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list, max_length=8)
    search_strategies: list[SearchStrategy] = Field(default_factory=list, max_length=6)
    component_roles: list[ComponentRole] = Field(default_factory=list, max_length=4)
    language: str | None = None
    minimum_stars: int = Field(default=0, ge=0)
    licenses: list[str] = Field(default_factory=list)
    active_within_days: int | None = Field(default=None, ge=1)
    clarification_questions: list[str] = Field(default_factory=list, max_length=1)


class SearchQuery(BaseModel):
    query: str
    keywords: list[str]
    fingerprint: str
    strategy_type: str = "rules_fallback"
    rationale: str = "Deterministic fallback query"
    hypothesis: str = ""
    expected_signals: list[str] = Field(default_factory=list)
    verifies: list[str] = Field(default_factory=list)
    component_role: str | None = None


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
    source_commit_sha: str | None = None
    implementation_status: Literal[
        "implemented", "documented_only", "uncertain", "contradicted"
    ] = "uncertain"
    implementation_evidence: str | None = None
    implementation_source_path: str | None = None
    implementation_source_commit_sha: str | None = None


class CorePurposeMatch(BaseModel):
    status: Literal["matched", "mismatched", "unknown"] = "unknown"
    evidence: str | None = None
    source_path: str | None = None
    source_commit_sha: str | None = None


class RepositoryAssessment(BaseModel):
    summary: str
    criteria: list[CriterionMatch]
    core_purpose: CorePurposeMatch = Field(default_factory=CorePurposeMatch)
