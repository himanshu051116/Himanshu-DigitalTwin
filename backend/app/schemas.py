from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

QualityStatus = Literal['VALID', 'DELAYED', 'MISSING', 'OUTLIER', 'IMPUTED']
RiskBand = Literal['LOW', 'MODERATE', 'HIGH', 'VERY HIGH', 'ACTIVE EXCURSION']

class PatientProfile(BaseModel):
    patient_id: str
    age: int
    sex: Literal['F', 'M']
    bmi: float
    hba1c: float
    fasting_glucose: float
    fasting_insulin: float
    triglycerides: float
    hdl: float
    ldl: float
    condition: str = 'Type 2 Diabetes'
    cohort: str = 'Research replay / synthetic demonstration'

class SensorReading(BaseModel):
    timestamp: str
    glucose: Optional[float]
    heart_rate: Optional[float]
    steps_5m: Optional[int]
    activity: Optional[float]
    carbs_active_g: Optional[float]
    minutes_since_meal: Optional[int]
    quality: QualityStatus
    provenance: dict[str, str]

class ForecastPoint(BaseModel):
    horizon_min: int
    population: float
    personalized: float
    lower: float
    upper: float

class PredictionAudit(BaseModel):
    issued_at: str
    horizon_min: int
    predicted: float
    observed: Optional[float] = None
    residual: Optional[float] = None
    resolved: bool = False

class TwinSnapshot(BaseModel):
    patient: PatientProfile
    twin_version: int
    timestamp: str
    sync_status: str
    reading: SensorReading
    forecasts: list[ForecastPoint]
    excursion_risk: float = Field(ge=0, le=1)
    risk_band: RiskBand
    confidence: Literal['HIGH', 'MODERATE', 'LOW']
    personal_bias: dict[str, float]
    explanations: list[dict[str, float | str]]
    recent_history: list[dict]
    timeline: list[dict]
    audit: list[PredictionAudit]
    model_metrics: dict[str, float | str]

class ScenarioRequest(BaseModel):
    patient_id: str
    carbs_g: Optional[float] = Field(default=None, ge=0, le=200)
    activity: Optional[float] = Field(default=None, ge=0, le=1)
    glucose: Optional[float] = Field(default=None, ge=40, le=400)

class ScenarioResponse(BaseModel):
    baseline: list[ForecastPoint]
    scenario: list[ForecastPoint]
    note: str
