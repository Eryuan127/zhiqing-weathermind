from app import create_app
from services.weather_service import normalize, condition
from services.http_client import UpstreamError
import pytest

@pytest.mark.parametrize("query", ["", "latitude=nan&longitude=0", "latitude=91&longitude=0", "latitude=0&longitude=inf", "latitude=x&longitude=2"])
def test_coordinates(query):
    assert create_app().test_client().get('/api/weather?'+query).status_code == 400

def test_names():
    client=create_app().test_client()
    assert client.get('/api/locations?name= ').status_code==400
    assert client.get('/api/locations?name=a').status_code==400

def test_cross_midnight_and_missing():
    result=normalize({'timezone':'Asia/Shanghai','current':{'time':'2026-11-06T23:30'},'hourly':{'time':['2026-11-06T23:00','2026-11-07T00:00','2026-11-07T23:00','2026-11-08T00:00'],'temperature_2m':[1,2,3,4]}})
    assert [r['temperature'] for r in result['hourly']]==[2,3]
    assert result['hourly'][0]['precipitation_probability'] is None
    assert result['warnings']

def test_invalid_upstream():
    with pytest.raises(UpstreamError): normalize({})

def test_service_error(monkeypatch):
    def fail(*args): raise UpstreamError('unavailable')
    monkeypatch.setattr('weather_routes.get_weather',fail)
    assert create_app().test_client().get('/api/weather?latitude=0&longitude=0').status_code==502

def test_candidates(monkeypatch):
    monkeypatch.setattr('weather_routes.search_locations',lambda name: [])
    assert create_app().test_client().get('/api/locations?name=不存在').json=={'locations':[]}

def test_codes():
    assert condition(95)['description']=='雷暴'
    assert condition(None)['description']=='未知天气'
