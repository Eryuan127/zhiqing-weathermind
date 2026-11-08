"""Mock provider tests for free prose, protected facts and visible fallback."""
import json
import pytest
from services import qwen_decision as q, weather_agent as agent
from test_qwen_phase4 import isolated, fake_client, decision


def test_rewrites_whole_answer_and_receives_history(monkeypatch):
    from types import SimpleNamespace
    seen=[]
    evidence='上海 11月9日（周一）气温 8.2～15.9°C。'
    protected,facts=q.answer_evidence(evidence)
    def stream(factory,messages):
        seen.append(json.loads(messages[1].content))
        return SimpleNamespace(tool_calls=[dict(name='GroundedAnswer',args=dict(answer='只穿长袖长裤，早晚可能会冷。气温为{{fact_1}}，建议带件外套，午后按体感增减。'))],usage_metadata=None)
    monkeypatch.setattr(q,'stream_call',stream)
    text,log=q.explain(dict(message='只穿长袖长裤会冷吗',history=[{'user':'明天怎么穿','assistant':'建议带外套'}],intent='clothing'),evidence)
    assert log['status']=='ok' and text!=evidence
    assert '8.2～15.9°C' in text and '{{' not in text
    assert seen[0]['recent_history'] and seen[0]['verified_evidence']==protected


@pytest.mark.parametrize('draft',[
    '明天99°C。','温度为{{fact_99}}。','明天三十摄氏度。',
    '放心穿就行。','气温{{fact_0}}。<script>alert()</script>',
])
def test_invalid_facts_fall_back(monkeypatch,draft):
    fake_client(monkeypatch,[dict(name='GroundedAnswer',args=dict(answer=draft))])
    evidence='气温20°C。'
    text,log=q.explain({'message':'天气'},evidence)
    assert text==evidence and log['status']=='error'


def test_end_to_end_modes_differ(monkeypatch):
    monkeypatch.setattr(q,'decide',lambda s:(decision(),dict(status='ok')))
    fake_client(monkeypatch,[dict(name='GroundedAnswer',args=dict(answer='现在出门可以先参考气温{{fact_0}}，再按自己的体感增减衣服。'))])
    rules=agent.chat('rule-answer','上海当前天气',mode='rules')
    model=agent.chat('model-answer','上海当前天气',mode='qwen')
    assert model['mode']=='qwen'
    assert model['response']!=rules['response']
    assert model['execution']['explanation']['stage']=='generate_grounded_answer'
    assert model['tools'][0]['result']['data']==rules['tools'][0]['result']['data']
