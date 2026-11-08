"""Daily temperature features; every target uses only earlier dates."""
from datetime import date, timedelta
import math
import numpy as np
FEATURES = ['lag_1', 'lag_2', 'lag_3', 'lag_7', 'mean_3', 'mean_7', 'std_7', 'day_sin', 'day_cos']
def features_for(target, history):
    dates = [target - timedelta(days=i) for i in range(1, 8)]
    if any(d not in history or history[d] is None for d in dates):
        return None
    v = [float(history[d]) for d in dates]
    if not all(math.isfinite(x) for x in v):
        return None
    phase = 2 * math.pi * (target.timetuple().tm_yday - 1) / 365.2425
    return [v[0], v[1], v[2], v[6], float(np.mean(v[:3])), float(np.mean(v)), float(np.std(v)), math.sin(phase), math.cos(phase)]
def read_history(data):
    daily = data.get('daily', {})
    times, values = daily.get('time', []), daily.get('temperature_2m_mean', [])
    if len(times) != len(values) or len(set(times)) != len(times):
        raise ValueError('历史数据日期重复或字段长度不一致')
    return {date.fromisoformat(t): v for t, v in zip(times, values)}
def build_dataset(data):
    history = read_history(data)
    rows = []
    for target in sorted(history):
        x = features_for(target, history)
        y = history[target]
        if x is not None and y is not None and math.isfinite(float(y)):
            rows.append((target.isoformat(), x, float(y)))
    if not rows:
        raise ValueError('没有完整的连续7日历史窗口')
    return [r[0] for r in rows], np.asarray([r[1] for r in rows]), np.asarray([r[2] for r in rows])
