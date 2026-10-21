import json
import pandas as pd
from app.cgmacros import load_cgmacros_subject
from app.fhir import extract_fhir_phenotype

def test_cgmacros_adapter_preserves_meal_and_identity(tmp_path):
    p=tmp_path/'CGMacros-027.csv'
    pd.DataFrame({
      'Timestamp':['1/1/2026 08:00','1/1/2026 08:01','1/1/2026 08:02','1/1/2026 08:03','1/1/2026 08:04','1/1/2026 08:05'],
      'Dexcom GL':[120,121,122,123,124,126],'HR':[70,71,72,72,73,74],'Mets':[12,12,13,14,13,12],
      'Meal Type':['Breakfast',None,None,None,None,None],'Carbs':[50,None,None,None,None,None],
      'Calories':[400,None,None,None,None,None],'Protein':[20,None,None,None,None,None],'Fat':[15,None,None,None,None,None],'Fiber':[8,None,None,None,None,None]
    }).to_csv(p,index=False)
    x=load_cgmacros_subject(p)
    assert x.iloc[0]['subject_id']=='CGM-027'
    assert x.iloc[0]['carbs'] == 50
    assert x.iloc[0]['carbs_active_g'] >= 50
    assert x.iloc[0]['minutes_since_meal']==0

def test_fhir_extract_minimal_bundle():
    b={'resourceType':'Bundle','entry':[
      {'resource':{'resourceType':'Patient','id':'p1','gender':'male','birthDate':'1970-01-01'}},
      {'resource':{'resourceType':'Observation','code':{'coding':[{'code':'4548-4'}]},'valueQuantity':{'value':7.8,'unit':'%'}}},
      {'resource':{'resourceType':'Condition','code':{'text':'Type 2 diabetes'}}}
    ]}
    x=extract_fhir_phenotype(b)
    assert x['patient_id']=='p1' and x['observations']['hba1c']['value']==7.8
    assert 'Type 2 diabetes' in x['conditions']

def test_cgmacros_marks_interpolated_interval(tmp_path):
    p=tmp_path/'CGMacros-031.csv'
    times=pd.date_range('2026-01-01 08:00',periods=21,freq='1min')
    gl=[120,121,122,123,124]+[None]*7+[130,131,132,133,134,135,136,137,138]
    pd.DataFrame({'Timestamp':times.astype(str),'Dexcom GL':gl,'HR':[70]*21,'Mets':[12]*21,'Carbs':[0]*21}).to_csv(p,index=False)
    x=load_cgmacros_subject(p)
    # Right-closed 08:10 bucket has no valid observations and must be labelled imputed.
    row=x.loc[x['timestamp']==pd.Timestamp('2026-01-01 08:10')].iloc[0]
    assert row['glucose']==row['glucose']
    assert row['quality']=='IMPUTED'

def test_cgmacros_does_not_mix_cgm_devices(tmp_path):
    import pandas as pd
    from app.cgmacros import load_cgmacros_subject
    p=tmp_path/'CGMacros-001.csv'
    pd.DataFrame({
        'Timestamp':pd.date_range('2026-01-01',periods=4,freq='1min'),
        'Dexcom GL':[100,None,102,103],
        'Libre GL':[130,131,132,133],
        'HR':[70,70,71,71], 'Mets':[10,10,10,10],
        'Calories (Activity)':[0,0,0,0], 'Meal Type':[None]*4,
        'Calories':[0]*4,'Carbs':[0]*4,'Protein':[0]*4,'Fat':[0]*4,'Fiber':[0]*4,
        'Amount Consumed':[None]*4,
    }).to_csv(p,index=False)
    out=load_cgmacros_subject(p,resample='1min')
    assert set(out['cgm_source'])=={'Dexcom'}
    # The Dexcom gap may be imputed, but it must never be replaced by the 131 Libre value.
    assert out.loc[1,'glucose'] != 131


def test_cgmacros_official_bio_schema_aliases(tmp_path):
    from app.cgmacros import load_bio
    p=tmp_path/'bio.csv'
    pd.DataFrame({
        'Subject ID':[1,2],
        'Age':[45,61],
        'Gender':['F','M'],
        'BMI':[29.1,31.2],
        'A1c PDL (Lab)':[6.2,7.8],
        'Fasting GLU - PDL (Lab)':[111,151],
        'Insulin':[8.2,15.5],
        'Triglycerides':[120,210],
        'HDL':[55,39],
        'LDL (Cal)':[101,132],
    }).to_csv(p,index=False)
    x=load_bio(p)
    assert x.loc[0,'subject_id']=='CGM-001'
    assert x.loc[1,'hba1c']==7.8
    assert x.loc[1,'fasting_glucose']==151
    assert x.loc[1,'ldl']==132
