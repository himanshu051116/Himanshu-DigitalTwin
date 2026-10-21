from pathlib import Path
import numpy as np
import pandas as pd
from scripts.benchmark_shanghai import benchmark


def test_shanghai_baseline_benchmark(tmp_path: Path):
    for sid,offset in [(2000,0),(2001,25)]:
        n=48
        t=np.arange(n)
        pd.DataFrame({
            'timestamp':pd.date_range('2026-01-01',periods=n,freq='15min'),
            'glucose_value_mg_dl':120+offset+25*np.sin(t/5),
        }).to_csv(tmp_path/f'{sid}.csv',index=False)
    r=benchmark(tmp_path)
    assert r['subjects']==2
    assert set(r['baseline_metrics'])=={'30','60','120'}
    assert r['baseline_metrics']['30']['persistence']['n']>0
    assert 0 <= r['event_prevalence'] <= 1
