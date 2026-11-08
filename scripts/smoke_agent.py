"""Opt-in network smoke checks. Never calls Qwen or trains anything."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.online_ml import predict_online
from services.agent_tools import get_current_weather
result=dict(online=predict_online(31.23,121.47),current=get_current_weather.invoke(dict(latitude=31.23,longitude=121.47)))
path=Path(__file__).resolve().parents[1]/'artifacts/hourly/live_smoke.json'
path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved real API results:',path)
print('Online status:',result['online']['status'])
