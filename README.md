# TalentRank AI — Single-purpose HR Resume Screening

A local MVP for one focused workflow: **select a role → paste the job description → upload multiple resumes → analyze → review evidence → download Excel**.

## What it does
- Accepts PDF, DOCX and TXT resumes (maximum 10 MB each; up to 50 per run).
- Extracts available contact and role details from the resume text; fields not found are left blank or marked “Not stated”.
- Derives screening criteria from the selected role and pasted job description.
- Distinguishes skills evidenced in work/project text from skills mentioned only in a skills list.
- Checks mandatory requirements separately and flags missing or unverified evidence.
- Redacts protected-attribute lines before scoring and does not score age, gender, religion, caste, disability, marital status, ethnicity or similar attributes.
- Detects identical file content within a screening run and skips duplicate processing.
- Reports extraction failures per file without assigning a fabricated score.
- Generates a real `.xlsx` workbook with `Candidate Screening`, `Summary`, and `Rubric` sheets, filters, frozen headers, wrapped text, readable widths, number formats, score conditional formatting, and formula-injection protection.

## Scoring
The default 100-point rubric follows the provided GCP candidate-screening workbook structure:
- Role-specific experience: 20 points
- Overall relevant experience: 10 points
- Generic must-haves: 25 points
- Role-specific must-haves: 30 points
- Nice-to-have skills: 10 points
- Evidence quality: 5 points

Fit bands: Strong Fit 80–100; Good Fit 65–79; Moderate Fit 50–64; Not a Fit below 50.

Only explicit years-of-experience statements are used; duration is not inferred from dates. Work/project mentions receive full skill evidence credit, skills-list-only mentions receive partial credit and are flagged for verification, and skills not found receive no evidence credit. The rubric is deterministic and configurable from the selected job description, but it is not a validated predictor of job performance. Treat every score as decision support, not a final hiring decision. Human review is required.

## Run on Windows PowerShell

Extract the ZIP. Keep your existing project-specific `.venv` if you already created it. Use two terminals.

### Terminal 1 — FastAPI backend
From the project root:

```powershell
cd backend
..\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -v
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: http://127.0.0.1:8000/api/health  
API documentation: http://127.0.0.1:8000/docs

The backend test suite includes core unit tests plus end-to-end API coverage for multi-file upload, duplicate skipping, extraction failure reporting, and Excel workbook download. The updated suite currently passes **16 tests** in the development test environment.

If your virtual environment is elsewhere, activate that environment rather than creating or modifying another project's environment.

### Terminal 2 — React web UI
From the project root in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually http://localhost:5173.

## Excel export
After at least one screening has completed, select **Download Excel** in the results section. The button calls the backend export endpoint and downloads a workbook generated with OpenPyXL; it is not a placeholder.

## API
- `GET /api/health`
- `GET /api/screenings`
- `POST /api/screenings` — multipart fields `role`, `job_description`, and repeated `files`
- `GET /api/screenings/{screening_id}/results`
- `GET /api/screenings/{screening_id}/export`

SQLite is used by default at `backend/talentrank.db`. You may set `DATABASE_URL` to a supported SQLAlchemy database URL. Existing SQLite files are reused; the changes do not add database columns.

## Limitations and responsible use
This is a local MVP. The scoring logic uses deterministic text rules, not an LLM or validated hiring model. OCR for scanned PDFs is not enabled. Contact fields and experience values may be absent or misidentified when source formatting is unusual. Do not auto-reject candidates based on score. Review the original resume and verify experience, credentials, mandatory requirements, and claims with a qualified human. Before public deployment, add authentication, authorization, secure storage, privacy/retention controls, upload scanning, rate limits, database migrations, and monitoring.
