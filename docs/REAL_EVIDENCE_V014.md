# v0.14.0 evidence decision record

**Source:** CGMacros PhysioNet 1.0.0; 45 real participants (15 no diabetes, 16 prediabetes, 14 T2D). Read-only independent research evidence, not the canonical deployment model.

| Horizon | Persistence MAE | ML MAE | Improvement | Observed coverage for nominal 80% | Subjects improved by online adaptation |
|---|---:|---:|---:|---:|---:|
| 30 min | 14.82 | 13.09 | 11.65% | 77.10% | 2/10 |
| 60 min | 22.94 | 20.77 | 9.47% | 73.68% | 3/10 |
| 120 min | 32.46 | 27.67 | 14.76% | 70.92% | 5/10 |

Research study 120-minute new-excursion-onset AUROC 0.727 vs current-glucose baseline 0.665, AUPRC 0.475, Brier 0.1654 (test prevalence 23.39%). These are NOT clinical alarm performance guarantees. The five repeated holdout splits overlap and cannot be treated as independent trials.

## Defects exposed and fixed in this development cycle

1. The prior canonical offline personalizer immediately consumed future `truth` before its due time. The replacement uses only the current VALID measured glucose at the **exact due timestamp**; the model's future truth is used strictly to score forecasts after replay.
2. Five-minute CGMacros resampling was left-labelled, potentially making subsequent observations appear early; it is right-labelled and right-closed.
3. Prior forecast targets could include interpolated observations or cross recording gaps. They are now invalidated unless all intervening CGM samples are valid and consecutive.
4. Inference formerly replaced optional missing values using manually computed defaults before invoking the pipeline imputer, causing training/deployment skew. Fitted pipelines now receive true NaN.
5. Primary promotion no longer depends on adaptation success, but adaptation has its **own mandatory gate**; trained 80% interval display has a separate coverage gate.
6. A development smoke override or an incomplete official 45-patient preflight now blocks promotion.
7. `Intensity`-only recordings are accounted for during preflight, but their unit is not silently converted to METs.
8. Shanghai transport width approval no longer incorrectly inherits the CGMacros primary width flag.

## Remaining work

The published real benchmark is from an independent implementation; it does **not** establish success of the modified canonical `train_submission.py` on the real cohort. The canonical run, exact runtime artifact evaluation, uncertainty recalibration and Shanghai external test must precede model promotion. Until then, the built-in twin remains a clearly labelled simulation, and the independent real study is read-only in the Evidence UI.
