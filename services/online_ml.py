"""Online adapter: uses only Open-Meteo model analysis at/before issue time."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import math,hashlib
import joblib
from services.http_client import fetch
from services.ml_service import ROOT
from ml.hourly import features, FEATURES
from services.shanghai_scope import contains

def predict_online(latitude, longitude, now=None):
    now=now or datetime.now(ZoneInfo('Asia/Shanghai'))
    issue=now.astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None,minute=0,second=0,microsecond=0)
    target=issue+timedelta(hours=1)
    result=dict(mode='live_prediction',status='unavailable',prediction=None,target_time=target.isoformat(),data_time=None,model=None,source='Open-Meteo model analysis',scope='Shanghai municipality polygon; multi-point ERA5-trained model applied to operational model analysis; live accuracy unverified',unit='°C')
    if not contains(latitude,longitude):
        return dict(result,reason='outside_model_scope')
    path=ROOT/'artifacts/hourly_regional/model.joblib'
    if not path.exists(): return dict(result,reason='hourly_model_missing')
    bundle=joblib.load(path)
    if bundle.get('schema_version')!=2 or bundle.get('features')!=FEATURES or bundle.get('target')!='next_hour_temperature' or bundle.get('boundary_sha256')!=hashlib.sha256((ROOT/'data/shanghai_boundary.geojson').read_bytes()).hexdigest(): return dict(result,reason='incompatible_model')
    data=fetch('https://api.open-meteo.com/v1/forecast',dict(latitude=latitude,longitude=longitude,timezone='Asia/Shanghai',past_days=2,forecast_days=1,hourly='temperature_2m'))
    h=data.get('hourly',{}); history={}
    for t,v in zip(h.get('time',[]),h.get('temperature_2m',[])):
        stamp=datetime.fromisoformat(t)
        if stamp<=issue: history[stamp]=v
    x=features(target,history)
    if x is None: return dict(result,reason='insufficient_as_of_hourly_data')
    prediction=x[0] if bundle['selected']=='persistence' else float(bundle['model'].predict([x])[0])
    if not math.isfinite(prediction): return dict(result,reason='invalid_prediction')
    return dict(result,status='experimental',prediction=round(prediction,2),data_time=issue.isoformat(),model='hourly_'+bundle['selected'],training_points=len(bundle['sources']),model_version='shanghai_regional_v2',reason='operational_accuracy_unverified')
