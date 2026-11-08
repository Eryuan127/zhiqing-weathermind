"""Fixed chronological train/validation/test experiment; no test-set selection."""
import argparse
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joblib
import numpy as np
import sklearn
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
from ml.dataset import build_dataset, FEATURES

def metrics(y, pred):
    return {'mae': float(mean_absolute_error(y, pred)), 'rmse': float(np.sqrt(mean_squared_error(y, pred)))}
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default='data/shanghai_2021_2025.json')
    p.add_argument('--output', default='artifacts/ml')
    args = p.parse_args()
    source = Path(args.data)
    data = json.loads(source.read_text(encoding='utf-8'))
    dates, X, y = build_dataset(data)
    dates = np.asarray(dates)
    train = dates < '2024-01-01'
    val = (dates >= '2024-01-01') & (dates < '2025-01-01')
    test = (dates >= '2025-01-01') & (dates <= '2025-12-31')
    if min(train.sum(), val.sum(), test.sum()) < 60:
        raise ValueError('Each fixed time split requires at least 60 valid samples')
    candidates = {'linear': make_pipeline(StandardScaler(), LinearRegression()), 'ridge': make_pipeline(StandardScaler(), Ridge(alpha=10)), 'random_forest': RandomForestRegressor(n_estimators=200, min_samples_leaf=5, max_depth=12, random_state=42, n_jobs=-1)}
    validation = {'persistence': metrics(y[val], X[val, 0])}
    for name, model in candidates.items():
        model.fit(X[train], y[train])
        validation[name] = metrics(y[val], model.predict(X[val]))
    # Include the naive baseline in model selection; do not force ML to win.
    selected = min(validation, key=lambda name: validation[name]['mae'])
    fit = train | val
    results = {'persistence': metrics(y[test], X[test, 0])}
    predictions = {'persistence': X[test, 0]}
    for name, model in candidates.items():
        model.fit(X[fit], y[fit])
        predictions[name] = model.predict(X[test])
        results[name] = metrics(y[test], predictions[name])
    # Ablation: remove calendar features, keeping the same Ridge configuration.
    ablated = make_pipeline(StandardScaler(), Ridge(alpha=10))
    ablated.fit(X[fit, :7], y[fit])
    predictions['ridge_no_calendar'] = ablated.predict(X[test, :7])
    results['ridge_no_calendar'] = metrics(y[test], predictions['ridge_no_calendar'])
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    def split_info(mask):
        return {'start': dates[mask][0], 'end': dates[mask][-1], 'samples': int(mask.sum())}
    report = {'task': 'One-day-ahead daily mean temperature, Shanghai ERA5 reanalysis', 'scope': 'Shanghai only; historical rolling one-step evaluation, not operational forecast accuracy', 'data_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'provenance': data.get('_provenance'), 'features': FEATURES, 'splits': {'train': split_info(train), 'validation': split_info(val), 'test': split_info(test)}, 'validation_metrics': validation, 'selected_by_validation_mae': selected, 'test_metrics': results, 'seed': 42, 'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'sklearn': sklearn.__version__}, 'limitations': ['ERA5 is reanalysis, not station observations', 'Historical lag values may be delayed or revised in live use', 'No claim to outperform Open-Meteo operational forecasts', 'No independent probability interval calibration']}
    report['worst_cases'] = sorted([{'date': str(d), 'actual': float(a), 'prediction': float(b), 'absolute_error': float(abs(a-b))} for d,a,b in zip(dates[test], y[test], predictions[selected])], key=lambda row: row['absolute_error'], reverse=True)[:10]
    (output/'metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output/'test_predictions.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'actual', *predictions])
        writer.writerows(zip(dates[test], y[test], *predictions.values()))
    # Serialized files are local trusted artifacts, never accepted as user uploads.
    joblib.dump({'selected': selected, 'model': candidates.get(selected), 'features': FEATURES, 'data_sha256': report['data_sha256']}, output/'model.joblib')
    lines = ['# Shanghai temperature experiment', '', 'Target: next-day daily mean temperature (Celsius).', '', '| Model | Validation MAE | Test MAE | Test RMSE |', '|---|---:|---:|---:|']
    for name, m in results.items():
        lines.append(f'| {name} | {validation.get(name, {}).get("mae", float("nan")):.3f} | {m["mae"]:.3f} | {m["rmse"]:.3f} |')
    lines += ['', f'Selected using validation only: {selected}', '', 'Calendar ablation is diagnostic only and is not used for selection.', '', *report['limitations']]
    (output/'experiment.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'selected': selected, 'test_metrics': results}, indent=2))
if __name__ == '__main__': main()
