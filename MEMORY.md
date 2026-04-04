# MEMORY.md - 半点心的长期记忆

## 关于我 / Boss
- **名字**：半点心 / ybbms
- **风格**：简洁、高效、直接了当；喜欢第一性思维
- **地点/时区**：中国四川成都 / Asia/Shanghai

## 通知渠道（详见 TOOLS.md）
- 所有通知统一走 Telegram @DABDX_BOT，闲鱼通知走 @ybbmsBDX_BOT

## 记忆管理规则
- 临时记忆 → `memory/YYYY-MM-DD.md`（7天后归档）；永久记忆 → MEMORY.md（Boss明确要求时）
- 硬规矩：每次任务完成后立即更新，不跳过

## 项目索引

### 闲鱼项目
- [闲鱼-概览] 整合框架 `~/.openclaw/workspace/minty-omni/`，实际运行 `~/Desktop/XianyuAutoAgent-main/`
- [闲鱼-价格] 星铁3天20/7天40/30天68；终末地3天22/7天42/30天85；绝区零私信问价
- [闲鱼-飞书] 订单 `gcngnzrgqobg.feishu.cn/base/A6wNbKVaeaW4Uqs1ZaNcjzvdn8f`；话术库 `...JQmiboWCtaErOasckfHcICF0nTg`
- [闲鱼-模块] AI客服/Cookie同步/滑块风控/飞书订单/飞书话术同步/cron每4h 均✅；QQ售后❌已卸载
- [闲鱼-素材工厂] 11:00自动跑→12:00发Telegram日报；脚本`~/Desktop/素材工厂/文案降重_脚本.py`；违禁词：大牛/代练/代肝
- [闲鱼-热门角色] 崩铁4.1（风堇/遐蝶/爻光/火花）；绝区零2.7（南宫羽/叶瞬光/柚叶）；终末地1.1.8（余烬/骏卫/莱万汀）

### BDX-A股增强版
- [BDX-概览] v4.0，路径`~/.openclaw/workspace/bdx-astock/`；目标年化20%+（模拟→实盘）
- [BDX-Phase] ✅ Phase 1-5完成（涨停/宏观/技术/资金/内部人/反操纵/基本面/情绪/散户/题材/选股/RSRS/回测/组合优化）；🔄 Phase R（持仓生命周期）；🔄 Phase X（极端行情/市场结构）
- [BDX-最终目标] 买什么✅/何时买✅/何时卖✅/加仓减仓✅/自我迭代✅/复盘总结✅/预测市场🔄
- [BDX-踩坑-必记] Python 3.12（3.14不兼容akshare/vnpy）；`*_proxy`变量开局清除；baostock多取120天；新浪财经K线代替东方财富；Telegram发消息前`re.sub`去HTML标签
- [BDX-数据层] 实时akshare/日线baostock(Python3.12)/分钟K线新浪财经/新闻东方财富JSONP
- [BDX-依赖] vnpy 4.3.0(py3.12数据记录)；pyqlib 0.9.7(py3.12回测)；baostock 0.8.9(py3.12实时)
- [BDX-cron] 工作日 08:30 / 15:05 / 15:30 / 21:00
- [BDX-实盘] Mac本地分析→HTTP API→Windows机QMT执行

### SHR自动化（星穹铁道）
- [SHR-概览] `~/.openclaw/workspace/shr-automation/`，目标PC端全自动（主线/支线/宝箱/解密/探索）
- [SHR-Windows] vivobook Pro15(i5-12450H+16G+RTX3050)，Python 3.11.9
- [SHR-技术] MSS+OpenCV+pymem+SendInput+PyQt6+PaddleOCR；DLL Hook方案(AnimeSDK 4.1.0)
- [SHR-状态] M0验证✅；DLL auto-scan✅；YOLO标注/Win PC联调/内存层 待做

### OpenClaw
- [OpenClaw-安装] `npm i -g @qingchencloud/openclaw-zh --registry=https://registry.npmmirror.com`
- [OpenClaw-升级] 升级前必备份（workspace/cron_jobs.json/credentials/lancedb-pro向量库）；升级后检查插件加载状态
- [OpenClaw-Python铁律] 所有带C/C++扩展的包必须用Python 3.12，写死路径不用系统默认

### ClawTeam-OpenClaw
- [ClawTeam] 多Agent协同框架；`pip install -e .`安装；`~/bin/clawteam`调用

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
- AI漫剧：末日生存原创爽文；工具链Ideogram+MiniMax TTS+FFmpeg；等Boss提供主角人设
- SHR自动化：等Boss在Win PC不注入DLL跑一轮确认崩溃频率
- BDX：继续空仓等RSRS信号，6个月模拟盘验证中
- 素材工厂：11:00 cron自动跑，无需介入
