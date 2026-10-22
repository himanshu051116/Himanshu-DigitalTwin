from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import math
import numpy as np
from .model import HORIZONS, PersonalAdapter, PopulationForecaster, risk_band, context_key

@dataclass
class PendingForecast:
    issued_index: int
    due_index: int
    issued_at: str
    horizon: int
    population: float
    personalized: float
    context: str = 'baseline'
    resolved: bool = False
    observed: float | None = None
    residual: float | None = None
    resolution_status: str = 'PENDING'
    verification_quality: str | None = None

@dataclass
class ReplaySession:
    patient_id: str
    profile: dict
    stream: list[dict]
    index: int = -1
    twin_version: int = 0
    history: deque = field(default_factory=lambda: deque(maxlen=72))
    timeline: deque = field(default_factory=lambda: deque(maxlen=30))
    pending: list[PendingForecast] = field(default_factory=list)
    adapter: PersonalAdapter = field(default_factory=PersonalAdapter)
    last_valid_glucose: float | None = None
    last_valid_index: int = -1
    max_stale_minutes: int = 15
    consecutive_valid_samples: int = 0
    min_trained_history_samples: int = 13
    model: PopulationForecaster = field(default_factory=PopulationForecaster)
    model_label: str = 'demo-heuristic-forecaster'
    cadence_min: int = 5

    def reset(self):
        self.index = -1
        self.twin_version = 0
        self.history.clear(); self.timeline.clear(); self.pending.clear()
        self.adapter = PersonalAdapter(); self.last_valid_glucose = None; self.last_valid_index = -1; self.consecutive_valid_samples = 0

    def _clean_reading(self, raw: dict) -> dict:
        r = dict(raw)
        if r['quality'] == 'MISSING' or r['glucose'] is None:
            r['glucose'] = self.last_valid_glucose
        elif r['quality'] == 'OUTLIER' and self.last_valid_glucose is not None:
            r['glucose'] = float(np.clip(r['glucose'], self.last_valid_glucose-25, self.last_valid_glucose+25))
        if r['glucose'] is not None:
            self.last_valid_glucose = r['glucose']
        return r

    def _stale_minutes(self) -> int | None:
        if self.last_valid_index < 0:
            return None
        return max(0, (self.index - self.last_valid_index) * self.cadence_min)

    def _abstention_reason(self) -> str | None:
        stale = self._stale_minutes()
        if stale is None:
            return 'No valid CGM glucose reading is available.'
        if stale > self.max_stale_minutes:
            return f'Last valid CGM observation is {stale} minutes old (limit {self.max_stale_minutes}).'
        if getattr(self.model, 'is_trained', False) and self.consecutive_valid_samples < self.min_trained_history_samples:
            return (f'Trained model requires {self.min_trained_history_samples} consecutive valid '
                    f'{self.cadence_min}-minute glucose observations; have {self.consecutive_valid_samples}.')
        return None

    def _must_abstain(self) -> bool:
        return self._abstention_reason() is not None

    def _features(self, reading: dict) -> dict:
        vals = [float(h['glucose']) for h in self.history if h.get('glucose') is not None]
        g = float(reading['glucose']) if reading.get('glucose') is not None else (vals[-1] if vals else float(self.profile['fasting_glucose']))
        steps_15 = max(1, round(15 / self.cadence_min))
        if len(vals) > steps_15:
            slope = (vals[-1] - vals[-1-steps_15]) / (steps_15 * self.cadence_min)
        elif len(vals) >= 2:
            slope = (vals[-1] - vals[0]) / max(float(self.cadence_min), (len(vals)-1) * self.cadence_min)
        else:
            slope = 0.0
        n30 = max(1, round(30 / self.cadence_min)); n60 = max(1, round(60 / self.cadence_min))
        roll30_vals = vals[-n30:] if vals else [g]
        roll60_vals = vals[-n60:] if vals else [g]
        roll30 = float(np.mean(roll30_vals)); roll60 = float(np.mean(roll60_vals))
        std60 = float(np.std(roll60_vals, ddof=1)) if len(roll60_vals) >= 2 else 0.0
        cv60 = float(std60 / roll60) if roll60 else 0.0
        try:
            ts = datetime.fromisoformat(str(reading['timestamp']).replace('Z', '+00:00'))
            minute = ts.hour * 60 + ts.minute
        except (ValueError, TypeError):
            minute = 0
        return {
            'glucose': g,
            'slope_15': float(slope),
            'roll30': roll30,
            'roll60': roll60,
            'std60': std60,
            'cv60': cv60,
            'carbs_active_g': float(reading.get('carbs_active_g')) if reading.get('carbs_active_g') is not None else np.nan,
            'minutes_since_meal': float(reading.get('minutes_since_meal')) if reading.get('minutes_since_meal') is not None else np.nan,
            'activity': float(reading.get('activity')) if reading.get('activity') is not None else np.nan,
            'heart_rate': float(reading.get('heart_rate')) if reading.get('heart_rate') is not None else np.nan,
            'hour_sin': float(math.sin(2*math.pi*minute/1440)),
            'hour_cos': float(math.cos(2*math.pi*minute/1440)),
        }

    def _resolve_due(self, observed: float | None, quality: str):
        """Resolve forecasts only against genuine observations at their due time.

        Missing, interpolated, or outlier-adjusted values must never teach the personal
        adapter. Otherwise the twin can appear to "learn" from values that were not
        actually observed. A forecast whose due observation is unusable is closed as
        SKIPPED_QUALITY rather than being incorrectly matched to a later timestamp.
        """
        for p in self.pending:
            if not p.resolved and p.due_index <= self.index:
                p.resolved = True
                p.verification_quality = quality
                if p.due_index == self.index and quality == 'VALID' and observed is not None:
                    observed = float(observed)
                    p.observed = observed
                    p.residual = self.adapter.update(p.horizon, p.context, p.population, p.personalized, observed, learn=getattr(self.model, 'personalization_enabled', True))
                    p.resolution_status = 'VERIFIED'
                    self.timeline.appendleft({
                        'timestamp': self.stream[self.index]['timestamp'],
                        'type': 'ADAPT',
                        'message': f'{p.horizon}m forecast verified; residual {p.residual:+.1f} mg/dL'
                    })
                else:
                    p.resolution_status = 'SKIPPED_QUALITY'
                    self.timeline.appendleft({
                        'timestamp': self.stream[self.index]['timestamp'],
                        'type': 'QUALITY',
                        'message': f'{p.horizon}m forecast verification skipped ({quality})'
                    })
        # Prevent unbounded growth in long replay/streaming sessions while retaining recent audit history.
        if len(self.pending) > 720:
            unresolved = [p for p in self.pending if not p.resolved]
            resolved = [p for p in self.pending if p.resolved][-180:]
            self.pending = resolved + unresolved

    def _interval_half_width(self, horizon: int, features: dict, quality_penalty: float = 1.0) -> tuple[float, str]:
        if hasattr(self.model, 'interval_half_width'):
            width = self.model.interval_half_width(horizon, features, self.profile)
            if width is not None and np.isfinite(width):
                label = getattr(self.model, 'interval_label', 'empirical-trained-interval')
                return float(width) * quality_penalty, label
        # Demonstration fallback: transparent heuristic, never presented as calibrated.
        sigma = 8 + horizon*0.075 + min(15, abs(features['slope_15'])*4)
        return float(1.28*sigma*quality_penalty), 'heuristic-demo'

    def _snapshot_payload(self, reading: dict, confidence: str, forecasts: list[dict], risk: float | None) -> dict:
        f = self._features(reading)
        mae_p = self.adapter.mae_population(); mae_t = self.adapter.mae_personalized()
        active_excursion=(reading.get('glucose') is not None and float(reading['glucose']) > 180)
        alert_threshold=getattr(self.model,'alert_probability_threshold',None)
        if self._must_abstain():
            stale = self._stale_minutes()
            alert_state=('WARMING UP — UNAVAILABLE'
                         if stale is not None and stale <= self.max_stale_minutes
                         else 'SENSOR STALE — UNAVAILABLE')
        elif active_excursion:
            alert_state='ACTIVE EXCURSION'
        elif alert_threshold is not None:
            alert_state='ALERT' if risk >= float(alert_threshold) else 'MONITOR'
        else:
            alert_state=risk_band(risk)
        return {
            'patient': self.profile,
            'twin_version': self.twin_version,
            'timestamp': reading['timestamp'],
            'sync_status': 'SYNCHRONIZED' if confidence != 'LOW' and not self._must_abstain() else 'DEGRADED',
            'forecast_status': 'ABSTAINED' if self._must_abstain() else 'AVAILABLE',
            'minutes_since_last_valid_glucose': self._stale_minutes(),
            'abstention_reason': self._abstention_reason(),
            'consecutive_valid_glucose_samples': self.consecutive_valid_samples,
            # Never display a carried-forward stale glucose as a fresh reading.
            'reading': {k: (None if k=='glucose' and self._must_abstain() else reading.get(k))
                        for k in ['timestamp','glucose','heart_rate','steps_5m','activity','carbs_active_g','minutes_since_meal','quality','provenance']},
            'forecasts': forecasts,
            # An already-active high glucose is not a 100% probability of a
            # new *future* onset. Likewise a stale sensor cannot support risk.
            'excursion_risk': round(risk,4) if risk is not None else None,
            'risk_band': 'UNAVAILABLE' if self._must_abstain() else ('ACTIVE EXCURSION' if active_excursion else risk_band(risk)),
            'risk_mode': ('sensor-stale' if self._stale_minutes() is None or self._stale_minutes()>self.max_stale_minutes else 'warmup') if self._must_abstain() else ('active-excursion' if active_excursion else 'forecast'),
            'alert_state': alert_state,
            'alert_probability_threshold': float(alert_threshold) if alert_threshold is not None else None,
            'confidence': confidence,
            'personal_bias': self.adapter.flat_biases(),
            'explanations': [] if self._must_abstain() else self.model.explanation(f, self.profile),
            'explanation_method': 'unavailable-insufficient-sensor-data' if self._must_abstain() else 'input-context-summary',
            # Model internals may carry the last valid glucose over short sensor gaps.
            # Exposed observed history MUST NOT claim those carried values are measured.
            'recent_history': [
                {**sample, 'glucose': (sample.get('glucose')
                                      if sample.get('quality') == 'VALID' else None)}
                for sample in list(self.history)[-36:]
            ],
            'timeline': list(self.timeline)[:12],
            'audit': [vars(p) for p in self.pending if p.resolved][-12:],
            'model_info': (self.model.metadata() if hasattr(self.model, 'metadata') else {'mode': self.model_label, 'trained': False}),
            'model_metrics': {
                'population_mae': round(mae_p,2) if mae_p is not None else 'collecting',
                'personalized_mae': round(mae_t,2) if mae_t is not None else 'collecting',
                'resolved_forecasts': sum(1 for p in self.pending if p.resolved),
                'verified_forecasts': sum(1 for p in self.pending if p.resolution_status == 'VERIFIED'),
                'skipped_verifications': sum(1 for p in self.pending if p.resolution_status == 'SKIPPED_QUALITY'),
                'evaluation_mode': 'online replay verification',
            }
        }

    def step(self, steps: int = 1) -> dict:
        snapshot = None
        for _ in range(max(1, steps)):
            if self.index + 1 >= len(self.stream):
                break
            self.index += 1; self.twin_version += 1
            raw = self.stream[self.index]
            genuine = (raw.get('quality') == 'VALID' and raw.get('glucose') is not None
                       and math.isfinite(float(raw['glucose'])))
            if genuine:
                # Source must retain its real clock cadence: a discontinuity or
                # missing/outlier sample breaks the valid-history window.
                cadence_ok = False
                if self.index > 0:
                    try:
                        now = datetime.fromisoformat(str(raw['timestamp']).replace('Z','+00:00'))
                        prev = datetime.fromisoformat(str(self.stream[self.index-1]['timestamp']).replace('Z','+00:00'))
                        cadence_ok = (now-prev).total_seconds()==self.cadence_min*60
                    except (ValueError, TypeError):
                        cadence_ok = False
                self.consecutive_valid_samples = self.consecutive_valid_samples+1 if cadence_ok else 1
                self.last_valid_index = self.index
            else:
                self.consecutive_valid_samples = 0
            reading = self._clean_reading(raw)
            if reading['glucose'] is None:
                reading['glucose'] = self.profile['fasting_glucose']
            self._resolve_due(raw.get('glucose'), raw.get('quality', 'MISSING'))
            self.history.append(reading)
            f = self._features(reading)
            forecasts = []
            population_values = []
            if not self._must_abstain():
                quality_penalty = 1.0 if raw['quality'] == 'VALID' else 1.7
                for h in HORIZONS:
                    pop = self.model.forecast(f, self.profile, h)
                    ctx = context_key(f)
                    pers = float(np.clip(pop + (self.adapter.bias(h, ctx) if getattr(self.model, 'personalization_enabled', True) else 0.0), 50, 350))
                    half_width, interval_method = self._interval_half_width(h, f, quality_penalty)
                    forecasts.append({'horizon_min': h, 'population': round(pop,1), 'personalized': round(pers,1),
                                      'lower': round(max(45,pers-half_width),1), 'upper': round(min(380,pers+half_width),1),
                                      'interval_method': interval_method})
                    population_values.append(pers)
                    self.pending.append(PendingForecast(self.index, self.index + max(1, round(h / self.cadence_min)), reading['timestamp'], h, pop, pers, ctx))
            risk = (None if self._must_abstain() or f['glucose'] > 180
                    else self.model.excursion_probability(population_values, f, self.profile))
            if raw['quality'] == 'MISSING': confidence = 'LOW'
            elif raw['quality'] in ('OUTLIER','IMPUTED') or len(self.history) < 5: confidence = 'MODERATE'
            else: confidence = 'HIGH'
            if self._must_abstain():
                confidence = 'LOW'  # confidence in the *forecast*, not the last sensor measurement
            if self.index > 0 and self.stream[self.index-1].get('minutes_since_meal') is None and raw.get('minutes_since_meal') == 0:
                self.timeline.appendleft({'timestamp': reading['timestamp'], 'type': 'MEAL', 'message': f"Meal event; {raw['carbs_active_g']:.0f} g active carbohydrates"})
            if self._must_abstain():
                self.timeline.appendleft({'timestamp': reading['timestamp'], 'type':'QUALITY',
                                          'message':'Forecast withheld: '+str(self._abstention_reason())})
            else:
                status_msg = ('active glucose excursion' if risk is None else f'new-onset risk {risk*100:.0f}%')
                self.timeline.appendleft({'timestamp': reading['timestamp'], 'type': 'SYNC',
                                          'message': f'Twin v{self.twin_version} synchronized; {status_msg}'})
            snapshot = self._snapshot_payload(reading, confidence, forecasts, risk)
        return snapshot or self.snapshot()

    def snapshot(self):
        if self.index < 0:
            return self.step(1)
        r = self.history[-1]
        f = self._features(r)
        forecasts=[]; vals=[]
        if not self._must_abstain():
            for h in HORIZONS:
                pop=self.model.forecast(f,self.profile,h); ctx=context_key(f); pers=float(np.clip(pop+(self.adapter.bias(h,ctx) if getattr(self.model, 'personalization_enabled', True) else 0.0),50,350)); vals.append(pers)
                half_width, interval_method=self._interval_half_width(h,f,1.0 if r.get('quality')=='VALID' else 1.7)
                forecasts.append({'horizon_min':h,'population':round(pop,1),'personalized':round(pers,1),'lower':round(max(45,pers-half_width),1),'upper':round(min(380,pers+half_width),1),'interval_method':interval_method})
        risk=None if self._must_abstain() or f['glucose']>180 else self.model.excursion_probability(vals,f,self.profile)
        quality = r.get('quality', 'VALID')
        confidence = 'LOW' if self._must_abstain() or quality == 'MISSING' else ('MODERATE' if quality in ('OUTLIER','IMPUTED') or len(self.history)<5 else 'HIGH')
        return self._snapshot_payload(r, confidence, forecasts, risk)

    def scenario(self, carbs_g=None, activity=None, glucose=None):
        snap=self.snapshot()
        if snap['forecast_status'] == 'ABSTAINED':
            return [], []
        r=dict(snap['reading']); f=self._features(r)
        if carbs_g is not None: f['carbs_active_g']=carbs_g
        if activity is not None: f['activity']=activity
        if glucose is not None: f['glucose']=glucose
        out=[]
        for h in HORIZONS:
            pop=self.model.forecast(f,self.profile,h); ctx=context_key(f); pers=float(np.clip(pop+(self.adapter.bias(h,ctx) if getattr(self.model, 'personalization_enabled', True) else 0.0),50,350)); half_width, interval_method=self._interval_half_width(h,f,1.0)
            out.append({'horizon_min':h,'population':round(pop,1),'personalized':round(pers,1),'lower':round(max(45,pers-half_width),1),'upper':round(min(380,pers+half_width),1),'interval_method':interval_method})
        return snap['forecasts'], out
