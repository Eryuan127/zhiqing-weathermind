"""Real regional ERA5 training. A separate artifact never overwrites legacy models."""
import sys,json,hashlib,time,csv,os
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.shanghai_scope import sample_points,contains
from services.http_client import fetch,UpstreamError
from ml.hourly import features,FEATURES
import numpy as np,joblib
import importlib.metadata as package_metadata
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge,LinearRegression
from sklearn.metrics import mean_absolute_error,mean_squared_error
root=Path(__file__).resolve().parents[1];cache=root/'data/shanghai_regional';cache.mkdir(exist_ok=True);out=root/'artifacts/hourly_regional';out.mkdir(exist_ok=True)
points_file=cache/'points.json'
points=json.loads(points_file.read_text('utf-8')) if points_file.exists() else sample_points(12)
assert all(contains(p['latitude'],p['longitude']) for p in points),'A training point is outside the current municipality boundary'
points_file.write_text(json.dumps(points,indent=2),'utf-8');all_rows=[];sources=[]
for point in points:
 path=cache/(point['id']+'.json')
 if not path.exists():
  print('Downloading',point['id'],flush=True)
  params=dict(latitude=point['latitude'],longitude=point['longitude'],start_date='2023-01-01',end_date='2025-12-31',hourly='temperature_2m',timezone='Asia/Shanghai',models='era5')
  # Pace historical calls, bounded retry, preserve raw response and provenance.
  for attempt in range(3):
   try:
    data=fetch('https://archive-api.open-meteo.com/v1/archive',params);break
   except UpstreamError as exc:
    if attempt==2:raise
    print('Retry',point['id'],exc.kind,flush=True);time.sleep(30)
  raw=dict(point=point,params=params,source='Open-Meteo ERA5 reanalysis, not station observations',retrieved_at=datetime.now(timezone.utc).isoformat(),data=data)
  path.write_text(json.dumps(raw,ensure_ascii=False),'utf-8');time.sleep(9)
 raw=json.loads(path.read_text('utf-8'));assert raw['point']==point,'Cached coordinate mismatch';h=raw['data']['hourly'];history={datetime.fromisoformat(t):v for t,v in zip(h['time'],h['temperature_2m'])}
 rows=[(point['id'],t.isoformat(),features(t,history),v) for t,v in sorted(history.items()) if isinstance(v,(int,float)) and features(t,history) is not None]
 all_rows.extend(rows);sources.append(dict(**point,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),grid_latitude=raw['data']['latitude'],grid_longitude=raw['data']['longitude'],n=len(rows)))
x=np.array([r[2] for r in all_rows]);y=np.array([r[3] for r in all_rows]);dates=np.array([r[1] for r in all_rows]);regions=np.array([r[0] for r in all_rows]);train=dates<'2024';val=(dates>='2024')&(dates<'2025');test=dates>='2025'
models={'linear':make_pipeline(StandardScaler(),LinearRegression()),'ridge':make_pipeline(StandardScaler(),Ridge(alpha=10))}
validation={'persistence':float(mean_absolute_error(y[val],x[val,0]))}
for name,model in models.items():model.fit(x[train],y[train]);validation[name]=float(mean_absolute_error(y[val],model.predict(x[val])))
selected=min(validation,key=validation.get);predictions={'persistence':x[test,0]}
for name,model in models.items():model.fit(x[train|val],y[train|val]);predictions[name]=model.predict(x[test])
def metrics(actual,pred):return dict(mae=float(mean_absolute_error(actual,pred)),rmse=float(np.sqrt(mean_squared_error(actual,pred))))
per_point={}
for point in points:
 mask=regions[test]==point['id'];per_point[point['id']]=dict(n=int(mask.sum()),models={n:metrics(y[test][mask],p[mask]) for n,p in predictions.items()})
# Geographic generalization diagnostic: each region left out entirely, fixed Ridge alpha.
# ERA5 grid cells may be shared/correlated: group by returned grid, not requested label.
grids={p['id']:(p['grid_latitude'],p['grid_longitude']) for p in sources};unique=sorted(set(grids.values()));spatial=[]
for grid in unique:
 held=np.array([grids[r]==grid for r in regions]);fit=(train|val)&~held;evaluate=test&held
 model=make_pipeline(StandardScaler(),Ridge(alpha=10));model.fit(x[fit],y[fit]);spatial.append(dict(grid=list(grid),n=int(evaluate.sum()),ridge=metrics(y[evaluate],model.predict(x[evaluate])),persistence=metrics(y[evaluate],x[evaluate,0])))
manifest_hash=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
report=dict(environment={n:package_metadata.version(n) for n in ['numpy','scikit-learn','joblib']},training_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),schema_version=2,target='next_hour_temperature',features=FEATURES,selected=selected,validation_mae=validation,test_mae={n:metrics(y[test],p)['mae'] for n,p in predictions.items()},test_metrics={n:metrics(y[test],p) for n,p in predictions.items()},scope='Shanghai municipality polygon; pooled 12-point ERA5 historical experiment; live accuracy unverified',splits={n:int(mask.sum()) for n,mask in [('train_2023',train),('validation_2024',val),('test_2025',test)]},sources=sources,unique_grid_cells=len(unique),per_point=per_point,spatial_holdout=spatial,data_sha256=manifest_hash,boundary_sha256=hashlib.sha256((root/'data/shanghai_boundary.geojson').read_bytes()).hexdigest(),limitations=['2023-2025 ERA5 gridded reanalysis, not station observations','Neighboring and duplicate grid cells are correlated','Time split per point; no future lags or standardization leakage','Geographic holdout diagnostic does not select deployment model','Historical boundary approximation; coastal reclamation may differ','Only one-step prediction, not a tomorrow forecast'])
(out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');joblib.dump(dict(model=models.get(selected),**report),out/'model.joblib')
with (out/'test_predictions.csv').open('w',newline='',encoding='utf-8') as f:
 test_regions=regions[test];test_dates=dates[test];test_y=y[test]
 writer=csv.writer(f);writer.writerow(['point','time','actual',*predictions]);writer.writerows([test_regions[i],test_dates[i],test_y[i],*[v[i] for v in predictions.values()]] for i in range(test.sum()))
print(json.dumps(dict(selected=selected,validation_mae=validation,test_mae=report['test_mae'],unique_grid_cells=len(unique)),indent=2),flush=True)
