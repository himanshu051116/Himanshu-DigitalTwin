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

function MiniChart({history, forecasts}:{history:any[]; forecasts:Forecast[]}){
  const W=820,H=255,pad=34;
  const pts=history.filter(x=>typeof x.glucose==='number');
  const values=[...pts.map(x=>x.glucose), ...forecasts.map(x=>x.personalized), ...forecasts.map(x=>x.lower), ...forecasts.map(x=>x.upper)];
  const min=Math.min(90,...values)-10,max=Math.max(180,...values)+10;
  const y=(v:number)=>H-pad-(v-min)/(max-min)*(H-pad*2);
  const x=(i:number,total:number)=>pad+i/(Math.max(1,total-1))*(W-pad*2);
  const histPath=pts.map((p,i)=>(i?'L':'M')+`${x(i,pts.length+3)},${y(p.glucose)}`).join(' ');
  const startX=pts.length?x(pts.length-1,pts.length+3):pad;
  const predXs=forecasts.map((_,i)=>x(pts.length+i,pts.length+3));
  const currentY=y(pts.at(-1)?.glucose||forecasts[0]?.personalized||120);
  const predPath=`M${startX},${currentY} `+forecasts.map((f,i)=>`L${predXs[i]},${y(f.personalized)}`).join(' ');
  const upper=[{x:startX,y:y(pts.at(-1)?.glucose||forecasts[0]?.personalized||120)},...forecasts.map((f,i)=>({x:predXs[i],y:y(f.upper)}))];
  const lower=[...forecasts.map((f,i)=>({x:predXs[i],y:y(f.lower)})).reverse(),{x:startX,y:y(pts.at(-1)?.glucose||forecasts[0]?.personalized||120)}];
  const band=[...upper,...lower].map((p,i)=>(i?'L':'M')+`${p.x},${p.y}`).join(' ')+' Z';
  return <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Observed and forecast glucose trajectory">
    {[100,140,180,220].filter(v=>v>min&&v<max).map(v=><g key={v}><line x1={pad} x2={W-pad} y1={y(v)} y2={y(v)} className="grid"/><text x="4" y={y(v)+4} className="axis">{v}</text></g>)}
    {forecasts.length>0 && <path d={band} className="uncertainty"/>}
    <path d={histPath} className="observed"/><path d={predPath} className="predicted"/>
    {forecasts.map((f,i)=><g key={f.horizon_min}><circle cx={predXs[i]} cy={y(f.personalized)} r="4.5" className="forecastDot"/><text x={predXs[i]-16} y={H-8} className="axis">+{f.horizon_min}m</text></g>)}
    <text x={pad} y="16" className="legend">Observed</text><text x={pad+80} y="16" className="legend predictedText">Forecast + uncertainty</text>
  </svg>
}

function Badge({children,tone='neutral'}:{children:React.ReactNode;tone?:string}){ return <span className={`badge ${tone}`}>{children}</span>; }

export default function Home(){
  const [patients,setPatients]=useState<Patient[]>([]); const [pid,setPid]=useState('HDT-027'); const [snap,setSnap]=useState<Snap|null>(null);
  const [running,setRunning]=useState(false); const [speed,setSpeed]=useState(1); const timer=useRef<ReturnType<typeof setInterval>|null>(null);
  const [tab,setTab]=useState<'twin'|'scenario'|'evidence'>('twin'); const [scenario,setScenario]=useState<any>(null); const [scenarioInputs,setScenarioInputs]=useState({carbs:70,activity:.2});
  const request=useCallback(async(path:string,opts?:RequestInit)=>{ const r=await fetch(API+path,opts); if(!r.ok) throw new Error(await r.text()); return r.json(); },[]);
  const reset=useCallback(async(id=pid)=>{ const d=await request(`/api/replay/${id}/reset`,{method:'POST'}); setSnap(d);setScenario(null); },[pid,request]);
  const step=useCallback(async(count=1)=>{ const d=await request(`/api/replay/${pid}/step?steps=${count}`,{method:'POST'}); setSnap(d); },[pid,request]);
  useEffect(()=>{request('/api/patients').then((p)=>{setPatients(p); if(p.length)setPid(p[0].patient_id);}).catch(console.error)},[request]);
  useEffect(()=>{ if(pid) reset(pid).catch(console.error); },[pid]);
  useEffect(()=>{ if(timer.current) clearInterval(timer.current); if(running){ timer.current=setInterval(()=>step(speed).catch(()=>setRunning(false)),1000);} return()=>{if(timer.current)clearInterval(timer.current)}; },[running,speed,step]);
  const riskAvailable=typeof snap?.excursion_risk==='number' && (snap?.forecasts.length??0)>0;
  const riskPct=riskAvailable?Math.round((snap!.excursion_risk as number)*100):null;
  const riskTone=riskPct===null?'neutral':riskPct>=70?'danger':riskPct>=45?'warn':riskPct>=20?'caution':'good';
  const improvement=useMemo(()=>{if(!snap)return null; const a=snap.model_metrics.population_mae,b=snap.model_metrics.personalized_mae; if(typeof a==='number'&&typeof b==='number'&&a>0)return ((a-b)/a*100);return null},[snap]);
  async function runScenario(){ const d=await request('/api/scenario',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient_id:pid,carbs_g:scenarioInputs.carbs,activity:scenarioInputs.activity})});setScenario(d); }
  if(!snap) return <main className="loading">Initializing HimanshuDigitalTwin…</main>;
  return <main>
    <header className="topbar">
      <div><div className="brandRow"><div className="mark">HD</div><div><h1>HimanshuDigitalTwin</h1><p>Synthetic patient replay · research prototype</p></div></div></div>
      <div className="headerActions"><Badge tone={snap.sync_status==='SYNCHRONIZED'?'good':'warn'}>● {snap.sync_status}</Badge><Badge>v{snap.twin_version.toLocaleString()}</Badge></div>
    </header>
    <div className="disclaimer">Research demonstration only · Default replay and risk are synthetic and uncalibrated · No diagnosis, dosing, or treatment recommendation.</div>
    <nav className="nav"><button className={tab==='twin'?'active':''} onClick={()=>setTab('twin')}>Twin workspace</button><button className={tab==='scenario'?'active':''} onClick={()=>setTab('scenario')}>Scenario lab</button><button className={tab==='evidence'?'active':''} onClick={()=>setTab('evidence')}>Evidence & safety</button></nav>
    <section className="controls card">
      <div><label>Patient</label><select value={pid} onChange={e=>{setRunning(false);setPid(e.target.value)}}>{patients.map(p=><option key={p.patient_id}>{p.patient_id}</option>)}</select></div>
      <div className="profileQuick"><span>{snap.patient.age} y</span><span>{snap.patient.sex}</span><span>BMI {snap.patient.bmi}</span><span>HbA1c {snap.patient.hba1c}%</span></div>
      <div className="playback"><button className="primary" onClick={()=>setRunning(v=>!v)}>{running?'Pause replay':'Run replay'}</button><button onClick={()=>step(1)}>Step</button><button onClick={()=>reset()}>Reset</button><select value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={1}>1×</option><option value={3}>3×</option><option value={6}>6×</option><option value={12}>12×</option></select></div>
    </section>

    {tab==='twin' && <>
      <section className="metricGrid">
        <div className="card metric"><div className="eyebrow">Current glucose</div><div className="big">{n(snap.reading.glucose)} <small>mg/dL</small></div><div className="subrow"><Badge tone={snap.reading.quality==='VALID'?'good':'warn'}>{snap.reading.quality}</Badge><span>{fmtTime(snap.timestamp)}</span></div></div>
        <div className="card metric"><div className="eyebrow">2-hour excursion risk · illustrative</div><div className={`big ${riskTone}`}>{riskPct===null?'Withheld':`${riskPct}%`}</div><div className="subrow"><Badge tone={riskTone}>{riskPct===null?'UNAVAILABLE':snap.risk_band}</Badge><span>{riskPct===null?'No valid forecast available':`${snap.confidence} confidence · not calibrated`}</span></div></div>
        <div className="card metric"><div className="eyebrow">Wearable state</div><div className="big">{n(snap.reading.heart_rate)} <small>bpm</small></div><div className="subrow"><span>Activity {Math.round(snap.reading.activity*100)}%</span><span>{snap.reading.steps_5m} steps/5m</span></div></div>
        <div className="card metric"><div className="eyebrow">Personalization</div><div className="big">{improvement===null?'Learning':`${Math.max(-99,improvement).toFixed(1)}%`}</div><div className="subrow"><span>{improvement===null?'Awaiting resolved forecasts':'MAE improvement vs population'}</span></div></div>
      </section>
      <section className="mainGrid">
        <div className="card chartCard"><div className="sectionHead"><div><h2>Observed → forecast trajectory</h2><p>Simulated replay with illustrative, uncalibrated intervals</p></div><Badge>{snap.forecasts.length ? `${snap.confidence} · simulated` : 'Forecast withheld'}</Badge></div><MiniChart history={snap.recent_history} forecasts={snap.forecasts}/><div className="forecastRows">{snap.forecasts.map(f=><div key={f.horizon_min}><span>+{f.horizon_min} min</span><strong>{f.personalized} mg/dL</strong><small>population {f.population} · interval {f.lower}–{f.upper}</small></div>)}</div></div>
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
