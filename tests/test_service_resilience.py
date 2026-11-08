"""Network/cache failures are Mock-only; no external requests in this module."""
import pytest,requests,json
from services import http_client as http
from services import geocoding_service as geo
@pytest.fixture(autouse=True)
def isolate(monkeypatch,tmp_path):
    monkeypatch.setenv("AGENT_DB",str(tmp_path/"resilience.sqlite3"))
    from services.agent_tools import _WEATHER_CACHE
    _WEATHER_CACHE.clear()
    geo._CACHE.clear();token=http.DIAGNOSTICS.set([]);rid=http.REQUEST_ID.set('test-request')
    monkeypatch.setattr(http.time,'sleep',lambda seconds:None)
    yield
    http.DIAGNOSTICS.reset(token);http.REQUEST_ID.reset(rid);geo._CACHE.clear()

def response(status=200,body='{}'):
    r=requests.Response();r.status_code=status;r._content=body.encode();return r

def test_timeout_is_bounded_and_redacted(monkeypatch):
    calls=[]
    def fail(*args,**kwargs):calls.append(kwargs);raise requests.Timeout('secret-token-must-never-log')
    monkeypatch.setattr(requests,'get',fail)
    with pytest.raises(http.UpstreamError) as error:http.fetch('https://geocoding-api.open-meteo.com/v1/search',{'name':'上海'})
    assert len(calls)==2 and error.value.kind=='timeout' and error.value.service=='geocoding'
    trail=http.DIAGNOSTICS.get();assert len(trail)==2 and trail[0]['request_id']=='test-request'
    assert 'secret-token' not in json.dumps(trail) and trail[0]['timeout']==[5,20]

@pytest.mark.parametrize('status,retries',[(429,2),(503,2),(401,1),(400,1)])
def test_http_status_preserved_and_retry_policy(monkeypatch,status,retries):
    calls=[]
    def get(*a,**k):calls.append(1);return response(status)
    monkeypatch.setattr(requests,'get',get)
    with pytest.raises(http.UpstreamError) as error:http.fetch('https://api.open-meteo.com/v1/forecast',{})
    assert error.value.status_code==status and len(calls)==retries and error.value.kind=='http'

def test_connection_retry_then_success(monkeypatch):
    calls=[]
    def get(*a,**k):
        calls.append(1)
        if len(calls)==1:raise requests.ConnectionError()
        return response(200,'{"ok":true}')
    monkeypatch.setattr(requests,'get',get)
    assert http.fetch('https://api.open-meteo.com/v1/forecast',{})['ok']
    assert [r['status'] for r in http.DIAGNOSTICS.get()]==['error','ok']

def test_cached_coordinates_expire_and_are_copy_safe(monkeypatch):
    clock=[0];calls=[]
    monkeypatch.setattr(geo.time,'monotonic',lambda:clock[0])
    def fetch(*a):calls.append(1);return dict(results=[dict(name='上海',latitude=31.22,longitude=121.46,timezone='Asia/Shanghai')])
    monkeypatch.setattr(geo,'fetch',fetch)
    first=geo.search_locations('上海');first[0]['latitude']=0
    assert geo.search_locations('上海')[0]['latitude']==31.22 and len(calls)==1
    clock[0]=geo.CACHE_TTL+1;geo.search_locations('上海');assert len(calls)==2

def test_network_failure_is_not_cached_as_city_missing(monkeypatch):
    def fail(*a):raise http.UpstreamError('城市查询网络连接失败',kind='network',service='geocoding')
    monkeypatch.setattr(geo,'fetch',fail)
    with pytest.raises(http.UpstreamError):geo.search_locations('上海')
    assert not geo._CACHE

def test_invalid_json_is_protocol_error(monkeypatch):
    monkeypatch.setattr(requests,'get',lambda *a,**k:response(200,'not-json'))
    with pytest.raises(http.UpstreamError) as error:http.fetch('https://api.open-meteo.com/v1/forecast',{})
    assert error.value.kind=='invalid_response'

def test_same_coordinate_weather_cache_safe_fallback(monkeypatch):
    from services import agent_tools as at
    success=dict(source='Open-Meteo',timezone='Asia/Shanghai',current=dict(time='2026-11-06T18:00',temperature=16),hourly=[],daily=[],warnings=[])
    monkeypatch.setattr(at,'get_weather',lambda *a:success)
    at.get_current_weather.invoke(dict(latitude=31.22,longitude=121.46))
    def fail(*a):raise http.UpstreamError('天气API网络失败',kind='network',service='weather')
    monkeypatch.setattr(at,'get_weather',fail)
    result=at.get_current_weather.invoke(dict(latitude=31.22,longitude=121.46))
    assert result['cached'] and result['updated_at']=='2026-11-06T18:00'
    assert result['data']['temperature']==16 and '缓存' in result['warnings'][0]
    with pytest.raises(http.UpstreamError):at.get_current_weather.invoke(dict(latitude=30.27,longitude=120.15))
    key=(31.22,121.46);at._WEATHER_CACHE[key]=(http.time.monotonic()-301,success)
    with pytest.raises(http.UpstreamError):at.get_current_weather.invoke(dict(latitude=31.22,longitude=121.46))

def test_tls_reason_recorded_without_raw_exception(monkeypatch):
    def fail(*a,**k):raise requests.exceptions.SSLError('UNEXPECTED_EOF secret-password')
    monkeypatch.setattr(requests,'get',fail)
    with pytest.raises(http.UpstreamError):http.fetch('https://api.open-meteo.com/v1/forecast',{})
    trail=http.DIAGNOSTICS.get()
    assert trail[-1]['network_reason']=='tls_unexpected_eof' and 'secret-password' not in json.dumps(trail)

def test_geocoding_cache_survives_memory_reset(monkeypatch):
    calls=[]
    def fetch(*a):calls.append(1);return dict(results=[dict(name='上海',latitude=31.22,longitude=121.46,timezone='Asia/Shanghai')])
    monkeypatch.setattr(geo,'fetch',fetch)
    geo.search_locations('上海');geo._CACHE.clear()
    def offline(*a):raise AssertionError('disk cache must be used')
    monkeypatch.setattr(geo,'fetch',offline)
    result=geo.search_locations('上海')
    assert result[0]['latitude']==31.22 and len(calls)==1
    assert http.DIAGNOSTICS.get()[-1]['status']=='persistent_cache_hit'

@pytest.mark.parametrize('mode,fallback',[('auto',True),('system',False)])
def test_proxy_tls_eof_direct_fallback(monkeypatch,mode,fallback):
    monkeypatch.setenv('WEATHER_PROXY_MODE',mode)
    monkeypatch.setattr(requests.utils,'get_environ_proxies',lambda url:{'https':'http://private-proxy'})
    calls=[]
    def get(*args,**kwargs):
        calls.append(kwargs)
        if len(calls)==1 or not fallback:raise requests.exceptions.SSLError('UNEXPECTED_EOF secret')
        return response(200,'{"ok":true}')
    monkeypatch.setattr(requests,'get',get)
    if fallback:assert http.fetch('https://api.open-meteo.com/v1/forecast',{})['ok']
    else:
        with pytest.raises(http.UpstreamError):http.fetch('https://api.open-meteo.com/v1/forecast',{})
    assert len(calls)==2 and 'proxies' not in calls[0]
    assert ('proxies' in calls[1])==fallback
    assert all(call.get('verify',True) is True for call in calls)
    assert 'secret' not in json.dumps(http.DIAGNOSTICS.get())
    assert http.DIAGNOSTICS.get()[-1]['connection_route']==('direct' if fallback else 'system')

def test_proxy_certificate_error_never_bypasses_verification(monkeypatch):
    monkeypatch.setenv('WEATHER_PROXY_MODE','auto')
    calls=[]
    def get(*args,**kwargs):calls.append(kwargs);raise requests.exceptions.SSLError('CERTIFICATE_VERIFY_FAILED')
    monkeypatch.setattr(requests,'get',get)
    with pytest.raises(http.UpstreamError):http.fetch('https://api.open-meteo.com/v1/forecast',{})
    assert len(calls)==2 and all('proxies' not in c and c.get('verify',True) for c in calls)

def test_direct_proxy_mode_and_host_boundary(monkeypatch):
    monkeypatch.setenv('WEATHER_PROXY_MODE','direct');calls=[]
    monkeypatch.setattr(requests,'get',lambda *a,**k:(calls.append(k) or response(200,'{"ok":true}')))
    http.fetch('https://geocoding-api.open-meteo.com/v1/search',{})
    assert calls[-1]['proxies']=={'http':'','https':'','all':''}
    http.fetch('https://example.com/api',{});assert 'proxies' not in calls[-1]
