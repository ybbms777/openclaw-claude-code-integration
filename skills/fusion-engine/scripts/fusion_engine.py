#!/usr/bin/env python3
"""
多源融合引擎 (Data Fusion Engine)
整合命令执行反馈、用户交互、系统状态信号，生成综合决策上下文
"""

import json
import os
import sys
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class FusionScore:
    """融合评分结果"""
    memory_relevance: float    # LanceDB相关记忆的可信度 (0-100)
    cmd_success_rate: float    # 历史执行成功率 (0-100)
    user_preference: float     # 用户偏好信号 (0-100)
    system_health: float       # 系统当前状态 (0-100)

    final_score: float         # 加权融合分数 (0-100)
    decision: str              # 决策建议: "auto_allow", "request_confirm", "block"
    reasoning: Dict            # 决策理由


class MultiSourceFusionEngine:
    """多源数据融合引擎"""

    def __init__(self, workspace_dir: str = None):
        """
        初始化融合引擎

        Args:
            workspace_dir: OpenClaw工作目录
        """
        self.workspace = Path(workspace_dir or
                             os.path.expanduser("~/.openclaw/workspace"))

        # 数据源路径
        self.lancedb_dir = self.workspace / "memory" / "lancedb-pro"
        self.cmd_log = self.workspace / ".command-execution.jsonl"
        self.user_log = self.workspace / ".user-interactions.jsonl"
        self.fusion_log = self.workspace / ".fusion-decisions.jsonl"

        # 权重配置（可调）
        self.weights = {
            "memory": 0.30,          # LanceDB相关性
            "cmd_success": 0.30,     # 命令成功率
            "user_pref": 0.25,       # 用户偏好
            "system": 0.15,          # 系统状态
        }

        # 决策阈值
        self.thresholds = {
            "auto_allow": 75,        # > 75: 自动执行
            "request_confirm": 50,   # 50-75: 请求确认
            "block": 0,              # < 50: 阻止
        }

        # 创建日志目录
        self.fusion_log.parent.mkdir(parents=True, exist_ok=True)

    def fuse_decision_context(self, tool_name: str, params: dict,
                            session_id: str = None) -> FusionScore:
        """
        整合多个数据源，生成综合上下文评分

        Args:
            tool_name: 工具名称 (e.g., "bash", "write", "read")
            params: 工具参数
            session_id: 会话ID（可选）

        Returns:
            FusionScore 对象
        """
        reasoning = {}

        # 1. 评估LanceDB记忆的相关性
        memory_score = self._evaluate_memory_relevance(tool_name, params, session_id)
        reasoning["memory"] = {
            "score": memory_score,
            "note": "基于LanceDB中相关记忆的可信度"
        }

        # 2. 评估命令执行成功率
        cmd_score = self._evaluate_cmd_success_rate(tool_name, params)
        reasoning["cmd_success"] = {
            "score": cmd_score,
            "note": "基于历史执行的成功率"
        }

        # 3. 评估用户交互偏好
        user_score = self._evaluate_user_preference(tool_name, params, session_id)
        reasoning["user_pref"] = {
            "score": user_score,
            "note": "基于用户过往决策模式"
        }

        # 4. 评估系统健康status
        system_score = self._evaluate_system_health()
        reasoning["system"] = {
            "score": system_score,
            "note": "基于系统资源和网络状态"
        }

        # 5. 计算加权融合分数
        final_score = self._weighted_fusion(
            memory_score, cmd_score, user_score, system_score
        )

        # 6. 生成决策建议
        decision = self._make_decision(final_score)

        return FusionScore(
            memory_relevance=memory_score,
            cmd_success_rate=cmd_score,
            user_preference=user_score,
            system_health=system_score,
            final_score=final_score,
            decision=decision,
            reasoning=reasoning
        )

    def _evaluate_memory_relevance(self, tool_name: str, params: dict,
                                  session_id: str = None) -> float:
        """
        评估LanceDB中相关记忆的可信度

        相关性高的场景：
        - 在相同项目中以前成功执行过类似操作
        - LanceDB中有相关的最佳实践
        - 相关记忆的importance评分高

        Args:
            tool_name: 工具名称
            params: 工具参数
            session_id: 会话ID

        Returns:
            0-100的相关性评分
        """
        score = 50  # 基础分

        try:
            # 查询LanceDB中相关的记忆
            similar_memories = self._query_lancedb(
                tool_name=tool_name,
                limit=5,
                threshold=0.7
            )

            if not similar_memories:
                return 40  # 无相关记忆，低信心

            # 统计相关记忆的质量
            total_importance = 0
            success_count = 0

            for mem in similar_memories:
                importance = mem.get("importance", 0.5)
                total_importance += importance

                # 检查是否成功
                if mem.get("status") == "success":
                    success_count += 1

            # 计算平均重要性和成功率
            avg_importance = total_importance / len(similar_memories)
            success_rate = success_count / len(similar_memories)

            score = 40 + (avg_importance * 40) + (success_rate * 20)

            return min(100, score)

        except Exception as e:
            print(f"[warn] 评估记忆相关性失败: {e}", file=sys.stderr)
            return 50

    def _evaluate_cmd_success_rate(self, tool_name: str, params: dict) -> float:
        """
        评估此工具在历史中的执行成功率

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            0-100的成功率评分
        """
        try:
            if not self.cmd_log.exists():
                return 60  # 无历史记录，保守估计

            total = 0
            success = 0

            with open(self.cmd_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("tool") == tool_name:
                            total += 1
                            if record.get("status") == "success":
                                success += 1
                    except json.JSONDecodeError:
                        continue

            if total == 0:
                return 60

            success_rate = (success / total) * 100
            return min(100, success_rate)

        except Exception as e:
            print(f"[warn] 评估命令成功率失败: {e}", file=sys.stderr)
            return 60

    def _evaluate_user_preference(self, tool_name: str, params: dict,
                                 session_id: str = None) -> float:
        """
        评估用户过往的决策偏好

        用户模式：
        - 是否经常拒绝此类操作
        - 是否经常确认并成功
        - 相似操作的用户满意度

        Args:
            tool_name: 工具名称
            params: 工具参数
            session_id: 会话ID

        Returns:
            0-100的偏好评分
        """
        try:
            if not self.user_log.exists():
                return 50  # 无用户交互记录

            approved = 0
            rejected = 0
            satisfaction_sum = 0
            satisfaction_count = 0

            with open(self.user_log, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("tool") == tool_name:
                            action = record.get("action")
                            if action == "approved":
                                approved += 1
                            elif action == "rejected":
                                rejected += 1

                            # 收集满意度评分
                            sat = record.get("satisfaction")
                            if sat is not None:
                                satisfaction_sum += sat
                                satisfaction_count += 1

                    except json.JSONDecodeError:
                        continue

            total_interactions = approved + rejected

            if total_interactions == 0:
                return 50

            # 计算接受率
            acceptance_rate = (approved / total_interactions) * 100

            # 计算平均满意度
            avg_satisfaction = 50  # 默认中间值
            if satisfaction_count > 0:
                avg_satisfaction = (satisfaction_sum / satisfaction_count) * 100

            # 综合评分
            score = (acceptance_rate * 0.6) + (avg_satisfaction * 0.4)

            return min(100, score)

        except Exception as e:
            print(f"[warn] 评估用户偏好失败: {e}", file=sys.stderr)
            return 50

    def _evaluate_system_health(self) -> float:
        """
        评估系统当前的健康状态

        指标：
        - CPU使用率
        - 内存使用率
        - 磁盘空间
        - 网络连接

        Returns:
            0-100的系统健康评分
        """
        try:
            health_scores = []

            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_score = 100 - cpu_percent  # 低使用率=高分
            health_scores.append(cpu_score)

            # 内存使用率
            mem = psutil.virtual_memory()
            mem_score = 100 - mem.percent
            health_scores.append(mem_score)

            # 磁盘空间
            disk = psutil.disk_usage('/')
            disk_score = 100 - disk.percent
            health_scores.append(disk_score)

            # 平均值
            avg_score = sum(health_scores) / len(health_scores)

            return max(10, min(100, avg_score))

        except Exception as e:
            print(f"[warn] 评估系统健康失败: {e}", file=sys.stderr)
            return 60

    def _weighted_fusion(self, memory: float, cmd: float,
                        user: float, system: float) -> float:
        """
        计算加权融合分数

        Args:
            memory: LanceDB相关性 (0-100)
            cmd: 命令成功率 (0-100)
            user: 用户偏好 (0-100)
            system: 系统健康 (0-100)

        Returns:
            加权融合分数 (0-100)
        """
        fusion = (
            memory * self.weights["memory"] +
            cmd * self.weights["cmd_success"] +
            user * self.weights["user_pref"] +
            system * self.weights["system"]
        )

        return round(min(100, max(0, fusion)), 1)

    def _make_decision(self, score: float) -> str:
        """
        基于融合分数做出决策

        Args:
            score: 融合分数 (0-100)

        Returns:
            "auto_allow", "request_confirm", 或 "block"
        """
        if score >= self.thresholds["auto_allow"]:
            return "auto_allow"
        elif score >= self.thresholds["request_confirm"]:
            return "request_confirm"
        else:
            return "block"

    def _query_lancedb(self, tool_name: str, limit: int = 5,
                      threshold: float = 0.7) -> List[Dict]:
        """
        查询LanceDB中相关的记忆

        Args:
            tool_name: 工具名称
            limit: 返回记录数
            threshold: 相似度阈值

        Returns:
            相关记忆列表
        """
        # 这里应该调用实际的LanceDB查询
        # 暂时返回空列表（placeholder）
        return []

    def save_decision(self, tool_name: str, score: FusionScore,
                     session_id: str = None) -> None:
        """
        保存融合决策到日志"""
        try:
            record = {
                "timestamp": datetime.now().isoformat(),
                "tool": tool_name,
                "session_id": session_id,
                "fusion_score": score.final_score,
                "decision": score.decision,
                "components": {
                    "memory": score.memory_relevance,
                    "cmd_success": score.cmd_success_rate,
                    "user_pref": score.user_preference,
                    "system": score.system_health,
                }
            }

            with open(self.fusion_log, 'a') as f:
                f.write(json.dumps(record) + '\n')

        except Exception as e:
            print(f"[error] 保存融合决策失败: {e}", file=sys.stderr)


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description="多源融合引擎")
    parser.add_argument("tool_name", help="工具名称")
    parser.add_argument("--params", default="{}", help="工具参数JSON")
    parser.add_argument("--session-id", default=None, help="会话ID")
    parser.add_argument("--workspace", default=None, help="工作目录")
    parser.add_argument("--save", action="store_true", help="保存决策")

    args = parser.parse_args()

    try:
        engine = MultiSourceFusionEngine(args.workspace)

        params = json.loads(args.params)

        score = engine.fuse_decision_context(
            args.tool_name, params, args.session_id
        )

        if args.save:
            engine.save_decision(args.tool_name, score, args.session_id)

        # 输出结果
        print(json.dumps({
            "tool": args.tool_name,
            "scores": {
                "memory": score.memory_relevance,
                "cmd_success": score.cmd_success_rate,
                "user_preference": score.user_preference,
                "system_health": score.system_health,
            },
            "final_score": score.final_score,
            "decision": score.decision,
            "reasoning": score.reasoning,
        }, indent=2))

        return 0

    except Exception as e:
        print(f"[error] 处理失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
