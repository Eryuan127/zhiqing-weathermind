"""Regional model and polygon regressions; operational inputs are explicit fixtures."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import pytest
from services.shanghai_scope import contains
from services.online_ml import predict_online
POINTS={'黄浦':(31.23,121.49),'徐汇':(31.18,121.43),'长宁':(31.22,121.42),'静安':(31.23,121.45),'普陀':(31.24,121.39),'虹口':(31.26,121.49),'杨浦':(31.27,121.52),'闵行':(31.11,121.38),'宝山':(31.40,121.49),'嘉定':(31.39,121.25),'浦东':(31.24,121.56),'金山':(30.72,121.34),'松江':(31.03,121.23),'青浦':(31.15,121.12),'奉贤':(30.92,121.47),'崇明':(31.63,121.40),'临港':(30.90,121.92),'长兴岛':(31.39,121.70),'横沙岛':(31.34,121.84)}
@pytest.mark.parametrize('name',list(POINTS))
def test_all_districts_and_islands_can_predict_without_center_snap(monkeypatch,name):
 point=POINTS[name];assert contains(*point)
 received=[]
 def forecast(url,params):
  received.append(params)
  return {'hourly':{'time':['2026-11-06T10:00','2026-11-06T09:00','2026-11-05T11:00','2026-11-06T11:00'],'temperature_2m':[20,19,18,9999]}}
 monkeypatch.setattr('services.online_ml.fetch',forecast)
 result=predict_online(*point,datetime(2026,11,6,10,30,tzinfo=ZoneInfo('Asia/Shanghai')))
 assert result['status']=='experimental' and result['prediction']<100
 assert result['model_version']=='shanghai_regional_v2' and result['training_points']==12
 assert received[0]['latitude']==point[0] and received[0]['longitude']==point[1]

@pytest.mark.parametrize('point',[(31.38,120.98),(31.30,120.58),(30.27,120.15),(32.02,120.86),(0,0)])
def test_nearby_cities_not_admitted_by_bounding_box(monkeypatch,point):
 monkeypatch.setattr('services.online_ml.fetch',lambda *a:pytest.fail('outside coordinates must not call weather'))
 assert not contains(*point) and predict_online(*point)['reason']=='outside_model_scope'

def test_regional_training_provenance_and_geographic_holdouts():
 root=Path(__file__).resolve().parents[1];report=json.loads((root/'artifacts/hourly_regional/metrics.json').read_text(encoding='utf-8'))
 assert report['schema_version']==2 and len(report['sources'])==12
 assert report['splits']['test_2025']==105120
 assert len(report['spatial_holdout'])==report['unique_grid_cells']
 assert all(contains(s['latitude'],s['longitude']) and len(s['sha256'])==64 for s in report['sources'])
 assert report['selected']==min(report['validation_mae'],key=report['validation_mae'].get)
