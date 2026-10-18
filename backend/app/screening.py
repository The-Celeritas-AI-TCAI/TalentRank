"""Transparent, deterministic resume screening helpers. No protected attributes are scored."""
from __future__ import annotations
import re
from typing import Any
from .extraction import redact_protected

SKILL_TERMS = [
    "Python","SQL","Java","C++","C#","JavaScript","TypeScript","React","Node.js","FastAPI","Flask",
    "Machine Learning","Deep Learning","NLP","LLM","RAG","LangChain","LangGraph","TensorFlow","PyTorch",
    "scikit-learn","Pandas","NumPy","statistics","A/B testing","Power BI","Tableau","Excel","ETL",
    "data modeling","data modelling","data warehousing","Spark","PySpark","Airflow","dbt","Kafka",
    "BigQuery","Dataflow","Pub/Sub","Cloud Composer","GCP","Google Cloud","AWS","Azure","Docker",
    "Kubernetes","Terraform","CI/CD","Git","REST API","API design","PostgreSQL","MySQL","MongoDB",
    "communication","stakeholder management","requirements gathering","Agile","Scrum","testing",
    "unit testing","system design","Linux","Bash","GitHub Actions","Jenkins","Looker","Vertex AI",
    "prompt engineering","embeddings","vector database","feature engineering","model evaluation",
    "data visualization","forecasting","regression","classification","computer vision","MLOps",
]
EDUCATION_TERMS = ["b.tech","b.e.","bachelor","master","m.tech","m.s.","ph.d","degree","diploma","certified","certification"]

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def _matches(text: str, term: str) -> list[re.Match]:
    # Avoid treating short skills as substrings inside unrelated words.
    escaped = re.escape(term.lower())
    return list(re.finditer(r"(?<![\w+#])" + escaped + r"(?![\w+#])", text.lower(), re.I))

def _snippets(text: str, term: str, limit: int = 2) -> list[str]:
    out=[]
    for m in _matches(text, term):
        start=max(0, text.rfind("\n", 0, m.start())+1)
        end=text.find("\n", m.end())
        if end < 0: end=min(len(text),m.end()+150)
        line=" ".join(text[start:end].split())
        if line and line not in out:
            out.append(line[:260])
        if len(out)>=limit: break
    return out

def _section_parts(text: str) -> tuple[str,str,str,str]:
    lines=text.splitlines()
    work=[]; skills=[]; projects=[]; other=[]
    section="other"
    headers={
      "skills":r"^(technical\s+)?skills|^core competencies|^competencies|^technologies|^tools\s*(?:&|and)?\s*technologies",
      "work":r"^experience|^work history|^employment history|^professional experience|^career history|^work experience",
      "projects":r"^projects?|^selected projects|^academic projects|^key projects",
      "other":r"^education|^academic background|^certifications?|^licenses|^summary|^professional summary|^profile|^objective|^awards|^publications|^languages|^interests|^volunteer",
    }
    for line in lines:
        clean=line.strip().strip(":").lower()
        new=None
        for kind,pat in headers.items():
            if re.match(pat,clean,re.I): new=kind; break
        if new:
            section=new
            continue
        if section=="skills": skills.append(line)
        elif section=="work": work.append(line)
        elif section=="projects": projects.append(line)
        else: other.append(line)
    return "\n".join(work), "\n".join(skills), "\n".join(projects), "\n".join(other)

def extract_jd_criteria(role: str, jd: str) -> dict[str, Any]:
    """Extract explicit must-have language and skill terms from the supplied job description."""
    text=jd or ""
    sentences=[s.strip(" \t-•*") for s in re.split(r"[\n.!;]+",text) if s.strip()]
    mandatory_lines=[s for s in sentences if re.search(r"\b(mandatory|must(?:\s+have)?|required|required to|minimum|at least|need to|essential|non[- ]negotiable)\b",s,re.I)]
    preferred_lines=[s for s in sentences if re.search(r"\b(preferred|nice to have|bonus|desirable|plus)\b",s,re.I)]
    terms=[]
    for term in SKILL_TERMS:
        if _matches(text,term):
            terms.append(term)
    # Keep explicitly named skills, not every word from a role title.
    mandatory_text=" ".join(mandatory_lines)
    preferred_text=" ".join(preferred_lines)
    must=[t for t in terms if _matches(mandatory_text,t)]
    preferred=[t for t in terms if _matches(preferred_text,t) and t not in must]
    specific=[t for t in terms if t not in must and t not in preferred]
    # A short JD still needs a useful rubric; use its mentioned skill terms as requirements.
    if not must:
        must=specific[:]
        specific=[]
    # If no recognized skills were present, derive a few safe domain terms from the role/JD.
    if not must:
        stop={"and","the","with","from","this","that","will","have","your","you","for","are","our","role","work","team","years","year","using","able","good","strong","plus","required","must","nice","have"}
        role_words=[w for w in re.findall(r"[A-Za-z][A-Za-z+#.-]{3,}", f"{role} {jd}") if w.lower() not in stop]
        must=list(dict.fromkeys(role_words[:8]))
    # Extract explicit experience threshold only; don't infer from job seniority.
    exp_req=None
    for line in mandatory_lines + sentences:
        m=re.search(r"\b(?:at least|minimum of|minimum|more than|over)?\s*(\d{1,2}(?:\.\d+)?)\+?\s*(?:years?|yrs?)\b",line,re.I)
        if m:
            exp_req=float(m.group(1)); break
    generic=set(["Python","SQL","communication","stakeholder management","Excel","Git","REST API","testing","Agile","Scrum"])
    return {
      "role":role.strip(),"jd":text,"mandatory_lines":mandatory_lines,
      "mandatory_skills":list(dict.fromkeys(must)),
      "role_specific_skills":list(dict.fromkeys(specific)),
      "preferred_skills":list(dict.fromkeys(preferred)),
      "generic_skills":[t for t in must if t in generic],
      "role_skills":[t for t in must if t not in generic],
      "min_years":exp_req,
    }

def _extract_years(text: str) -> float|None:
    vals=[]
    for m in re.finditer(r"\b(\d{1,2}(?:\.\d{1,2})?)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:overall\s+|total\s+|professional\s+)?experience\b",text,re.I):
        try: vals.append(float(m.group(1)))
        except ValueError: pass
    return max(vals) if vals else None

def _contact(text: str) -> dict[str,str]:
    email_match=re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",text,re.I)
    phone_match=re.search(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)",text)
    email=email_match.group(0) if email_match else ""
    phone=re.sub(r"\s+"," ",phone_match.group(0)).strip() if phone_match else ""
    # Location is extracted only from an explicitly labelled field/line.
    loc=""
    m=re.search(r"(?im)^\s*(?:location|based in|address)\s*[:\-]\s*(.+)$",text)
    if m: loc=m.group(1).strip()[:120]
    return {"email":email,"phone":phone,"location":loc}

def _candidate_name(text: str, filename: str) -> str:
    for line in text.splitlines()[:15]:
        line=" ".join(line.strip().split())
        if 1 < len(line.split()) <= 5 and len(line)<70 and not re.search(r"@|https?://|\d{3,}|resume|curriculum vitae|phone|email|linkedin|github",line,re.I):
            if not re.search(r"\b(experience|engineer|developer|analyst|manager|skills|profile|summary|education)\b",line,re.I):
                return line
    from pathlib import Path
    return Path(filename).stem.replace("_"," ").replace("-"," ")[:200] or "Candidate"

def _latest_role(text: str) -> str:
    work,_,_,_= _section_parts(text)
    lines=[re.sub(r"\s+"," ",x.strip()) for x in work.splitlines() if x.strip()]
    for line in lines[:12]:
        if len(line)>5 and len(line)<180 and not re.search(r"@|https?://|^\d{4}\b|^\d{1,2}/\d{4}",line):
            if re.search(r"\b(engineer|developer|analyst|scientist|manager|consultant|architect|specialist|intern|lead|administrator|designer|researcher|officer)\b",line,re.I):
                return line[:180]
    return ""

def _years_for_role(text: str, role: str) -> float|None:
    # Only accept an explicit years statement near the role/domain wording.
    role_terms=[w for w in re.findall(r"[A-Za-z][A-Za-z+#.-]{1,}",role.lower()) if w not in {"engineer","developer","specialist","professional","analyst","scientist","manager"}]
    lines=text.splitlines()
    for i,line in enumerate(lines):
        around=" ".join(lines[max(0,i-1):min(len(lines),i+2)])
        if role_terms and any(t in around.lower() for t in role_terms):
            y=_extract_years(around)
            if y is not None: return y
    return None

def assess_resume(pages: list[str], filename: str, role: str, jd: str) -> dict[str,Any]:
    raw="\n".join(pages)
    clean=redact_protected(raw)
    work,skills_section,projects_section,other=_section_parts(clean)
    criteria=extract_jd_criteria(role,jd)
    contact=_contact(raw)  # contact fields are extracted, never used for scoring
    name=_candidate_name(clean,filename)
    latest=_latest_role(clean)
    total_years=_extract_years(clean)
    role_years=_years_for_role(clean,role)
    all_skill_terms=criteria["mandatory_skills"]+criteria["role_specific_skills"]+criteria["preferred_skills"]
    # Separate work/project evidence from a skills-list-only mention.
    demonstrated=[]; listed=[]; missing=[]; skill_evidence={}
    work_and_projects=work+"\n"+projects_section
    for term in dict.fromkeys(all_skill_terms):
        work_hits=_snippets(work_and_projects,term,2)
        skill_hits=_snippets(skills_section,term,1)
        negative_pattern = re.compile(
            r"\b(?:no experience (?:with|in)|not familiar with|never used|lack of|no hands-on (?:experience|with)|not used)\b.{0,70}" + re.escape(term) +
            r"|" + re.escape(term) + r".{0,50}\b(?:not used|no experience|not familiar|never used|lack of)\b", re.I)
        negative_hits=[snippet for snippet in work_hits if negative_pattern.search(snippet)]
        if negative_hits:
            missing.append(term); skill_evidence[term]={"status":"explicit lack / contradictory evidence — verify","evidence":negative_hits}
        elif work_hits:
            demonstrated.append(term); skill_evidence[term]={"status":"demonstrated in work/project text","evidence":work_hits}
        elif skill_hits or _matches(clean,term):
            listed.append(term); evidence=skill_hits or _snippets(clean,term,1)
            skill_evidence[term]={"status":"listed only / not demonstrated in work history","evidence":evidence}
        else:
            missing.append(term); skill_evidence[term]={"status":"not found in extracted resume text","evidence":[]}
    mandatory=[]
    for line in criteria["mandatory_lines"]:
        # Evaluate requirements that can be checked from extracted evidence; leave all others explicitly for HR verification.
        line_skills=[term for term in criteria["mandatory_skills"] if _matches(line,term)]
        if line_skills:
            demonstrated_line=[t for t in line_skills if skill_evidence.get(t,{}).get("status")=="demonstrated in work/project text"]
            listed_line=[t for t in line_skills if skill_evidence.get(t,{}).get("status","").startswith("listed only")]
            missing_line=[t for t in line_skills if t not in demonstrated_line and t not in listed_line]
            if missing_line: line_status="Not found — verify: "+", ".join(missing_line)
            elif listed_line: line_status="Listed only — verify: "+", ".join(listed_line)
            else: line_status="Evidence found in work/project text: "+", ".join(demonstrated_line)
        elif criteria["min_years"] is not None and re.search(r"\b(?:years?|yrs?)\b",line,re.I):
            if total_years is None: line_status="Unverified — no explicit total-years statement"
            elif total_years>=criteria["min_years"]: line_status=f"Meets stated years ({total_years:g} explicitly stated)"
            else: line_status=f"Below stated minimum ({total_years:g} explicitly stated; {criteria['min_years']:g} requested)"
        else:
            line_status="Manual verification required — compare against resume evidence"
        mandatory.append({"requirement":line[:300],"status":line_status})
    for term in criteria["mandatory_skills"]:
        status=skill_evidence.get(term,{}).get("status","not found")
        if status=="demonstrated in work/project text": label="Demonstrated"
        elif status.startswith("listed only"): label="Listed only — verify"
        else: label="Not found — verify"
        mandatory.append({"requirement":term,"status":label})
    if criteria["min_years"] is not None:
        if total_years is None: label="Unverified — no explicit total-years statement"
        elif total_years>=criteria["min_years"]: label=f"Meets stated years ({total_years:g} explicitly stated)"
        else: label=f"Below stated minimum ({total_years:g} explicitly stated; {criteria['min_years']:g} requested)"
        mandatory.append({"requirement":f"At least {criteria['min_years']:g} years experience","status":label})
    # Score components mirror the reference workbook's transparent 100-point rubric.
    def skill_credit(terms):
        terms=list(dict.fromkeys(terms))
        if not terms: return 0.0
        pts=0
        for term in terms:
            st=skill_evidence.get(term,{}).get("status","")
            pts += 1.0 if st=="demonstrated in work/project text" else (0.4 if st.startswith("listed only") else 0.0)
        return round(100*pts/len(terms),1)
    min_years=criteria["min_years"]
    if role_years is None:
        exp20=0.0
    else:
        exp20=round(min(100,role_years/min_years*100) if min_years else min(100,role_years/5*100),1)
    if total_years is None:
        exp10=0.0
    else:
        exp10=round(min(100,total_years/(min_years or 5)*100),1)
    all_required_terms=list(dict.fromkeys(criteria["mandatory_skills"] + criteria["role_specific_skills"]))
    generic_set={"Python","SQL","communication","stakeholder management","Excel","Git","REST API","testing","Agile","Scrum"}
    generic_terms=[t for t in all_required_terms if t in generic_set]
    role_terms=[t for t in all_required_terms if t not in generic_set]
    # If a JD has no criteria for a rubric category, treat that category as neutral rather than
    # deducting points for requirements the employer did not specify.
    generic25=skill_credit(generic_terms) if generic_terms else 100.0
    role30=skill_credit(role_terms) if role_terms else 100.0
    nice10=skill_credit(criteria["preferred_skills"]) if criteria["preferred_skills"] else 100.0
    # Evidence strength is based on distinct demonstrated skill evidence and an explicit role/history section.
    evidence_parts=(1 if work.strip() else 0)+(1 if skills_section.strip() else 0)+(1 if total_years is not None else 0)+(1 if latest else 0)
    evidence5=round(evidence_parts/4*100,1)
    # Project/responsibility fit uses evidence lines from work/projects that match JD skills and selected role.
    role_tokens=[w.lower() for w in re.findall(r"[A-Za-z]{4,}",role) if w.lower() not in {"engineer","developer","specialist","professional"}]
    role_hits=[t for t in role_tokens if t in clean.lower()]
    responsibility20=round(min(100, (len(set(role_hits))/max(1,len(set(role_tokens))))*100),1) if role_tokens else 0.0
    projects_lines=[]
    for line in projects_section.splitlines():
        if re.search(r"project|built|developed|implemented|designed|deployed|created|led|automated|optimized|optimised",line,re.I) and len(line.strip())>20:
            projects_lines.append(" ".join(line.split())[:260])
    projects10=round(min(100,len(projects_lines)*25),1)
    # Sum weighted points. No missing fact is fabricated; absent evidence gets no points and is flagged.
    breakdown={
      "Role-Specific Experience (20)":round(exp20*.20,2),
      "Overall Relevant Experience (10)":round(exp10*.10,2),
      "Generic Must-Haves (25)":round(generic25*.25,2),
      "Role-Specific Must-Haves (30)":round(role30*.30,2),
      "Nice-to-Have (10)":round(nice10*.10,2),
      "Evidence Quality (5)":round(evidence5*.05,2),
    }
    # The responsibility/project signals inform rationale and red flags, not an extra hidden weight.
    total=round(sum(breakdown.values()),2)
    band="Strong Fit" if total>=80 else "Good Fit" if total>=65 else "Moderate Fit" if total>=50 else "Not a Fit"
    mandatory_missing=[x["requirement"] for x in mandatory if any(k in x["status"].lower() for k in ["not found","unverified","below","listed only","needs review","manual verification"])]
    demonstrated_mand=[t for t in criteria["mandatory_skills"] if skill_evidence.get(t,{}).get("status")=="demonstrated in work/project text"]
    listed_mand=[t for t in criteria["mandatory_skills"] if skill_evidence.get(t,{}).get("status","").startswith("listed only")]
    gaps=[]
    if missing: gaps.append("Not found: "+", ".join(missing))
    if listed: gaps.append("Listed only; practical evidence not found: "+", ".join(listed))
    if total_years is None: gaps.append("Total experience is not explicitly quantified in the resume")
    if role_years is None: gaps.append("Role-specific experience is not explicitly quantified; no years inferred from dates")
    if criteria["min_years"] and (total_years is None or total_years<criteria["min_years"]):
        gaps.append(f"Requested experience threshold: {criteria['min_years']:g}+ years; resume evidence does not verify it")
    red_flags=[]
    if not work.strip(): red_flags.append("No clearly labelled work-experience section was extracted")
    if not latest: red_flags.append("Current/latest role could not be identified confidently")
    if not contact["email"]: red_flags.append("Email not found in extracted text")
    if not contact["phone"]: red_flags.append("Phone not found in extracted text")
    if listed_mand: red_flags.append("Mandatory skills appear only in a skills/list section: "+", ".join(listed_mand))
    missing_mand=[t for t in criteria["mandatory_skills"] if t in missing]
    if missing_mand: red_flags.append("Mandatory skills not evidenced in extracted resume text: "+", ".join(missing_mand))
    negative_mand=[t for t in criteria["mandatory_skills"] if "explicit lack" in skill_evidence.get(t,{}).get("status","")]
    if negative_mand: red_flags.append("Resume contains a possible explicit lack/contradiction for: "+", ".join(negative_mand))
    if criteria["min_years"] and (total_years is None or total_years<criteria["min_years"]): red_flags.append("Mandatory experience threshold is unverified or below the stated minimum")
    must_have_gaps=list(dict.fromkeys(mandatory_missing))
    if criteria["min_years"] is not None and total_years is None:
        must_have_gaps.append("Total experience threshold cannot be verified from an explicit years statement")
    rationale=f"{len(demonstrated)} JD skills have work/project evidence; {len(listed)} are only listed or lack work-history evidence; {len(missing)} were not found. Score uses the six displayed weighted components. This is a deterministic text-evidence screen, not a prediction of job performance."
    return {
      "profile":{"email":contact["email"],"phone":contact["phone"],"location":contact["location"],"latest_role":latest,
        "total_experience":total_years,"role_experience":role_years,"mandatory_check":mandatory,"mandatory_missing":mandatory_missing,
        "skill_evidence":skill_evidence,"score_breakdown":breakdown,"rationale":rationale,"red_flags":red_flags,
        "projects":projects_lines[:8],"criteria":criteria},
      "score":total,"fit_band":band,"demonstrated":demonstrated,"listed":listed,"missing":missing,
      "gaps":gaps,"must_have_gaps":must_have_gaps,"rationale":rationale,"red_flags":red_flags,
      "key_matched_skills":demonstrated,"mandatory_skills":criteria["mandatory_skills"],
      "total_years":total_years,"role_years":role_years,"name":name,
    }
