"""Explicit live evaluation; no mocked success or automatic paid-model switching."""
import sys,os,json,tempfile,time,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from services.weather_agent import chat
parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true',help='Allow real external API requests');parser.add_argument('--mode',choices=['rules','qwen'],default='rules');parser.add_argument('--limit',type=int,default=3);parser.add_argument('--case',help='Only run one case ID, e.g. T06');args=parser.parse_args()
if not args.live:parser.error('Use --live to permit external requests. Qwen mode may consume configured model quota.')
root=Path(__file__).resolve().parents[1];cases=json.loads((root/'data/task_benchmark.json').read_text(encoding='utf-8'))['cases'];cases=[c for c in cases if not args.case or c['id']==args.case][:max(1,min(20,args.limit))];records=[]
if not cases:parser.error('Unknown case ID')
with tempfile.TemporaryDirectory() as tmp:
 os.environ['AGENT_DB']=tmp+'/evaluation.sqlite3';create_app()
 for case in cases:
  start=time.monotonic()
  try:
   turns=[chat('eval-'+case['id'],text,mode=args.mode) for text in case['turns']];result=turns[-1]
   valid=not result['tools'] if case.get('no_tools') else result['city']==case['city'] and case['tool'] in [t['name'] for t in result['tools']] and all(t['status'] in ('ok','experimental') for t in result['tools'])
   if args.mode=='qwen':valid=valid and all(t['mode']=='qwen' for t in turns)
   records.append(dict(id=case['id'],contract_pass=valid,elapsed_ms=round((time.monotonic()-start)*1000),turns=turns))
  except Exception as e:records.append(dict(id=case['id'],contract_pass=False,error_type=type(e).__name__))
report=dict(kind='Live API contract evaluation; not independent semantic/user accuracy',mode=args.mode,tested=len(records),passed=sum(r['contract_pass'] for r in records),records=records)
out=root/'artifacts/evaluation';out.mkdir(exist_ok=True);path=out/(time.strftime('%Y%m%d-%H%M%S')+'-'+args.mode+'.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(str(path));print('tested',report['tested'],'passed',report['passed'])
