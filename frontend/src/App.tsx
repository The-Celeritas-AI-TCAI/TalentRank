import { useEffect, useMemo, useRef, useState } from 'react';
import { UploadCloud, FileText, FileSpreadsheet, X, CheckCircle2, AlertCircle, LoaderCircle, Download, ShieldCheck, ChevronDown, BriefcaseBusiness, SearchCheck, RefreshCw, Info } from 'lucide-react';
import './styles.css';

const API = (import.meta as any).env?.VITE_API_URL || 'http://127.0.0.1:8000/api';
const ROLES = ['AI/ML Engineer','Data Scientist','Data Engineer','Software Engineer','Cloud / GCP Engineer','DevOps Engineer','Business Analyst','QA Engineer','Product Analyst','Other / Custom Role'];
type Profile = {
  email?: string; phone?: string; location?: string; latest_role?: string;
  total_experience?: number|null; role_experience?: number|null; mandatory_check?: {requirement:string;status:string}[];
  mandatory_missing?: string[]; score_breakdown?: Record<string,number>; rationale?: string; red_flags?: string[];
  demonstrated_skills?: string[]; listed_skills?: string[]; missing_skills?: string[]; general_gaps?: string[];
  skill_evidence?: Record<string,{status:string;evidence:string[]}>;
};
type Candidate = {
  id:string; job_id:string; name:string; filename:string; status:string; status_label:string;
  match_score:number|null; fit_band:string|null; rank:number|null; error:string|null;
  verified_skills:string[]; unverified_skills:string[]; confirmed_absent_skills:string[];
  evidence_summary:string; profile:Profile; created_at?:string;
};
type Screening = {id:string;title:string;description:string;candidate_count:number;created_at?:string};
type Results = {screening:Screening;candidates:Candidate[]};
type Duplicate = {filename:string;duplicate_of:string;reason:string};
type AnalyzeResponse = {screening:Screening;processed:number;assessed:number;failed:number;duplicates:Duplicate[];candidates:Candidate[]};

async function request(path:string, init:RequestInit={}) {
  const res=await fetch(`${API}${path}`,init);
  if(!res.ok){let message=`Request failed (${res.status})`;try{const body=await res.json();message=body.detail||message;}catch{}throw new Error(message);}
  return res.json();
}
const fmtYears=(n:number|null|undefined)=>n===null||n===undefined?'Not stated':`${n} yrs`;
function bandClass(band:string|null|undefined){return band==='Strong Fit'?'strong':band==='Good Fit'?'good':band==='Moderate Fit'?'moderate':band==='Not a Fit'?'notfit':'neutral';}
function App(){
  const [role,setRole]=useState('AI/ML Engineer');
  const [customRole,setCustomRole]=useState('');
  const [jd,setJd]=useState('');
  const [files,setFiles]=useState<File[]>([]);
  const [candidates,setCandidates]=useState<Candidate[]>([]);
  const [screening,setScreening]=useState<Screening|null>(null);
  const [duplicates,setDuplicates]=useState<Duplicate[]>([]);
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [query,setQuery]=useState('');
  const [bandFilter,setBandFilter]=useState('All fit bands');
  const [expanded,setExpanded]=useState<string|null>(null);
  const inputRef=useRef<HTMLInputElement>(null);

  useEffect(()=>{(async()=>{
    try{
      const sessions:Screening[]=await request('/screenings');
      if(sessions.length){
        const latest=sessions[0]; const data:Results=await request(`/screenings/${latest.id}/results`);
        setScreening(data.screening);setCandidates(data.candidates);setJd(data.screening.description);
        if(ROLES.includes(data.screening.title))setRole(data.screening.title);else{setRole('Other / Custom Role');setCustomRole(data.screening.title);}
      }
    }catch(e:any){setError(`Could not connect to the backend. Confirm FastAPI is running at 127.0.0.1:8000. ${e.message}`);}
    finally{setLoading(false);}
  })();},[]);

  const chosenRole=role==='Other / Custom Role'?customRole.trim():role;
  const acceptedFiles=useMemo(()=>files.filter(f=>/\.(pdf|docx|txt)$/i.test(f.name)&&f.size<=10*1024*1024),[files]);
  const visible=useMemo(()=>candidates.filter(c=>{
    const matchesQuery=`${c.name} ${c.filename} ${c.profile?.latest_role||''} ${c.profile?.email||''}`.toLowerCase().includes(query.toLowerCase());
    const matchesBand=bandFilter==='All fit bands'||c.fit_band===bandFilter||(bandFilter==='Processing failed'&&c.status==='failed');
    return matchesQuery&&matchesBand;
  }),[candidates,query,bandFilter]);
  const scored=candidates.filter(c=>c.status==='scored');
  const counts={
    total:candidates.length,scored:scored.length,failed:candidates.filter(c=>c.status==='failed').length,
    strong:scored.filter(c=>c.fit_band==='Strong Fit').length,good:scored.filter(c=>c.fit_band==='Good Fit').length,
    moderate:scored.filter(c=>c.fit_band==='Moderate Fit').length,notfit:scored.filter(c=>c.fit_band==='Not a Fit').length
  };

  function addFiles(list:FileList|null){
    if(!list)return;
    const incoming=Array.from(list);
    const valid=incoming.filter(f=>/\.(pdf|docx|txt)$/i.test(f.name)&&f.size<=10*1024*1024);
    const invalid=incoming.length-valid.length;
    setFiles(prev=>[...prev,...valid].filter((f,i,a)=>a.findIndex(x=>x.name===f.name&&x.size===f.size)===i).slice(0,50));
    if(invalid)setNotice('Some files were skipped. Upload PDF, DOCX or TXT files up to 10 MB each.');
    else setNotice('');
  }
  function resetRun(){setCandidates([]);setScreening(null);setDuplicates([]);setQuery('');setBandFilter('All fit bands');setExpanded(null);setError('');setNotice('');}
  async function analyze(){
    if(!chosenRole){setError('Select or enter a job role.');return;}
    if(jd.trim().length<10){setError('Paste a job description or job summary of at least 10 characters.');return;}
    if(!acceptedFiles.length){setError('Upload at least one PDF, DOCX or TXT resume.');return;}
    setBusy(true);setError('');setNotice('');
    const fd=new FormData();fd.append('role',chosenRole);fd.append('job_description',jd.trim());
    acceptedFiles.forEach(f=>fd.append('files',f));
    try{
      const data:AnalyzeResponse=await request('/screenings',{method:'POST',body:fd});
      setScreening(data.screening);setCandidates(data.candidates);setDuplicates(data.duplicates||[]);setFiles([]);setExpanded(null);
      setNotice(`Analysis complete: ${data.assessed} assessed, ${data.failed} failed, ${(data.duplicates||[]).length} duplicate file(s) skipped.`);
      if(inputRef.current)inputRef.current.value='';
    }catch(e:any){setError(e.message||'Could not analyze resumes.');}
    finally{setBusy(false);}
  }
  async function downloadExcel(){
    if(!screening)return;
    setError('');
    try{
      const res=await fetch(`${API}/screenings/${screening.id}/export`);
      if(!res.ok){let message='Excel export failed';try{const body=await res.json();message=body.detail||message;}catch{}throw new Error(message);}
      const blob=await res.blob();
      if(blob.size===0)throw new Error('The server returned an empty Excel workbook.');
      const url=URL.createObjectURL(blob);const a=document.createElement('a');
      a.href=url;a.download=`talentrank-screening-${chosenRole.replace(/[^a-z0-9]+/gi,'-').toLowerCase()||'report'}.xlsx`;
      document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
      setNotice('Excel workbook downloaded successfully.');
    }catch(e:any){setError(e.message||'Excel export failed.');}
  }
  function newScreening(){resetRun();setFiles([]);setJd('');setRole('AI/ML Engineer');setCustomRole('');}
  return <div className="app">
    <header className="topbar">
      <div className="brand"><div className="brand-mark">TR</div><div><div className="brand-name">TalentRank <span>AI</span></div><div className="brand-subtitle">RESUME SCREENING</div></div></div>
      <div className="topbar-right"><span className="local-status"><i/> Local workspace</span><span className="topbar-divider"/><span className="privacy"><ShieldCheck size={16}/> Evidence-led · Human reviewed</span></div>
    </header>
    <main className="page">
      <section className="intro">
        <div><div className="eyebrow">HR SCREENING WORKSPACE</div><h1>Screen resumes against a role</h1><p>Enter the job requirements, upload multiple resumes, and review transparent evidence-based scores.</p></div>
        {screening&&<button className="btn btn-secondary" onClick={newScreening}><RefreshCw size={16}/> New screening</button>}
      </section>

      {error&&<div className="alert alert-error"><AlertCircle size={18}/><span>{error}</span><button onClick={()=>setError('')} aria-label="Dismiss"><X size={16}/></button></div>}
      {notice&&<div className="alert alert-success"><CheckCircle2 size={18}/><span>{notice}</span><button onClick={()=>setNotice('')} aria-label="Dismiss"><X size={16}/></button></div>}
      {loading&&<div className="loading-card"><LoaderCircle className="spin" size={20}/> Loading your latest screening…</div>}

      <section className="workflow-grid">
        <div className="panel setup-panel">
          <div className="panel-heading"><div className="step-number">1</div><div><h2>Define the role</h2><p>Select a role and provide the actual job requirements.</p></div></div>
          <div className="field">
            <label htmlFor="role">Selected job role <span className="required">*</span></label>
            <div className="select-control"><BriefcaseBusiness size={17}/><select id="role" value={role} onChange={e=>setRole(e.target.value)}><option value="" disabled>Select a role</option>{ROLES.map(r=><option key={r}>{r}</option>)}</select><ChevronDown size={16}/></div>
          </div>
          {role==='Other / Custom Role'&&<div className="field"><label htmlFor="custom-role">Custom job role <span className="required">*</span></label><input id="custom-role" value={customRole} onChange={e=>setCustomRole(e.target.value)} placeholder="e.g. Salesforce Administrator"/></div>}
          <div className="field"><label htmlFor="jd">Job description or summary <span className="required">*</span></label><textarea id="jd" rows={9} value={jd} onChange={e=>setJd(e.target.value)} placeholder={'Paste the job description here. Include responsibilities, mandatory skills, minimum experience, qualifications and nice-to-have requirements…'} maxLength={20000}/><div className="field-footer"><span>Scoring criteria are derived from this text.</span><span>{jd.length.toLocaleString()} / 20,000</span></div></div>
          <div className="notice-inline"><Info size={16}/><span>Explicit “must-have”, “required”, “minimum” and “nice-to-have” statements help separate mandatory checks from preferred skills.</span></div>
        </div>

        <div className="panel upload-panel">
          <div className="panel-heading"><div className="step-number">2</div><div><h2>Upload resumes</h2><p>Compare multiple candidates in one screening run.</p></div></div>
          <input ref={inputRef} className="hidden-input" type="file" multiple accept=".pdf,.docx,.txt" onChange={e=>addFiles(e.target.files)}/>
          <div className="dropzone" role="button" tabIndex={0} onClick={()=>inputRef.current?.click()} onKeyDown={e=>{if(e.key==='Enter'||e.key===' ')inputRef.current?.click();}} onDragOver={e=>{e.preventDefault();e.currentTarget.classList.add('dragging');}} onDragLeave={e=>e.currentTarget.classList.remove('dragging')} onDrop={e=>{e.preventDefault();e.currentTarget.classList.remove('dragging');addFiles(e.dataTransfer.files);}}>
            <div className="upload-illustration"><UploadCloud size={25}/></div><strong>Drop resume files here</strong><span>or <b>browse files</b></span><small>PDF, DOCX or TXT · Maximum 10 MB each · Up to 50 files</small>
          </div>
          <div className="file-summary"><span><FileText size={16}/> {files.length} selected</span><span>{(files.reduce((sum,f)=>sum+f.size,0)/1024/1024).toFixed(1)} MB total</span></div>
          {files.length>0?<div className="file-list">{files.map((f,i)=><div className="file-row" key={`${f.name}-${f.size}-${i}`}><div className="file-type"><FileText size={17}/></div><div className="file-info"><strong title={f.name}>{f.name}</strong><small>{(f.size/1024).toFixed(0)} KB</small></div><span className={/\.(pdf|docx|txt)$/i.test(f.name)&&f.size<=10*1024*1024?'file-valid':'file-invalid'}>{/\.(pdf|docx|txt)$/i.test(f.name)&&f.size<=10*1024*1024?'Ready':'Invalid'}</span><button className="remove-file" onClick={()=>setFiles(prev=>prev.filter((_,idx)=>idx!==i))} aria-label={`Remove ${f.name}`}><X size={15}/></button></div>)}</div>:<div className="empty-files"><FileText size={22}/><span>No resumes added yet</span><small>Your selected files will appear here.</small></div>}
          <button className="btn btn-primary analyze-btn" onClick={analyze} disabled={busy||loading}><SearchCheck size={17}/>{busy?'Analyzing resumes…':'Analyze Resumes'}{busy&&<LoaderCircle className="spin" size={16}/>}</button>
          <div className="upload-footnote"><ShieldCheck size={14}/> Protected attributes are excluded from scoring. Extraction failures are reported individually.</div>
        </div>
      </section>

      {(candidates.length>0||screening)&&<section className="results-section">
        <div className="results-heading"><div><div className="eyebrow">SCREENING RESULTS</div><h2>Candidate assessment</h2><p>{screening?.title||chosenRole} · {candidates.length} resume record(s) in this screening</p></div><button className="btn btn-primary" onClick={downloadExcel}><Download size={16}/> Download Excel</button></div>
        <div className="metric-grid">
          <div className="metric"><span>Total resumes</span><strong>{counts.total}</strong><small>Including failed extraction</small></div>
          <div className="metric"><span>Analyzed</span><strong>{counts.scored}</strong><small>Evidence-based text scores</small></div>
          <div className="metric"><span>Strong / Good fit</span><strong>{counts.strong+counts.good}</strong><small>{counts.strong} strong · {counts.good} good</small></div>
          <div className="metric"><span>Needs attention</span><strong>{counts.moderate+counts.notfit+counts.failed}</strong><small>Review gaps and extraction errors</small></div>
        </div>
        {duplicates.length>0&&<div className="alert alert-warning"><Info size={18}/><div><strong>{duplicates.length} duplicate file(s) skipped</strong>{duplicates.map((d,i)=><p key={i}>{d.filename} duplicates {d.duplicate_of}</p>)}</div></div>}
        <div className="panel results-panel">
          <div className="results-toolbar"><div className="result-count"><strong>Results</strong><span>{visible.length} shown</span></div><div className="filters"><div className="search-control"><SearchCheck size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search candidate or file"/></div><select value={bandFilter} onChange={e=>setBandFilter(e.target.value)}><option>All fit bands</option><option>Strong Fit</option><option>Good Fit</option><option>Moderate Fit</option><option>Not a Fit</option><option>Processing failed</option></select></div></div>
          {visible.length===0?<div className="no-results"><SearchCheck size={24}/><strong>No matching candidates</strong><span>Change the search or fit-band filter.</span></div>:<div className="table-scroll"><table className="candidate-table"><thead><tr><th>Rank</th><th>Candidate</th><th>Latest role</th><th>Experience</th><th>Score</th><th>Fit band</th><th>Mandatory checks</th><th></th></tr></thead><tbody>{visible.map(c=>{
            const p=c.profile||{};const checks=p.mandatory_check||[];const flagged=checks.filter(x=>/unverified|not found|below|listed only/i.test(x.status)).length;
            return <tr key={c.id} className={c.status==='failed'?'failed-row':''}>
              <td>{c.rank?`#${c.rank}`:'—'}</td>
              <td><div className="candidate-name"><div className="candidate-avatar">{(c.name||'C').split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase()}</div><div><strong>{c.name}</strong><small>{c.filename}</small>{c.status==='failed'&&<em>{c.error||'Extraction failed'}</em>}</div></div></td>
              <td>{p.latest_role||'Not identified'}</td><td>{fmtYears(p.total_experience)}</td>
              <td>{c.match_score===null||c.match_score===undefined?<span className="score-na">Not scored</span>:<div className="score-wrap"><strong>{c.match_score.toFixed(1)}</strong><span className="score-track"><i style={{width:`${Math.max(0,Math.min(100,c.match_score))}%`}}/></span></div>}</td>
              <td><span className={`fit-pill ${bandClass(c.fit_band)}`}>{c.fit_band||c.status_label}</span></td>
              <td>{c.status==='failed'?<span className="status-flag">Failed</span>:flagged?<span className="status-flag">{flagged} to verify</span>:<span className="status-ok">Review evidence</span>}</td>
              <td><button className="details-btn" onClick={()=>setExpanded(expanded===c.id?null:c.id)}>{expanded===c.id?'Hide':'Details'}</button></td>
            </tr>;
          })}</tbody></table></div>}
          {visible.map(c=>expanded===c.id&&<div className="candidate-detail" key={`detail-${c.id}`}>
            <div className="detail-title"><div><h3>{c.name}</h3><p>{c.profile?.email||'Email not found'} {c.profile?.phone?` · ${c.profile.phone}`:''} {c.profile?.location?` · ${c.profile.location}`:''}</p></div><button className="remove-file" onClick={()=>setExpanded(null)} aria-label="Close details"><X size={16}/></button></div>
            {c.status==='failed'?<div className="alert alert-error"><AlertCircle size={17}/>{c.error||'Resume could not be extracted.'}</div>:<>
              <p className="rationale">{c.profile?.rationale||c.evidence_summary}</p>
              <div className="detail-columns"><div><h4>Score breakdown</h4>{Object.entries(c.profile?.score_breakdown||{}).map(([label,score])=><div className="breakdown-row" key={label}><span>{label}</span><strong>{Number(score).toFixed(1)}</strong></div>)}</div>
                <div><h4>Matched skill evidence</h4><div className="skill-group"><b>Demonstrated in work/projects</b><p>{(c.profile?.demonstrated_skills||[]).join(', ')||'No demonstrated JD skills identified.'}</p></div><div className="skill-group"><b>Listed only — verify</b><p>{(c.profile?.listed_skills||[]).join(', ')||'None identified.'}</p></div><div className="skill-group"><b>Not found in extracted text</b><p>{(c.profile?.missing_skills||[]).join(', ')||'None identified.'}</p></div></div>
                <div><h4>Mandatory requirements</h4>{(c.profile?.mandatory_check||[]).length?(c.profile?.mandatory_check||[]).map((x,i)=><div className="mandatory-row" key={i}><span>{x.requirement}</span><b className={/demonstrated|meets stated/i.test(x.status)?'status-ok':'status-flag'}>{x.status}</b></div>):<p className="muted">No explicit mandatory statements were detected; review the JD manually.</p>}<h4 className="subheading">Red flags / verify</h4><ul className="flag-list">{(c.profile?.red_flags||[]).map((x,i)=><li key={i}>{x}</li>)}{!(c.profile?.red_flags||[]).length&&<li>No automatic red flags detected. Verify source documents manually.</li>}</ul></div>
              </div>
            </>}
          </div>)}
        </div>
        <div className="disclaimer"><ShieldCheck size={17}/><p><strong>Decision support only.</strong> Scores reflect deterministic text matching and evidence visible in extracted resume text, not a validated prediction of job performance. Do not automatically reject or select candidates from scores alone. Verify requirements and claims with human review.</p></div>
      </section>}
      <footer className="footer"><span>TalentRank AI · Resume Screening</span><span>Built for evidence-led HR review</span></footer>
    </main>
  </div>;
}
export default App;
