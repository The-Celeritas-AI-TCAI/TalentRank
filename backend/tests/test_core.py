import io, pytest, pymupdf, docx
from openpyxl import load_workbook
from pydantic import ValidationError
from app.scoring import *
from app.extraction import extract, redact_protected
from app.fallback import assess_fallback
from app.excel_export import build_workbook, RANK_COLUMNS, safe_text

JOB = {"id": "J1", "title": "Python Backend Engineer", "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
       "min_years": 4, "domain_keywords": ["backend", "api"], "education_keywords": ["B.Tech", "Computer Science"]}
RESUME = """Asha Rao
Gender: Female
Date of Birth: 01/02/1990
Senior Backend Engineer with 6 years of experience building APIs.
Skills: Python, FastAPI, PostgreSQL
Education: B.Tech Computer Science
Projects
Built an invoicing backend API processing 1M requests per day with FastAPI.
"""

def test_weights_normalize():
    n = ScoringConfig(weights={"skills": 70, "experience": 50, "role_domain": 40, "projects": 20, "education": 20}).normalized_weights()
    assert sum(n.values()) == pytest.approx(100) and n["skills"] == pytest.approx(35)

def test_scoring_math_and_band():
    a = AssessmentInput(
        skills=[SkillFinding(skill="A", status="verified", evidence="used A"), SkillFinding(skill="B", status="confirmed_absent")],
        experience=CriterionInput(score=80, evidence=["e"]), role_domain=CriterionInput(score=60, evidence=["e"]),
        projects=CriterionInput(score=100, evidence=["e"]), education=CriterionInput(score=50, evidence=["e"]))
    r = score_assessment(a)
    assert r.match_score == pytest.approx(50*.35 + 80*.25 + 60*.2 + 100*.1 + 50*.1)  # 66.0
    assert r.fit_band == "Moderate Fit"
    assert band_for(85, DEFAULT_BANDS) == "Excellent Fit" and band_for(84.9, DEFAULT_BANDS) == "Strong Fit" and band_for(49.9, DEFAULT_BANDS) == "Low Fit"

def test_missing_section_not_zero():
    a = AssessmentInput(skills=[SkillFinding(skill="A", status="verified", evidence="x")],
                        experience=CriterionInput(score=100, evidence=["e"]), role_domain=CriterionInput(score=100, evidence=["e"]),
                        education=CriterionInput(score=100, evidence=["e"]))  # no projects
    assert score_assessment(a).match_score == 100.0

def test_no_evidence_is_incomplete_not_zero():
    r = score_assessment(AssessmentInput(skills=[SkillFinding(skill="A", status="unverified")]))
    assert r.status == "incomplete" and r.match_score is None and r.fit_band is None

def test_unverified_vs_confirmed_absent():
    a = AssessmentInput(skills=[SkillFinding(skill="A", status="unverified"), SkillFinding(skill="B", status="confirmed_absent")],
                        experience=CriterionInput(score=90, evidence=["e"]), role_domain=CriterionInput(score=90, evidence=["e"]))
    r = score_assessment(a)
    assert r.unverified_skills == ["A"] and r.confirmed_absent_skills == ["B"]

def test_verified_skill_requires_evidence():
    with pytest.raises(ValidationError):
        SkillFinding(skill="A", status="verified")

def test_invalid_ai_output_rejected():
    with pytest.raises(ValidationError):
        CriterionInput(score=140)

def test_ranking_ties_and_incomplete():
    mk = lambda s, st="scored": ScoreResult(status=st, match_score=s, fit_band="x", evidence_coverage=100, criterion_scores={}, weights_used={}, verified_skills=[], unverified_skills=[], confirmed_absent_skills=[])
    rk = rank([("a", mk(90)), ("b", mk(90)), ("c", mk(70)), ("d", mk(None, "incomplete"))])
    assert rk == {"d": None, "a": 1, "b": 1, "c": 3}

def _files(tmp_path):
    t = tmp_path / "ok.txt"; t.write_text(RESUME)
    d = docx.Document(); [d.add_paragraph(l) for l in RESUME.splitlines()]; d.save(tmp_path / "ok.docx")
    p = pymupdf.open(); pg = p.new_page(); pg.insert_text((50, 50), "Skills: Python FastAPI PostgreSQL. Backend engineer with 6 years of experience in APIs and databases."); p.save(tmp_path / "ok.pdf")
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf at all")
    (tmp_path / "empty.txt").write_text("")
    (tmp_path / "x.exe").write_bytes(b"MZ")
    return tmp_path

def test_extraction_and_failure_isolation(tmp_path):
    _files(tmp_path)
    res = {n: extract(tmp_path / n) for n in ["ok.txt", "ok.docx", "ok.pdf", "bad.pdf", "empty.txt", "x.exe"]}
    assert [res[n].ok for n in res] == [True, True, True, False, False, False]
    assert all(res[n].error for n in ["bad.pdf", "empty.txt", "x.exe"])  # reasons surfaced, none silently skipped
    assert extract(tmp_path / "missing.pdf").ok is False                  # never raises

def test_protected_attributes_redacted_and_not_scored():
    red = redact_protected(RESUME)
    assert "Female" not in red and "01/02/1990" not in red
    base = assess_fallback([RESUME], JOB)
    swapped = assess_fallback([RESUME.replace("Female", "Male").replace("01/02/1990", "05/06/1960")], JOB)
    assert score_assessment(base) == score_assessment(swapped)

def test_fallback_pipeline_evidence():
    a = assess_fallback([RESUME], JOB)
    r = score_assessment(a)
    assert r.verified_skills == ["Python", "FastAPI", "PostgreSQL"] and r.unverified_skills == ["Docker"]
    assert r.confirmed_absent_skills == [] and r.status == "scored"
    assert next(f for f in a.skills if f.skill == "Python").evidence

def _cand(i, name, status, score=None, **kw):
    return dict(id=i, name=name, status=status, match_score=score, fit_band="Strong Fit" if score else None,
                criterion_scores={"skills": 80, "experience": 70, "role_domain": 60, "projects": 50, "education": 40},
                filename=f"{i}.pdf", **kw)

def test_excel_export(tmp_path):
    cands = [
        _cand("a", "Zed", "scored", 91.5, verified_skills=["Python"],
              criterion_evidence={"_profile":{"email":"zed@example.com","score_breakdown":{"Role-Specific Experience (20)":18},
                "demonstrated_skills":["Python"],"rationale":"Python evidenced in work history.","red_flags":[],"mandatory_check":[{"requirement":"Python","status":"Demonstrated"}]}}),
        _cand("b", "=HYPERLINK(\"http://evil\")", "scored", 55.0, evidence_summary="+cmd|' /C calc'!A0"),
        _cand("c", "Fail", "failed", error="Password protected PDF"), _cand("d", "Inc", "incomplete")
    ]
    cands[2]["criterion_scores"] = {}
    ranks = rank([(c["id"], ScoreResult(status=c["status"], match_score=c["match_score"], fit_band="x", evidence_coverage=1, criterion_scores={}, weights_used={}, verified_skills=[], unverified_skills=[], confirmed_absent_skills=[])) for c in cands])
    wb = load_workbook(io.BytesIO(build_workbook({"id": "J1", "title": "Eng", "description":"Python role"}, cands, ranks)))
    assert wb.sheetnames == ["Candidate Screening", "Summary", "Rubric"]
    ws = wb["Candidate Screening"]
    hdr = next(r for r in range(1, 12) if ws.cell(r, 1).value == "Rank")
    assert ws.cell(hdr,2).value == "Candidate"
    assert ws.freeze_panes and ws.auto_filter.ref
    assert ws.cell(hdr + 1, 20).value == 91.5 and isinstance(ws.cell(hdr + 1, 20).value, float)
    assert ws.cell(hdr + 2, 2).value.startswith("'=")
    assert ws.cell(hdr + 3, 1).value is None and "extraction failure" in str(ws.cell(hdr + 3, 22).value).lower()
    assert ws.cell(hdr + 3, 20).value is None
    assert wb["Summary"]["A10"].value == "Fit Band"
    assert wb["Rubric"]["A3"].value == "Component"
    for row in ws.iter_rows():
        for c in row:
            assert not (c.data_type == "f"), "no live formulas allowed"

def test_safe_text():
    assert safe_text("=1+1") == "'=1+1" and safe_text("@SUM(A1)") == "'@SUM(A1)" and safe_text("Normal") == "Normal" and safe_text(5) == 5
