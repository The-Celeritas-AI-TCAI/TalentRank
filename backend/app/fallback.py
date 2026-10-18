"""Deterministic fallback assessor (no AI). Evidence-based only; never invents data."""
from __future__ import annotations
import re
from .scoring import AssessmentInput, CriterionInput, SkillFinding, SkillStatus
from .extraction import redact_protected

_NEG = re.compile(r"\b(no experience (with|in)|not familiar with|never used|lack of)\b", re.I)


def _snippet(text: str, idx: int, n: int = 90) -> str:
    return " ".join(text[max(0, idx - n): idx + n].split())


def assess_fallback(pages: list[str], job: dict) -> AssessmentInput:
    """job: {required_skills, preferred_skills, title, min_years, domain_keywords, education_keywords}"""
    pages = [redact_protected(p) for p in pages]
    full = "\n".join(pages)
    low = full.lower()
    findings: list[SkillFinding] = []
    for skill in job.get("required_skills", []):
        m = re.search(r"(?<![\w+#.])" + re.escape(skill.lower()) + r"(?![\w+#])", low)
        if m:
            page = next((i + 1 for i, p in enumerate(pages) if skill.lower() in p.lower()), None)
            findings.append(SkillFinding(skill=skill, status=SkillStatus.VERIFIED, evidence=_snippet(full, m.start()), page=page))
        else:
            neg = re.search(_NEG.pattern + r".{0,40}" + re.escape(skill.lower()), low, re.I)
            findings.append(SkillFinding(skill=skill,
                            status=SkillStatus.CONFIRMED_ABSENT if neg else SkillStatus.UNVERIFIED))

    # explicit "N years" statements only; no inference from dates
    yrs = [float(x) for x in re.findall(r"(\d{1,2}(?:\.\d)?)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:\w+\s+){0,3}experience", low)]
    years = max(yrs) if yrs else None
    need = job.get("min_years") or 0
    exp = CriterionInput()
    if years is not None:
        exp = CriterionInput(score=min(100.0, years / need * 100) if need else 100.0,
                             evidence=[f"Resume states {years:g} years of experience"],
                             gaps=[] if not need or years >= need else [f"Needs {need}+ years"])

    title_words = {w for w in re.findall(r"[a-z]{3,}", job.get("title", "").lower())}
    dom = [k for k in job.get("domain_keywords", []) if k.lower() in low]
    domain_pool = list(title_words) + [k.lower() for k in job.get("domain_keywords", [])]
    role = CriterionInput()
    if domain_pool:
        hits = [w for w in domain_pool if w in low]
        role = CriterionInput(score=round(len(hits) / len(domain_pool) * 100, 1),
                              evidence=[f"Mentions: {', '.join(sorted(set(hits))[:6])}"] if hits else [],
                              gaps=[])
    pm = re.search(r"\n\s*(projects?|key projects)\s*\n(.{40,})", full, re.I | re.S)
    proj = CriterionInput(score=70.0, evidence=[" ".join(pm.group(2).split())[:160]]) if pm else CriterionInput()
    ed_kw = job.get("education_keywords", [])
    eh = [k for k in ed_kw if k.lower() in low]
    edu = CriterionInput(score=round(len(eh) / len(ed_kw) * 100, 1), evidence=[f"Found: {', '.join(eh)}"] if eh else []) if ed_kw else CriterionInput()
    return AssessmentInput(skills=findings, experience=exp, role_domain=role, projects=proj, education=edu, relevant_years=years)
