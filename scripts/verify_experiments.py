"""Recompute saved test metrics without training, network access or external packages."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path


def verify(root):
    metrics = json.loads((root / 'artifacts/hourly_regional/metrics.json').read_text(encoding='utf-8'))
    predictions = root / 'artifacts/hourly_regional/test_predictions.csv'
    if not predictions.exists():
        predictions = predictions.with_suffix('.csv.gz')
    opener = gzip.open if predictions.suffix == '.gz' else open
    errors = {name: [0.0, 0.0] for name in metrics['test_metrics']}
    count = 0
    with opener(predictions, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            if not row['time'].startswith('2025-'):
                raise ValueError('Prediction row outside the 2025 test split')
            actual = float(row['actual'])
            for name, sums in errors.items():
                error = float(row[name]) - actual
                if not math.isfinite(error):
                    raise ValueError('Non-finite error')
                sums[0] += abs(error)
                sums[1] += error * error
            count += 1
    expected_count = metrics['splits']['test_2025']
    if count != expected_count or count == 0:
        raise ValueError(f'Sample count mismatch: {count} != {expected_count}')
    calculated = {}
    for name, (absolute, squared) in errors.items():
        calculated[name] = {'mae': absolute / count, 'rmse': math.sqrt(squared / count)}
        for key, value in calculated[name].items():
            expected = metrics['test_metrics'][name][key]
            if not math.isclose(value, expected, rel_tol=0.0, abs_tol=1e-9):
                raise ValueError(f'{name} {key} mismatch: {value} != {expected}')
    return {'status': 'PASS', 'n': count, 'prediction_file': str(predictions.relative_to(root)),
            'file_sha256': hashlib.sha256(predictions.read_bytes()).hexdigest(), 'metrics': calculated}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root), ensure_ascii=False, indent=2))
