"""Separate hourly experiment. Existing daily artifacts are never overwritten."""
import sys, json, hashlib
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests, joblib, numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.metrics import mean_absolute_error
from ml.hourly import features, FEATURES
root=Path(__file__).resolve().parents[1]
p=root/'data/shanghai_hourly_2021_2025.json'
if not p.exists():
    r=requests.get('https://archive-api.open-meteo.com/v1/archive',params=dict(latitude=31.23,longitude=121.47,start_date='2021-01-01',end_date='2025-12-31',hourly='temperature_2m',timezone='Asia/Shanghai',models='era5'),timeout=120)
    r.raise_for_status(); p.write_text(json.dumps(r.json()),encoding='utf-8')
d=json.loads(p.read_text(encoding='utf-8'))['hourly']; history={datetime.fromisoformat(t):v for t,v in zip(d['time'],d['temperature_2m'])}
rows=[(t,features(t,history),v) for t,v in sorted(history.items()) if v is not None and features(t,history) is not None]
X=np.array([r[1] for r in rows]); y=np.array([r[2] for r in rows]); dates=np.array([r[0].isoformat() for r in rows])
train=dates<'2024'; val=(dates>='2024')&(dates<'2025'); test=dates>='2025'
models={'linear':make_pipeline(StandardScaler(),LinearRegression()),'ridge':make_pipeline(StandardScaler(),Ridge(alpha=10))}
vm={'persistence':float(mean_absolute_error(y[val],X[val,0]))}
for n,m in models.items(): m.fit(X[train],y[train]); vm[n]=float(mean_absolute_error(y[val],m.predict(X[val])))
selected=min(vm,key=vm.get); tm={'persistence':float(mean_absolute_error(y[test],X[test,0]))}
for n,m in models.items(): m.fit(X[train|val],y[train|val]); tm[n]=float(mean_absolute_error(y[test],m.predict(X[test])))
out=root/'artifacts/hourly'; out.mkdir(exist_ok=True)
report=dict(target='next_hour_temperature',features=FEATURES,selected=selected,validation_mae=vm,test_mae=tm,data_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),scope='Shanghai only; ERA5 historical hourly rolling evaluation; operational accuracy unverified',splits={n:int(mask.sum()) for n,mask in [('train',train),('validation',val),('test',test)]})
(out/'metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
joblib.dump(dict(model=models.get(selected),**report),out/'model.joblib')
print(json.dumps(report,indent=2))
