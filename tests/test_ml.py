from datetime import date, timedelta
import pytest
from ml.dataset import features_for, build_dataset
from app import create_app

def test_features_only_use_prior_days():
    target=date(2025,1,10)
    history={target-timedelta(days=i):float(i) for i in range(1,8)}
    first=features_for(target,history)
    history[target]=9999
    history[target+timedelta(days=1)]=-9999
    assert features_for(target,history)==first
    assert first[:4]==[1,2,3,7]

def test_calendar_gaps_are_not_bridged():
    target=date(2025,1,10)
    history={target-timedelta(days=i):float(i) for i in range(1,8)}
    del history[target-timedelta(days=4)]
    assert features_for(target,history) is None

def test_null_history_rejected():
    target=date(2025,1,10)
    history={target-timedelta(days=i):float(i) for i in range(1,8)}
    history[target-timedelta(days=2)]=None
    assert features_for(target,history) is None

def test_duplicate_dates_rejected():
    with pytest.raises(ValueError):
        build_dataset({'daily':{'time':['2025-01-01','2025-01-01'],'temperature_2m_mean':[1,2]}})

def test_experiment_and_replay():
    client=create_app().test_client()
    report=client.get('/api/ml/experiment')
    if report.status_code==503:
        pytest.skip('Real experiment artifacts not generated')
    assert report.status_code==200
    splits=report.json['splits']
    assert splits['train']['end']<splits['validation']['start']<splits['test']['start']
    result=client.get('/api/ml/prediction?date=2025-11-06')
    assert result.status_code==200
    assert result.json['mode']=='historical_replay'
    assert result.json['input_end_date']<'2025-11-06'
    assert client.get('/api/ml/prediction?date=2026-11-07').status_code==400
    assert client.get('/api/ml/prediction?date=bad').status_code==400
