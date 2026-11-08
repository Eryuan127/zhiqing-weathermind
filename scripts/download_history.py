"""Download fixed, reproducible ERA5 data. Run from the project root."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.http_client import fetch

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--latitude', type=float, default=31.22222)
    parser.add_argument('--longitude', type=float, default=121.45806)
    parser.add_argument('--start', default='2021-01-01')
    parser.add_argument('--end', default='2025-12-31')
    parser.add_argument('--output', default='data/shanghai_2021_2025.json')
    args = parser.parse_args()
    if not -90 <= args.latitude <= 90 or not -180 <= args.longitude <= 180:
        parser.error('Invalid coordinates')
    params = dict(latitude=args.latitude, longitude=args.longitude, start_date=args.start, end_date=args.end, daily='temperature_2m_mean', timezone='Asia/Shanghai', models='era5')
    data = fetch('https://archive-api.open-meteo.com/v1/archive', params)
    data['_provenance'] = {'source': 'Open-Meteo ERA5 reanalysis', 'url': 'https://archive-api.open-meteo.com/v1/archive', 'params': params, 'downloaded_at': datetime.now(timezone.utc).isoformat(), 'license': 'CC BY 4.0; attribution Open-Meteo / ECMWF ERA5'}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Saved {len(data.get("daily", {}).get("time", []))} days to {path}; SHA256 {hashlib.sha256(path.read_bytes()).hexdigest()}')
if __name__ == '__main__': main()
