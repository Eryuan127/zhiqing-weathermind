# 当前版本演示说明

启动入口：在仓库根目录执行 python run_weather.py，默认 http://127.0.0.1:5001/ 。
当前首页由 templates/index.html 提供；完整助手由登录后内嵌的 /assistant?embedded=1 提供；悬浮小窗属于当前首页。

1. 在天气首页选择上海，展示当前天气、小时趋势、US AQI、七日预报。
2. 登录后点击右上角“问问知晴”，进入完整助手，展示天气上下文、会话列表及输入框。
3. 提问“明天下午上海会下雨吗”，检查时间范围、数据依据及工具执行记录。
4. 返回首页，点击右下角悬浮按钮，查看小窗以及“完整对话”入口。
5. 通过“更多工具 / 实验功能”运行下一小时气温预测，检查上海适用范围与实验标记。

当前界面截图由作者提供，位于docs/screenshots：dashboard.png、assistant.png、compact-assistant.png。第三张含原页面浮层遮挡，未修饰图片。
截图2为欢迎状态，截图3为初始摘要，不能声称它们展示了一轮成功的工具调用。现场问答以实际执行为准。
历史2026年11月7日的JSON及截图仅作历史日志留档，不作为当前版本界面。
第5章的误差图来自保存的测试预测，与当前页面的天气值分开解释。


## 2026年11月18日完整规则查询

执行入口为 `python run_weather.py --port 5083`，使用独立演示账号，在完整助手中明确选择规则模式并提问“明天下午上海会下雨吗”。演示用端口不改变默认5001端口。

- [输入问题](screenshots/20261118-input.png)
- [最终回答](screenshots/20261118-answer.png)
- [展开执行依据](screenshots/20261118-execution.png)
- [完整脱敏记录](../artifacts/evaluation/20261118-rules-demonstration.json)

执行路径：parse_request → check_context → plan_tools → execute_tools → validate_results → generate_response；get_hourly_forecast状态为ok，HTTP 200。本轮查询11月19日12:00—17:00，返回8.9～10.6°C，最大小时降水概率0%，并说明仍不能保证无雨。它是查询时刻的业务预报，不是后续实测，也未调用Qwen。数据库、凭证、会话及请求标识符不公开。

[11月7日T01历史脱敏记录](../artifacts/evaluation/20261107-T01-public.json)另行留档，对应不同日期的17.8～19.3°C和90%降水概率，不替代本轮记录。

## 作者提供的功能截图

- [模型初始状态](screenshots/author-model-collapsed.png)、[展开历史实验](screenshots/author-model-before-run.png)、[运行后结果](screenshots/author-model-result.png)：14.32°C是单次输出，历史MAE不代表实时误差。
- [执行模式说明](screenshots/author-mode-explanation.png)、[模式选项](screenshots/author-mode-options.png)：规则模式和Qwen共用工具与天气事实；设置截图不构成Qwen成功率证据。
- [账号菜单](screenshots/author-account-menu.png)、[个人资料](screenshots/author-profile-settings.png)、[常用城市](screenshots/author-saved-cities.png)。
- [原始文件哈希](screenshots/author-features-source.json)。截图保持原样，界面中公开昵称及账号显示来自作者提供的素材，不提供登录凭证。

完整助手可新建、切换、恢复、清空会话，支持停止生成、复制消息及个人修订；小窗最多5次提问后可转完整对话继续。编辑回复不会改写原始工具依据。
