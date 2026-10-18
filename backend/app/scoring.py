"""Deterministic scoring engine. AI output (validated by Pydantic) feeds criterion
inputs; all arithmetic (weights, overall score, bands, coverage) is done here."""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator

CRITERIA = ["skills", "experience", "role_domain", "projects", "education"]
DEFAULT_WEIGHTS = {"skills": 35, "experience": 25, "role_domain": 20, "projects": 10, "education": 10}
DEFAULT_BANDS = [(85, "Excellent Fit"), (70, "Strong Fit"), (50, "Moderate Fit"), (0, "Low Fit")]


class SkillStatus(str, Enum):
    VERIFIED = "verified"            # evidence found in resume
    UNVERIFIED = "unverified"        # resume silent: NOT proof the candidate lacks it
    CONFIRMED_ABSENT = "confirmed_absent"  # resume explicitly indicates lack


class SkillFinding(BaseModel):
    skill: str
    status: SkillStatus
    evidence: Optional[str] = None
    page: Optional[int] = None

    @model_validator(mode="after")
    def verified_needs_evidence(self):
        if self.status == SkillStatus.VERIFIED and not (self.evidence and self.evidence.strip()):
            raise ValueError("verified skill requires an evidence snippet (no fabrication)")
        return self


class CriterionInput(BaseModel):
    """score is None when the resume gave no basis for assessing this criterion."""
    score: Optional[float] = Field(default=None, ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class AssessmentInput(BaseModel):
    skills: list[SkillFinding] = Field(default_factory=list)
    experience: CriterionInput = CriterionInput()
    role_domain: CriterionInput = CriterionInput()
    projects: CriterionInput = CriterionInput()
    education: CriterionInput = CriterionInput()
    relevant_years: Optional[float] = None


class ScoringConfig(BaseModel):
    weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    bands: list[tuple[float, str]] = Field(default_factory=lambda: list(DEFAULT_BANDS))
    min_coverage_for_ranking: float = 0.4  # below this the assessment is "incomplete", not low

    def normalized_weights(self) -> dict[str, float]:
        w = {k: max(0.0, float(self.weights.get(k, 0))) for k in CRITERIA}
        total = sum(w.values())
        if total <= 0:
            raise ValueError("At least one weight must be positive")
        return {k: v / total * 100 for k, v in w.items()}


class ScoreResult(BaseModel):
    status: str                      # "scored" | "incomplete"
    match_score: Optional[float]
    fit_band: Optional[str]
    evidence_coverage: float         # 0-100, separate from fit
    criterion_scores: dict[str, Optional[float]]
    weights_used: dict[str, float]
    verified_skills: list[str]
    unverified_skills: list[str]
    confirmed_absent_skills: list[str]


def skills_score(findings: list[SkillFinding]) -> Optional[float]:
    """Verified/total required. Unverified skills earn no credit but are reported
    as 'unverified', never as 'confirmed absent', and they lower coverage."""
    if not findings:
        return None
    v = sum(f.status == SkillStatus.VERIFIED for f in findings)
    return round(v / len(findings) * 100, 2)


def skills_coverage(findings: list[SkillFinding]) -> float:
    if not findings:
        return 0.0
    known = sum(f.status != SkillStatus.UNVERIFIED for f in findings)
    return known / len(findings)


def band_for(score: float, bands) -> str:
    for threshold, name in sorted(bands, key=lambda b: -b[0]):
        if score >= threshold:
            return name
    return sorted(bands, key=lambda b: b[0])[0][1]


def score_assessment(a: AssessmentInput, cfg: ScoringConfig | None = None) -> ScoreResult:
    cfg = cfg or ScoringConfig()
    w = cfg.normalized_weights()
    crit: dict[str, Optional[float]] = {"skills": skills_score(a.skills)}
    coverage_parts = {"skills": skills_coverage(a.skills)}
    for k in ("experience", "role_domain", "projects", "education"):
        c: CriterionInput = getattr(a, k)
        crit[k] = None if c.score is None else round(c.score, 2)
        coverage_parts[k] = 1.0 if (c.score is not None and c.evidence) else (0.5 if c.score is not None else 0.0)

    coverage = sum(w[k] * coverage_parts[k] for k in CRITERIA)  # 0-100 since w sums to 100
    scored = {k: v for k, v in crit.items() if v is not None}
    verified = [f.skill for f in a.skills if f.status == SkillStatus.VERIFIED]
    unver = [f.skill for f in a.skills if f.status == SkillStatus.UNVERIFIED]
    absent = [f.skill for f in a.skills if f.status == SkillStatus.CONFIRMED_ABSENT]
    base = dict(evidence_coverage=round(coverage, 1), criterion_scores=crit, weights_used=w,
                verified_skills=verified, unverified_skills=unver, confirmed_absent_skills=absent)

    if not scored or coverage < cfg.min_coverage_for_ranking * 100:
        # Insufficient evidence: flag as incomplete; never convert to a low score.
        return ScoreResult(status="incomplete", match_score=None, fit_band=None, **base)

    # Re-normalise over criteria that actually have a score so a missing section
    # (e.g. no projects listed) is not silently treated as zero.
    wsum = sum(w[k] for k in scored)
    overall = round(sum(scored[k] * w[k] for k in scored) / wsum, 2)
    return ScoreResult(status="scored", match_score=overall, fit_band=band_for(overall, cfg.bands), **base)


def rank(results: list[tuple[str, ScoreResult]]) -> dict[str, Optional[int]]:
    """Dense-free competition ranking (ties share a rank). Incomplete -> None."""
    valid = sorted([(cid, r.match_score) for cid, r in results if r.status == "scored"], key=lambda t: -t[1])
    out: dict[str, Optional[int]] = {cid: None for cid, r in results if r.status != "scored"}
    prev, pos = None, 0
    for i, (cid, s) in enumerate(valid, 1):
        if s != prev:
            pos, prev = i, s
        out[cid] = pos
    return out
