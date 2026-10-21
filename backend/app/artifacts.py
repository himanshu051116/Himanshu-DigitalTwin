from __future__ import annotations
from pathlib import Path
from typing import Any
from sklearn.pipeline import Pipeline
import math
import hashlib
import joblib
import numpy as np
import pandas as pd

from .model import HORIZONS, PopulationForecaster


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def verify_promotion_gate(model_dir: Path, gate: dict | None) -> dict | None:
    """Do not trust stale PASS markers after artifacts are modified/retrained.

    SHA-256 detects mismatched model/gate files, not malicious joblib payloads.
    Only load artifacts from trusted directories.
    """
    if gate is None: return None
    # A stale or manually contradictory marker may carry a true runtime flag
    # while its overall primary evidence is FAIL/TRAINING. Never promote it.
    if gate.get('status') != 'PASS':
        gate={**gate, 'runtime_promotion_allowed':False}
    # Feature-level approvals can never remain active after the population
    # candidate is denied, even if an old/manual JSON marker contradicts itself.
    if not gate.get('runtime_promotion_allowed'):
        gate={**gate,'runtime_personalization_allowed':False,
              'runtime_interval_allowed':False}
    if not (gate.get('runtime_promotion_allowed') or gate.get('runtime_external_transport_allowed')):
        return gate
    hashes=gate.get('artifact_sha256') or {}
    required=[f'forecast_{h}.joblib' for h in HORIZONS]+['event_120.joblib'] if gate.get('runtime_promotion_allowed') else []
    if gate.get('runtime_external_transport_allowed'):
        required += [f'transport_forecast_{h}.joblib' for h in HORIZONS]+['transport_event_120.joblib']
    invalid=[]
    for name in required:
        path=Path(model_dir)/name
        if not hashes.get(name) or not path.is_file():
            invalid.append(name+': missing file or expected digest')
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=hashes[name]:
            invalid.append(name+': SHA-256 mismatch')
    if invalid:
        return {**gate,'status':'INVALID_INTEGRITY',
            'runtime_promotion_allowed':False,
            'runtime_personalization_allowed':False,
            'runtime_interval_allowed':False,
            'runtime_external_transport_allowed':False,
            'external_interval_validated':False,
            'integrity_errors':invalid}
    return gate


class ArtifactForecaster(PopulationForecaster):
    """Loads subject-grouped research model artifacts while preserving the engine contract.

    The class is intentionally tolerant of missing optional artifacts. Forecast artifacts
    are required for all three horizons; a trained risk artifact is optional. If risk is
    absent, the parent class's clearly-labelled demonstration risk fallback is used.
    """

    def __init__(self, model_dir: str | Path):
        self.model_dir = Path(model_dir)
        self.forecast_artifacts: dict[int, dict] = {}
        for h in HORIZONS:
            p = self.model_dir / f'forecast_{h}.joblib'
            if not p.exists():
                raise FileNotFoundError(f'Missing forecast artifact: {p}')
            art = joblib.load(p)
            if int(art.get('horizon', h)) != h or 'model' not in art or 'features' not in art:
                raise ValueError(f'Invalid forecast artifact: {p}')
            self.forecast_artifacts[h] = art
        event_path = self.model_dir / 'event_120.joblib'
        legacy_risk_path = self.model_dir / 'risk_120.joblib'
        chosen = event_path if event_path.exists() else legacy_risk_path
        self.risk_artifact = joblib.load(chosen) if chosen.exists() else None
        first = self.forecast_artifacts[30]
        self.source = str(first.get('source', first.get('training_cohort', 'trained-research-artifact')))
        self.validation = first.get('validation', first.get('evaluation', 'subject-grouped'))
        self.promotion = None
        promotion_path = self.model_dir / 'promotion.json'
        if promotion_path.exists():
            import json
            try:
                self.promotion = verify_promotion_gate(self.model_dir,json.loads(promotion_path.read_text()))
            except (json.JSONDecodeError, OSError):
                self.promotion = {'status':'INVALID','runtime_promotion_allowed':False}
        checks = {c.get('name'):c for c in (self.promotion or {}).get('checks', [])}
        self.personalization_enabled = bool(
            self.promotion and self.promotion.get('runtime_promotion_allowed')
            and self.promotion.get('runtime_personalization_allowed',False)
            and all(checks.get(f'personalization_{h}',{}).get('passed') for h in HORIZONS)
        )

    def _row(self, artifact: dict, features: dict, profile: dict) -> pd.DataFrame:
        impute = artifact.get('feature_defaults', artifact.get('imputation', {})) or {}
        # Modern training uses an in-pipeline SimpleImputer fitted only on the
        # training fold. Passing made-up medians before the pipeline would
        # change the trained predictor's missing-value semantics at inference.
        pipeline_imputes = isinstance(artifact.get('model'), Pipeline) and (
            'imputer' in artifact['model'].named_steps)
        values = {}
        for name in artifact['features']:
            if name in features:
                value = features[name]
            elif name in profile:
                value = profile[name]
            elif name == 'hba1c_missing':
                value = 1.0 if pd.isna(profile.get('hba1c')) else 0.0
            else:
                value = impute.get(name, 0.0)
            if pipeline_imputes:
                values[name] = _safe_float(value, float('nan'))
            else:
                values[name] = _safe_float(value, impute.get(name, 0.0))
        return pd.DataFrame([values], columns=artifact['features'])

    def forecast(self, features: dict, profile: dict, horizon: int) -> float:
        art = self.forecast_artifacts[horizon]
        pred = float(art['model'].predict(self._row(art, features, profile))[0])
        return float(np.clip(pred, 45, 380))

    def excursion_probability(self, forecasts: list[float], features: dict, profile: dict) -> float:
        if self.risk_artifact is None:
            return super().excursion_probability(forecasts, features, profile)
        art = self.risk_artifact
        row = self._row(art, features, profile)
        model = art['model']
        if hasattr(model, 'predict_proba'):
            return float(np.clip(model.predict_proba(row)[0, 1], 0, 1))
        # HistGradientBoostingClassifier exposes predict_proba, but keep a safe fallback.
        return float(np.clip(model.predict(row)[0], 0, 1))

    def explanation(self, features: dict, profile: dict) -> list[dict]:
        # Do not falsely label this as SHAP/local attribution. This is a transparent input
        # context summary until a validated local explanation artifact is added.
        base = super().explanation(features, profile)
        for item in base:
            item['method'] = 'input-context-summary'
        return base



    def interval_half_width(self, horizon: int, features: dict | None = None, profile: dict | None = None) -> float | None:
        art = self.forecast_artifacts[horizon]
        if not (self.promotion and self.promotion.get('runtime_interval_allowed')
                and self.promotion.get('runtime_promotion_allowed')):
            return None
        value = art.get('interval_half_width_80')
        return float(value) if value is not None and np.isfinite(value) else None

    @property
    def interval_label(self) -> str:
        if (self.promotion and self.promotion.get('runtime_promotion_allowed')
                and self.promotion.get('runtime_interval_allowed')) and all(
                self.forecast_artifacts[h].get('interval_half_width_80') is not None for h in HORIZONS):
            return 'empirical-80pct-patient-balanced-oof-research'
        return 'heuristic-fallback-uncalibrated'

    @property
    def is_trained(self) -> bool:
        return len(self.forecast_artifacts) == len(HORIZONS)

    def metadata(self) -> dict:
        threshold = 180
        horizon = 120
        if self.risk_artifact is not None:
            threshold = self.risk_artifact.get('event_threshold_mg_dl', self.risk_artifact.get('threshold_mg_dl', threshold))
            horizon = self.risk_artifact.get('event_horizon_min', self.risk_artifact.get('horizon', horizon))
        event_definition = (self.risk_artifact or {}).get(
            'event_definition', f'new glucose excursion > {threshold} mg/dL within {horizon} minutes'
        )
        return {
            'mode': 'real-data-trained' if self.risk_artifact is not None else 'real-data-forecast-only',
            'trained': True,
            'source': self.source,
            'validation': self.validation,
            'event_definition': event_definition,
            'uncertainty': self.interval_label,
            'personalization_enabled': self.personalization_enabled,
            'promotion_status': (self.promotion or {}).get('status'),
            'alert_probability_threshold': (self.risk_artifact or {}).get('alert_probability_threshold'),
        }


    @property
    def alert_probability_threshold(self) -> float | None:
        value=(self.risk_artifact or {}).get('alert_probability_threshold')
        return float(value) if value is not None else None

    @property
    def model_label(self) -> str:
        risk = 'trained-risk' if self.risk_artifact is not None else 'heuristic-risk-fallback'
        return f'{self.source}; {risk}; validation={self.validation}'



class TransportArtifactForecaster(ArtifactForecaster):
    """Modality-matched CGM/phenotype artifact for external Shanghai replay.

    Uses only transport_forecast_* and transport_event_120 artifacts. Online
    personalization is deliberately disabled because the primary promotion gate
    validates adaptation on CGMacros, not on the external Shanghai cohort.
    """
    def __init__(self, model_dir: str | Path):
        self.model_dir=Path(model_dir)
        self.forecast_artifacts={}
        for h in HORIZONS:
            p=self.model_dir/f'transport_forecast_{h}.joblib'
            if not p.exists(): raise FileNotFoundError(f'Missing transport forecast artifact: {p}')
            art=joblib.load(p)
            if int(art.get('horizon',h))!=h or 'model' not in art or 'features' not in art:
                raise ValueError(f'Invalid transport forecast artifact: {p}')
            self.forecast_artifacts[h]=art
        risk_path=self.model_dir/'transport_event_120.joblib'
        self.risk_artifact=joblib.load(risk_path) if risk_path.exists() else None
        first=self.forecast_artifacts[30]
        self.source=str(first.get('source',first.get('training_cohort','CGMacros-transport-artifact')))
        self.validation=first.get('validation',first.get('evaluation','modality-matched external transport'))
        self.promotion=None
        pp=self.model_dir/'promotion.json'
        if pp.exists():
            import json
            try: self.promotion=verify_promotion_gate(self.model_dir,json.loads(pp.read_text()))
            except (json.JSONDecodeError,OSError): self.promotion={'status':'INVALID'}
        self.personalization_enabled=False

    def interval_half_width(self, horizon: int, features: dict | None = None, profile: dict | None = None) -> float | None:
        if not (self.promotion and self.promotion.get('runtime_external_transport_allowed')
                and self.promotion.get('external_interval_validated')):
            return None
        value=self.forecast_artifacts[horizon].get('interval_half_width_80')
        return float(value) if value is not None and np.isfinite(value) else None

    @property
    def interval_label(self) -> str:
        if (self.promotion and self.promotion.get('runtime_external_transport_allowed')
                and self.promotion.get('external_interval_validated') and all(
                    self.forecast_artifacts[h].get('interval_half_width_80') is not None for h in HORIZONS)):
            return 'empirical-80pct-CGMacros-transport-calibrated'
        return 'heuristic-fallback-uncalibrated'

    @property
    def model_label(self) -> str:
        risk='trained-transport-risk' if self.risk_artifact is not None else 'transport-risk-fallback'
        return f'{self.source}; modality-matched-Shanghai-transport; {risk}; validation={self.validation}'


def load_transport_forecaster(model_dir: str | Path | None = None):
    if model_dir:
        try:
            model=TransportArtifactForecaster(model_dir)
            return model,model.model_label
        except (FileNotFoundError,ValueError,KeyError):
            pass
    model=PopulationForecaster()
    return model,'demo-heuristic-forecaster; Shanghai modalities unavailable; not real-data validated'

def load_best_forecaster(model_dir: str | Path | None = None):
    """Return a trained artifact forecaster when complete artifacts exist, else demo fallback."""
    if model_dir:
        try:
            model = ArtifactForecaster(model_dir)
            return model, model.model_label
        except (FileNotFoundError, ValueError, KeyError):
            pass
    model = PopulationForecaster()
    return model, 'demo-heuristic-forecaster; heuristic-risk; not real-data validated'
