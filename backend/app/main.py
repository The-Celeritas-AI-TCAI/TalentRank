from __future__ import annotations
import hashlib, io, os, re, tempfile, uuid
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, Depends, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .database import Base, engine, get_db
from .models import Job, Candidate, AuditEvent
from .extraction import extract
from .screening import assess_resume, extract_jd_criteria
from .scoring import rank
from .excel_export import build_workbook

Base.metadata.create_all(bind=engine)
app = FastAPI(
    title="TalentRank AI Resume Screening API",
    version="2.0.0",
    description="Single-purpose, evidence-based resume screening. Scores support human review and are not hiring decisions."
)
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_FILES = int(os.getenv("MAX_UPLOAD_FILES", "50"))

def _profile(candidate: Candidate) -> dict:
    return (candidate.criterion_evidence or {}).get("_profile") or (candidate.criterion_gaps or {}).get("_profile") or {}

def serialize_candidate(c: Candidate) -> dict:
    profile = _profile(c)
    return {
        "id": c.id, "job_id": c.job_id, "name": c.name, "filename": c.filename,
        "status": c.status, "status_label": {"scored":"Analyzed","incomplete":"Incomplete","failed":"Failed"}.get(c.status,c.status),
        "match_score": c.match_score, "fit_band": c.fit_band, "rank": c.rank,
        "relevant_years": c.relevant_years, "evidence_coverage": c.evidence_coverage,
        "criterion_scores": c.criterion_scores or {}, "weights_used": c.weights_used or {},
        "verified_skills": c.verified_skills or [], "unverified_skills": c.unverified_skills or [],
        "confirmed_absent_skills": c.confirmed_absent_skills or [],
        "criterion_evidence": c.criterion_evidence or {}, "criterion_gaps": c.criterion_gaps or {},
        "projects": c.projects or [], "evidence_summary": c.evidence_summary or "",
        "error": c.error, "review_status": c.review_status,
        "profile": {k:v for k,v in profile.items() if k != "file_hash"},
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }

def serialize_job(job: Job, db: Session|None=None) -> dict:
    count=0
    if db is not None:
        count=db.query(Candidate).filter(Candidate.job_id==job.id).count()
    return {"id":job.id,"title":job.title,"description":job.description,"candidate_count":count,
            "created_at":job.created_at.isoformat() if job.created_at else None}

def _audit(db: Session, action: str, detail: str, job_id: str|None=None, candidate_id: str|None=None):
    db.add(AuditEvent(action=action,detail=detail[:1000],job_id=job_id,candidate_id=candidate_id))

@app.get("/api/health")
def health():
    return {"status":"ok","service":"TalentRank AI API","version":"2.0.0"}

@app.get("/api/screenings")
def list_screenings(db: Session=Depends(get_db)):
    jobs=db.query(Job).order_by(desc(Job.created_at)).all()
    result=[]
    for job in jobs:
        rows=db.query(Candidate).filter(Candidate.job_id==job.id).all()
        # Hide legacy recruiter-workspace records that were not created by this screening workflow.
        if rows and any("_profile" in (c.criterion_evidence or {}) for c in rows):
            result.append(serialize_job(job,db))
    return result

@app.post("/api/screenings", status_code=201)
async def analyze_resumes(
    role: Annotated[str, Form(min_length=2, max_length=200)],
    job_description: Annotated[str, Form(min_length=10, max_length=20000)],
    files: Annotated[list[UploadFile], File(...)],
    db: Session=Depends(get_db),
):
    role=role.strip()
    job_description=job_description.strip()
    if not role: raise HTTPException(422,"Select a job role.")
    if len(job_description)<10: raise HTTPException(422,"Paste a job description or job summary (at least 10 characters).")
    if not files: raise HTTPException(422,"Upload at least one PDF, DOCX, or TXT resume.")
    if len(files)>MAX_UPLOAD_FILES: raise HTTPException(413,f"Maximum {MAX_UPLOAD_FILES} resumes per screening.")
    criteria=extract_jd_criteria(role,job_description)
    if not criteria["mandatory_skills"] and not criteria["role_specific_skills"] and not criteria["preferred_skills"]:
        raise HTTPException(422,"Could not identify any role requirements from the job description. Add explicit skills, responsibilities, or must-have requirements.")

    job=Job(
        id=str(uuid.uuid4()), title=role, description=job_description,
        required_skills=criteria["mandatory_skills"], preferred_skills=criteria["preferred_skills"],
        min_years=criteria["min_years"] or 0, domain_keywords=criteria["role_specific_skills"],
        education_keywords=[]
    )
    db.add(job); db.flush()
    existing=db.query(Candidate).filter(Candidate.job_id==job.id).all()
    seen_hashes={(_profile(c).get("file_hash")):c.filename for c in existing if _profile(c).get("file_hash")}
    created=[]; duplicates=[]; batch_hashes={}
    for uploaded in files:
        filename=Path(uploaded.filename or "resume").name[:255]
        suffix=Path(filename).suffix.lower()
        if suffix not in {".pdf",".docx",".txt"}:
            cid=str(uuid.uuid4())
            c=Candidate(id=cid,job_id=job.id,name=Path(filename).stem[:200] or "Candidate",filename=filename,status="failed",
                        error="Unsupported file type. Upload PDF, DOCX, or TXT.",review_status="Pending review",
                        criterion_evidence={"_profile":{"red_flags":["Unsupported file type"],"rationale":"File was not analyzed."}})
            db.add(c); created.append(c); _audit(db,"resume.failed",f"{filename}: unsupported file type",job.id,cid); continue
        raw=await uploaded.read(MAX_FILE_BYTES+1)
        if len(raw)>MAX_FILE_BYTES:
            cid=str(uuid.uuid4())
            c=Candidate(id=cid,job_id=job.id,name=Path(filename).stem[:200] or "Candidate",filename=filename,status="failed",
                        error="File exceeds 10 MB limit.",review_status="Pending review",
                        criterion_evidence={"_profile":{"red_flags":["File exceeds 10 MB limit"],"rationale":"File was not analyzed."}})
            db.add(c); created.append(c); _audit(db,"resume.failed",f"{filename}: too large",job.id,cid); continue
        file_hash=hashlib.sha256(raw).hexdigest()
        duplicate_of=seen_hashes.get(file_hash) or batch_hashes.get(file_hash)
        if duplicate_of:
            duplicates.append({"filename":filename,"duplicate_of":duplicate_of,"reason":"Identical file content; not processed twice."})
            continue
        batch_hashes[file_hash]=filename
        cid=str(uuid.uuid4())
        base_profile={"file_hash":file_hash,"email":"","phone":"","location":"","latest_role":"","total_experience":None,
                      "role_experience":None,"mandatory_check":[],"mandatory_missing":[],"score_breakdown":{},
                      "rationale":"","red_flags":[],"demonstrated_skills":[],"listed_skills":[],"missing_skills":[],"general_gaps":[]}
        try:
            with tempfile.TemporaryDirectory() as td:
                temp=Path(td)/filename
                temp.write_bytes(raw)
                extraction=extract(temp)
            if not extraction.ok:
                raise ValueError(extraction.error or "Text extraction failed")
            result=assess_resume(extraction.pages,filename,role,job_description)
            profile=result["profile"]
            profile["file_hash"]=file_hash
            profile["demonstrated_skills"]=result["demonstrated"]
            profile["listed_skills"]=result["listed"]
            profile["missing_skills"]=result["missing"]
            profile["general_gaps"]=result["must_have_gaps"]
            breakdown=profile["score_breakdown"]
            weights={"Role-Specific Experience (20)":20,"Overall Relevant Experience (10)":10,"Generic Must-Haves (25)":25,
                     "Role-Specific Must-Haves (30)":30,"Nice-to-Have (10)":10,"Evidence Quality (5)":5}
            ev={
              "_profile":profile,
              "skills":[f"{skill}: {profile['skill_evidence'].get(skill,{}).get('status','unverified')}" for skill in result["demonstrated"]+result["listed"]+result["missing"]],
              "experience":[f"Explicit total experience statement: {profile['total_experience']} years"] if profile["total_experience"] is not None else [],
              "role_domain":[f"Selected role: {role}"] if profile["latest_role"] else [],
            }
            gaps={"_profile":profile,"skills":result["gaps"],"experience":[] if profile["total_experience"] is not None else ["Total experience not explicitly quantified"],
                  "role_domain":[] if profile["role_experience"] is not None else ["Role-specific experience not explicitly quantified"]}
            c=Candidate(
                id=cid,job_id=job.id,name=result["name"],filename=filename,status="scored",
                match_score=result["score"],fit_band=result["fit_band"],relevant_years=result["total_years"],
                evidence_coverage=round(100*len(result["demonstrated"])/max(1,len(result["demonstrated"])+len(result["listed"])+len(result["missing"])),1),
                criterion_scores=breakdown,weights_used=weights,
                verified_skills=result["demonstrated"],unverified_skills=result["listed"],confirmed_absent_skills=result["missing"],
                criterion_evidence=ev,criterion_gaps=gaps,projects=profile.get("projects",[]),
                evidence_summary=result["rationale"],error=None,review_status="Pending review"
            )
            created.append(c); db.add(c); seen_hashes[file_hash]=filename
            _audit(db,"resume.analyzed",filename,job.id,cid)
        except Exception as exc:
            base_profile["red_flags"]=[str(exc)[:300]]
            base_profile["rationale"]="Resume could not be analyzed. Review the error and re-upload or inspect the file manually."
            c=Candidate(id=cid,job_id=job.id,name=Path(filename).stem.replace("_"," ")[:200] or "Candidate",filename=filename,
                        status="failed",error=str(exc)[:500],review_status="Pending review",
                        criterion_evidence={"_profile":base_profile},criterion_gaps={"_profile":base_profile})
            created.append(c); db.add(c); _audit(db,"resume.failed",f"{filename}: {str(exc)[:300]}",job.id,cid)
    db.flush()
    all_candidates=db.query(Candidate).filter(Candidate.job_id==job.id).all()
    rank_results=[]
    for c in all_candidates:
        fake=type("Score",(),{"status":c.status,"match_score":c.match_score})()
        rank_results.append((c.id,fake))
    ranks=rank(rank_results)
    for c in all_candidates: c.rank=ranks.get(c.id)
    db.commit()
    for c in all_candidates: db.refresh(c)
    return {
      "screening":serialize_job(job,db),
      "processed":len(created),
      "assessed":sum(c.status=="scored" for c in created),
      "failed":sum(c.status=="failed" for c in created),
      "duplicates":duplicates,
      "candidates":[serialize_candidate(c) for c in sorted(created,key=lambda x:(x.rank is None,x.rank or 10**9,x.name.lower()))],
    }

@app.get("/api/screenings/{screening_id}/results")
def screening_results(screening_id: str, db: Session=Depends(get_db)):
    job=db.get(Job,screening_id)
    if not job: raise HTTPException(404,"Screening not found")
    candidates=db.query(Candidate).filter(Candidate.job_id==screening_id).all()
    candidates.sort(key=lambda c:(c.rank is None,c.rank or 10**9,c.name.lower()))
    return {"screening":serialize_job(job,db),"candidates":[serialize_candidate(c) for c in candidates]}

@app.get("/api/screenings/{screening_id}/export")
def export_screening(screening_id: str, db: Session=Depends(get_db)):
    job=db.get(Job,screening_id)
    if not job: raise HTTPException(404,"Screening not found")
    candidates=db.query(Candidate).filter(Candidate.job_id==screening_id).all()
    payload=[serialize_candidate(c) for c in candidates]
    ranks={c.id:c.rank for c in candidates}
    workbook=build_workbook({"id":job.id,"title":job.title,"description":job.description},payload,ranks)
    safe=re.sub(r"[^A-Za-z0-9_-]+","-",job.title).strip("-") or "screening"
    return StreamingResponse(io.BytesIO(workbook),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":f'attachment; filename="talentrank-screening-{safe}.xlsx"'})

# Compatibility route for an already-open browser/API client; the UI uses the single-purpose endpoint above.
@app.get("/api/jobs/{job_id}/export")
def legacy_export(job_id: str, db: Session=Depends(get_db)):
    return export_screening(job_id,db)
