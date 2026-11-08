"""Read-only access to trusted local experiments; no training in HTTP requests."""
import json
import hashlib
from pathlib import Path
from datetime import date
ROOT = Path(__file__).resolve().parents[1]
class ModelUnavailable(Exception):
    pass
def experiment():
    path = ROOT/'artifacts/ml/metrics.json'
    if not path.exists():
        raise ModelUnavailable('尚未训练模型，请按 README 下载历史数据并运行训练脚本。')
    return json.loads(path.read_text(encoding='utf-8'))
def predict(target_date):
    import joblib
    from ml.dataset import features_for, read_history
    report = experiment()
    target = date.fromisoformat(target_date)
    # API is explicitly a replay endpoint; do not pass historical output off as live prediction.
    if not '2025-01-01' <= target.isoformat() <= '2025-12-31':
        raise ValueError('当前模型仅支持2025年测试区间的历史回放，不提供实时未来预测。')
    if not (ROOT/'data/shanghai_2021_2025.json').exists() or not (ROOT/'artifacts/ml/model.joblib').exists():
        raise ModelUnavailable('数据或模型文件缺失，请重新下载并训练。')
    data = json.loads((ROOT/'data/shanghai_2021_2025.json').read_text(encoding='utf-8'))
    raw = ROOT/'data/shanghai_2021_2025.json'
    if hashlib.sha256(raw.read_bytes()).hexdigest() != report['data_sha256']:
        raise ModelUnavailable('历史数据版本已变化，请重新训练后回放。')
    history = read_history(data)
    x = features_for(target, history)
    if x is None:
        raise ModelUnavailable('预测日前连续7日数据不足。')
    bundle = joblib.load(ROOT/'artifacts/ml/model.joblib')
    if bundle['data_sha256'] != report['data_sha256']:
        raise ModelUnavailable('模型与实验报告版本不一致，请重新训练。')
    prediction = x[0] if bundle['selected'] == 'persistence' else float(bundle['model'].predict([x])[0])
    return {'mode':'historical_replay', 'city':'上海', 'target_date':target.isoformat(), 'target':'daily_mean_temperature', 'unit':'°C', 'prediction':round(prediction, 1), 'actual':history.get(target), 'model':bundle['selected'], 'input_end_date':date.fromordinal(target.toordinal()-1).isoformat(), 'test_mae':report['test_metrics'][bundle['selected']]['mae'], 'notice':'历史回放，非实时预报；ERA5再分析数据不等同于站点观测。'}
