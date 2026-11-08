import pytest
from services.air_quality import get_air_quality
from services.http_client import UpstreamError
from services import weather_agent as agent
from test_agent_constraints import environment

def test_normalizes_air_quality_without_filling_missing_values(monkeypatch):
 monkeypatch.setattr('services.air_quality.fetch',lambda *a:dict(timezone='Asia/Shanghai',current={'time':'2026-11-06T18:00','us_aqi':40,'pm2_5':None},hourly={'time':['2026-11-06T19:00'],'us_aqi':[41],'pm2_5':[-1]}))
 data=get_air_quality(30,120)
 assert data['current']['pm2_5'] is None and data['hourly'][0]['pm2_5'] is None
 assert data['standard']=='US AQI' and '非附近' in data['notice']

@pytest.mark.parametrize('lat,lon',[(float('nan'),120),(91,120),(30,181)])
def test_invalid_coordinates(lat,lon):
 with pytest.raises(ValueError):get_air_quality(lat,lon)

def test_agent_uses_real_air_tool_contract():
 result=agent.chat('air-contract','上海明天下午AQI怎么样',mode='rules')
 assert result['tools'][0]['name']=='get_air_quality_forecast'
 assert 'US AQI' in result['response'] and '非附近监测站实测' in result['response']
 assert result['time_window']['period']=='下午'

def test_missing_air_data_rejected(monkeypatch):
 def missing(*a):return dict(status='ok',source='fixture',timezone='Asia/Shanghai',updated_at='2026-11-06T18:00',hourly=[dict(time='2026-11-07T12:00',us_aqi=None,pm2_5=9)],notice='fixture')
 monkeypatch.setattr('services.air_quality.get_air_quality',missing)
 result=agent.chat('missing-air','上海明天下午AQI怎么样',mode='rules')
 assert '数据不完整' in result['response']


def test_air_quality_comparison_reports_both_cities():
 result=agent.chat('air-compare','上海和杭州明天下午空气质量',mode='rules')
 assert len(result['tools'])==2 and '上海所选时段' in result['response'] and '杭州所选时段' in result['response']
