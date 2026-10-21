from __future__ import annotations
import json
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
)
from sklearn.model_selection import GroupKFold


def _imputation_values(frame: pd.DataFrame, features: list[str]) -> dict[str, float]:
    values: dict[str, float] = {}
    for c in features:
        s = pd.to_numeric(frame[c], errors='coerce')
        med = s.median()
        values[c] = float(med) if pd.notna(med) else 0.0
    return values


def _fill(frame: pd.DataFrame, features: list[str], impute: dict[str, float]) -> pd.DataFrame:
    x = frame[features].apply(pd.to_numeric, errors='coerce').copy()
    return x.fillna(impute)


def _macro_subject_mae(frame: pd.DataFrame, truth='truth', pred='prediction') -> float:
    vals=[]
    for _,g in frame.groupby('subject_id', observed=True):
        vals.append(mean_absolute_error(g[truth], g[pred]))
    return float(np.mean(vals)) if vals else float('nan')


def grouped_regression_oof(
    data: pd.DataFrame,
    features: list[str],
    target: str,
    estimator_factory: Callable[[], object],
    n_splits: int = 5,
) -> tuple[dict, pd.DataFrame]:
    work = data.dropna(subset=['subject_id', target, 'glucose']).copy()
    groups = work['subject_id']
    n_groups = int(groups.nunique())
    if n_groups < 2:
        raise ValueError('Need at least two subjects for grouped validation.')
    splitter = GroupKFold(n_splits=min(n_splits, n_groups))
    oof_parts = []
    folds = []
    passthrough=[c for c in ['carbs_active_g','activity'] if c in work.columns]
    for fold_i, (tr, va) in enumerate(splitter.split(work, groups=groups), start=1):
        train = work.iloc[tr]
        valid = work.iloc[va]
        model = estimator_factory()
        model.fit(train[features], train[target])
        pred = model.predict(valid[features])
        out = valid[['subject_id', 'timestamp', 'glucose', target] + passthrough].copy()
        out['prediction'] = pred
        out['persistence'] = valid['glucose'].to_numpy()
        out['fold'] = fold_i
        out = out.rename(columns={target: 'truth'})
        oof_parts.append(out)
        folds.append({
            'fold': fold_i,
            'train_subjects': int(train['subject_id'].nunique()),
            'validation_subjects': int(valid['subject_id'].nunique()),
            'rows': int(len(valid)),
            'mae': float(mean_absolute_error(valid[target], pred)),
            'rmse': float(mean_squared_error(valid[target], pred) ** .5),
            'persistence_mae': float(mean_absolute_error(valid[target], valid['glucose'])),
        })
    oof = pd.concat(oof_parts, ignore_index=True).sort_values(['subject_id', 'timestamp'])
    metrics = {
        'rows': int(len(oof)),
        'subjects': int(oof['subject_id'].nunique()),
        'mae_pooled': float(mean_absolute_error(oof['truth'], oof['prediction'])),
        'rmse_pooled': float(mean_squared_error(oof['truth'], oof['prediction']) ** .5),
        'mae_macro_subject': _macro_subject_mae(oof),
        'persistence_mae_pooled': float(mean_absolute_error(oof['truth'], oof['persistence'])),
        'persistence_mae_macro_subject': _macro_subject_mae(oof, pred='persistence'),
        'improvement_vs_persistence_pct': float(
            100 * (mean_absolute_error(oof['truth'], oof['persistence']) - mean_absolute_error(oof['truth'], oof['prediction']))
            / max(1e-9, mean_absolute_error(oof['truth'], oof['persistence']))
        ),
        'folds': folds,
    }
    return metrics, oof


def grouped_classifier_oof(
    data: pd.DataFrame,
    features: list[str],
    target: str,
    estimator_factory: Callable[[], object],
    n_splits: int = 5,
) -> tuple[dict, pd.DataFrame]:
    work = data.dropna(subset=['subject_id', target, 'glucose']).copy()
    work[target] = work[target].astype(int)
    groups = work['subject_id']
    n_groups = int(groups.nunique())
    if n_groups < 2:
        raise ValueError('Need at least two subjects for grouped validation.')
    splitter = GroupKFold(n_splits=min(n_splits, n_groups))
    parts = []
    folds = []
    for fold_i, (tr, va) in enumerate(splitter.split(work, groups=groups), start=1):
        train = work.iloc[tr]
        valid = work.iloc[va]
        if train[target].nunique() < 2:
            raise ValueError(f'Risk training fold {fold_i} has only one class.')
        model = estimator_factory()
        model.fit(train[features], train[target])
        prob = model.predict_proba(valid[features])[:, 1]
        out = valid[['subject_id', 'timestamp', 'glucose', target]].copy()
        out['probability'] = prob
        out['fold'] = fold_i
        out = out.rename(columns={target: 'truth'})
        parts.append(out)
        fold_metrics = {'fold': fold_i, 'rows': int(len(valid)), 'event_rate': float(valid[target].mean())}
        if valid[target].nunique() == 2:
            fold_metrics['auroc'] = float(roc_auc_score(valid[target], prob))
            fold_metrics['auprc'] = float(average_precision_score(valid[target], prob))
        else:
            fold_metrics['auroc'] = None
            fold_metrics['auprc'] = None
        folds.append(fold_metrics)
    oof = pd.concat(parts, ignore_index=True).sort_values(['subject_id', 'timestamp'])
    y = oof['truth'].astype(int)
    p = oof['probability']
    metrics = {
        'rows': int(len(oof)),
        'subjects': int(oof['subject_id'].nunique()),
        'event_rate': float(y.mean()),
        'auroc': float(roc_auc_score(y, p)) if y.nunique() == 2 else None,
        'auprc': float(average_precision_score(y, p)) if y.nunique() == 2 else None,
        'brier': float(brier_score_loss(y, p)),
        'current_glucose_auroc_baseline': float(roc_auc_score(y, oof['glucose'])) if y.nunique() == 2 else None,
        'folds': folds,
    }
    return metrics, oof


def _adapt_context(row: pd.Series) -> str:
    if float(row.get('carbs_active_g', 0) or 0) >= 15:
        return 'postmeal'
    if float(row.get('activity', 0) or 0) >= .55:
        return 'active'
    return 'baseline'


def personalization_from_oof(
    oof: pd.DataFrame, calibration_fraction: float = .30,
    clip: float = 35.0, alpha: float = .12, *, horizon_minutes: int = 60,
) -> dict:
    """Chronological causal replay of the live context-specific EMA adapter.

    A forecast made at time t *cannot* update a bias until t + horizon,
    and only if a genuine glucose measurement exists at that exact time.
    Out-of-fold prediction truth is used for evaluation after replay, NEVER
    to update personalization at its origin time.
    """
    if horizon_minutes <= 0:
        raise ValueError('Forecast horizon must be positive.')
    rows=[]
    for sid,g in oof.sort_values('timestamp').groupby('subject_id',observed=True):
        g=g.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
        if len(g)<20: continue
        cut=max(5,int(len(g)*calibration_fraction))
        if cut>=len(g)-5: continue
        biases={'baseline':0.0,'postmeal':0.0,'active':0.0}
        pending={}
        for i,row in g.iterrows():
            now=pd.Timestamp(row['timestamp'])
            valid=bool(row.get('quality','VALID')=='VALID') and pd.notna(row['glucose'])
            # Close any missed due-time forecasts without learning. A missing
            # due observation must not be matched to a later glucose value.
            for due in [t for t in pending if t<=now]:
                due_preds=pending.pop(due)
                if due==now and valid:
                    for pop,ctx in due_preds:
                        residual=float(row['glucose'])-pop
                        biases[ctx]=(1-alpha)*biases[ctx]+alpha*float(np.clip(residual,-clip,clip))
            ctx=_adapt_context(row)
            pop=float(row['prediction'])
            personalized=pop+biases[ctx]
            if i>=cut:
                rec=row.copy()
                rec['personalized']=personalized
                rec['context']=ctx
                rec['bias_before_update']=biases[ctx]
                rows.append(rec)
            due=now+pd.Timedelta(minutes=horizon_minutes)
            pending.setdefault(due,[]).append((pop,ctx))
    if not rows:
        return {'status':'insufficient-data'}
    ev=pd.DataFrame(rows)
    subject_rows=[]
    for sid,g in ev.groupby('subject_id',observed=True):
        subject_rows.append({
            'subject_id':sid,
            'population_mae':float(mean_absolute_error(g['truth'],g['prediction'])),
            'personalized_mae':float(mean_absolute_error(g['truth'],g['personalized'])),
        })
    sub=pd.DataFrame(subject_rows)
    pop=float(mean_absolute_error(ev['truth'],ev['prediction']))
    per=float(mean_absolute_error(ev['truth'],ev['personalized']))
    return {
        'method':'causal due-time context-aware EMA, only valid measured glucose',
        'horizon_minutes':horizon_minutes,
        'subjects_evaluated':int(len(sub)),
        'calibration_fraction':calibration_fraction,'alpha':alpha,
        'population_mae_pooled':pop,'personalized_mae_pooled':per,
        'improvement_pct_pooled':float(100*(pop-per)/max(pop,1e-9)),
        'subjects_improved_fraction':float((sub.personalized_mae<sub.population_mae).mean()),
        'population_mae_macro_subject':float(sub.population_mae.mean()),
        'personalized_mae_macro_subject':float(sub.personalized_mae.mean()),
    }


def fit_and_save_final(
    data: pd.DataFrame,
    features: list[str],
    target: str,
    estimator_factory: Callable[[], object],
    path: Path,
    *,
    horizon: int | None = None,
    source: str,
    validation: str,
    extra: dict | None = None,
):
    work = data.dropna(subset=[target, 'subject_id']).copy()
    impute = _imputation_values(work, features)
    model = estimator_factory()
    model.fit(work[features], work[target])
    artifact = {
        'model': model,
        'features': features,
        'imputation': impute,
        'source': source,
        'validation': validation,
    }
    if horizon is not None:
        artifact['horizon'] = int(horizon)
    if extra:
        artifact.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)
    return artifact


def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False))
