#!/usr/bin/env python3
"""
规则优化框架 (Rule Optimizer)
追踪规则效能、建议优化、支持A/B测试
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict
import statistics

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oeck.runtime_core.workspace import WorkspaceResolver

@dataclass
class RuleMetrics:
    """规则效能指标"""
    rule_id: str
    trigger_frequency: int        # 每周触发次数
    fix_rate: float              # 修复成功率 (%)
    cost_overhead_ms: float      # 延迟开销 (毫秒)
    user_satisfaction: float     # 用户满意度 (1-5)

    # 计算得出
    effectiveness_score: float = 0.0  # 0-100
    status: str = "active"             # active, testing, deprecated
    variants: List[str] = field(default_factory=list)


@dataclass
class RuleVariant:
    """规则变体"""
    variant_id: str
    parent_rule_id: str
    modification: str           # 修改说明
    a_b_test_sample: float      # AB测试的样本比例 (0-1)
    trial_effectiveness: Optional[float] = None
    status: str = "pending"     # pending, active, rejected


class RuleOptimizer:
    """规则优化器"""

    def __init__(self, workspace_dir: str = None):
        """
        初始化规则优化器

        Args:
            workspace_dir: OpenClaw工作目录
        """
        self.resolver = WorkspaceResolver.from_workspace(workspace_dir)
        self.workspace = self.resolver.layout.workspace_root

        # 数据源路径
        self.rule_metrics_log = self.resolver.log_file("rule-metrics")
        self.rule_variants_log = self.resolver.log_file("rule-variants")
        self.ab_test_results = self.resolver.log_file("ab-test-results")

        # 创建日志目录
        self.rule_metrics_log.parent.mkdir(parents=True, exist_ok=True)

        # 效能阈值
        self.thresholds = {
            "high_effective": 80,    # > 80: 效能好
            "moderate": 50,          # 50-80: 中等
            "low_effective": 20,     # < 20: 需要优化或废弃
        }

    def evaluate_rule_effectiveness(self, rule_id: str) -> RuleMetrics:
        """
        评估规则的实际效能

        Args:
            rule_id: 规则ID

        Returns:
            RuleMetrics 对象
        """
        # 收集规则的应用历史
        trigger_freq = self._get_trigger_frequency(rule_id)
        fix_rate = self._get_fix_rate(rule_id)
        cost = self._get_avg_cost(rule_id)
        satisfaction = self._get_avg_satisfaction(rule_id)

        # 计算综合效能评分
        effectiveness = self._calculate_effectiveness(
            trigger_freq, fix_rate, cost, satisfaction
        )

        # 确定规则状态
        status = self._determine_rule_status(effectiveness)

        # 获取相关变体
        variants = self._get_rule_variants(rule_id)

        return RuleMetrics(
            rule_id=rule_id,
            trigger_frequency=trigger_freq,
            fix_rate=fix_rate,
            cost_overhead_ms=cost,
            user_satisfaction=satisfaction,
            effectiveness_score=effectiveness,
            status=status,
            variants=variants
        )

    def suggest_rule_variants(self, rule_id: str) -> List[RuleVariant]:
        """
        基于效能数据，建议规则变体

        Args:
            rule_id: 规则ID

        Returns:
            建议的规则变体列表
        """
        metrics = self.evaluate_rule_effectiveness(rule_id)

        if metrics.effectiveness_score > 80:
            return []  # 效能好，无需优化

        suggestions = []

        # 低效能：建议宽松版本
        if metrics.effectiveness_score < 50:
            suggestions.append(RuleVariant(
                variant_id=f"{rule_id}_loose",
                parent_rule_id=rule_id,
                modification="条件更宽松，减少误检",
                a_b_test_sample=0.05
            ))

        # 中等效能：建议严格版本
        if 50 <= metrics.effectiveness_score < 80:
            suggestions.append(RuleVariant(
                variant_id=f"{rule_id}_strict",
                parent_rule_id=rule_id,
                modification="条件更严格，提高准确性",
                a_b_test_sample=0.05
            ))

        # 建议混合版本
        if metrics.effectiveness_score < 70:
            suggestions.append(RuleVariant(
                variant_id=f"{rule_id}_hybrid",
                parent_rule_id=rule_id,
                modification="条件重新平衡",
                a_b_test_sample=0.05
            ))

        return suggestions

    def _get_trigger_frequency(self, rule_id: str) -> int:
        """获取规则在过去7天的触发次数"""
        try:
            if not self.rule_metrics_log.exists():
                return 0

            count = 0
            cutoff = datetime.now() - timedelta(days=7)

            with open(self.rule_metrics_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("rule_id") == rule_id:
                            ts = datetime.fromisoformat(record.get("timestamp", ""))
                            if ts > cutoff:
                                count += 1
                    except (json.JSONDecodeError, ValueError):
                        continue

            return count

        except Exception:
            return 0

    def _get_fix_rate(self, rule_id: str) -> float:
        """获取规则的修复成功率"""
        try:
            if not self.rule_metrics_log.exists():
                return 50.0

            total = 0
            fixed = 0

            with open(self.rule_metrics_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("rule_id") == rule_id:
                            total += 1
                            if record.get("fixed"):
                                fixed += 1
                    except json.JSONDecodeError:
                        continue

            if total == 0:
                return 50.0

            return (fixed / total) * 100

        except Exception:
            return 50.0

    def _get_avg_cost(self, rule_id: str) -> float:
        """获取规则的平均延迟开销（毫秒）"""
        try:
            if not self.rule_metrics_log.exists():
                return 0.0

            costs = []

            with open(self.rule_metrics_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("rule_id") == rule_id:
                            cost = record.get("latency_ms", 0)
                            if cost:
                                costs.append(cost)
                    except json.JSONDecodeError:
                        continue

            if not costs:
                return 0.0

            return statistics.mean(costs)

        except Exception:
            return 0.0

    def _get_avg_satisfaction(self, rule_id: str) -> float:
        """获取规则的平均用户满意度（1-5）"""
        try:
            if not self.rule_metrics_log.exists():
                return 3.0

            scores = []

            with open(self.rule_metrics_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("rule_id") == rule_id:
                            score = record.get("satisfaction")
                            if score:
                                scores.append(score)
                    except json.JSONDecodeError:
                        continue

            if not scores:
                return 3.0

            return statistics.mean(scores)

        except Exception:
            return 3.0

    def _calculate_effectiveness(self, freq: int, fix_rate: float,
                                cost: float, satisfaction: float) -> float:
        """
        计算综合效能评分

        考虑因素：
        - 触发频率（高频规则应大有裨益）
        - 修复成功率（主要指标）
        - 延迟开销（低于50ms为好）
        - 用户满意度（1-5转100分制）
        """
        # 基础分：修复成功率
        base = fix_rate

        # 用户满意度加权
        sat_score = (satisfaction / 5.0) * 100
        weighted = (base * 0.6) + (sat_score * 0.4)

        # 延迟惩罚：>100ms时明显扣分
        if cost > 100:
            weighted *= 0.8
        elif cost > 50:
            weighted *= 0.9

        return min(100, max(0, weighted))

    def _determine_rule_status(self, effectiveness: float) -> str:
        """确定规则状态"""
        if effectiveness > 80:
            return "active"  # 保持活跃
        elif effectiveness > 50:
            return "active"   # 仍然活跃但监控
        elif effectiveness > 20:
            return "testing"  # 需要测试变体
        else:
            return "deprecated"  # 考虑废弃

    def _get_rule_variants(self, rule_id: str) -> List[str]:
        """获取规则的所有相关变体"""
        variants = []
        try:
            if self.rule_variants_log.exists():
                with open(self.rule_variants_log, 'r') as f:
                    for line in f:
                        try:
                            record = json.loads(line)
                            if record.get("parent_rule_id") == rule_id:
                                variants.append(record.get("variant_id"))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass

        return variants

    def record_rule_application(self, rule_id: str, fixed: bool = True,
                               latency_ms: float = 0.0,
                               satisfaction: Optional[float] = None) -> None:
        """
        记录规则的应用情况

        Args:
            rule_id: 规则ID
            fixed: 是否修复了问题
            latency_ms: 规则应用的延迟
            satisfaction: 用户满意度评分 (1-5)
        """
        try:
            record = {
                "timestamp": datetime.now().isoformat(),
                "rule_id": rule_id,
                "fixed": fixed,
                "latency_ms": latency_ms,
                "satisfaction": satisfaction,
            }

            with open(self.rule_metrics_log, 'a') as f:
                f.write(json.dumps(record) + '\n')

        except Exception as e:
            print(f"[error] 记录规则应用失败: {e}", file=sys.stderr)

    def record_ab_test_result(self, variant_id: str, effectiveness: float,
                             sample_count: int) -> None:
        """
        记录A/B测试结果

        Args:
            variant_id: 变体ID
            effectiveness: 变体的效能评分
            sample_count: 测试样本数
        """
        try:
            record = {
                "timestamp": datetime.now().isoformat(),
                "variant_id": variant_id,
                "effectiveness": effectiveness,
                "sample_count": sample_count,
                "conclusion": "promote" if effectiveness > 75 else "reject",
            }

            with open(self.ab_test_results, 'a') as f:
                f.write(json.dumps(record) + '\n')

        except Exception as e:
            print(f"[error] 记录A/B测试结果失败: {e}", file=sys.stderr)


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description="规则优化框架")
    parser.add_argument("rule_id", help="规则ID")
    parser.add_argument("--evaluate", action="store_true", help="评估规则效能")
    parser.add_argument("--suggest", action="store_true", help="建议变体")
    parser.add_argument("--record", action="store_true", help="记录应用")
    parser.add_argument("--fixed", action="store_true", help="是否修复问题")
    parser.add_argument("--latency", type=float, default=0.0, help="延迟(ms)")
    parser.add_argument("--satisfaction", type=float, help="用户满意度(1-5)")
    parser.add_argument("--workspace", default=None, help="工作目录")

    args = parser.parse_args()

    try:
        optimizer = RuleOptimizer(args.workspace)

        if args.evaluate:
            metrics = optimizer.evaluate_rule_effectiveness(args.rule_id)
            print(json.dumps({
                "rule_id": metrics.rule_id,
                "trigger_frequency": metrics.trigger_frequency,
                "fix_rate": metrics.fix_rate,
                "cost_overhead_ms": metrics.cost_overhead_ms,
                "user_satisfaction": metrics.user_satisfaction,
                "effectiveness_score": metrics.effectiveness_score,
                "status": metrics.status,
            }, indent=2))

        elif args.suggest:
            variants = optimizer.suggest_rule_variants(args.rule_id)
            print(json.dumps([asdict(v) for v in variants], indent=2))

        elif args.record:
            optimizer.record_rule_application(
                args.rule_id,
                args.fixed,
                args.latency,
                args.satisfaction
            )
            print(f"✅ 已记录规则 {args.rule_id} 的应用")

        return 0

    except Exception as e:
        print(f"[error] 处理失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
