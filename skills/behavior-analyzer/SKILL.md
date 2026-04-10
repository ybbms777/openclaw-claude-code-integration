---
name: behavior-analyzer
description: 会话行为分析引擎。实时检测Agent的异常行为模式（重复犯错、角色漂移、缓存效率下降、权限级别提升），生成会话质量评分（0-100）。支持趋势分析、预警和自动建议。
model: minimax-portal/MiniMax-M2.7
effort: medium
---

# Behavior Analyzer — 会话行为分析引擎

## 功能概述

从 self-eval、cache-monitor、evolve、yolo_classifier 等多个数据源实时收集数据，分析OpenClaw Agent的行为模式，生成综合的会话质量评分和异常预警。

## 核心功能

### 1. 会话质量评分（0-100）

基于4个维度的综合评分：

| 维度 | 权重 | 说明 |
|------|------|------|
| 错误模式 | 40% | 检测重复犯错（用户纠正、工具失败次数） |
| 角色漂移 | 30% | 检测规则触发频率异常升高 |
| 权限级别 | 20% | 检测权限操作(HIGH/CRITICAL)增加 |
| 缓存效率 | 10% | 检测缓存失效频率上升 |

**评分含义**：
- **90-100** 🟢 优秀：可以继续正常操作
- **70-89** 🟡 良好：监控中
- **40-69** 🟠 警告：建议降级策略
- **<40** 🔴 严重：立即暂停，等待用户干预

### 2. 异常模式检测

| 异常类型 | 触发条件 | 建议操作 |
|---------|---------|---------|
| 重复犯错 | 同类错误 ≥ 3次 | 查看 /evolve 规则 |
| 角色漂移 | 规则触发 > 10次 | 执行 /compile 重新加载 |
| 缓存降级 | 今日变更 > 3次 | 检查SOUL.md变更 |
| 权限级别 | HIGH/CRITICAL > 50% | 确认是否预期行为 |

### 3. 趋势分析与预测

```
stable  →  improving  →  declining  →  critical
```

对比会话历史分数，判断会话质量的发展趋势。

### 4. 自动建议系统

根据检测到的异常和评分等级，自动生成**可执行的建议**：

- 严重异常：⛔ 暂停自动操作
- 重复错误：🔄 更新规则
- 缓存问题：⚡ 重新初始化缓存
- 权限异常：🔐 需要用户确认

---

## 数据源

### 必需（自动）
- `self-eval.py` 的异常记录（reflection 记忆）
- `cache-monitor.py` 的变更日志
- `evolve.py` 的规则应用记录
- `yolo_classifier.py` 的权限决策

### 可选（增强分析）
- LanceDB 记忆系统的效率指标
- 会话历史快照

---

## 使用方式

### Python API

```python
from skills.behavior_analyzer.scripts.behavior_analyzer import SessionBehaviorAnalyzer

analyzer = SessionBehaviorAnalyzer()

# 分析特定会话
metrics = analyzer.analyze_session("session_123")

print(f"健康分数: {metrics.health_score}")
print(f"异常: {metrics.anomaly_patterns}")
print(f"建议: {metrics.recommended_actions}")

# 保存到历史文件
analyzer.save_metrics(metrics)
```

### CLI 使用

```bash
# 分析当前会话
python3 behavior_analyzer.py current

# 分析特定会话
python3 behavior_analyzer.py session_123

# 输出 JSON
python3 behavior_analyzer.py session_123 --json

# 保存分析结果
python3 behavior_analyzer.py session_123 --save-history
```

### 与 OpenClaw 钩子集成

```python
# agent:tool_dispatch 钩子中调用
def should_dispatch_tool(tool_name, params, session_id):
    analyzer = SessionBehaviorAnalyzer()
    metrics = analyzer.analyze_session(session_id)
    
    if metrics.warning_level == "critical":
        return False  # 阻止工具调用
    
    return True  # 允许调用
```

---

## 配置

### 阈值配置

在 `behavior_analyzer.py` 中修改：

```python
self.thresholds = {
    "error_repetition": 3,       # 重复犯错的阈值
    "rule_violation_rate": 0.4,  # 规则触发频率高时的阈值
    "cache_fail_rate": 0.3,      # 缓存失效频率
    "permission_escalation": 5,  # 权限体级的数量
}
```

---

## 输出示例

### 健康会话
```
📊 会话行为分析 - session_123
时间: 2026-04-11T10:30:00
健康分数: 85.0/100 🟢
质量趋势: improving
警告等级: none

建议操作:
  ✅ 会话状态良好，可以继续
```

### 异常会话
```
📊 会话行为分析 - session_456
时间: 2026-04-11T10:35:00
健康分数: 35.0/100 🔴
质量趋势: declining
警告等级: critical

异常模式 (3):
  • 重复犯错：用户纠正 (4次)
  • 角色漂移：规则触发 12 次
  • 权限级别提升：6/10 为高风险

建议操作:
  ⛔ 严重异常：立即暂停自动操作，等待用户介入
  📋 查看详细日志了解具体问题
  🔄 检测到重复错误：建议查看 /evolve 规则是否需要更新
```

---

## 测试

```bash
# 运行所有测试
pytest skills/behavior-analyzer/tests/ -v

# 运行特定测试
pytest skills/behavior-analyzer/tests/test_behavior_analyzer.py::TestBehaviorAnalyzer::test_analyze_session_healthy -v

# 生成覆盖率报告
pytest skills/behavior-analyzer/tests/ --cov=skills.behavior_analyzer
```

---

## 集成点

### With Week 1-4 Systems
- ✅ 使用 self-eval.py 的异常记录
- ✅ 使用 cache-monitor.py 的状态
- ✅ 使用 evolve.py 的规则应用日志
- ✅ 使用 yolo_classifier.py 的权限决策

### With OpenClaw 2.0 钩子
- `agent:tool_dispatch` — 工具调用决策前
- `session:end` — 会话结束时保存快照
- `rule:effectiveness_update` — 规则效能变化时

---

## 性能指标

- **分析耗时**: < 500ms (typically < 200ms)
- **内存开销**: < 50MB
- **存储占用**: 每个会话 < 50KB
- **历史保留**: 最近100条记录

---

## 故障排查

### 问题：分析结果总是满分

**原因**：数据源文件不存在
**解决**：确保 self-eval.py, cache-monitor.py 等已正确运行

### 问题：权限异常频繁触发

**原因**：权限打分阈值过高
**解决**：调整 `permission_escalation` 阈值

---

## 进阶：自定义异常检测器

继承 `SessionBehaviorAnalyzer` 并重写检测方法：

```python
class CustomBehaviorAnalyzer(SessionBehaviorAnalyzer):
    def _detect_error_patterns(self, session_id):
        # 自定义错误检测逻辑
        return super()._detect_error_patterns(session_id)
```

---

## 许可

遵循项目主许可证。

