from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .data import generate_demo_patients
from .engine import ReplaySession
from .browser_sessions import BrowserSessionStore, BrowserSession, COOKIE_NAME, SESSION_TTL_SECONDS, SessionCapacityError
from .schemas import ScenarioRequest
from .fhir import extract_fhir_phenotype
from .artifacts import load_best_forecaster, load_transport_forecaster, verify_promotion_gate
from .real_replay import find_shanghai_file, build_shanghai_replay, find_cgmacros_file, build_cgmacros_replay

VERSION = '0.20.0'
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv('HDT_DATA_ROOT', str(BASE_DIR/'data'/'raw')))
STATIC_DIR = BASE_DIR / 'static'
INDEPENDENT_RESEARCH_PATH = BASE_DIR / 'reports' / 'research' / 'cgmacros_45_2026-10-12.json'

def independent_cgmacros_evidence():
    if not INDEPENDENT_RESEARCH_PATH.is_file():
        return None
    try:
        payload=json.loads(INDEPENDENT_RESEARCH_PATH.read_text(encoding='utf-8'))
    except (ValueError,OSError):
        return None
    # The independent 45-subject study is not an artifact/promotion manifest.
    return {**payload, 'production_model_promoted':False}


app = FastAPI(
    title='HimanshuDigitalTwin API',
    version=VERSION,
    description='Adaptive metabolic digital twin research prototype',
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000','http://127.0.0.1:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/')
def prototype_home():
    return FileResponse(STATIC_DIR / 'index.html')

app.mount('/prototype', StaticFiles(directory=str(STATIC_DIR)), name='prototype')


def _promotion(candidate: Path) -> dict | None:
    p=candidate/'promotion.json'
    if not p.exists():
        return None
    try:
        return verify_promotion_gate(candidate,json.loads(p.read_text()))
    except (json.JSONDecodeError,OSError):
        return {'status':'INVALID','runtime_promotion_allowed':False}


def _select_model():
    # Explicit override is useful for research/debugging and is always surfaced in model status.
    if os.getenv('HDT_MODEL_DIR'):
        candidate=Path(os.environ['HDT_MODEL_DIR'])
        model,label=load_best_forecaster(candidate)
        if not label.startswith('demo-heuristic'):
            gate=_promotion(candidate)
            suffix='promoted' if gate and gate.get('runtime_promotion_allowed') else 'explicit-unpromoted-override'
            return model, f'{label}; {suffix}', candidate

    # Automatic runtime promotion is deliberately strict: only the canonical submission
    # artifacts are eligible, and only after the evidence gate writes PASS. Legacy/research
    # artifacts never silently replace the demo model.
    candidate=BASE_DIR/'models'/'submission'
    gate=_promotion(candidate)
    if gate and gate.get('runtime_promotion_allowed'):
        model,label=load_best_forecaster(candidate)
        if not label.startswith('demo-heuristic'):
            return model, f'{label}; promoted-by-evidence-gate', candidate

    model,label=load_best_forecaster(None)
    return model,label,None


MODEL, MODEL_LABEL, ACTIVE_MODEL_DIR = _select_model()
_transport_gate=_promotion(ACTIVE_MODEL_DIR) if ACTIVE_MODEL_DIR else None
_allow_transport=bool(_transport_gate and _transport_gate.get('runtime_external_transport_allowed')) or os.getenv('HDT_ALLOW_UNPROMOTED_TRANSPORT')=='1'
TRANSPORT_MODEL, TRANSPORT_MODEL_LABEL = load_transport_forecaster(ACTIVE_MODEL_DIR) if (ACTIVE_MODEL_DIR and _allow_transport) else load_transport_forecaster(None)
if ACTIVE_MODEL_DIR and not _allow_transport:
    TRANSPORT_MODEL_LABEL += '; external-transport-not-promoted'
DEMO = generate_demo_patients()
BROWSER_SESSIONS = BrowserSessionStore(DEMO, MODEL, MODEL_LABEL)


@app.middleware("http")
async def browser_demo_session(request: Request, call_next):
    # For the local judge demo, a browser owns its own ephemeral replay state.
    # This cookie is not proof of identity and must never protect patient records.
    try:
        token, state = BROWSER_SESSIONS.obtain(request.cookies.get(COOKIE_NAME))
    except SessionCapacityError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    request.state.demo_session = state
    response = await call_next(request)
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_TTL_SECONDS, httponly=True,
        secure=request.url.scheme == "https", samesite="lax", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _browser_state(request: Request) -> BrowserSession:
    return request.state.demo_session


@app.get('/api/health')
def health():
    return {
        'status':'ok',
        'project':'HimanshuDigitalTwin',
        'version':VERSION,
        'mode':'research-prototype',
        'model_source':MODEL_LABEL,
    }


@app.get('/api/patients')
def patients(request: Request):
    state = _browser_state(request)
    with state.lock:
        return [s.profile for s in state.patients.values()]



@app.get('/api/real/status')
def real_data_status():
    shanghai_root = DATA_ROOT/'shanghai'
    cg_root = DATA_ROOT/'cgmacros'
    from .shanghai import discover_shanghai_subject_files
    from .cgmacros import discover_subject_files
    sh = discover_shanghai_subject_files(shanghai_root) if shanghai_root.exists() else []
    cg = discover_subject_files(cg_root) if cg_root.exists() else []
    return {
        'data_root': str(DATA_ROOT),
        'shanghai_subjects_available': len(sh),
        'cgmacros_subjects_available': len(cg),
        'note':'Raw research datasets are not bundled. Download them with scripts/download_real_data.py.',
    }




@app.get('/api/real/subjects')
def real_subjects():
    from .shanghai import discover_shanghai_subject_files
    from .cgmacros import discover_subject_files, normalize_subject_id
    sh_root = DATA_ROOT/'shanghai'
    cg_root = DATA_ROOT/'cgmacros'
    sh = discover_shanghai_subject_files(sh_root) if sh_root.exists() else []
    cg = discover_subject_files(cg_root) if cg_root.exists() else []
    return {
        'shanghai': [f'SH-{int(p.stem)}' for p in sh if p.stem.isdigit()],
        'cgmacros': [normalize_subject_id(p.stem) for p in cg],
    }

@app.post('/api/real/shanghai/load/{subject_id}')
def load_real_shanghai(subject_id: str, request: Request):
    try:
        f = find_shanghai_file(DATA_ROOT/'shanghai', subject_id)
        profile, stream, cadence = build_shanghai_replay(f, BASE_DIR/'data'/'reference'/'shanghai_t2dm_metadata.csv')
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc))
    pid = profile['patient_id']
    state = _browser_state(request)
    with state.lock:
        state.patients[pid] = ReplaySession(pid, profile, stream, model=TRANSPORT_MODEL, model_label=TRANSPORT_MODEL_LABEL, cadence_min=cadence)
        return state.patients[pid].step(1)


@app.post('/api/real/cgmacros/load/{subject_id}')
def load_real_cgmacros(subject_id: str, request: Request):
    try:
        root = DATA_ROOT/'cgmacros'
        f = find_cgmacros_file(root, subject_id)
        profile, stream, cadence = build_cgmacros_replay(f, root)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc))
    pid = profile['patient_id']
    state = _browser_state(request)
    with state.lock:
        state.patients[pid] = ReplaySession(pid, profile, stream, model=MODEL, model_label=MODEL_LABEL, cadence_min=cadence)
        return state.patients[pid].step(1)

@app.post('/api/replay/{patient_id}/reset')
def reset(patient_id: str, request: Request):
    state = _browser_state(request)
    with state.lock:
        if patient_id not in state.patients: raise HTTPException(404, 'Unknown patient')
        session = state.patients[patient_id]
        session.reset()
        return session.step(1)


@app.post('/api/replay/{patient_id}/step')
def step(patient_id: str, request: Request, steps: int = 1):
    state = _browser_state(request)
    with state.lock:
        if patient_id not in state.patients: raise HTTPException(404, 'Unknown patient')
        return state.patients[patient_id].step(min(max(1, steps), 24))


@app.get('/api/replay/{patient_id}/snapshot')
def snapshot(patient_id: str, request: Request):
    state = _browser_state(request)
    with state.lock:
        if patient_id not in state.patients: raise HTTPException(404, 'Unknown patient')
        return state.patients[patient_id].snapshot()


# Competition demo is intentionally limited to bundled synthetic profiles.
# It resets the selected patient and advances to a reproducible clinical story
# without changing any evidence gate or claiming real patient measurements.
DEMO_CHAPTERS = {
    'baseline': (0, 'Initial EHR + wearable/CGM state'),
    'breakfast': (75, 'Breakfast response and forecast'),
    'lunch': (315, 'Lunch-associated glucose evolution'),
    'verification': (395, 'Future observations resolve earlier predictions'),
    'sensor_gap': (445, 'Missing CGM readings and safe abstention'),
    'recovery': (475, 'Post-outage synchronization and audit trail'),
}


@app.get('/api/demo/chapters')
def demo_chapters():
    return {'simulation_only': True, 'patient_id': 'HDT-027',
            'chapters': [{'id': name, 'minute': minute, 'description': desc}
                         for name, (minute, desc) in DEMO_CHAPTERS.items()],
            'note': 'Deterministic simulated walkthrough, not a clinical replay or trained-model validation.'}


@app.post('/api/demo/chapter/{chapter_id}')
def demo_chapter(chapter_id: str, request: Request, patient_id: str = 'HDT-027'):
    if chapter_id not in DEMO_CHAPTERS:
        raise HTTPException(404, 'Unknown demo chapter')
    if patient_id not in DEMO:
        raise HTTPException(400, 'Guided demo requires a bundled synthetic patient')
    state = _browser_state(request)
    with state.lock:
        session = state.patients[patient_id]
        session.reset()
        minutes, description = DEMO_CHAPTERS[chapter_id]
        steps = min(len(session.stream), minutes // session.cadence_min + 1)
        snap = session.step(steps)
        return {'chapter': chapter_id, 'description': description,
                'simulation_only': True, 'snapshot': snap,
                'note': 'Synthetic replay. Do not interpret the demonstration as validated patient-specific predictions.'}


@app.post('/api/scenario')
def scenario(req: ScenarioRequest, request: Request):
    state = _browser_state(request)
    with state.lock:
        if req.patient_id not in state.patients: raise HTTPException(404, 'Unknown patient')
        baseline, scenario_values = state.patients[req.patient_id].scenario(req.carbs_g, req.activity, req.glucose)
        return {
            'baseline': baseline,
            'scenario': scenario_values,
            'note': 'Exploratory model-based scenario estimate. Not a treatment recommendation or causal effect estimate.',
        }


@app.post('/api/fhir/ingest')
def fhir_ingest(bundle: dict):
    try:
        phenotype = extract_fhir_phenotype(bundle)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {
        'status':'parsed',
        'phenotype':phenotype,
        'note':'FHIR ingestion demonstrates interoperability only; it is not merged with unrelated sensor subjects.',
    }


@app.get('/api/model/status')
def model_status():
    metrics = None
    if ACTIVE_MODEL_DIR is not None:
        p = ACTIVE_MODEL_DIR / 'metrics.json'
        if p.exists():
            try:
                metrics = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                metrics = {'error':'metrics.json could not be parsed'}
    evidence_manifest = None
    evidence_path = BASE_DIR / 'reports' / 'evidence_manifest.json'
    if evidence_path.exists():
        try:
            evidence_manifest = json.loads(evidence_path.read_text())
        except (json.JSONDecodeError, OSError):
            evidence_manifest = {'error':'evidence_manifest.json could not be parsed'}
    # Runtime truth must follow the gate that belongs to the *active* artifact
    # directory. Never use a stale reports/submission_gate.json to authorize
    # an explicitly loaded, unhashed, or otherwise unapproved artifact directory.
    gate = _promotion(ACTIVE_MODEL_DIR) if ACTIVE_MODEL_DIR is not None else None
    return {
        'active_model': MODEL_LABEL,
        'shanghai_transport_model': TRANSPORT_MODEL_LABEL,
        'artifact_directory': str(ACTIVE_MODEL_DIR) if ACTIVE_MODEL_DIR else None,
        'real_artifacts_active': ACTIVE_MODEL_DIR is not None,
        'metrics': metrics,
        'evidence_manifest_present': evidence_manifest is not None,
        'independent_research_evidence_available': independent_cgmacros_evidence() is not None,
        'submission_gate': gate,
        'runtime_promotion_allowed': bool(ACTIVE_MODEL_DIR is not None and gate and gate.get('runtime_promotion_allowed')),
        'runtime_personalization_allowed': bool(ACTIVE_MODEL_DIR is not None and gate and gate.get('runtime_personalization_allowed')),
        'runtime_interval_allowed': bool(ACTIVE_MODEL_DIR is not None and gate and gate.get('runtime_interval_allowed')),
        'external_validation_available': bool(evidence_manifest and evidence_manifest.get('external')),
        'runtime_external_transport_allowed': bool(ACTIVE_MODEL_DIR is not None and gate and gate.get('runtime_external_transport_allowed')),
        'external_interval_validated': bool(gate and gate.get('external_interval_validated')),
        'evidence_manifest': evidence_manifest,
    }


@app.get('/api/research/evidence')
def research_evidence():
    return {
        'source': 'independent real CGMacros benchmark, not the canonical application training pipeline',
        'research_only': True,
        'active_model_unchanged': True,
        'data': independent_cgmacros_evidence(),
    }


@app.get('/api/evidence')
def evidence():
    return {
        'project':'HimanshuDigitalTwin',
        'prototype_data':'Built-in replay patients are reproducible simulation and are labelled as such.',
        'real_data_status':{
            'ShanghaiT2DM':'adapter + cohort metadata + leakage-safe training pipeline implemented',
            'CGMacros':'multimodal adapter + grouped training/risk pipeline implemented',
            'FHIR':'interoperability parser implemented; never joined to unrelated sensor subjects',
        },
        'active_model':MODEL_LABEL,
        'independent_real_cgmacros_research': independent_cgmacros_evidence(),
        'evaluation_rules':[
            'Never split adjacent CGM rows randomly across train/test',
            'Group all visits/recording periods by patient ID',
            'Compare every glucose forecaster against persistence',
            'Report pooled and macro-subject MAE/RMSE by horizon',
            'Evaluate 120-minute excursion risk separately with AUROC/AUPRC/Brier',
            'Personalization must use out-of-fold subjects and chronological calibration/evaluation',
            'Never claim Indian clinical validation without representative Indian cohort validation',
        ],
        'safety':[
            'Research prototype only','No diagnosis','No dosing or treatment recommendation',
            'Scenario Lab is associational/model-based, not causal',
        ],
        'twin_criteria':[
            'patient-specific state','continuous synchronization','future prediction',
            'prediction verification','online personal residual adaptation',
            'uncertainty and data-quality awareness','auditable versioned timeline',
        ],
    }


@app.websocket('/ws/replay/{patient_id}')
async def ws_replay(websocket: WebSocket, patient_id: str):
    # WebSockets do not pass through the HTTP cookie-issuing middleware.
    state = BROWSER_SESSIONS.existing(websocket.cookies.get(COOKIE_NAME))
    if state is None:
        await websocket.close(code=4401)
        return
    with state.lock:
        present = patient_id in state.patients
    if not present:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    try:
        while True:
            with state.lock:
                snap = state.patients[patient_id].step(1)
            await websocket.send_json(snap)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
