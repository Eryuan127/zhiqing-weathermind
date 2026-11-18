# 设计技能与工程复用记录

本轮实际复用 landing-page-design 开发技能，来源为开发环境安装目录。它指导间距、字号、状态反馈和组件一致性，不是运行时天气工具。不能将 LangGraph 工具或参考组件库自动称作第三方 skill。

技能文件 SHA256：203569792660ab6d71dcb2e4fa673c0c7a0df7c99801d04ab419a4cb08aceb2c

输入：现有 Flask 页面、用户指定的居中毛玻璃导航/头像/小窗交互。输出：重整后的 CSS、空气质量及模型卡片、测试和截图。权限：本地文件及明确授权的外部资料查询；运行时无需加载该技能。

实际采用：统一间距、有限字号、圆角体系、键盘焦点、加载/错误/空状态。适配：保留用户指定毛玻璃导航；依据工具型页面的信息密度组织网格，不引入营销页段落；保留原生JS而不强制React/Vue。

改造前：style.css 中多个版本反复覆盖 header、sidebar、panel 和断点。改造后：单一token与网格定义、明确组件区段和两组主要断点；保留账号组件规则。交互、手机布局及原有定位/会话需要浏览器回归，不能仅凭截图判断可用性。

参考而未复制运行时代码：Material UI Grid、Element Plus的反馈/可控性原则、shadcn语义颜色。来源链接在 README。依赖版本见 third-party-versions.json。

许可核验：2026年11月18日核对上游历史提交a2735a3eaf092eaaffb6dc17df25de33ef3bd048，本地技能正文经LF换行归一化后与该版本一致，整体许可证为MIT。上游当前分支内容已变化，不能用当前HEAD替代历史匹配结果。许可原文见licenses/landing-page-design-MIT.txt，匹配提交、哈希及比较说明见licenses/landing-page-design-source.json；未分发技能正文。自写CSS与仅参考的组件设计文档分别记录。

尚未实施的证据：独立用户研究、视觉改造的人效收益、去除该skill后的受控消融。不能将开发者测试等同用户研究；用户研究方案见 USER_STUDY.md。
