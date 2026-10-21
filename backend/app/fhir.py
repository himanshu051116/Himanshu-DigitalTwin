from __future__ import annotations
from typing import Any

LOINC_MAP = {
    '4548-4':'hba1c',        # Hemoglobin A1c
    '2345-7':'glucose',      # Glucose [Mass/volume] in Serum or Plasma
    '39156-5':'bmi',         # BMI
}

def extract_fhir_phenotype(bundle: dict[str,Any]) -> dict[str,Any]:
    """Extract a minimal phenotype from an HL7 FHIR R4 Bundle without inventing links."""
    if bundle.get('resourceType')!='Bundle':
        raise ValueError('Expected a FHIR Bundle')
    out={'patient_id':None,'sex':None,'birthDate':None,'observations':{},'conditions':[],'medications':[]}
    for entry in bundle.get('entry',[]):
        r=entry.get('resource',{})
        typ=r.get('resourceType')
        if typ=='Patient':
            out['patient_id']=r.get('id'); out['sex']=r.get('gender'); out['birthDate']=r.get('birthDate')
        elif typ=='Observation':
            coding=((r.get('code') or {}).get('coding') or [{}])[0]
            code=coding.get('code'); key=LOINC_MAP.get(code,code or coding.get('display','observation'))
            q=r.get('valueQuantity') or {}
            out['observations'][key]={'value':q.get('value'),'unit':q.get('unit'),'effective':r.get('effectiveDateTime')}
        elif typ=='Condition':
            text=((r.get('code') or {}).get('text') or (((r.get('code') or {}).get('coding') or [{}])[0].get('display')))
            if text: out['conditions'].append(text)
        elif typ in ('MedicationRequest','MedicationStatement'):
            med=(r.get('medicationCodeableConcept') or {}).get('text')
            if med: out['medications'].append(med)
    return out
