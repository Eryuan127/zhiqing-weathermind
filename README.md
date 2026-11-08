# 知晴 WeatherMind

面向校园通勤与户外活动的天气决策原型。游客可定位或手动选城查看天气，注册登录后使用规则或 Qwen 助手。首页提供当前天气、逐小时趋势、七日预报、空气质量和本地下一小时气温实验。

## 本地运行

需要 Python 3.11+，推荐使用独立虚拟环境。项目使用 Flask、SQLite、原生 JavaScript、CSS Grid 与本地 ECharts，无需 Node 构建。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock.txt
.venv\Scripts\python run_weather.py
```

打开 http://127.0.0.1:5001/ 。端口占用时入口拒绝重复启动，可用 `--port 5002` 更换端口。默认 AGENT_DB 为 data/agent.sqlite3。数据库、.env、会话密钥和用户位置不得公开提交。

## 位置与账号

首次进入不强制注册。浏览器定位需要授权及 HTTPS/localhost，拒绝、不支持或超时时提示手动选城，不回退上海。城市名称由 BigDataCloud 客户端逆地理编码解析；失败时保留坐标查询，提示城市名解析失败。

助手优先使用本轮明确城市、当前会话已确认且有效的位置、当前账号绑定的首页位置，否则询问城市。退出/切换账号会清理共享位置并通知其他标签页刷新。小窗单独新建会话，最多5次提问，之后可转完整聊天继续。助手接口服务端要求登录并校验会话归属。

## 数据与模型边界

- 天气：Open-Meteo，当前/小时/日预报分别展示，降水概率不是实时降水量。
- 空气质量：Open-Meteo / CAMS，使用 US AQI 和 PM2.5（μg/m³）；网格模式估计与预报，不等于附近站点实测，也不等于中国 AQI。
- 下一小时模型：上海市域多区域 Ridge，预测下一整点。历史ERA5滚动一步评估不代表实时精度；模型按上海市域多边形检查坐标，覆盖郊区与主要岛屿，不覆盖其他城市，也不能代替明天下午预报。
- 日均温历史回放为另一套实验，验证集选择线性回归；不能与小时 Ridge 混为一谈。

## Qwen（可选）

规则模式无需模型密钥。按 .env.example 在本地配置 DASHSCOPE_API_KEY、QWEN_MODEL、QWEN_BASE_URL；只有自行确认额度及用完即停后才设置 QWEN_FREE_ONLY_CONFIRMED=true。程序不能读取账户余额或承诺免费。密钥仅在后端读取。Qwen失败明确标注，不伪称成功、不自动换模型重试。

## 测试与证据

```powershell
python -m pytest tests -q
python scripts/analyze_hourly.py
# 显式许可真实外部请求；Qwen模式可能消耗所配置模型额度
python scripts/evaluate_tasks.py --live --mode rules --limit 6
python scripts/evaluate_tasks.py --live --mode qwen --limit 3
```

pytest 使用明确的离线测试夹具，不代表真实API成功率。data/task_benchmark.json 为20条开发回归任务，并非独立留出集或用户研究。真实调用会生成独立时间戳JSON，保留失败记录，不覆盖旧实验。

模型主实验：scripts/train_hourly.py、scripts/train_models.py。诊断脚本 analyze_hourly.py 不改写已部署模型、不在测试集重选模型，输出分季节、气温突变和特征消融分析及逐条预测。

- artifacts/hourly/metrics.json：小时模型验证与测试指标。
- artifacts/hourly/analysis/：本次本地重算的分组与消融证据。
- artifacts/evaluation/：真实任务调用记录。
- artifacts/improvement-tests.txt：本轮程序测试结果。
- docs/SKILL_REUSE.md：设计技能与工程复用记录。
- docs/USER_STUDY.md：待实施用户任务测试；不包含虚构参与者或结果。

## 来源

[Open-Meteo天气](https://open-meteo.com/en/docs)、[空气质量/CAMS来源与署名](https://open-meteo.com/en/docs/air-quality-api)、[BigDataCloud客户端城市解析](https://www.bigdatacloud.com/docs/free-api/free-reverse-geocode-to-city-api)、[Material UI网格](https://mui.com/material-ui/react-grid/)、[Element Plus设计原则](https://element-plus.org/en-US/guide/design.html)、[shadcn主题](https://ui.shadcn.com/docs/theming)。

代码依赖锁定见 requirements-lock.txt，ECharts 为 Apache-2.0；API数据按各提供者条款使用，本项目为课程原型。AI辅助参与了代码、测试和设计；报告作者仍须核查数据并解释模型和代码。课程正式提交还需完成PDF报告、可访问仓库或网盘、演示及来源许可清单。

## 停止生成与消息操作

完整助手输入框右侧在请求和逐字显示期间提供“停止生成”。前端立即停止增加文字，服务端在节点及工具边界检查取消标记，并以事务提交对话；已取消结果不会随后写入历史。Qwen 的理解/规划及结果解释已采用流式上游连接；取消后会中止正在等待的读取并关闭该次HTTP连接，阻止后续调用。服务商收到终止前已经处理的输入与已经生成的输出仍可能消耗token，不能撤回既有用量。天气等非模型接口仍在节点边界检查取消。

气泡悬停或键盘聚焦显示灰色复制/编辑图标；触屏上常显。用户消息编辑后作为新问题重新提交。助手回复可保存个人修订并标记已编辑，不改写原始工具依据，也不把个人修订冒充模型原答。清除会话同时清理修订和取消未完成请求。

### Qwen 流式用量记录

正常结束请求启用 include_usage，保存服务商返回的最终用量。中途取消可能收不到最终用量包，记录 usage=null、usage_complete=false，不把缺失用量当作0。model_stream审计只记录请求编号、片段数、连接关闭与取消状态，不保存提示词或密钥。若完整模型结果已返回、页面仅剩逐字显示，此时停止显示不能追回已发生token。

## 上海全市小时模型 v2

默认在线预测已切换到 artifacts/hourly_regional/model.joblib。新模型使用上海市域12个公开采样点（10个ERA5网格）的2023—2025真实历史小时数据，按2023训练、2024验证、2025测试，另按整个实际网格做地理留出诊断；不读取用户位置历史训练。

```powershell
python scripts/prepare_shanghai_boundary.py
python scripts/train_shanghai_regional.py
```

脚本复用 data/shanghai_regional/points.json 固定采样坐标、缓存原始响应并检查坐标一致性，不覆盖原 artifacts/hourly 下的单点模型。首次运行训练脚本会访问历史API并控制请求间隔。脚本只用验证集选模，地理留出不参与选模。每个采样点的测试误差、原始数据哈希与逐条预测保存在新目录。

边界采用 DataV.GeoAtlas / AMAP 的16区几何，仅供学习交流，不是权威测绘界线，商业发布或再分发前需另核验授权；不把整块矩形误当上海。源坐标GCJ-02，经MIT许可的coordTransform_py数学转换代码迭代近似为WGS84，来源/许可见 data/shanghai_boundary.source.json 与 docs/licenses/。首次准备边界需已有 data/shanghai_datav_gcj02.geojson；来源URL记录在元数据中。

0.444°C 为多点ERA5历史滚动测试MAE，不是实时精度保证。部分留出网格不优于持久性基线；数据网格粗、邻近位置相关，不能据此宣称每个街道已验证。报告：SHANGHAI_REGIONAL_REPORT.md。
