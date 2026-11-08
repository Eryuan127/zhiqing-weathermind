"""Deterministic AQ fixtures for offline tests; live validation is separate."""
import pytest
from datetime import timedelta

@pytest.fixture(autouse=True)
def offline_air_quality(monkeypatch):
    def fixture(lat,lon):
        from services.time_constraints import local_now
        now=local_now('Asia/Shanghai').replace(tzinfo=None,minute=0,second=0,microsecond=0)
        return dict(status='ok',source='UNIT TEST CAMS fixture',standard='US AQI',timezone='Asia/Shanghai',updated_at=now.isoformat(),current=dict(time=now.isoformat(),us_aqi=42,pm2_5=9),hourly=[dict(time=(now.replace(hour=0)+timedelta(hours=i)).isoformat(),us_aqi=42,pm2_5=9) for i in range(96)],notice='单元测试夹具，非真实API结果')
    monkeypatch.setattr('services.air_quality.get_air_quality',fixture)
