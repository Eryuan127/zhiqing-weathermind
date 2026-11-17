# 上海市域下一小时气温模型升级记录

## 已交付

默认在线小时预测切换到多区域模型，不再用中心坐标±0.15度作为范围。范围按16个区的市域多边形判断，覆盖郊区和主要岛屿；昆山、苏州、杭州等邻市不因落在大矩形内就被放行。原中心单点模型、指标和日均温实验保留，未覆盖。

## 数据与训练

12个公开研究采样点，实际对应10个ERA5网格。真实历史数据通过Open-Meteo历史API取得，时间2023-01-01至2025-12-31；原始响应、请求参数、UTC获取时间和SHA256保留在data/shanghai_regional。不是用户GPS，不是气象站实测。

每个点使用目标之前的1、2、24小时气温和小时正余弦，目标为下一整点气温；不取目标小时或未来输入，不跨缺失补造数据。2023训练，2024验证，2025测试；标准化只在相应拟合集拟合。验证比较持久性、线性回归、Ridge（alpha=10），选择Ridge后用2023—2024重新拟合；测试集不选模。

初始粗边界有误，两个初始样本被识别为新边界之外，按地理有效性替换，原始响应留在initial-boundary-samples目录，不参与最终训练。替换不是依据测试误差筛选。

样本数：训练104832、验证105408、测试105120。采样点同网格及邻近点相关，不能将这些记录宣称为完全独立样本。

## 结果

| 模型 | 验证MAE °C | 测试MAE °C | 测试RMSE °C |
| --- | --- | --- | --- |
| persistence | 0.427124 | 0.468988 | 0.797486 |
| linear | 0.427019 | 0.443984 | 0.685559 |
| ridge | 0.426907 | 0.443937 | 0.685480 |

Ridge相对本次同数据持久性基线测试MAE降低约5.34%。旧单点实验时间和地点不同，不能用旧MAE与新MAE的差值宣称公平提升。

另做整网格地理留出：把同一个实际返回气象网格下的所有采样点一起排除，固定Ridge超参数，仅作诊断、不参与选模。10组中7组优于持久性，3组不优于；因此不能宣称所有区域均优于基线。逐组和逐点结果见metrics.json，逐条预测见artifacts/hourly_regional/test_predictions.csv.gz（解压为CSV）。

历史评估不是实时精度。当前线上输入来自Open-Meteo业务模式分析，ERA5训练到业务输入存在分布差异；未知实时误差不得宣称0.444°C。

## 边界与许可

第一份geoBoundaries粗边界误排金山、临港等地，未用于部署。最终使用DataV.GeoAtlas/AMAP的16区几何，官方用途为学习交流；本课程原型适用，商业发布或再分发前需另核查授权。来源 https://geo.datav.aliyun.com/areas_v3/bound/310000_full.json ，官方说明 https://help.aliyun.com/en/datav/datav-7-0/user-guide/datav-geoatlas-widgets/ 。不是权威测绘/最新海岸线。

源GCJ-02坐标以迭代近似转换成WGS84后才用于浏览器GPS/天气坐标判定，未混用坐标系。转换代码摘用wandergis/coordTransform_py的4个数学函数，MIT授权、原作者和来源哈希保留在docs/licenses。源数据哈希、16区和转换说明见data/shanghai_boundary.source.json。

## 验证

全量pytest：242 passed（13条现有依赖弃用警告），这是2026年11月7日的历史记录；当前复测见docs/VALIDATION.md。

新增回归覆盖16个区加临港、长兴、横沙代表坐标均能调用真实本地模型；这些测试的气温输入是明确夹具，不代表真实天气API结果。保留目标小时污染测试，确认不使用未来值。域外坐标在调用天气前被拒绝。

独立真实API输入加真实本地模型检查（无Mock）：
- 中心城区：experimental，预测 17.78°C，目标 2026-11-07T15:00:00。
- 青浦：experimental，预测 18.29°C，目标 2026-11-07T15:00:00。
- 松江：experimental，预测 18.22°C，目标 2026-11-07T15:00:00。
- 金山：experimental，预测 18.73°C，目标 2026-11-07T15:00:00。
- 临港：experimental，预测 18.35°C，目标 2026-11-07T15:00:00。
- 崇明：experimental，预测 18.16°C，目标 2026-11-07T15:00:00。
- 长兴岛：experimental，预测 17.51°C，目标 2026-11-07T15:00:00。
- 横沙岛：experimental，预测 17.62°C，目标 2026-11-07T15:00:00。

上述是当前时刻真实推理连通性，不是未来实测准确率。原始记录artifacts/hourly_regional/live-verification.json。

真实首页无Mock：手动选择金山公开测试点（旧方框之外）后成功显示预测和新实验表，手机无横向溢出，无JS错误。旧版截图未随当前版本提交；历史运行记录见artifacts/hourly_regional/browser-verification.txt，当前界面见docs/screenshots/。

## 主要修改与复现

- services/shanghai_scope.py：本地行政区多边形及边缘判断。
- services/coord_transform.py、scripts/prepare_shanghai_boundary.py：坐标系处理、边界来源记录。
- scripts/train_shanghai_regional.py：真实多点数据缓存、时间划分、基线比较、网格留出及独立产物。
- services/online_ml.py：加载v2模型，验证特征及边界SHA256，按原始所选坐标查询输入，不偷偷替换成市中心。
- weather_routes.py、static/insights.js、templates/index.html：实验指标切换与范围说明、动态模型名称。
- tests/test_shanghai_regional.py：区域、外市、推理与来源检查。

运行python scripts/prepare_shanghai_boundary.py，再运行python scripts/train_shanghai_regional.py。已缓存的数据无需重复下载；raw文件内坐标必须与固定points.json一致。模型产物在artifacts/hourly_regional/，无需重训原日均温模型。

## 限制

支持按市域边界查询不等于每个街道都已实测。ERA5空间分辨率有限，边界本身存在年代、近似转换和海岸变化误差；极近边界或新填海位置仍可能需校核。仅预测下一小时，不做明天下午的本地Ridge预测。部分空间留出不优于基线，实时校准和新增年份验证仍是后续工作。
