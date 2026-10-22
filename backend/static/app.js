const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let pid='HDT-027', snap=null, timer=null, running=false;
const api=async(path,opts)=>{const r=await fetch(path,opts); if(!r.ok)throw new Error(await r.text()); return r.json()};
const fmtTime=v=>new Date(v).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
const num=(v,d=0)=>(v===null||v===undefined||v==='')?'—':(Number.isFinite(Number(v))?Number(v).toFixed(d):'—');
const text=(v,fallback='—')=>(v===null||v===undefined||v==='')?fallback:String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const badgeTone=(el,tone)=>{el.className='badge '+tone};

async function init(){
 const patients=await api('/api/patients');
 if(!Array.isArray(patients)||patients.length===0)throw new Error('No bundled demo patients are available.');
 $('#patientSelect').innerHTML=patients.map(p=>`<option>${text(p.patient_id)}</option>`).join('');
 pid=patients[0].patient_id;
 // Judge demo must work even if optional cohort enumeration or research reports fail.
 await reset();
 const extras=await Promise.allSettled([refreshRealSubjects(),refreshModelEvidence()]);
 if(extras[0].status==='rejected'){
  $('#realStatus').textContent='Optional research-cohort lookup unavailable; synthetic demo remains available.';
  $('#loadRealBtn').disabled=true;
 }
 if(extras[1].status==='rejected'){
  $('#modelEvidence').textContent='Optional model evidence could not be loaded; see the repository evidence index.';
  $('#realResearch').textContent='Independent research report unavailable from the running API.';
 }
}
async function refreshRealSubjects(){
 const d=await api('/api/real/subjects');
 const opts=[...d.shanghai.map(x=>({id:x,kind:'ShanghaiT2DM'})),...d.cgmacros.map(x=>({id:x,kind:'CGMacros'}))];
 $('#realSubject').innerHTML=opts.length?opts.map(o=>`<option value="${text(o.id)}" data-kind="${text(o.kind)}">${text(o.kind)} · ${text(o.id)}</option>`).join(''):'<option value="">No local real cohort downloaded</option>';
 $('#loadRealBtn').disabled=!opts.length;
 const cgReady=d.cgmacros.length===45?'CGMacros complete':'CGMacros incomplete'; const shReady=d.shanghai.length===100?'Shanghai complete':'Shanghai incomplete'; $('#realStatus').textContent=opts.length?`${d.shanghai.length}/100 Shanghai · ${d.cgmacros.length}/45 CGMacros · ${cgReady} · ${shReady}`:'Download a cohort to enable real replay';
}
async function refreshModelEvidence(){
 const d=await api('/api/model/status');
 const gate=d.submission_gate?.status||'NOT RUN'; const promoted=d.runtime_promotion_allowed?'PASS — eligible':'NO'; $('#modelEvidence').innerHTML=`<div><span>Active runtime</span><b>${text(d.active_model)}</b></div><div><span>Real artifacts active</span><b>${d.real_artifacts_active?'YES':'NO — demo fallback'}</b></div><div><span>Evidence promotion gate</span><b>${gate}</b></div><div><span>Automatic promotion</span><b>${promoted}</b></div><div><span>Primary evidence manifest</span><b>${d.evidence_manifest_present?'AVAILABLE':'NOT RUN'}</b></div><div><span>Independent real CGMacros research</span><b>${d.independent_research_evidence_available?'45 SUBJECTS — RESEARCH ONLY':'NOT ATTACHED'}</b></div><div><span>Patient-specific adaptation gate</span><b>${d.runtime_personalization_allowed?'PASS':'NOT APPROVED'}</b></div><div><span>Trained 80% interval gate</span><b>${d.runtime_interval_allowed?'PASS':'NOT APPROVED'}</b></div><div><span>External Shanghai validation</span><b>${d.external_validation_available?'AVAILABLE':'NOT RUN'}</b></div><div><span>Artifact directory</span><b>${text(d.artifact_directory)}</b></div>`;
 const holder=$('#realResearch');
 if(holder){
  try{
   const study=await api('/api/research/evidence');
   const r=study.data;
   if(r?.horizons){
    const table=[30,60,120].map(h=>{const z=r.horizons[String(h)];if(!z)return '';
      return `<tr><td>${h} min</td><td>${num(z.mae,2)}</td><td>${num(z.persistence,2)}</td><td>${num(z.improvement,2)}%</td><td>${num(z.coverage*100,1)}%</td><td>${z.adaptive_wins}/10</td></tr>`;}).join('');
    const evt=r.event_onset_120||{};
    holder.innerHTML=`<p class="muted">Actual CGMacros research data: 45 participants, 5 patient-stratified test splits. Independent benchmark — <b>not the active runtime model</b>, and not clinical validation.</p><div class="research-scroll"><table class="research-table"><thead><tr><th>Horizon</th><th>ML MAE</th><th>Persistence</th><th>Gain</th><th>80% coverage</th><th>Helped by adaptation</th></tr></thead><tbody>${table}</tbody></table></div><p class="muted">120-minute new-onset AUROC: ${num(evt.auroc,3)} · interval and personalization validation <b>NOT APPROVED</b>. Shanghai external validation pending.</p>`;
   }else holder.textContent='Independent real research summary unavailable.';
  }catch(error){holder.textContent='Independent research summary could not be loaded.';}
 }

}
let mutationQueue=Promise.resolve(),stepQueued=false;
function queueReplay(action){
 const task=mutationQueue.then(action,action);
 mutationQueue=task.then(()=>undefined,()=>undefined);
 return task;
}
function displayReplayError(error){
 running=false;clearInterval(timer);
 $('#runBtn').textContent='Run replay';
 $('#dataBanner').textContent='Replay problem: '+(error instanceof Error?error.message:String(error))+' · Try Reset.';
}
async function reset(){
 running=false;clearInterval(timer);$('#runBtn').textContent='Run replay';
 try{
  const target=pid;
  const result=await queueReplay(()=>api(`/api/replay/${target}/reset`,{method:'POST'}));
  if(target===pid){snap=result;render();}
 }catch(error){displayReplayError(error);throw error;}
}
async function step(n=1){
 if(stepQueued)return;
 stepQueued=true;
 try{
  const target=pid;
  const result=await queueReplay(()=>api(`/api/replay/${target}/step?steps=${n}`,{method:'POST'}));
  if(target===pid){snap=result;render();}
 }catch(error){displayReplayError(error);}
 finally{stepQueued=false;}
}
function render(){
 if(!snap)return;
 $('#versionBadge').textContent='v'+snap.twin_version.toLocaleString(); $('#syncBadge').textContent='● '+snap.sync_status; badgeTone($('#syncBadge'),snap.sync_status==='SYNCHRONIZED'?'good':'warn');
 const source=snap.patient.data_source||snap.patient.cohort||'Simulation'; $('#quickProfile').innerHTML=`<span>${text(snap.patient.age)} y</span><span>${text(snap.patient.sex)}</span><span>BMI ${num(snap.patient.bmi,1)}</span><span>HbA1c ${num(snap.patient.hba1c,1)}%</span><span>${text(source)}</span>`; $('#dataBanner').textContent=source==='CGMacros'||source==='ShanghaiT2DM'?`Real research replay · ${source} · not clinical use`:'Research demonstration only · No diagnosis, dosing, or treatment recommendation · Current patient is simulated research replay.';
 $('#glucose').innerHTML=`${num(snap.reading.glucose)} <small>mg/dL</small>`; $('#qualityBadge').textContent=snap.reading.quality; badgeTone($('#qualityBadge'),snap.reading.quality==='VALID'?'good':'warn'); $('#timeNow').textContent=fmtTime(snap.timestamp);
 const availableRisk=typeof snap.excursion_risk==='number'&&Number.isFinite(snap.excursion_risk), rp=availableRisk?Math.round(snap.excursion_risk*100):null, state=snap.alert_state||snap.risk_band, tone=state==='ACTIVE EXCURSION'?'danger':!availableRisk?'warn':state==='ALERT'?'warn':rp>=70?'danger':rp>=45?'warn':rp>=20?'caution':'good'; $('#risk').textContent=availableRisk?rp+'%':'—'; $('#risk').className='big '+tone; $('#riskBadge').textContent=state; badgeTone($('#riskBadge'),tone); const rawAt=snap.alert_probability_threshold; const at=rawAt==null?null:Number(rawAt); $('#confidence').textContent='Data: '+snap.confidence+' · '+(at!==null&&Number.isFinite(at)?`research alert ≥ ${Math.round(at*100)}%`:'threshold unvalidated'); const isResearchModel=Boolean(snap.model_info?.trained); $('#riskModelFlag').textContent=isResearchModel?'RESEARCH MODEL · NOT FOR CLINICAL USE':'SIMULATED · UNCALIBRATED RISK';
 $('#heartRate').innerHTML=`${num(snap.reading.heart_rate)} <small>bpm</small>`; $('#wearableSub').innerHTML=`<span>Activity ${snap.reading.activity==null?'—':Math.round(Number(snap.reading.activity)*100)+'%'}</span><span>${text(snap.reading.steps_5m)} steps/5m</span>`;
 const a=snap.model_metrics.population_mae,b=snap.model_metrics.personalized_mae; const imp=(typeof a==='number'&&typeof b==='number'&&a>0)?((a-b)/a*100):null; $('#improvement').textContent=imp===null?'Learning':imp.toFixed(1)+'%'; $('#resolvedCount').textContent=snap.model_metrics.resolved_forecasts+' resolved';
 $('#chartConfidence').textContent='Sensor/data confidence: '+snap.confidence; drawChart();
 $('#forecastRows').innerHTML=snap.forecasts.length?(snap.reading.quality!=='VALID'?'<p class="muted">Latest CGM sample is not verified. Estimates use earlier data; the current glucose is not a measured observation.</p>':'')+snap.forecasts.map(f=>`<div><span>+${f.horizon_min} min</span><strong>${f.personalized} mg/dL</strong><small>population ${f.population} · interval ${f.lower}–${f.upper} · ${text(f.interval_method)}</small></div>`).join(''):'<p class="muted">Forecast withheld: '+text(snap.abstention_reason)+'</p>';
 $('#drivers').innerHTML=snap.explanations.map(e=>`<div><span>${text(e.factor)}</span><div class="bar"><i class="${e.direction==='down'?'down':''}" style="width:${Math.max(6,e.strength*100)}%"></i></div><b>${e.direction==='up'?'↑':'↓'}</b></div>`).join('');
 $('#currentFacts').innerHTML=`<div><span>Active carbs</span><b>${snap.reading.carbs_active_g==null?'—':num(snap.reading.carbs_active_g,1)+' g'}</b></div><div><span>Minutes since meal</span><b>${text(snap.reading.minutes_since_meal)}</b></div><div><span>Dataset</span><b>${text(source)}</b></div>`;
 $('#learning').innerHTML=`<div><span>Population MAE</span><strong>${typeof a==='number'?a+' mg/dL':'collecting'}</strong></div><div><span>Personalized MAE</span><strong>${typeof b==='number'?b+' mg/dL':'collecting'}</strong></div><div><span>Resolved forecasts</span><strong>${snap.model_metrics.resolved_forecasts}</strong></div>`;
 $('#biases').innerHTML=Object.entries(snap.personal_bias).filter(([k])=>k.includes('postmeal')).map(([k,v])=>`<div><span>${k.replace('_',' · +')}m</span><b>${v>0?'+':''}${v}</b></div>`).join('');
 $('#timeline').innerHTML=snap.timeline.slice(0,8).map(t=>`<div><time>${fmtTime(t.timestamp)}</time><span class="event ${t.type.toLowerCase()}">${t.type}</span><p>${text(t.message)}</p></div>`).join('');
 $('#provenance').innerHTML=`<div><span>Current stream</span><b>${text(snap.reading.provenance?.stream)}</b></div><div><span>Glucose channel</span><b>${text(snap.reading.provenance?.glucose)}</b></div><div><span>Wearable channel</span><b>${text(snap.reading.provenance?.activity,'not available')}</b></div><div><span>Runtime model</span><b>${text(snap.model_info?.source||snap.model_info?.mode||'unknown')}</b></div><div><span>Validation</span><b>${text(snap.model_info?.validation,'demo only')}</b></div><div><span>Twin version</span><b>#${snap.twin_version}</b></div>`;
}
function drawChart(){
 const svg=$('#trajectory'), W=820,H=255,pad=35;
 const history=Array.isArray(snap.recent_history)?snap.recent_history:[];
 const forecasts=Array.isArray(snap.forecasts)?snap.forecasts:[];
 const now=Date.parse(snap.timestamp);
 const startTime=history.length?Date.parse(history[0].timestamp):now;
 const t0=Number.isFinite(startTime)?Math.min(startTime,now):now-5*60*1000;
 const endTime=now+120*60*1000;
 const xTime=t=>pad+(Math.max(t0,Math.min(endTime,t))-t0)/Math.max(1,endTime-t0)*(W-2*pad);
 const actual=history.filter(p=>p.quality==='VALID'&&typeof p.glucose==='number'&&Number.isFinite(p.glucose));
 const values=[...actual.map(p=>p.glucose),...forecasts.flatMap(f=>[f.personalized,f.lower,f.upper].filter(Number.isFinite))];
 const low=Math.min(90,...values)-10,high=Math.max(180,...values)+10;
 const y=v=>H-pad-(v-low)/Math.max(1,high-low)*(H-2*pad);
 // Do not connect across missing/outlier/imputed CGM. Engine history may carry
 // numerical glucose forward internally; that is not an observed measurement.
 let observedPath='',penUp=true;
 for(const p of history){
  const t=Date.parse(p.timestamp);
  if(p.quality!=='VALID'||typeof p.glucose!=='number'||!Number.isFinite(t)){
   penUp=true;continue;
  }
  observedPath+=(penUp?'M':'L')+xTime(t)+','+y(p.glucose)+' ';
  penUp=false;
 }
 const hasMeasuredCurrent=snap.reading?.quality==='VALID'&&
  typeof snap.reading?.glucose==='number'&&Number.isFinite(snap.reading.glucose);
 const showForecast=hasMeasuredCurrent&&forecasts.length>0;
 const forecastPoints=showForecast?forecasts.filter(f=>Number.isFinite(f.personalized)).map(f=>({
  x:xTime(now+f.horizon_min*60000),y:y(f.personalized),upper:y(f.upper),lower:y(f.lower),h:f.horizon_min
 })):[];
 const first=showForecast?{x:xTime(now),y:y(snap.reading.glucose)}:null;
 const forecastPath=first?'M'+first.x+','+first.y+' '+forecastPoints.map(p=>'L'+p.x+','+p.y).join(' '):'';
 const region=first&&forecastPoints.length?
  'M'+first.x+','+first.y+' '+forecastPoints.map(p=>'L'+p.x+','+p.upper).join(' ')+
  ' '+[...forecastPoints].reverse().map(p=>'L'+p.x+','+p.lower).join(' ')+
  ' L'+first.x+','+first.y+' Z':'';
 const grid=[100,140,180,220].filter(v=>v>low&&v<high).map(v=>
  '<line x1="'+pad+'" x2="'+(W-pad)+'" y1="'+y(v)+'" y2="'+y(v)+'" class="grid"/>'+
  '<text x="3" y="'+(y(v)+4)+'" class="axis">'+v+'</text>').join('');
 const nodes=forecastPoints.map(p=>'<circle cx="'+p.x+'" cy="'+p.y+'" r="4.5" class="forecastDot"/>'+
  '<text x="'+(p.x-18)+'" y="'+(H-6)+'" class="axis">+'+p.h+'m</text>').join('');
 const missing=history.some(p=>p.quality!=='VALID');
 const legend='<text x="'+pad+'" y="16" class="legend">Measured CGM (valid only)</text>'+
  (showForecast?'<text x="'+(pad+210)+'" y="16" class="legend predictedText">Illustrative forecast</text>':'')+
  (missing?'<text x="'+(W-170)+'" y="16" class="legend">Gaps omitted</text>':'');
 svg.innerHTML=grid+(region?'<path d="'+region+'" class="uncertainty"/>':'')+
  '<path d="'+observedPath.trim()+'" class="observed"/>'+
  (forecastPath?'<path d="'+forecastPath+'" class="predicted"/>':'')+nodes+legend;
 svg.setAttribute('aria-label',showForecast?
  'Valid CGM history with gaps omitted and illustrative 30, 60 and 120-minute projections on a true elapsed-time scale':
  'Valid CGM history with missing readings omitted; forecast is withheld');
}

$('#judgeDemoBtn').addEventListener('click',async()=>{
 running=false;clearInterval(timer);$('#runBtn').textContent='Run replay';
 const button=$('#judgeDemoBtn'),chapter=$('#judgeChapter').value;
 button.disabled=true;button.textContent='Loading chapter…';
 try{
  const d=await queueReplay(()=>api(`/api/demo/chapter/${chapter}`,{method:'POST'}));
  pid=d.snapshot.patient.patient_id;
  $('#patientSelect').value=pid;
  snap=d.snapshot;render();
  $('#dataBanner').textContent='GUIDED SYNTHETIC DEMO · '+d.description+' · Not a clinical model validation.';
 }catch(error){$('#dataBanner').textContent='Guided demo error: '+error.message;}
 finally{button.disabled=false;button.textContent='Show chapter';}
});
$('#patientSelect').addEventListener('change',async e=>{running=false;clearInterval(timer);$('#runBtn').textContent='Run replay';pid=e.target.value;await reset()});
$('#runBtn').addEventListener('click',()=>{running=!running;$('#runBtn').textContent=running?'Pause replay':'Run replay';clearInterval(timer);if(running)timer=setInterval(()=>step(Number($('#speedSelect').value)),1000)});
$('#stepBtn').addEventListener('click',()=>step(1)); $('#resetBtn').addEventListener('click',()=>reset().catch(()=>{}));
$('#loadRealBtn').addEventListener('click',async()=>{const sel=$('#realSubject'), id=sel.value;if(!id)return;const kind=sel.selectedOptions[0]?.dataset.kind;running=false;clearInterval(timer);const path=kind==='CGMacros'?`/api/real/cgmacros/load/${id}`:`/api/real/shanghai/load/${id}`;snap=await queueReplay(()=>api(path,{method:'POST'}));pid=snap.patient.patient_id;let opt=[...$('#patientSelect').options].find(o=>o.value===pid);if(!opt){opt=document.createElement('option');opt.value=pid;opt.textContent=pid;$('#patientSelect').appendChild(opt)}$('#patientSelect').value=pid;render()});
$$('.tab').forEach(b=>b.addEventListener('click',()=>{
 $$('.tab').forEach(x=>x.classList.remove('active'));
 b.classList.add('active');
 $$('.view').forEach(v=>v.classList.add('hidden'));
 $('#view'+b.dataset.tab[0].toUpperCase()+b.dataset.tab.slice(1)).classList.remove('hidden');
}));
$('#carbSlider').addEventListener('input',e=>$('#carbLabel').textContent=e.target.value+' g'); $('#activitySlider').addEventListener('input',e=>$('#activityLabel').textContent=Math.round(e.target.value*100)+'%');
$('#scenarioBtn').addEventListener('click',async()=>{const d=await api('/api/scenario',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient_id:pid,carbs_g:Number($('#carbSlider').value),activity:Number($('#activitySlider').value)})}); $('#scenarioResult').className='scenario-rows'; $('#scenarioResult').innerHTML=d.baseline.map((b,i)=>{const s=d.scenario[i],delta=s.personalized-b.personalized;return `<div class="scenario-row"><span>+${b.horizon_min} min</span><div><small>Current</small><strong>${b.personalized}</strong></div><div><small>Scenario</small><strong>${s.personalized}</strong></div><div class="${delta>0?'upText':'downText'}">${delta>0?'+':''}${delta.toFixed(1)} mg/dL</div></div>`}).join('')+`<p class="safety-note">${d.note}</p>`});
init().catch(e=>{const pre=document.createElement('pre');pre.style.color='white';pre.textContent='Startup error: '+(e instanceof Error?e.message:String(e));document.body.replaceChildren(pre)});
