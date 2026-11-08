import pytest
from services.weather_agent import token_usage
from test_qwen_phase4 import isolated, decision

def test_chat_exports_turn_total(monkeypatch):
    from services import qwen_decision as q, weather_agent as agent
    monkeypatch.setattr(q,'decide',lambda s:(decision(),dict(status='ok',usage={'total_tokens':400})))
    monkeypatch.setattr(q,'explain',lambda s,t:(t,dict(status='ok',usage={'total_tokens':250})))
    result=agent.chat('tokens','上海当前天气',mode='qwen')
    assert result['execution']['token_usage']==dict(total_tokens=650,complete=True)
    rules=agent.chat('rules-tokens','上海当前天气',mode='rules')
    assert 'token_usage' not in rules['execution']

@pytest.mark.parametrize('logs,expected',[
    ([{'usage':{'total_tokens':400}},{'usage':{'total_tokens':250}}],{'total_tokens':650,'complete':True}),
    ([{'usage':{'total_tokens':400}},{}],{'total_tokens':400,'complete':False}),
    ([{},None],{'total_tokens':None,'complete':False}),
    ([{'usage':{'total_tokens':0}}],{'total_tokens':0,'complete':True}),
    ([{'usage':{'total_tokens':-1}}],{'total_tokens':None,'complete':False}),
])
def test_sum_turn_usage(logs,expected):
    assert token_usage(*logs)==expected
