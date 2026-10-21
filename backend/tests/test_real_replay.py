from pathlib import Path
import pandas as pd
from app.real_replay import build_shanghai_replay, build_cgmacros_replay


def test_build_shanghai_real_replay(tmp_path):
    subj=tmp_path/'2000.csv'
    pd.DataFrame({'timestamp':pd.date_range('2024-01-01',periods=20,freq='15min'),'glucose_value_mg_dl':range(100,120)}).to_csv(subj,index=False)
    meta=tmp_path/'meta.csv'
    pd.DataFrame([{'person_id':2000,'diabetes_type':'T2D','age':57,'gender':'male','race_ethnicity':'','hba1c_%':7.6,'CGM_type':'Libre','glucose_level_record_count':20,'average_glucose_level_mg_dl':110,'count_days_with_CGM_data':1}]).to_csv(meta,index=False)
    profile,stream,cadence=build_shanghai_replay(subj,meta)
    assert profile['patient_id']=='SH-2000' and cadence==15
    assert stream[0]['provenance']['dataset']=='ShanghaiT2DM'
    assert stream[0]['heart_rate'] is None


def test_build_cgmacros_real_replay(tmp_path):
    pd.DataFrame([{'Subject':1,'Age':40,'Gender':'F','BMI':28,'HbA1c':7.2,'Fasting Glucose':118,'Insulin':10,'Triglycerides':130,'HDL':50,'LDL':100}]).to_csv(tmp_path/'bio.csv',index=False)
    folder=tmp_path/'CGMacros-001'; folder.mkdir()
    f=folder/'CGMacros-001.csv'
    t=pd.date_range('2025-01-01 08:00',periods=16,freq='1min')
    pd.DataFrame({'Timestamp':t,'Dexcom GL':range(110,126),'HR':[70]*16,'Mets':[12]*16,'Meal Type':['Breakfast']+[None]*15,'Carbs':[40]+[None]*15,'Calories':[350]+[None]*15,'Protein':[20]+[None]*15,'Fat':[10]+[None]*15,'Fiber':[5]+[None]*15}).to_csv(f,index=False)
    profile,stream,cadence=build_cgmacros_replay(f,tmp_path)
    assert profile['patient_id']=='CGM-001' and cadence==5
    assert stream[0]['provenance']['dataset']=='CGMacros'
    assert stream[0]['carbs_active_g'] >= 40


def test_shanghai_missing_modalities_remain_json_safe_with_demo_fallback(tmp_path):
    import json
    from app.engine import ReplaySession
    from app.model import PopulationForecaster

    subj=tmp_path/'2000.csv'
    pd.DataFrame({
        'timestamp':pd.date_range('2024-01-01',periods=20,freq='15min'),
        'glucose_value_mg_dl':[120+i for i in range(20)],
    }).to_csv(subj,index=False)
    meta=tmp_path/'meta.csv'
    pd.DataFrame([{
        'person_id':2000,'diabetes_type':'T2D','age':57,'gender':'male',
        'race_ethnicity':'','hba1c_%':7.6,'CGM_type':'Libre',
        'glucose_level_record_count':20,'average_glucose_level_mg_dl':129.5,
        'count_days_with_CGM_data':1,
    }]).to_csv(meta,index=False)
    profile,stream,cadence=build_shanghai_replay(subj,meta)
    session=ReplaySession('SH-2000', profile, stream, model=PopulationForecaster(), cadence_min=cadence)
    snapshot=session.step(1)
    # FastAPI/Starlette JSON responses reject NaN/Inf; missing Shanghai modalities
    # must stay semantically missing without contaminating calculated risk/output.
    json.dumps(snapshot, allow_nan=False)
    assert snapshot['reading']['activity'] is None
    assert snapshot['reading']['carbs_active_g'] is None
    assert 0.0 <= snapshot['excursion_risk'] <= 1.0
