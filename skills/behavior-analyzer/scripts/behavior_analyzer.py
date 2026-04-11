#!/usr/bin/env python3
"""
行为分析引擎 (Behavior Analyzer)
从多个数据源实时分析OpenClaw Agent的行为，生成会话质量评分和异常检测
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import Counter

from skills.shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BehaviorMetrics:
    """会话行为指标"""
    health_score: float  # 0-100
    anomaly_patterns: List[str]
    quality_trend: str  # "stable", "declining", "improving"
    warning_level: str  # "none", "warning", "critical"
    recommended_actions: List[str]
    session_id: str
    timestamp: str
    details: Dict


class SessionBehaviorAnalyzer:
    """会话行为分析器"""

    def __init__(self, workspace_dir: str = None):
        """
        初始化行为分析器

        Args:
            workspace_dir: OpenClaw工作目录，默认~/.openclaw/workspace
        """
        self.workspace = Path(workspace_dir or
                             os.path.expanduser("~/.openclaw/workspace"))

        # 数据源路径
        self.sessions_dir = self.workspace / "agents" / "main" / "sessions"
        self.lancedb_dir = self.workspace / "memory" / "lancedb-pro"
        self.recovery_dir = self.workspace / "skills" / "compact-guardian"
        self.behavior_log = self.workspace / ".behavior-analytics"

        # 创建行为日志目录
        self.behavior_log.mkdir(parents=True, exist_ok=True)

        # 阈值配置
        self.thresholds = {
            "error_repetition": 3,      # 重复犯错的阈值
            "rule_violation_rate": 0.4,  # 规则触发频率高时的阈值
            "cache_fail_rate": 0.3,      # 缓存失效频率
            "permission_escalation": 5,  # 权限体级的数量
        }

    def analyze_session(self, session_id: str) -> BehaviorMetrics:
        """
        分析单个会话的行为

        Args:
            session_id: 会话ID

        Returns:
            BehaviorMetrics 对象
        """
        details = {}
        anomalies = []

        # 1. 检测重复犯错
        error_score, error_anomalies = self._detect_error_patterns(session_id)
        anomalies.extend(error_anomalies)
        details["error_score"] = error_score

        # 2. 检测角色漂移（规则触发频率）
        role_score, role_anomalies = self._detect_role_drift(session_id)
        anomalies.extend(role_anomalies)
        details["role_drift_score"] = role_score

        # 3. 检测缓存效率下降
        cache_score, cache_anomalies = self._detect_cache_degradation(session_id)
        anomalies.extend(cache_anomalies)
        details["cache_score"] = cache_score

        # 4. 检测权限决策变化
        perm_score, perm_anomalies = self._detect_permission_escalation(session_id)
        anomalies.extend(perm_anomalies)
        details["permission_score"] = perm_score

        # 5. 综合评分
        health_score = self._calculate_health_score(
            error_score, role_score, cache_score, perm_score
        )

        # 6. 判断趋势
        trend = self._analyze_trend(session_id, health_score)

        # 7. 确定警告等级
        warning = self._determine_warning_level(health_score, anomalies)

        # 8. 生成建议
        recommendations = self._generate_recommendations(
            health_score, anomalies, warning
        )

        return BehaviorMetrics(
            health_score=health_score,
            anomaly_patterns=anomalies,
            quality_trend=trend,
            warning_level=warning,
            recommended_actions=recommendations,
            session_id=session_id,
            timestamp=datetime.now().isoformat(),
            details=details
        )

    def _detect_error_patterns(self, session_id: str) -> Tuple[float, List[str]]:
        """检测重复犯错模式（来自 self-eval.py 的异常记录）"""
        anomalies = []
        score = 100.0  # 满分

        try:
            # 查找 self-eval 的反射记忆
            reflection_log = self.workspace / ".self-eval-reflections.jsonl"
            if not reflection_log.exists():
                return score, anomalies

            error_counts = Counter()

            with open(reflection_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("session_id") == session_id:
                            category = record.get("category", "")
                            if category in ["用户纠正", "工具失败", "上报触发"]:
                                error_counts[category] += 1
                    except json.JSONDecodeError:
                        continue

            # 判断是否重复犯错
            for error_type, count in error_counts.items():
                if count >= self.thresholds["error_repetition"]:
                    anomalies.append(f"重复犯错：{error_type} ({count}次)")
                    score -= 20

            return max(0, score), anomalies

        except Exception as e:
            logger.warning(f"检测错误模式失败: {e}")
            return 100.0, []

    def _detect_role_drift(self, session_id: str) -> Tuple[float, List[str]]:
        """检测角色漂移（规则触发频率提高）"""
        anomalies = []
        score = 100.0

        try:
            # 从 evolve.py 的规则应用日志查询
            rule_log = self.workspace / ".evolve-rule-applications.jsonl"
            if not rule_log.exists():
                return score, anomalies

            rule_triggers = 0
            with open(rule_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("session_id") == session_id:
                            rule_triggers += 1
                    except json.JSONDecodeError:
                        continue

            # 如果规则触发频率过高，表示可能角色漂移
            if rule_triggers > 10:
                anomalies.append(f"角色漂移：规则触发 {rule_triggers} 次")
                score -= 30

            return max(0, score), anomalies

        except Exception as e:
            logger.warning(f"检测角色漂移失败: {e}")
            return 100.0, []

    def _detect_cache_degradation(self, session_id: str) -> Tuple[float, List[str]]:
        """检测缓存效率下降（来自 cache-monitor.py）"""
        anomalies = []
        score = 100.0

        try:
            # 查找 cache-monitor 的变更日志
            cache_monitor_file = self.workspace / ".cache-monitor.json"
            if not cache_monitor_file.exists():
                return score, anomalies

            with open(cache_monitor_file, 'r') as f:
                cache_state = json.load(f)

            # 检查近期缓存失效频率
            change_log = cache_state.get("change_log", [])
            recent_changes = len([c for c in change_log
                                 if c.get("date") == datetime.now().strftime("%Y-%m-%d")])

            if recent_changes > 3:
                anomalies.append(f"缓存效率下降：今日变更 {recent_changes} 次")
                score -= 15

            return max(0, score), anomalies

        except Exception as e:
            logger.warning(f"检测缓存降级失败: {e}")
            return 100.0, []

    def _detect_permission_escalation(self, session_id: str) -> Tuple[float, List[str]]:
        """检测权限决策变化（来自 yolo_classifier.py）"""
        anomalies = []
        score = 100.0

        try:
            # 查找权限决策日志
            perm_log = self.workspace / ".permission-decisions.jsonl"
            if not perm_log.exists():
                return score, anomalies

            high_risk_count = 0
            total_count = 0

            with open(perm_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("session_id") == session_id:
                            total_count += 1
                            risk = record.get("risk", "LOW")
                            if risk in ["HIGH", "CRITICAL"]:
                                high_risk_count += 1
                    except json.JSONDecodeError:
                        continue

            if total_count > 0:
                high_risk_ratio = high_risk_count / total_count
                if high_risk_ratio > 0.5:
                    anomalies.append(f"权限级别提升：{high_risk_count}/{total_count} 为高风险")
                    score -= 25

            return max(0, score), anomalies

        except Exception as e:
            logger.warning(f"检测权限级别变化失败: {e}")
            return 100.0, []

    def _calculate_health_score(self, error_score: float, role_score: float,
                               cache_score: float, perm_score: float) -> float:
        """计算综合健康分数"""
        # 权重：错误最重，其次是角色和权限，缓存最轻
        health = (
            error_score * 0.40 +
            role_score * 0.30 +
            perm_score * 0.20 +
            cache_score * 0.10
        )
        return round(max(0, min(100, health)), 1)

    def _analyze_trend(self, session_id: str, current_score: float) -> str:
        """分析会话健康度趋势"""
        try:
            history_file = self.behavior_log / f"{session_id}_history.json"
            if not history_file.exists():
                return "unknown"

            with open(history_file, 'r') as f:
                history = json.load(f)

            if len(history) < 2:
                return "stable"

            prev_score = history[-1].get("health_score", current_score)

            if current_score > prev_score + 5:
                return "improving"
            elif current_score < prev_score - 5:
                return "declining"
            else:
                return "stable"

        except Exception:
            return "unknown"

    def _determine_warning_level(self, health_score: float,
                                anomalies: List[str]) -> str:
        """确定警告等级"""
        if health_score < 20 or len(anomalies) > 3:
            return "critical"
        elif health_score < 50 or len(anomalies) > 1:
            return "warning"
        else:
            return "none"

    def _generate_recommendations(self, health_score: float,
                                 anomalies: List[str],
                                 warning: str) -> List[str]:
        """生成建议操作"""
        recommendations = []

        if warning == "critical":
            recommendations.append("⛔ 严重异常：立即暂停自动操作，等待用户介入")
            recommendations.append("📋 查看详细日志了解具体问题")

        if "重复犯错" in str(anomalies):
            recommendations.append("🔄 检测到重复错误：建议查看 /evolve 规则是否需要更新")

        if "角色漂移" in str(anomalies):
            recommendations.append("👤 行为异常：规则触发频繁，考虑执行 /compile 重新加载规则")

        if "缓存效率" in str(anomalies):
            recommendations.append("⚡ 缓存频繁失效：可能的 SOUL.md 变更，考虑 /cache-init")

        if "权限级别提升" in str(anomalies):
            recommendations.append("🔐 权限操作增多：请确认这是预期的行为")

        if health_score > 80:
            recommendations.append("✅ 会话状态良好，可以继续")

        return recommendations

    def save_metrics(self, metrics: BehaviorMetrics) -> None:
        """保存行为指标到文件"""
        history_file = self.behavior_log / f"{metrics.session_id}_history.json"

        try:
            history = []
            if history_file.exists():
                with open(history_file, 'r') as f:
                    history = json.load(f)

            history.append(asdict(metrics))

            # 只保留最近100条记录
            if len(history) > 100:
                history = history[-100:]

            with open(history_file, 'w') as f:
                json.dump(history, f, indent=2)

        except Exception as e:
            logger.error(f"保存行为指标失败: {e}")


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="行为分析引擎")
    parser.add_argument("session_id", nargs="?", default="current",
                       help="会话ID，默认为 'current'")
    parser.add_argument("--workspace", default=None,
                       help="OpenClaw 工作目录")
    parser.add_argument("--json", action="store_true",
                       help="输出 JSON 格式")
    parser.add_argument("--save-history", action="store_true",
                       help="保存分析结果到历史文件")

    args = parser.parse_args()

    try:
        analyzer = SessionBehaviorAnalyzer(args.workspace)
        metrics = analyzer.analyze_session(args.session_id)

        if args.save_history:
            analyzer.save_metrics(metrics)

        if args.json:
            print(json.dumps(asdict(metrics), indent=2))
        else:
            # 可读的输出格式
            print(f"📊 会话行为分析 - {args.session_id}")
            print(f"时间: {metrics.timestamp}")
            print(f"健康分数: {metrics.health_score}/100 {'🟢' if metrics.health_score > 70 else '🟡' if metrics.health_score > 40 else '🔴'}")
            print(f"质量趋势: {metrics.quality_trend}")
            print(f"警告等级: {metrics.warning_level}")

            if metrics.anomaly_patterns:
                print(f"\n异常模式 ({len(metrics.anomaly_patterns)}):")
                for anomaly in metrics.anomaly_patterns:
                    print(f"  • {anomaly}")

            if metrics.recommended_actions:
                print(f"\n建议操作:")
                for action in metrics.recommended_actions:
                    print(f"  {action}")

            return 0 if metrics.warning_level != "critical" else 1

    except Exception as e:
        logger.error(f"分析失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
