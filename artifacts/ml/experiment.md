# Shanghai temperature experiment

Target: next-day daily mean temperature (Celsius).

| Model | Validation MAE | Test MAE | Test RMSE |
|---|---:|---:|---:|
| persistence | 1.346 | 1.430 | 1.989 |
| linear | 1.270 | 1.363 | 1.822 |
| ridge | 1.308 | 1.396 | 1.858 |
| random_forest | 1.346 | 1.381 | 1.880 |
| ridge_no_calendar | nan | 1.429 | 1.926 |

Selected using validation only: linear

Calendar ablation is diagnostic only and is not used for selection.

ERA5 is reanalysis, not station observations
Historical lag values may be delayed or revised in live use
No claim to outperform Open-Meteo operational forecasts
No independent probability interval calibration