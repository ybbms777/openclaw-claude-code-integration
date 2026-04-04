# MEMORY.md - 半点心的长期记忆

## 关于我 / Boss
- **风格**：简洁、高效、直接了当；喜欢第一性思维
- **地点/时区**：中国四川成都 / Asia/Shanghai

## 通知渠道（详见 TOOLS.md）

## 记忆管理规则
- 临时记忆 → `memory/YYYY-MM-DD.md`（7天后归档）；永久记忆 → MEMORY.md（Boss明确要求时）
- 硬规矩：每次任务完成后立即更新，不跳过

## 项目索引

### [项目A] 电商自动化项目
- 概览：[项目A路径]；目标：电商客服自动化
- 热门定价：（按需查询）
- 飞书：订单与话术（按需获取）

### [项目B] 量化交易项目
- 概览：[项目B路径]；目标：量化策略年化20%+
- Phase 1-5 完成（选股/RSRS/回测/组合优化）；Phase R/X 进行中
- 踩坑必记：Python 3.12（3.14不兼容akshare/vnpy）；`*_proxy`变量开局清除；Telegram发消息前`re.sub`去HTML标签
- 数据层：akshare/baostock(3.12)/新浪财经K线
- Cron：工作日 08:30 / 15:05 / 15:30 / 21:00
- 架构：Mac本地分析→HTTP API→Windows机QMT执行

### [项目C] 自动化项目
- 概览：[项目C路径]；目标：PC端全自动
- Windows机器：Linux配置
- 技术：MSS+OpenCV+pymem+SendInput+PyQt6+PaddleOCR；DLL Hook方案
- 状态：M0验证✅；YOLO标注/内存层 待做

## 技术踩坑（永久记住）

- [踩坑-Python] hikyuu/vnpy/pyqlib/akshare 必须 Python 3.12，3.14绕不过
- [踩坑-解析] AI输出先`re.sub`去思考标签再处理，防止正则崩溃
- [踩坑-TG] 发大图用`sendDocument`而非`sendPhoto`更可靠；发前`re.sub`去HTML标签
- [踩坑-LanceDB] 数据多时auto-recall超时；compact成少量fragment后恢复；每周日凌晨3点cron自动整理
- [踩坑-插件] 安装前必须检查是否会修改SOUL.md/AGENTS.md，等Boss确认再装

## Boss习惯/规范

- [习惯-交付] 重要产出完成后主动告知存放位置，不等Boss问"在哪里"
- [习惯-上下文] Boss说"上下文快满了"→新会话开始主动读取memory文件恢复上下文
- [习惯-项目] Boss项目易中途搁置；重要决策后主动确认是否真的开始
- [习惯-飞书] 不走飞书私信，统一走Telegram

## 待推进
- [项目A] 自动化优化：当前模块运行稳定，按需调整
- [项目C] 内存层：等Boss在Win PC确认崩溃频率后推进
- [项目B] 量化：继续空仓等RSRS信号，模拟盘验证中
