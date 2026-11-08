from services.qwen_decision import compact_context,compact_history

def test_context_keeps_conditions_without_transport_metadata():
    context=dict(city='上海',latitude=31.23,location_verified_at=123,activity='跑步',preference='wind',avoid_wind=True,time_window=dict(dates=['2026-11-09'],period='下午',ranges=[dict(start='2026-11-09T14:00+08:00',end='2026-11-09T16:00+08:00')],duration_hours=2,avoid_rain=True,rain_threshold=20))
    compact=compact_context({'context':context})
    assert compact['city']=='上海' and compact['preference']=='wind'
    assert compact['time_window']['ranges']==context['time_window']['ranges']
    assert compact['time_window']['duration_hours']==2 and compact['time_window']['avoid_rain']
    assert 'latitude' not in compact and 'location_verified_at' not in compact
    assert 'latitude' in context

def test_history_preserves_recent_questions_and_limits_repeated_answers():
    history=[dict(user='早期问题',assistant='旧回答'*300),dict(user='明天上海怎么穿',assistant='详细天气报告'*100),dict(user='长袖加长裤会冷吗',assistant='建议带外套。')]
    compact=compact_history({'history':history})
    assert len(compact)==2 and compact[0]=={'user':'明天上海怎么穿'}
    assert compact[1]['assistant']=='建议带外套。'
    assert len(compact_history({'history':[history[0]]})[0]['assistant'])<280
    assert compact_history({})==[]
