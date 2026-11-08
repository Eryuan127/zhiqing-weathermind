"""Offline diagnostic ablations; never overwrites the deployed model or reselects on test."""
import sys,json,csv,hashlib
from pathlib import Path
from datetime import datetime
import numpy as np,joblib
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ml.hourly import features
root=Path(__file__).resolve().parents[1];raw=root/'data/shanghai_hourly_2021_2025.json';data=json.loads(raw.read_text())['hourly'];history={datetime.fromisoformat(t):v for t,v in zip(data['time'],data['temperature_2m'])}
rows=[(t,features(t,history),v) for t,v in sorted(history.items()) if v is not None and features(t,history) is not None]
x=np.array([r[1] for r in rows]);y=np.array([r[2] for r in rows]);dates=np.array([r[0].isoformat() for r in rows]);fit=dates<'2025';test=~fit
bundle=joblib.load(root/'artifacts/hourly/model.joblib')
assert hashlib.sha256(raw.read_bytes()).hexdigest()==bundle['data_sha256'],'Data/model mismatch'
predictions={'persistence':x[test,0],'deployed_'+bundle['selected']:bundle['model'].predict(x[test]) if bundle['model'] is not None else x[test,0]}
for name,cols in [('ridge_no_lag24',[0,1,3,4]),('ridge_no_cycle',[0,1,2])]:
 model=make_pipeline(StandardScaler(),Ridge(alpha=10));model.fit(x[fit][:,cols],y[fit]);predictions[name]=model.predict(x[test][:,cols])
truth=y[test];testdates=[r[0] for r in rows if r[0].year>=2025]
groups={'all':np.ones(len(truth),dtype=bool),'winter':np.array([t.month in (12,1,2) for t in testdates]),'spring':np.array([t.month in (3,4,5) for t in testdates]),'summer':np.array([t.month in (6,7,8) for t in testdates]),'autumn':np.array([t.month in (9,10,11) for t in testdates]),'change_at_least_2C':abs(truth-x[test,0])>=2}
report={'kind':'historical diagnostic, not live accuracy; ablations excluded from model selection','data_sha256':bundle['data_sha256'],'fit_years':'2021-2024','test_year':'2025','groups':{}}
for group,mask in groups.items():
 report['groups'][group]={'n':int(mask.sum()),'models':{name:dict(mae=float(np.mean(abs(values[mask]-truth[mask]))),rmse=float(np.sqrt(np.mean((values[mask]-truth[mask])**2)))) for name,values in predictions.items()} if mask.any() else {}}
out=root/'artifacts/hourly/analysis';out.mkdir(exist_ok=True)
(out/'analysis.json').write_text(json.dumps(report,indent=2))
with (out/'predictions.csv').open('w',newline='') as f:
 writer=csv.writer(f);writer.writerow(['time','actual',*predictions]);writer.writerows([dates[test][i],truth[i],*[v[i] for v in predictions.values()]] for i in range(len(truth)))
print(json.dumps(report['groups']['all'],indent=2))
