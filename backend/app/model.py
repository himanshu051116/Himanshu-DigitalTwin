from __future__ import annotations
from dataclasses import dataclass, field
import math
import numpy as np

HORIZONS = (30, 60, 120)


def risk_band(p: float) -> str:
    if p < .20: return 'LOW'
    if p < .45: return 'MODERATE'
    if p < .70: return 'HIGH'
    return 'VERY HIGH'


def context_key(features: dict) -> str:
    if features.get('carbs_active_g', 0) >= 15:
        return 'postmeal'
    if features.get('activity', 0) >= .55:
        return 'active'
    return 'baseline'

@dataclass
class PersonalAdapter:
    """Auditable context-aware online residual adapter.

    It learns a small correction per forecast horizon and physiological context instead
    of retraining the population model on every sensor point.
    """
    alpha: float = 0.12
    biases: dict[str, dict[int, float]] = field(default_factory=lambda: {
        'baseline': {30:0.0,60:0.0,120:0.0},
        'postmeal': {30:0.0,60:0.0,120:0.0},
        'active': {30:0.0,60:0.0,120:0.0},
    })
    counts: dict[str, dict[int, int]] = field(default_factory=lambda: {
        'baseline': {30:0,60:0,120:0}, 'postmeal': {30:0,60:0,120:0}, 'active': {30:0,60:0,120:0}
    })
    abs_errors_population: list[float] = field(default_factory=list)
    abs_errors_personalized: list[float] = field(default_factory=list)

    def bias(self, horizon: int, context: str) -> float:
        return self.biases.get(context, self.biases['baseline'])[horizon]

    def update(self, horizon: int, context: str, population_pred: float, personalized_pred: float, observed: float, *, learn: bool = True) -> float:
        residual = observed - population_pred
        if learn:
            old = self.bias(horizon, context)
            clipped = float(np.clip(residual, -35, 35))
            self.biases[context][horizon] = (1-self.alpha)*old + self.alpha*clipped
            self.counts[context][horizon] += 1
        self.abs_errors_population.append(abs(observed-population_pred))
        self.abs_errors_personalized.append(abs(observed-personalized_pred))
        return residual

    def flat_biases(self) -> dict[str, float]:
        return {f'{ctx}_{h}': round(v,2) for ctx,vals in self.biases.items() for h,v in vals.items()}

    def mae_population(self):
        return float(np.mean(self.abs_errors_population)) if self.abs_errors_population else None

    def mae_personalized(self):
        return float(np.mean(self.abs_errors_personalized)) if self.abs_errors_personalized else None

class PopulationForecaster:
    """Transparent dynamic forecaster for the executable PoC.

    Production can replace this with trained LightGBM/TCN artifacts without changing
    the TwinEngine contract.
    """
    def forecast(self, features: dict, profile: dict, horizon: int) -> float:
        g = features['glucose']
        slope = features['slope_15']
        carbs_raw=features.get('carbs_active_g',0); activity_raw=features.get('activity',0)
        carbs=0.0 if carbs_raw is None or (isinstance(carbs_raw,(float,np.floating)) and np.isnan(carbs_raw)) else float(carbs_raw)
        activity=0.0 if activity_raw is None or (isinstance(activity_raw,(float,np.floating)) and np.isnan(activity_raw)) else float(activity_raw)
        hba_raw = profile.get('hba1c')
        bmi_raw = profile.get('bmi')
        hba = 6.5 if hba_raw is None or (isinstance(hba_raw, float) and np.isnan(hba_raw)) else float(hba_raw)
        bmi = 25.0 if bmi_raw is None or (isinstance(bmi_raw, float) and np.isnan(bmi_raw)) else float(bmi_raw)
        trend = slope * min(horizon, 55) * math.exp(-horizon/145)
        meal_coeff = {30:.34, 60:.46, 120:.27}[horizon]
        meal = carbs * meal_coeff
        phenotype = max(0, hba-6.5)*2.6 + max(0, bmi-25)*0.15
        attenuation = activity * {30:6,60:10,120:13}[horizon]
        fg_raw = profile.get('fasting_glucose')
        fg = g if fg_raw is None or (isinstance(fg_raw, float) and np.isnan(fg_raw)) else float(fg_raw)
        regression = (fg - g) * {30:.04,60:.10,120:.22}[horizon]
        return float(np.clip(g + trend + meal + phenotype - attenuation + regression, 55, 340))

    def excursion_probability(self, forecasts: list[float], features: dict, profile: dict) -> float:
        peak = max(forecasts)
        # Calibrated for demo so high post-meal trajectories become visibly high-risk.
        # Missing modalities must remain unknown in the state but must not propagate NaN
        # into an API probability. The demo fallback treats unavailable meal context as
        # neutral (0 contribution); trained artifacts handle missingness in their own
        # fitted preprocessing pipeline.
        hba_raw = profile.get('hba1c')
        hba = 7.0 if hba_raw is None or (isinstance(hba_raw, (float, np.floating)) and np.isnan(hba_raw)) else float(hba_raw)
        carbs_raw = features.get('carbs_active_g')
        carbs = 0.0 if carbs_raw is None or (isinstance(carbs_raw, (float, np.floating)) and np.isnan(carbs_raw)) else float(carbs_raw)
        slope_raw = features.get('slope_15', 0.0)
        slope = 0.0 if slope_raw is None or (isinstance(slope_raw, (float, np.floating)) and np.isnan(slope_raw)) else float(slope_raw)
        x = -3.2 + .055*(peak-140) + .55*max(0, slope) + .010*carbs + .18*(hba-7)
        return float(1/(1+math.exp(-x)))

    def explanation(self, features: dict, profile: dict) -> list[dict]:
        carbs=features.get('carbs_active_g',0); activity=features.get('activity',0)
        carbs=0.0 if carbs is None or (isinstance(carbs,(float,np.floating)) and np.isnan(carbs)) else float(carbs)
        activity=0.0 if activity is None or (isinstance(activity,(float,np.floating)) and np.isnan(activity)) else float(activity)
        scores = [
            ('Recent carbohydrate load', min(1.0, carbs/65), 'up'),
            ('Recent glucose trend', min(1.0, max(0, features['slope_15'])/1.5), 'up'),
            ('HbA1c baseline phenotype', min(1.0, max(0, ((profile.get('hba1c') if profile.get('hba1c') is not None else 6.5)-6.5))/3), 'up'),
            ('Recent activity', min(1.0, activity), 'down'),
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [{'factor': n, 'strength': round(float(s), 2), 'direction': d} for n,s,d in scores]
