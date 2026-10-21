from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import numpy as np

@dataclass
class DemoPatient:
    profile: dict
    stream: list[dict]


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def generate_demo_patients(seed: int = 73, minutes: int = 720) -> dict[str, DemoPatient]:
    """Generate reproducible research-replay patients.

    This is explicitly demonstration data, not clinical data. The dynamics are designed
    to exercise the twin engine: meals, activity, sensor gaps and patient-specific response.
    """
    rng = np.random.default_rng(seed)
    configs = [
        ('HDT-027', 54, 'M', 31.4, 8.1, 132, 18.2, 216, 39, 126, 1.18, -0.12),
        ('HDT-041', 47, 'F', 28.2, 7.4, 119, 14.7, 171, 46, 111, 0.91, -0.20),
        ('HDT-063', 61, 'M', 33.1, 8.7, 148, 21.6, 238, 36, 139, 1.34, -0.08),
    ]
    start = datetime(2026, 10, 6, 7, 0, 0)
    patients: dict[str, DemoPatient] = {}
    for idx, cfg in enumerate(configs):
        pid, age, sex, bmi, hba1c, fg, insulin, tg, hdl, ldl, carb_sens, activity_effect = cfg
        profile = dict(patient_id=pid, age=age, sex=sex, bmi=bmi, hba1c=hba1c,
                       fasting_glucose=fg, fasting_insulin=insulin, triglycerides=tg,
                       hdl=hdl, ldl=ldl)
        glucose = float(fg + rng.normal(0, 4))
        stream = []
        meals = {
            60: (46 + idx*5, 'breakfast'),
            300: (72 - idx*4, 'lunch'),
            585: (64 + idx*3, 'dinner'),
        }
        active_meals: list[tuple[int, float]] = []
        for minute in range(0, minutes, 5):
            if minute in meals:
                active_meals.append((minute, meals[minute][0]))
            # meal effect decays over about 3 hours
            meal_effect = 0.0
            carbs_active = 0.0
            since_meal = None
            for mt, carbs in active_meals:
                dt = minute - mt
                if 0 <= dt <= 180:
                    # gamma-like absorption curve
                    response = carbs * carb_sens * (dt / 45.0) * math.exp(1 - dt / 45.0) if dt > 0 else 0
                    meal_effect += response * 0.58
                    carbs_active += carbs * math.exp(-dt / 80)
                    since_meal = dt if since_meal is None else min(since_meal, dt)
            # activity bouts after lunch and late afternoon
            activity = 0.12 + 0.55 * math.exp(-((minute-375)/55)**2) + 0.35 * math.exp(-((minute-510)/45)**2)
            activity = float(np.clip(activity + rng.normal(0, .05), 0, 1))
            steps = int(max(0, rng.normal(28 + 260*activity, 20)))
            hr = 68 + 34*activity + 0.05*(glucose-120) + rng.normal(0, 2.5)
            circadian = 5 * math.sin((minute / 720) * 2 * math.pi - 1.0)
            target = fg + meal_effect + circadian + activity_effect * (steps/12)
            glucose += 0.12 * (target - glucose) + rng.normal(0, 1.8)
            glucose = float(np.clip(glucose, 65, 310))

            quality = 'VALID'
            g_value = round(glucose, 1)
            if minute in (430, 435, 440):
                quality = 'MISSING'
                g_value = None
            elif minute == 445:
                quality = 'IMPUTED'
                g_value = round(glucose, 1)
            elif minute == 515 and idx == 2:
                quality = 'OUTLIER'
                g_value = round(min(350, glucose + 65), 1)

            stream.append({
                'timestamp': (start + timedelta(minutes=minute)).isoformat(),
                'glucose': g_value,
                'truth_glucose': round(glucose, 1),
                'heart_rate': round(float(hr), 1),
                'steps_5m': steps,
                'activity': round(activity, 3),
                'carbs_active_g': round(carbs_active, 1),
                'minutes_since_meal': since_meal,
                'quality': quality,
                'provenance': {
                    'stream': 'research-replay-demo',
                    'glucose': 'simulated CGM channel',
                    'activity': 'simulated wearable channel',
                    'meal': 'simulated meal log',
                }
            })
        patients[pid] = DemoPatient(profile=profile, stream=stream)
    return patients
