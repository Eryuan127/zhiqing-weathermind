import math
from flask import Blueprint, request, jsonify
from services.geocoding_service import search_locations
from services.weather_service import get_weather
from services.http_client import UpstreamError
api = Blueprint('api', __name__, url_prefix='/api')
@api.errorhandler(UpstreamError)
def upstream_error(exc):
    return jsonify(error=str(exc)), 502
@api.get('/locations')
def locations():
    name = request.args.get('name', '').strip()
    if not 2 <= len(name) <= 100:
        return jsonify(error='请输入 2 至 100 个字符的城市名称。'), 400
    return jsonify(locations=search_locations(name))
@api.get('/weather')
def weather():
    try:
        lat = float(request.args.get('latitude', ''))
        lon = float(request.args.get('longitude', ''))
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify(error='请提供有效坐标：纬度 -90 至 90，经度 -180 至 180。'), 400
    result=get_weather(lat,lon)
    return jsonify(result)

@api.get('/ml/experiment')
def ml_experiment():
    from services.ml_service import experiment, ModelUnavailable
    try:
        return jsonify(experiment())
    except ModelUnavailable as exc:
        return jsonify(error=str(exc)), 503
@api.get('/ml/prediction')
def ml_prediction():
    from services.ml_service import predict, ModelUnavailable
    try:
        return jsonify(predict(request.args.get('date', '')))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except ModelUnavailable as exc:
        return jsonify(error=str(exc)), 503

@api.get('/ml/online')
def online_prediction():
    from services.online_ml import predict_online
    try:
        lat=float(request.args.get('latitude','')); lon=float(request.args.get('longitude',''))
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180: raise ValueError()
        return jsonify(predict_online(lat,lon))
    except (ValueError,TypeError): return jsonify(error='请提供有效坐标'),400

@api.get('/air-quality')
def air_quality():
    from services.air_quality import get_air_quality
    try:return jsonify(get_air_quality(float(request.args.get('latitude','')),float(request.args.get('longitude',''))))
    except (ValueError,TypeError):return jsonify(error='请提供有效坐标'),400

@api.get('/ml/hourly-experiment')
def hourly_experiment():
    import json
    from pathlib import Path
    path=Path(__file__).resolve().parent/'artifacts/hourly_regional/metrics.json'
    if not path.exists():return jsonify(error='小时模型实验尚未生成'),503
    return jsonify(json.loads(path.read_text(encoding='utf-8')))
