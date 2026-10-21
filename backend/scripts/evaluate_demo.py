from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.data import generate_demo_patients
from app.engine import ReplaySession

def main():
    report={'mode':'system demonstration, not clinical validation','patients':{},'summary':{}}
    improvements=[]
    for pid,p in generate_demo_patients().items():
        s=ReplaySession(pid,p.profile,p.stream); maxrisk={'risk':-1}
        for _ in p.stream:
            snap=s.step(1)
            if snap['excursion_risk']>maxrisk['risk']:
                maxrisk={'risk':snap['excursion_risk'],'timestamp':snap['timestamp'],'glucose':snap['reading']['glucose'],'forecast_60':snap['forecasts'][1]['personalized']}
        pop=snap['model_metrics']['population_mae']; twin=snap['model_metrics']['personalized_mae']
        imp=(pop-twin)/pop*100 if isinstance(pop,(int,float)) and pop else 0
        improvements.append(imp)
        report['patients'][pid]={'population_mae':pop,'personalized_mae':twin,'mae_improvement_pct':round(imp,2),'max_risk':maxrisk,'max_observed_truth':max(x['truth_glucose'] for x in p.stream),'resolved_forecasts':snap['model_metrics']['resolved_forecasts']}
    report['summary']={'mean_mae_improvement_pct':round(sum(improvements)/len(improvements),2),'all_demo_patients_improved':all(x>0 for x in improvements)}
    out=Path(__file__).resolve().parents[2]/'docs'/'demo_system_evaluation.json'
    out.write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=='__main__':main()
