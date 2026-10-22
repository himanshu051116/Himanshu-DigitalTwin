'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

type Patient = { patient_id:string; age:number; sex:string; bmi:number; hba1c:number; fasting_glucose:number; condition:string; cohort:string };
type Forecast = {horizon_min:number; population:number; personalized:number; lower:number; upper:number};
type Snap = {
  patient:Patient; twin_version:number; timestamp:string; sync_status:string;
  reading:{glucose:number|null;heart_rate:number;steps_5m:number;activity:number;carbs_active_g:number;minutes_since_meal:number|null;quality:string;provenance:Record<string,string>};
  forecasts:Forecast[]; excursion_risk:number|null; risk_band:string; confidence:string; personal_bias:Record<string,number>;
  explanations:{factor:string;strength:number;direction:string}[]; recent_history:any[]; timeline:any[]; audit:any[]; model_metrics:Record<string,number|string>;
};

function fmtTime(v:string){ return new Date(v).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}); }
function n(v:number|null|undefined, digits=0){ return typeof v==='number' && Number.isFinite(v) ? v.toFixed(digits) : '—'; }

type HistoryReading = { timestamp:string; glucose:number|null; quality:string };

function MiniChart({history,forecasts,timestamp,validReading}:{history:HistoryReading[];forecasts:Forecast[];timestamp:string;validReading:number|null}){
  const W=820,H=255,pad=35;
  const now=Date.parse(timestamp);
  const earliest=history.length?Date.parse(history[0].timestamp):now;
  const from=Number.isFinite(earliest)?Math.min(earliest,now):now-5*60*1000;
  const until=now+120*60*1000;
  const at=(t:number)=>pad+(Math.max(from,Math.min(until,t))-from)/Math.max(1,until-from)*(W-2*pad);
  const actual=history.filter(p=>p.quality==='VALID'&&typeof p.glucose==='number'&&Number.isFinite(p.glucose));
  const vals=[...actual.map(p=>p.glucose as number),...forecasts.flatMap(f=>[f.personalized,f.lower,f.upper])];
  const low=Math.min(90,...vals)-10,high=Math.max(180,...vals)+10;
  const y=(v:number)=>H-pad-(v-low)/Math.max(1,high-low)*(H-2*pad);
  let obs='',disconnected=true;
  for(const p of history){
    const t=Date.parse(p.timestamp);
    if(p.quality!=='VALID'||typeof p.glucose!=='number'||!Number.isFinite(t)){
      disconnected=true;continue;
    }
    obs+=(disconnected?'M':'L')+`${at(t)},${y(p.glucose)} `;
    disconnected=false;
  }
  const mayForecast=validReading!==null && Number.isFinite(validReading) && forecasts.length>0;
  const first=mayForecast?{x:at(now),y:y(validReading as number)}:null;
  const points=first?forecasts.map(f=>({x:at(now+f.horizon_min*60000),y:y(f.personalized),upper:y(f.upper),lower:y(f.lower),h:f.horizon_min})):[];
  const pred=first?'M'+first.x+','+first.y+' '+points.map(p=>'L'+p.x+','+p.y).join(' '):'';
  const band=first&&points.length?
    'M'+first.x+','+first.y+' '+points.map(p=>'L'+p.x+','+p.upper).join(' ')+
    ' '+[...points].reverse().map(p=>'L'+p.x+','+p.lower).join(' ')+
    ' L'+first.x+','+first.y+' Z':'';
  return <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={first?'Glucose observations without imputed readings; illustrative forecasts spaced by elapsed minutes':'Observed valid glucose only; missing data omitted and forecast withheld'}>
    {[100,140,180,220].filter(v=>v>low&&v<high).map(v=><g key={v}><line x1={pad} x2={W-pad} y1={y(v)} y2={y(v)} className="grid"/><text x="3" y={y(v)+4} className="axis">{v}</text></g>)}
    {band && <path d={band} className="uncertainty"/>}
    <path d={obs.trim()} className="observed"/>
    {pred && <path d={pred} className="predicted"/>}
    {points.map(p=><g key={p.h}><circle cx={p.x} cy={p.y} r="4.5" className="forecastDot"/><text x={p.x-18} y={H-6} className="axis">+{p.h}m</text></g>)}
    <text x={pad} y="16" className="legend">Valid observed CGM only</text>
    {first && <text x={pad+210} y="16" className="legend predictedText">Illustrative forecast</text>}
    {history.some(p=>p.quality!=='VALID') && <text x={W-168} y="16" className="legend">Gaps omitted</text>}
  </svg>;
}

function errorText(e:unknown){ return e instanceof Error?e.message:'Unexpected API failure'; }

function Badge({children,tone='neutral'}:{children:React.ReactNode;tone?:string}){ return <span className={`badge ${tone}`}>{children}</span>; }

export default function Home(){
  const [patients,setPatients]=useState<Patient[]>([]); const [pid,setPid]=useState('HDT-027'); const [snap,setSnap]=useState<Snap|null>(null);
  const [error,setError]=useState(''); const [chapter,setChapter]=useState('baseline'); const skipNextReset=useRef(false);
  const [running,setRunning]=useState(false); const [speed,setSpeed]=useState(1); const timer=useRef<ReturnType<typeof setInterval>|null>(null);
  const [tab,setTab]=useState<'twin'|'scenario'|'evidence'>('twin'); const [scenario,setScenario]=useState<any>(null); const [scenarioInputs,setScenarioInputs]=useState({carbs:70,activity:.2});
  const request=useCallback(async(path:string,opts?:RequestInit)=>{ const r=await fetch(API+path,opts); if(!r.ok) throw new Error(await r.text()); return r.json(); },[]);
  const reset=useCallback(async(id=pid)=>{ const d=await request(`/api/replay/${id}/reset`,{method:'POST'}); setSnap(d);setScenario(null); },[pid,request]);
  const step=useCallback(async(count=1)=>{ const d=await request(`/api/replay/${pid}/step?steps=${count}`,{method:'POST'}); setSnap(d); },[pid,request]);
  useEffect(()=>{request('/api/patients').then((p)=>{if(!Array.isArray(p)||p.length===0)throw new Error('No demo patients available');setPatients(p);setPid(p[0].patient_id);}).catch(e=>setError(errorText(e)))},[request]);
  useEffect(()=>{if(skipNextReset.current){skipNextReset.current=false;return;}if(pid)reset(pid).catch(e=>setError(errorText(e)));},[pid]);
  useEffect(()=>{if(timer.current)clearInterval(timer.current);if(running){timer.current=setInterval(()=>step(speed).catch(e=>{setRunning(false);setError(errorText(e))}),1000);}return()=>{if(timer.current)clearInterval(timer.current)};},[running,speed,step]);
  const riskAvailable=typeof snap?.excursion_risk==='number' && (snap?.forecasts.length??0)>0;
  const riskPct=riskAvailable?Math.round((snap!.excursion_risk as number)*100):null;
  const riskTone=riskPct===null?'neutral':riskPct>=70?'danger':riskPct>=45?'warn':riskPct>=20?'caution':'good';
  const improvement=useMemo(()=>{if(!snap)return null; const a=snap.model_metrics.population_mae,b=snap.model_metrics.personalized_mae; if(typeof a==='number'&&typeof b==='number'&&a>0)return ((a-b)/a*100);return null},[snap]);
  async function runScenario(){try{const d=await request('/api/scenario',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient_id:pid,carbs_g:scenarioInputs.carbs,activity:scenarioInputs.activity})});setScenario(d);setError('');}catch(e){setError(errorText(e));}}
  async function showChapter(){
    setRunning(false);
    try{
      const d=await request('/api/demo/chapter/'+chapter,{method:'POST'});
      if(d.simulation_only!==true||!d.snapshot)throw new Error('Unexpected guided demo response');
      if(pid!==d.snapshot.patient.patient_id){skipNextReset.current=true;setPid(d.snapshot.patient.patient_id);}
      setSnap(d.snapshot);setScenario(null);setTab('twin');setError('');
    }catch(e){setError(errorText(e));}
  }
  if(!snap) return <main className="loading" role="status">{error?'Unable to start the research demo: '+error:'Initializing synthetic research demo…'}</main>;
  return <main>
    <header className="topbar">
      <div><div className="brandRow"><div className="mark">HD</div><div><h1>HimanshuDigitalTwin</h1><p>Synthetic patient replay · research prototype</p></div></div></div>
      <div className="headerActions"><Badge tone={snap.sync_status==='SYNCHRONIZED'?'good':'warn'}>● {snap.sync_status}</Badge><Badge>v{snap.twin_version.toLocaleString()}</Badge></div>
    </header>
    <div className="disclaimer">Research demonstration only · Default replay and risk are synthetic and uncalibrated · No diagnosis, dosing, or treatment recommendation.</div>
    {error && <div className="disclaimer" role="alert">Dashboard request failed: {error} <button type="button" onClick={()=>setError('')}>Dismiss</button></div>}
    <nav className="nav"><button className={tab==='twin'?'active':''} onClick={()=>setTab('twin')}>Twin workspace</button><button className={tab==='scenario'?'active':''} onClick={()=>setTab('scenario')}>Scenario lab</button><button className={tab==='evidence'?'active':''} onClick={()=>setTab('evidence')}>Evidence & safety</button></nav>
    <section className="controls card">
      <div><label>Patient</label><select value={pid} onChange={e=>{setRunning(false);setPid(e.target.value)}}>{patients.map(p=><option key={p.patient_id}>{p.patient_id}</option>)}</select></div>
      <div className="profileQuick"><span>{snap.patient.age} y</span><span>{snap.patient.sex}</span><span>BMI {snap.patient.bmi}</span><span>HbA1c {snap.patient.hba1c}%</span></div>
      <div className="playback"><button className="primary" onClick={()=>setRunning(v=>!v)}>{running?'Pause replay':'Run replay'}</button><button onClick={()=>step(1)}>Step</button><button onClick={()=>reset()}>Reset</button><select value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={1}>1×</option><option value={3}>3×</option><option value={6}>6×</option><option value={12}>12×</option></select></div>
    </section>

    <section className="guidedChapters card" aria-label="Guided judge demonstration">
      <div><strong>Guided judge demo</strong><p>Six reproducible synthetic checkpoints, including sensor gap and recovery</p></div>
      <label htmlFor="judgeChapterNext">Chapter</label>
      <select id="judgeChapterNext" value={chapter} onChange={e=>setChapter(e.target.value)}>
        <option value="baseline">1 · Baseline</option><option value="breakfast">2 · Breakfast</option>
        <option value="lunch">3 · Lunch</option><option value="verification">4 · Verification</option>
        <option value="sensor_gap">5 · Sensor gap</option><option value="recovery">6 · Recovery</option>
      </select>
      <button onClick={showChapter}>Show chapter</button>
    </section>

    {tab==='twin' && <>
      <section className="metricGrid">
        <div className="card metric"><div className="eyebrow">Current glucose</div><div className="big">{n(snap.reading.glucose)} <small>mg/dL</small></div><div className="subrow"><Badge tone={snap.reading.quality==='VALID'?'good':'warn'}>{snap.reading.quality}</Badge><span>{fmtTime(snap.timestamp)}</span></div></div>
        <div className="card metric"><div className="eyebrow">2-hour excursion risk · illustrative</div><div className={`big ${riskTone}`}>{riskPct===null?'Withheld':`${riskPct}%`}</div><div className="subrow"><Badge tone={riskTone}>{riskPct===null?'UNAVAILABLE':snap.risk_band}</Badge><span>{riskPct===null?'No valid forecast available':`${snap.confidence} confidence · not calibrated`}</span></div></div>
        <div className="card metric"><div className="eyebrow">Wearable state</div><div className="big">{n(snap.reading.heart_rate)} <small>bpm</small></div><div className="subrow"><span>Activity {Math.round(snap.reading.activity*100)}%</span><span>{snap.reading.steps_5m} steps/5m</span></div></div>
        <div className="card metric"><div className="eyebrow">Personalization</div><div className="big">{improvement===null?'Learning':`${Math.max(-99,improvement).toFixed(1)}%`}</div><div className="subrow"><span>{improvement===null?'Awaiting resolved forecasts':'MAE improvement vs population'}</span></div></div>
      </section>
      <section className="mainGrid">
        <div className="card chartCard"><div className="sectionHead"><div><h2>Observed → forecast trajectory</h2><p>Simulated replay with illustrative, uncalibrated intervals</p></div><Badge>{snap.forecasts.length ? `${snap.confidence} · simulated` : 'Forecast withheld'}</Badge></div><MiniChart history={snap.recent_history} forecasts={snap.forecasts} timestamp={snap.timestamp} validReading={snap.reading.quality==='VALID'?snap.reading.glucose:null}/><div className="forecastRows">{snap.forecasts.map(f=><div key={f.horizon_min}><span>+{f.horizon_min} min</span><strong>{f.personalized} mg/dL</strong><small>population {f.population} · interval {f.lower}–{f.upper}</small></div>)}</div></div>
        <div className="card"><div className="sectionHead"><div><h2>Why the twin changed</h2><p>Transparent directional contributors</p></div></div><div className="drivers">{snap.explanations.map(e=><div key={e.factor}><span>{e.factor}</span><div className="bar"><i style={{width:`${Math.max(6,e.strength*100)}%`}} className={e.direction==='down'?'down':''}/></div><b>{e.direction==='up'?'↑':'↓'}</b></div>)}</div><hr/><div className="facts"><div><span>Active carbs</span><b>{snap.reading.carbs_active_g} g</b></div><div><span>Minutes since meal</span><b>{snap.reading.minutes_since_meal ?? '—'}</b></div><div><span>FHIR/EHR phenotype</span><b>Adapter-ready</b></div></div></div>
      </section>
      <section className="lowerGrid">
        <div className="card"><div className="sectionHead"><div><h2>Twin learning</h2><p>Forecasts are verified against later observations</p></div></div><div className="compare"><div><span>Population MAE</span><strong>{typeof snap.model_metrics.population_mae==='number'?`${snap.model_metrics.population_mae} mg/dL`:'collecting'}</strong></div><div><span>Personalized MAE</span><strong>{typeof snap.model_metrics.personalized_mae==='number'?`${snap.model_metrics.personalized_mae} mg/dL`:'collecting'}</strong></div><div><span>Resolved forecasts</span><strong>{snap.model_metrics.resolved_forecasts}</strong></div></div><div className="biases">{Object.entries(snap.personal_bias).filter(([k])=>k.includes('postmeal')).map(([k,v])=><div key={k}><span>{k.replace('_',' · +')}m</span><b>{Number(v)>0?'+':''}{v}</b></div>)}</div></div>
        <div className="card"><div className="sectionHead"><div><h2>Twin event timeline</h2><p>Auditable state evolution</p></div></div><div className="timeline">{snap.timeline.slice(0,8).map((t,i)=><div key={i}><time>{fmtTime(t.timestamp)}</time><span className={`event ${t.type.toLowerCase()}`}>{t.type}</span><p>{t.message}</p></div>)}</div></div>
      </section>
    </>}

    {tab==='scenario' && <section className="scenarioGrid"><div className="card"><h2>Scenario laboratory</h2><p className="muted">Modify model inputs while keeping the patient twin unchanged. This is exploratory modelling, not a causal or treatment estimate.</p><label>Active carbohydrate input <b>{scenarioInputs.carbs} g</b></label><input type="range" min="0" max="140" value={scenarioInputs.carbs} onChange={e=>setScenarioInputs(v=>({...v,carbs:Number(e.target.value)}))}/><label>Activity intensity <b>{Math.round(scenarioInputs.activity*100)}%</b></label><input type="range" min="0" max="1" step="0.05" value={scenarioInputs.activity} onChange={e=>setScenarioInputs(v=>({...v,activity:Number(e.target.value)}))}/><button className="primary wide" onClick={runScenario}>Run exploratory scenario</button></div><div className="card"><h2>Estimated trajectory shift</h2>{scenario?<div className="scenarioCompare">{scenario.baseline.map((b:Forecast,i:number)=><div key={b.horizon_min}><span>+{b.horizon_min} min</span><div><small>Current</small><strong>{b.personalized}</strong></div><div><small>Scenario</small><strong>{scenario.scenario[i].personalized}</strong></div><div className={scenario.scenario[i].personalized-b.personalized>0?'upText':'downText'}>{(scenario.scenario[i].personalized-b.personalized)>0?'+':''}{(scenario.scenario[i].personalized-b.personalized).toFixed(1)} mg/dL</div></div>)}<p className="safetyNote">{scenario.note}</p></div>:<div className="empty">Choose inputs and run a scenario. The current twin state will not be mutated.</div>}</div></section>}

    {tab==='evidence' && <section className="evidenceGrid"><div className="card"><h2>What makes this a digital twin</h2><ul className="checkList"><li>Patient-specific state representation</li><li>Continuous timestamped synchronization</li><li>30/60/120-minute future-state prediction</li><li>Prediction → observation verification</li><li>Context-aware personal residual adaptation</li><li>Uncertainty + sensor quality awareness</li><li>Versioned, auditable timeline</li></ul></div><div className="card"><h2>Scientific guardrails</h2><ul className="checkList warning"><li>No random row-level train/test split for CGM data</li><li>Use grouped or leave-one-subject-out validation on real cohorts</li><li>No claim of Indian clinical validation without Indian cohort evidence</li><li>No diagnosis or medication/dosing recommendation</li><li>Scenario Lab does not claim causal effects</li></ul></div><div className="card"><h2>Data provenance</h2><div className="facts"><div><span>Current stream</span><b>{snap.reading.provenance.stream}</b></div><div><span>Glucose channel</span><b>{snap.reading.provenance.glucose}</b></div><div><span>Wearable channel</span><b>{snap.reading.provenance.activity}</b></div><div><span>Twin version</span><b>#{snap.twin_version}</b></div></div></div></section>}
    <footer><span>HimanshuDigitalTwin · Type-2 diabetes metabolic twin PoC</span><span>Research prototype · v0.10.0</span></footer>
  </main>
}
