# Six-slide submission presentation — text overview

**Team:** himanshusubh1510 · **Presenter:** Himanshu Shukla · **Institution:** MITS Gwalior

This text companion summarizes the six-slide deck. The [PowerPoint](HimanshuDigitalTwin_Presentation.pptx), [PDF](HimanshuDigitalTwin_Presentation.pdf), [preview](Preview_All_Six_Slides.png), and [browser slides](Presentation.html) are available in this repository.

## 1. HimanshuDigitalTwin
A patient-specific view of what glucose may do next. Historical patient context and incoming observations support 30-, 60- and 120-minute forecast scenarios. The synthetic demonstrator withholds predictions when glucose data is unreliable.

## 2. Clinical problem and patient example
A glucose reading is a snapshot, not a forecast. In one **synthetic replay**, the patient has 144 mg/dL glucose at 12:15 PM, 59.7 g recent carbohydrate context and wearable heart rate of 82 bpm. Demonstration forecasts are 155.5 mg/dL (+30 minutes), 156 mg/dL (+60 minutes) and 145.4 mg/dL (+120 minutes). These are illustrative, not clinically calibrated.

The editable [architecture graphic](../docs/assets/system-architecture.svg) and [technical mapping](../docs/ARCHITECTURE_AND_MODELS.md) accompany the [architecture PDF](architecture.pdf). The visual distinguishes the active synthetic replay from unpromoted independent research models.

## 3. System architecture
The twin combines patient phenotype and historical patterns with CGM readings, meal and activity/wearable information. It updates a patient state, produces horizon-specific glucose scenarios, checks observation reliability and may withhold predictions. A later valid glucose observation can be compared with the previously stored forecast.

## 4. Working prototype
The dashboard displays observed glucose, forecast trajectory, directional context contributors and labelled research/demo limitations. The active default dashboard runs a simulated replay.

## 5. Sensor-data safety
The demonstration shows a valid reading at 12:15 PM with a forecast, followed by a sensor-gap case at 2:25 PM with **forecast withheld**. The freshness threshold is 15 minutes from the last valid CGM observation.

## 6. Independent CGMacros study
The separate 45-participant study (14 Type-2 diabetes) reported model/persistence glucose MAE in mg/dL:

| Horizon | Persistence | Study model | Relative MAE reduction |
|---|---:|---:|---:|
| 30 min | 14.82 | 13.09 | 11.65% |
| 60 min | 22.94 | 20.77 | 9.47% |
| 120 min | 32.46 | 27.67 | 14.76% |

Only three participants with Type-2 diabetes were in the primary 10-person holdout. These results are from **an independent research experiment, not the model running in the live demo**. Personalization and nominal uncertainty intervals did not pass their quality gates. No clinical approval is claimed.

See [Judge quick start](../JUDGE_START_HERE.md) and [research evidence](../backend/reports/research/).
