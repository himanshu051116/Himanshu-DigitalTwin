from pathlib import Path
import json, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.shanghai import load_shanghai_metadata, cohort_profile

root=Path(__file__).resolve().parents[1]
meta=root/'data'/'reference'/'shanghai_t2dm_metadata.csv'
out=root/'data'/'reference'/'shanghai_t2dm_cohort_profile.json'
profile=cohort_profile(load_shanghai_metadata(meta))
out.write_text(json.dumps(profile,indent=2))
print(json.dumps(profile,indent=2))
