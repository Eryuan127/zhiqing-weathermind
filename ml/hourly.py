"""Leakage-safe hourly features, distinct from the daily replay experiment."""
import math
from datetime import datetime, timedelta
FEATURES = ['lag_1', 'lag_2', 'lag_24', 'hour_sin', 'hour_cos']
def features(target, history):
    values = [history.get(target-timedelta(hours=h)) for h in (1,2,24)]
    if any(not isinstance(v,(float,int)) or not math.isfinite(v) for v in values): return None
    return values + [math.sin(target.hour*math.tau/24), math.cos(target.hour*math.tau/24)]
