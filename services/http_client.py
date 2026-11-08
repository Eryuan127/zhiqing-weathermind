"""Bounded upstream retries and redacted diagnostics, never logs request parameters."""
import requests,time,uuid,logging,json,os
from urllib.parse import urlparse
from contextvars import ContextVar
DIAGNOSTICS=ContextVar('weather_diagnostics',default=None)
REQUEST_ID=ContextVar('weather_request_id',default=None)

def record(metadata):
    row=dict(request_id=REQUEST_ID.get(),**metadata)
    entries=DIAGNOSTICS.get()
    if entries is not None:entries.append(row)
    if row.get('status')=='error':logging.getLogger('weathermind.upstream').warning(json.dumps(row))

class UpstreamError(Exception):
    def __init__(self,message,*,kind='upstream',service=None,status_code=None,error_type=None):
        super().__init__(message);self.kind=kind;self.service=service;self.status_code=status_code;self.error_type=error_type
    def diagnostic(self):return dict(kind=self.kind,service=self.service,status_code=self.status_code,error_type=self.error_type)

def fetch(url,params):
    service='geocoding' if 'geocoding-api' in url else 'air_quality' if 'air-quality-api' in url else 'weather'
    host=urlparse(url).hostname or ''
    open_meteo=host=='open-meteo.com' or host.endswith('.open-meteo.com')
    proxy_mode=os.getenv('WEATHER_PROXY_MODE','auto') if open_meteo else 'system'
    if proxy_mode not in ('auto','system','direct'):raise UpstreamError('天气代理配置无效，请使用auto、system或direct。',kind='configuration',service=service)
    direct=proxy_mode=='direct'
    for attempt in range(1,3):
        started=time.monotonic();status_code=None
        try:
            options=dict(params=params,timeout=(5,20))
            if direct:options['proxies']={'http':'','https':'','all':''}
            response=requests.get(url,**options);status_code=response.status_code
            response.raise_for_status();data=response.json()
            if not isinstance(data,dict) or data.get('error'):raise ValueError('Invalid response')
            record(dict(connection_route='direct' if direct else 'system',service=service,status='ok',status_code=status_code,attempt=attempt,timeout=[5,20],elapsed_ms=round((time.monotonic()-started)*1000),call_chain='graph → tool/service → HTTP'))
            return data
        except (requests.RequestException,ValueError) as exc:
            kind='timeout' if isinstance(exc,requests.Timeout) else 'network' if isinstance(exc,requests.ConnectionError) else 'http' if isinstance(exc,requests.HTTPError) else 'invalid_response'
            detail=str(exc).upper()
            network_reason='tls_unexpected_eof' if 'UNEXPECTED_EOF' in detail else 'tls_certificate_verification' if 'CERTIFICATE_VERIFY_FAILED' in detail else 'tls_error' if isinstance(exc,requests.exceptions.SSLError) else None
            record(dict(connection_route='direct' if direct else 'system',network_reason=network_reason,service=service,status='error',kind=kind,error_type=type(exc).__name__,status_code=status_code,attempt=attempt,timeout=[5,20],elapsed_ms=round((time.monotonic()-started)*1000),call_chain='graph → tool/service → HTTP'))
            retry=kind in ['timeout','network'] or status_code in [429,500,502,503,504]
            if attempt<2 and retry:
                # A broken local proxy must not disable certificate verification.
                # Use the existing second attempt, with direct HTTPS, only for Open-Meteo.
                if proxy_mode=='auto' and not direct and network_reason=='tls_unexpected_eof' and requests.utils.get_environ_proxies(url):direct=True
                time.sleep(.15);continue
            label='城市查询' if service=='geocoding' else '空气质量API' if service=='air_quality' else '天气API'
            reason={'timeout':'请求超时','network':'网络连接失败','http':f'返回HTTP {status_code}','invalid_response':'返回数据无效'}[kind]
            raise UpstreamError(label+reason+'，请稍后重试。',kind=kind,service=service,status_code=status_code,error_type=type(exc).__name__) from exc
