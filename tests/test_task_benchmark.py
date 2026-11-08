import json
from pathlib import Path
import pytest
from services.weather_agent import chat
from test_agent_constraints import environment
CASES=json.loads((Path(__file__).resolve().parents[1]/'data/task_benchmark.json').read_text(encoding='utf-8'))['cases']
@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_task_contract(case):
 for text in case['turns']:result=chat('benchmark-'+case['id'],text,mode='rules')
 if case.get('no_tools'):assert not result['tools']
 else:
  assert result['city']==case['city']
  assert case['tool'] in [t['name'] for t in result['tools']]
