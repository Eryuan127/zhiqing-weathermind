from pathlib import Path
import csv,json,hashlib,gzip
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from datetime import datetime,timedelta
import numpy as np
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--output',type=Path)
args=parser.parse_args();R=args.root;O=args.output or R/'artifacts/report_figures';O.mkdir(parents=True,exist_ok=True)
available={f.name for f in font_manager.fontManager.ttflist}
font=next((name for name in ['Microsoft YaHei','Noto Sans CJK SC','SimHei','WenQuanYi Micro Hei'] if name in available),'DejaVu Sans')
if font=='DejaVu Sans':print('Install a CJK font such as Noto Sans CJK SC for readable Chinese chart labels.')
plt.rcParams.update({'font.family':font,'font.size':10,'axes.unicode_minus':False,'savefig.dpi':220})
source=R/'artifacts/hourly_regional/test_predictions.csv'
if not source.exists():source=source.with_suffix('.csv.gz')
opener=gzip.open if source.suffix=='.gz' else open
with opener(source,'rt',encoding='utf-8',newline='') as stream:rows=list(csv.DictReader(stream))
y=np.array([float(r['actual']) for r in rows]);names=['persistence','linear','ridge'];labels=['持久性基线','线性回归','Ridge'];colors=['#999999','#6586a8','#1c527a']
calc={}
for name in names:
 z=np.array([float(r[name]) for r in rows]);calc[name]={'mae':float(np.mean(abs(z-y))),'rmse':float(np.sqrt(np.mean((z-y)**2)))}
fig,axes=plt.subplots(1,2,figsize=(8,2.8))
for ax,key,title in zip(axes,['mae','rmse'],['(a) 测试集 MAE','(b) 测试集 RMSE']):
 values=[calc[n][key] for n in names];ax.bar(labels,values,color=colors,width=.55);ax.set_title(title);ax.set_ylabel('误差（°C）');ax.set_ylim(0,max(values)*1.24)
 ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
 for i,v in enumerate(values):ax.text(i,v+.012,f'{v:.6f}',ha='center',fontsize=9)
fig.tight_layout();fig.savefig(O/'01_测试集模型误差对比.png');plt.close(fig)
worst=max(rows,key=lambda r:abs(float(r['ridge'])-float(r['actual'])))
center=datetime.fromisoformat(worst['time']);subset=[r for r in rows if r['point']==worst['point'] and abs((datetime.fromisoformat(r['time'])-center).total_seconds())<=36*3600]
subset.sort(key=lambda r:r['time']);times=[datetime.fromisoformat(r['time']) for r in subset]
fig,ax=plt.subplots(figsize=(8,2.8))
for col,label,color,ls in [('actual','ERA5目标值','#222222','-'),('persistence','持久性基线','#aaaaaa','--'),('ridge','Ridge预测','#1c527a','-')]:
 ax.plot(times,[float(r[col]) for r in subset],label=label,color=color,linestyle=ls,linewidth=1.35)
ax.axvline(center,color='#a74e3e',linestyle=':',linewidth=1);ax.set_title('最大绝对误差案例附近72小时（SH09）');ax.set_ylabel('气温（°C）');ax.legend(ncol=3,frameon=False,fontsize=9);ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False)
import matplotlib.dates as mdates
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'));ax.xaxis.set_major_locator(mdates.HourLocator(interval=12));ax.tick_params(axis='x',labelsize=8)
fig.tight_layout();fig.savefig(O/'02_最大误差案例预测曲线.png');plt.close(fig)
manifest={'source':'artifacts/hourly_regional/test_predictions.csv','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'n':len(rows),'metrics':calc,'case_selection':'maximum absolute Ridge error; diagnostic, not representative performance','case':worst,'curve_n':len(subset)}
(O/'图表数据与来源.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
with (O/'最大误差案例曲线数据.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=subset[0].keys());w.writeheader();w.writerows(subset)
print(O)
