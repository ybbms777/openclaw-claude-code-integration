#!/usr/bin/env python3
"""
long_term_evolution.py — 长期演化系统

整合AI驱动优化、跨项目学习、冲突智能调和、可观测性仪表板。

功能：
  1. AI驱动规则优化 - 基于MiniMax API生成优化建议
  2. 跨项目知识转移 - 从相似项目迁移有效规则
  3. 智能冲突调和 - AI辅助的冲突解决方案
  4. 可观测性仪表板 - 系统健康度、效能指标、可视化

用法：
  python3 long_term_evolution.py --suggest --rule-id xxx
  python3 long_term_evolution.py --transfer --source project_a --target project_b
  python3 long_term_evolution.py --dashboard
  python3 long_term_evolution.py --observe
"""

import json
import os
import sys
import math
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, asdict, field
from collections import defaultdict, Counter
from enum import Enum
import statistics

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oeck.runtime_core.workspace import WorkspaceResolver

# ═══════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_API_URL = "https://api.minimaxi.com/v1/chat/completions"
MINIMAX_EMBED_URL = "https://api.minimaxi.com/v1/embeddings"


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RuleMetrics:
    """规则效能指标"""
    rule_id: str
    version_id: str
    effectiveness_score: float
    success_count: int
    failure_count: int
    avg_latency_ms: float
    user_satisfaction: float
    last_updated: str


@dataclass
class ProjectContext:
    """项目上下文"""
    project_id: str
    project_type: str
    tags: Set[str]
    rule_count: int
    avg_effectiveness: float
    common_patterns: List[str]


@dataclass
class OptimizationSuggestion:
    """优化建议"""
    suggestion_id: str
    rule_id: str
    current_state: Dict
    suggested_change: Dict
    rationale: str
    expected_improvement: float
    confidence: float
    ai_model: str = "MiniMax-M2"


@dataclass
class KnowledgeTransfer:
    """知识转移记录"""
    transfer_id: str
    source_project: str
    target_project: str
    transferred_rules: List[str]
    similarity_score: float
    effectiveness_gain: float
    timestamp: str


@dataclass
class SystemMetrics:
    """系统级指标"""
    total_agents: int
    total_rules: int
    total_adoptions: int
    avg_effectiveness: float
    health_score: float
    active_conflicts: int
    top_performers: List[Dict]
    recent_activity: List[Dict]


# ═══════════════════════════════════════════════════════════════════════════
# MiniMax API 调用
# ═══════════════════════════════════════════════════════════════════════════

def call_minimax(prompt: str, max_tokens: int = 512) -> Optional[str]:
    """调用MiniMax API生成优化建议"""
    if not MINIMAX_API_KEY:
        return None

    payload = json.dumps({
        "model": "MiniMax-M2",
        "messages": [
            {"role": "system", "content": "你是一个专业的AI规则优化助手。基于提供的规则数据和项目上下文，分析规则效能，提供优化建议。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }).encode("utf-8")

    req = urllib.request.Request(
        MINIMAX_API_URL,
        data=payload,
        headers={"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[warn] MiniMax API error: {e}", file=sys.stderr)
        return None


def get_embedding(text: str) -> Optional[List[float]]:
    """获取文本embedding"""
    if not MINIMAX_API_KEY:
        return None

    payload = json.dumps({
        "model": "minimax-embedding",
        "input": text[:2000],
    }).encode("utf-8")

    req = urllib.request.Request(
        MINIMAX_EMBED_URL,
        data=payload,
        headers={"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            return result["data"][0]["embedding"]
    except Exception as e:
        print(f"[warn] Embedding API error: {e}", file=sys.stderr)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# 1. AI驱动规则优化
# ═══════════════════════════════════════════════════════════════════════════

class AIRuleOptimizer:
    """AI驱动的规则优化器"""

    def __init__(self, workspace_dir: str = None):
        self.resolver = WorkspaceResolver.from_workspace(workspace_dir)
        self.workspace = self.resolver.layout.workspace_root
        legacy_metrics_dir = self.workspace / ".rule-metrics"
        self.metrics_dir = legacy_metrics_dir if legacy_metrics_dir.exists() else self.resolver.layout.state_dir / "rule-metrics"
        self.metrics_dir.mkdir(parents=True, exist_ok=True)

    def analyze_rule_performance(self, rule_id: str) -> Optional[RuleMetrics]:
        """分析规则效能"""
        metrics_file = self.metrics_dir / f"{rule_id}.json"

        if not metrics_file.exists():
            return None

        try:
            data = json.loads(metrics_file.read_text())
            return RuleMetrics(**data)
        except (json.JSONDecodeError, KeyError):
            return None

    def suggest_optimization(self, rule_id: str, project_context: Dict = None) -> List[OptimizationSuggestion]:
        """生成AI优化建议"""
        metrics = self.analyze_rule_performance(rule_id)
        if not metrics:
            return []

        # 构建分析上下文
        context_text = self._build_context_text(rule_id, metrics, project_context)

        # 调用AI分析
        prompt = f"""分析以下规则并提供优化建议：

规则ID: {rule_id}
当前效能: {metrics.effectiveness_score:.1f}
成功次数: {metrics.success_count}
失败次数: {metrics.failure_count}
平均延迟: {metrics.avg_latency_ms:.1f}ms
用户满意度: {metrics.user_satisfaction:.1f}/5

{context_text}

请提供：
1. 当前规则的问题分析
2. 具体的优化建议（JSON格式）
3. 预期改进幅度

输出格式：
<analysis>
[问题分析]
</analysis>

<suggestions>
[
  {{"type": "loosen", "change": "...", "reason": "...", "expected_gain": 0.1}},
  ...
]
</suggestions>
"""
        response = call_minimax(prompt, max_tokens=1024)
        if not response:
            return self._fallback_suggestions(rule_id, metrics)

        return self._parse_suggestions(rule_id, response, metrics)

    def _build_context_text(self, rule_id: str, metrics: RuleMetrics, project_context: Dict = None) -> str:
        """构建上下文文本"""
        context = []
        context.append(f"规则ID: {rule_id}")
        context.append(f"当前状态: 效能={metrics.effectiveness_score:.1f}, 成功率={metrics.success_count/(metrics.success_count+metrics.failure_count+1)*100:.1f}%")

        if project_context:
            context.append(f"项目类型: {project_context.get('type', 'unknown')}")
            context.append(f"项目标签: {', '.join(project_context.get('tags', []))}")

        return "\n".join(context)

    def _parse_suggestions(self, rule_id: str, response: str, metrics: RuleMetrics) -> List[OptimizationSuggestion]:
        """解析AI响应为优化建议"""
        suggestions = []

        # 提取suggestions部分
        import re
        match = re.search(r'<suggestions>\s*([\s\S]*?)\s*</suggestions>', response)
        if not match:
            return self._fallback_suggestions(rule_id, metrics)

        try:
            suggestion_data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return self._fallback_suggestions(rule_id, metrics)

        for i, s in enumerate(suggestion_data):
            suggestion = OptimizationSuggestion(
                suggestion_id=f"{rule_id}_opt_{i+1}",
                rule_id=rule_id,
                current_state={
                    "effectiveness": metrics.effectiveness_score,
                    "success_count": metrics.success_count,
                    "failure_count": metrics.failure_count,
                },
                suggested_change=s.get("change", {}),
                rationale=s.get("reason", ""),
                expected_improvement=s.get("expected_gain", 0.0),
                confidence=0.7,
            )
            suggestions.append(suggestion)

        return suggestions

    def _fallback_suggestions(self, rule_id: str, metrics: RuleMetrics) -> List[OptimizationSuggestion]:
        """回退建议（当AI不可用时）"""
        suggestions = []

        # 基于指标数据的启发式建议
        success_rate = metrics.success_count / (metrics.success_count + metrics.failure_count + 1)

        if success_rate < 0.7:
            suggestions.append(OptimizationSuggestion(
                suggestion_id=f"{rule_id}_opt_1",
                rule_id=rule_id,
                current_state={"effectiveness": metrics.effectiveness_score},
                suggested_change={"action": "loosen_condition", "description": "放宽触发条件"},
                rationale=f"成功率仅{success_rate*100:.1f}%，建议检查条件是否过于严格",
                expected_improvement=0.15,
                confidence=0.8,
            ))

        if metrics.avg_latency_ms > 100:
            suggestions.append(OptimizationSuggestion(
                suggestion_id=f"{rule_id}_opt_2",
                rule_id=rule_id,
                current_state={"latency": metrics.avg_latency_ms},
                suggested_change={"action": "add_cache", "description": "添加缓存层"},
                rationale=f"延迟过高({metrics.avg_latency_ms:.1f}ms)，建议添加缓存",
                expected_improvement=0.1,
                confidence=0.75,
            ))

        return suggestions

    def apply_suggestion(self, suggestion: OptimizationSuggestion) -> bool:
        """应用优化建议"""
        # 记录应用日志
        log_file = self.workspace / ".optimization-log.jsonl"
        record = {
            "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "suggestion_id": suggestion.suggestion_id,
            "rule_id": suggestion.rule_id,
            "expected_improvement": suggestion.expected_improvement,
        }

        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return True
        except OSError:
            return False


# ═══════════════════════════════════════════════════════════════════════════
# 2. 跨项目知识转移
# ═══════════════════════════════════════════════════════════════════════════

class CrossProjectKnowledgeTransfer:
    """跨项目知识转移学习"""

    def __init__(self, workspace_dir: str = None):
        self.resolver = WorkspaceResolver.from_workspace(workspace_dir)
        self.workspace = self.resolver.layout.workspace_root
        self.transfer_log = self.resolver.log_file("knowledge-transfer")
        self.project_profiles: Dict[str, ProjectContext] = {}

    def register_project(self, project_id: str, project_type: str, tags: Set[str]) -> None:
        """注册项目"""
        self.project_profiles[project_id] = ProjectContext(
            project_id=project_id,
            project_type=project_type,
            tags=tags,
            rule_count=0,
            avg_effectiveness=0.0,
            common_patterns=[],
        )

    def analyze_project_similarity(
        self,
        source_id: str,
        target_id: str,
    ) -> float:
        """分析两个项目的相似度"""
        if source_id not in self.project_profiles or target_id not in self.project_profiles:
            return 0.0

        source = self.project_profiles[source_id]
        target = self.project_profiles[target_id]

        # 类型相似度
        type_score = 1.0 if source.project_type == target.project_type else 0.75

        # 标签重叠度
        if source.tags and target.tags:
            overlap = len(source.tags & target.tags) / len(source.tags | target.tags)
        else:
            overlap = 0.0

        # 综合相似度
        return type_score * 0.4 + overlap * 0.6

    def find_similar_projects(
        self,
        target_id: str,
        min_similarity: float = 0.5,
    ) -> List[Tuple[str, float]]:
        """找到相似项目"""
        similar = []

        for pid in self.project_profiles:
            if pid == target_id:
                continue

            similarity = self.analyze_project_similarity(target_id, pid)
            if similarity >= min_similarity:
                similar.append((pid, similarity))

        similar.sort(key=lambda x: x[1], reverse=True)
        return similar

    def suggest_transfer_rules(
        self,
        source_id: str,
        target_id: str,
        min_effectiveness: float = 70.0,
    ) -> List[str]:
        """建议从源项目转移到目标项目的规则"""
        if source_id not in self.project_profiles:
            return []

        source = self.project_profiles[source_id]
        target = self.project_profiles[target_id]

        # 获取源项目的有效规则
        source_rules = self._get_project_rules(source_id)

        # 过滤目标项目已有的规则
        target_rules = self._get_project_rules(target_id)
        target_rule_ids = {r["rule_id"] for r in target_rules}

        # 推荐不在目标项目中的高效规则
        suggested = []
        for rule in source_rules:
            if rule["rule_id"] not in target_rule_ids:
                effectiveness = rule.get("effectiveness_score", 0)
                if effectiveness >= min_effectiveness:
                    # 检查标签兼容性
                    rule_tags = set(rule.get("tags", []))
                    if not rule_tags or rule_tags & target.tags:
                        suggested.append(rule["rule_id"])

        return suggested[:10]

    def execute_transfer(
        self,
        source_id: str,
        target_id: str,
        rule_ids: List[str],
    ) -> KnowledgeTransfer:
        """执行知识转移"""
        similarity = self.analyze_project_similarity(source_id, target_id)

        transfer = KnowledgeTransfer(
            transfer_id=f"transfer_{int(datetime.now().timestamp())}",
            source_project=source_id,
            target_project=target_id,
            transferred_rules=rule_ids,
            similarity_score=similarity,
            effectiveness_gain=0.0,
            timestamp=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        )

        # 记录转移
        self._log_transfer(transfer)

        return transfer

    def _get_project_rules(self, project_id: str) -> List[Dict]:
        """获取项目的规则"""
        # 简化实现：从本地规则目录读取
        rules_dir = self.resolver.local_rules_dir()
        rules = []

        if rules_dir.exists():
            for rule_file in rules_dir.glob("*.json"):
                try:
                    data = json.loads(rule_file.read_text())
                    rules.append(data)
                except json.JSONDecodeError:
                    continue

        return rules

    def _log_transfer(self, transfer: KnowledgeTransfer) -> None:
        """记录转移日志"""
        with open(self.transfer_log, "a") as f:
            f.write(json.dumps(asdict(transfer), ensure_ascii=False) + "\n")

    def get_transfer_history(
        self,
        project_id: Optional[str] = None,
    ) -> List[KnowledgeTransfer]:
        """获取转移历史"""
        if not self.transfer_log.exists():
            return []

        transfers = []
        with open(self.transfer_log) as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if project_id is None or data["source_project"] == project_id or data["target_project"] == project_id:
                        transfers.append(KnowledgeTransfer(**data))
                except (json.JSONDecodeError, KeyError):
                    continue

        transfers.sort(key=lambda x: x.timestamp, reverse=True)
        return transfers


# ═══════════════════════════════════════════════════════════════════════════
# 3. 智能冲突调和
# ═══════════════════════════════════════════════════════════════════════════

class IntelligentConflictResolver:
    """AI辅助的智能冲突调和器"""

    def __init__(self):
        self.resolution_cache: Dict[str, Dict] = {}

    def analyze_conflict(
        self,
        local_rule: Dict,
        community_rule: Dict,
    ) -> Dict:
        """分析冲突并提供AI辅助建议"""
        # 计算基础指标
        local_score = local_rule.get("effectiveness_score", 0)
        community_score = community_rule.get("effectiveness_score", 0)
        score_diff = abs(local_score - community_score)

        # 内容相似度
        content_similarity = self._calculate_content_similarity(
            local_rule.get("content", {}),
            community_rule.get("content", {}),
        )

        # 分析结果
        analysis = {
            "score_gap": score_diff,
            "content_similarity": content_similarity,
            "recommendation": self._generate_recommendation(
                local_score, community_score, score_diff, content_similarity
            ),
            "strategies": self._suggest_strategies(
                local_score, community_score, content_similarity
            ),
        }

        return analysis

    def _calculate_content_similarity(
        self,
        content_a: Dict,
        content_b: Dict,
    ) -> float:
        """计算内容相似度"""
        if not content_a or not content_b:
            return 0.0

        # 使用embedding计算相似度
        text_a = json.dumps(content_a, sort_keys=True)
        text_b = json.dumps(content_b, sort_keys=True)

        emb_a = get_embedding(text_a)
        emb_b = get_embedding(text_b)

        if emb_a and emb_b:
            return self._cosine_similarity(emb_a, emb_b)

        # 回退：简单关键词重叠
        keys_a = set(str(k).lower() for k in content_a.keys())
        keys_b = set(str(k).lower() for k in content_b.keys())

        if not keys_a or not keys_b:
            return 0.0

        overlap = len(keys_a & keys_b) / len(keys_a | keys_b)
        return overlap

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        if len(a) != len(b):
            return 0.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * y for x, y in zip(b, b)))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    def _generate_recommendation(
        self,
        local_score: float,
        community_score: float,
        score_diff: float,
        content_similarity: float,
    ) -> str:
        """生成推荐策略"""
        if score_diff < 10 and content_similarity > 0.8:
            return "MERGE"
        elif local_score > community_score + 15:
            return "LOCAL_PRIORITY"
        elif community_score > local_score + 15:
            return "COMMUNITY_PRIORITY"
        elif content_similarity < 0.3:
            return "KEEP_BOTH"
        else:
            return "VERSION"

    def _suggest_strategies(
        self,
        local_score: float,
        community_score: float,
        content_similarity: float,
    ) -> List[Dict]:
        """建议多种策略及预期结果"""
        strategies = []

        # 策略1：保留本地
        strategies.append({
            "strategy": "LOCAL_PRIORITY",
            "pros": ["保持项目特定行为", "避免引入未知风险"],
            "cons": ["可能错过更好的社群方案"],
            "expected_score": local_score,
            "confidence": 0.8 if local_score > community_score else 0.5,
        })

        # 策略2：采用社群
        strategies.append({
            "strategy": "COMMUNITY_PRIORITY",
            "pros": ["获得更优效能", "与其他项目保持一致"],
            "cons": ["可能不适用于本项目"],
            "expected_score": community_score,
            "confidence": 0.8 if community_score > local_score else 0.5,
        })

        # 策略3：合并
        if content_similarity > 0.5:
            merged_score = (local_score + community_score) / 2 + 5
            strategies.append({
                "strategy": "MERGE",
                "pros": ["综合两者优点", "可能发现新洞察"],
                "cons": ["结果不确定", "需要测试验证"],
                "expected_score": merged_score,
                "confidence": 0.6 if content_similarity > 0.7 else 0.4,
            })

        return strategies

    def resolve_with_ai(
        self,
        local_rule: Dict,
        community_rule: Dict,
        context: Dict = None,
    ) -> Dict:
        """使用AI解决冲突"""
        # 构建提示
        prompt = f"""分析并解决以下规则冲突：

本地规则:
- 规则ID: {local_rule.get('rule_id')}
- 效能: {local_rule.get('effectiveness_score', 0):.1f}
- 内容: {json.dumps(local_rule.get('content', {}), ensure_ascii=False)[:200]}

社群规则:
- 规则ID: {community_rule.get('rule_id')}
- 效能: {community_rule.get('effectiveness_score', 0):.1f}
- 内容: {json.dumps(community_rule.get('content', {}), ensure_ascii=False)[:200]}
"""

        if context:
            prompt += f"\n项目上下文: {json.dumps(context, ensure_ascii=False)[:200]}"

        prompt += """
请提供：
1. 冲突分析
2. 推荐的解决策略
3. 合并建议（如果有）

以JSON格式输出：
{
  "analysis": "...",
  "recommended_strategy": "...",
  "merged_content": {...},
  "confidence": 0.xx
}
"""

        response = call_minimax(prompt, max_tokens=1024)
        if not response:
            # 回退到基础分析
            analysis = self.analyze_conflict(local_rule, community_rule)
            return {
                "recommended_strategy": analysis["recommendation"],
                "confidence": 0.6,
                "analysis": "AI不可用，使用启发式分析",
            }

        # 解析响应
        import re
        match = re.search(r'\{[\s\S]*\}', response)
        if match:
            try:
                result = json.loads(match.group())
                return result
            except json.JSONDecodeError:
                pass

        # 回退
        analysis = self.analyze_conflict(local_rule, community_rule)
        return {
            "recommended_strategy": analysis["recommendation"],
            "confidence": 0.5,
            "analysis": "解析失败，使用默认策略",
        }


# ═══════════════════════════════════════════════════════════════════════════
# 4. 可观测性仪表板
# ═══════════════════════════════════════════════════════════════════════════

class ObservabilityDashboard:
    """系统可观测性仪表板"""

    def __init__(self, workspace_dir: str = None, central_api: str = None):
        self.resolver = WorkspaceResolver.from_workspace(workspace_dir)
        self.workspace = self.resolver.layout.workspace_root
        self.central_api = central_api or os.environ.get("KNOWLEDGE_FEDERATION_API")
        self.cache_file = self.resolver.log_file("dashboard-cache")
        self.cache_ttl = 60  # 1分钟缓存

    def get_system_metrics(self, force_refresh: bool = False) -> SystemMetrics:
        """获取系统级指标"""
        # 检查缓存
        if not force_refresh and self._is_cache_valid():
            return self._load_from_cache()

        # 从中央API获取数据
        if self.central_api:
            metrics = self._fetch_from_api()
        else:
            metrics = self._compute_local_metrics()

        # 缓存
        self._save_to_cache(metrics)

        return metrics

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self.cache_file.exists():
            return False

        try:
            cache = json.loads(self.cache_file.read_text())
            cache_time = cache.get("timestamp", 0)
            return (datetime.now().timestamp() - cache_time) < self.cache_ttl
        except (json.JSONDecodeError, OSError):
            return False

    def _load_from_cache(self) -> SystemMetrics:
        """从缓存加载"""
        try:
            cache = json.loads(self.cache_file.read_text())
            return SystemMetrics(**cache["metrics"])
        except (json.JSONDecodeError, KeyError):
            return self._compute_local_metrics()

    def _save_to_cache(self, metrics: SystemMetrics) -> None:
        """保存到缓存"""
        cache_data = {
            "timestamp": datetime.now().timestamp(),
            "metrics": asdict(metrics),
        }
        self.cache_file.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))

    def _fetch_from_api(self) -> SystemMetrics:
        """从中央API获取指标"""
        try:
            import urllib.request

            # 获取统计
            req = urllib.request.Request(
                f"{self.central_api}/federation/stats",
                headers={"User-Agent": "ObservabilityDashboard/1.0"},
                method="GET"
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            # 获取排行榜
            req2 = urllib.request.Request(
                f"{self.central_api}/federation/leaderboard?limit=5",
                headers={"User-Agent": "ObservabilityDashboard/1.0"},
                method="GET"
            )

            with urllib.request.urlopen(req2, timeout=10) as resp2:
                leaderboard = json.loads(resp2.read().decode())

            # 获取最近活动
            recent = self._get_recent_activity()

            # 计算健康分
            health = self._calculate_health_score(data)

            return SystemMetrics(
                total_agents=data.get("total_agents", 0),
                total_rules=data.get("total_rules", 0),
                total_adoptions=data.get("total_adoptions", 0),
                avg_effectiveness=self._calculate_avg_effectiveness(data),
                health_score=health,
                active_conflicts=0,
                top_performers=leaderboard[:5],
                recent_activity=recent,
            )

        except Exception as e:
            print(f"[warn] Failed to fetch from API: {e}", file=sys.stderr)
            return self._compute_local_metrics()

    def _compute_local_metrics(self) -> SystemMetrics:
        """计算本地指标"""
        rules_dir = self.resolver.local_rules_dir()
        rule_count = len(list(rules_dir.glob("*.json"))) if rules_dir.exists() else 0

        # 计算平均效能
        effectiveness_scores = []
        if rules_dir.exists():
            for rule_file in rules_dir.glob("*.json"):
                try:
                    data = json.loads(rule_file.read_text())
                    effectiveness_scores.append(data.get("effectiveness_score", 0))
                except json.JSONDecodeError:
                    continue

        avg_eff = statistics.mean(effectiveness_scores) if effectiveness_scores else 0

        return SystemMetrics(
            total_agents=1,
            total_rules=rule_count,
            total_adoptions=0,
            avg_effectiveness=avg_eff,
            health_score=75.0,  # 默认健康分
            active_conflicts=0,
            top_performers=[],
            recent_activity=[],
        )

    def _calculate_health_score(self, data: Dict) -> float:
        """计算系统健康分"""
        total_rules = data.get("total_rules", 0)
        total_adoptions = data.get("total_adoptions", 0)

        # 基于采纳率计算
        adoption_rate = total_adoptions / (total_rules * 10) if total_rules > 0 else 0
        adoption_score = min(adoption_rate * 100, 100)

        # 基于规则数计算
        rule_score = min(total_rules / 100, 100)

        return (adoption_score * 0.6 + rule_score * 0.4)

    def _calculate_avg_effectiveness(self, data: Dict) -> float:
        """计算平均效能"""
        top_10 = data.get("top_10", [])
        if not top_10:
            return 0

        return statistics.mean([r.get("score", 0) for r in top_10])

    def _get_recent_activity(self) -> List[Dict]:
        """获取最近活动"""
        activities = []

        # 从各种日志文件收集
        log_files = [
            self.resolver.log_file("federation-log"),
            self.resolver.log_file("knowledge-transfer"),
            self.resolver.log_file("optimization-log"),
        ]

        for log_file in log_files:
            if log_file.exists():
                try:
                    lines = log_file.read_text().strip().split("\n")
                    for line in lines[-10:]:  # 每个文件最多10条
                        try:
                            activities.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                except OSError:
                    continue

        # 按时间排序
        activities.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return activities[:20]

    def generate_dashboard_html(self) -> str:
        """生成HTML仪表板"""
        metrics = self.get_system_metrics()

        health_color = self._health_color(metrics.health_score)

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>OpenClaw 知识联邦 - 可观测性仪表板</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; background: #f5f5f5; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }}
        h1 {{ color: #333; }}
        .timestamp {{ color: #666; font-size: 14px; }}
        .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }}
        .card {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .card-label {{ color: #666; font-size: 14px; margin-bottom: 8px; }}
        .card-value {{ font-size: 32px; font-weight: bold; color: #333; }}
        .card-sub {{ color: #999; font-size: 12px; margin-top: 4px; }}
        .health-card {{ background: {health_color}; }}
        .health-value {{ color: white; }}
        .health-label {{ color: rgba(255,255,255,0.8); }}
        .section {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .section-title {{ font-size: 18px; font-weight: 600; margin-bottom: 16px; color: #333; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #eee; }}
        th {{ color: #666; font-weight: 500; font-size: 14px; }}
        .rank {{ width: 40px; }}
        .score {{ color: #4CAF50; font-weight: 500; }}
        .tag {{ display: inline-block; background: #e3f2fd; color: #1976d2; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px; }}
        .activity-item {{ padding: 12px 0; border-bottom: 1px solid #eee; }}
        .activity-time {{ color: #999; font-size: 12px; }}
        .activity-content {{ margin-top: 4px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 OpenClaw 知识联邦仪表板</h1>
        <div class="timestamp">最后更新: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>

    <div class="grid">
        <div class="card health-card">
            <div class="card-label health-label">系统健康分</div>
            <div class="card-value health-value">{metrics.health_score:.1f}</div>
            <div class="card-sub health-label">分数越高越好</div>
        </div>
        <div class="card">
            <div class="card-label">总规则数</div>
            <div class="card-value">{metrics.total_rules}</div>
            <div class="card-sub">活跃规则</div>
        </div>
        <div class="card">
            <div class="card-label">总Agent数</div>
            <div class="card-value">{metrics.total_agents}</div>
            <div class="card-sub">参与联邦</div>
        </div>
        <div class="card">
            <div class="card-label">总采纳数</div>
            <div class="card-value">{metrics.total_adoptions}</div>
            <div class="card-sub">规则采纳次数</div>
        </div>
    </div>

    <div class="grid">
        <div class="card" style="grid-column: span 2;">
            <div class="card-label">平均效能</div>
            <div class="card-value">{metrics.avg_effectiveness:.1f}</div>
            <div class="card-sub">Top10规则平均分</div>
        </div>
        <div class="card" style="grid-column: span 2;">
            <div class="card-label">活跃冲突</div>
            <div class="card-value">{metrics.active_conflicts}</div>
            <div class="card-sub">待解决冲突</div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">🏆 Top 10 规则排行榜</div>
        <table>
            <thead>
                <tr>
                    <th class="rank">#</th>
                    <th>规则ID</th>
                    <th>效能分</th>
                    <th>采纳数</th>
                    <th>标签</th>
                </tr>
            </thead>
            <tbody>
"""

        for i, rule in enumerate(metrics.top_performers, 1):
            tags = " ".join([f"<span class='tag'>{t}</span>" for t in rule.get("tags", [])[:3]])
            html += f"""
                <tr>
                    <td>{i}</td>
                    <td>{rule.get('rule_id', 'N/A')}</td>
                    <td class="score">{rule.get('score', 0):.1f}</td>
                    <td>{rule.get('adoption_count', 0)}</td>
                    <td>{tags}</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
    </div>

    <div class="section">
        <div class="section-title">📝 最近活动</div>
"""

        for activity in metrics.recent_activity[:10]:
            timestamp = activity.get("timestamp", "未知时间")
            html += f"""
        <div class="activity-item">
            <div class="activity-time">{timestamp}</div>
            <div class="activity-content">{json.dumps(activity, ensure_ascii=False)[:150]}...</div>
        </div>
"""

        html += """
    </div>
</body>
</html>
"""
        return html

    def _health_color(self, score: float) -> str:
        """根据健康分返回颜色"""
        if score >= 80:
            return "#4CAF50"  # 绿色
        elif score >= 60:
            return "#FFC107"  # 黄色
        else:
            return "#F44336"  # 红色

    def save_dashboard(self, output_path: str = None) -> str:
        """保存仪表板到文件"""
        if not output_path:
            output_path = str(self.workspace / "federation-dashboard.html")

        html = self.generate_dashboard_html()
        Path(output_path).write_text(html, encoding="utf-8")

        return output_path


# ═══════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="长期演化系统")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # AI优化建议
    opt_parser = subparsers.add_parser("suggest", help="AI优化建议")
    opt_parser.add_argument("--rule-id", required=True, help="规则ID")
    opt_parser.add_argument("--apply", action="store_true", help="应用建议")

    # 知识转移
    transfer_parser = subparsers.add_parser("transfer", help="跨项目知识转移")
    transfer_parser.add_argument("--source", required=True, help="源项目ID")
    transfer_parser.add_argument("--target", required=True, help="目标项目ID")
    transfer_parser.add_argument("--execute", action="store_true", help="执行转移")

    # 冲突分析
    conflict_parser = subparsers.add_parser("resolve", help="智能冲突解决")
    conflict_parser.add_argument("--local", required=True, help="本地规则JSON文件")
    conflict_parser.add_argument("--community", required=True, help="社群规则JSON文件")
    conflict_parser.add_argument("--ai", action="store_true", help="使用AI辅助")

    # 仪表板
    dash_parser = subparsers.add_parser("dashboard", help="生成仪表板")
    dash_parser.add_argument("--output", help="输出路径")
    dash_parser.add_argument("--open", action="store_true", help="打开HTML")

    # 观测
    observe_parser = subparsers.add_parser("observe", help="系统观测")
    observe_parser.add_argument("--refresh", action="store_true", help="强制刷新")

    args = parser.parse_args()

    if args.command == "suggest":
        optimizer = AIRuleOptimizer()
        suggestions = optimizer.suggest_optimization(args.rule_id)

        print(f"\n🎯 {args.rule_id} 优化建议:\n")
        for s in suggestions:
            print(f"  {s.suggestion_id}")
            print(f"  预期改进: +{s.expected_improvement*100:.1f}%")
            print(f"  理由: {s.rationale}")
            print(f"  建议: {s.suggested_change}")
            print()

        if args.apply and suggestions:
            optimizer.apply_suggestion(suggestions[0])
            print("✅ 已应用第一条建议")

    elif args.command == "transfer":
        transfer = CrossProjectKnowledgeTransfer()

        # 注册项目
        transfer.register_project(args.source, "python", {"python", "backend"})
        transfer.register_project(args.target, "python", {"python", "api"})

        similarity = transfer.analyze_project_similarity(args.source, args.target)
        print(f"项目相似度: {similarity:.2f}")

        suggested = transfer.suggest_transfer_rules(args.source, args.target)
        print(f"建议转移的规则: {', '.join(suggested) or '无'}")

        if args.execute and suggested:
            result = transfer.execute_transfer(args.source, args.target, suggested)
            print(f"✅ 已执行转移: {result.transfer_id}")

    elif args.command == "resolve":
        local_rule = json.loads(Path(args.local).read_text())
        community_rule = json.loads(Path(args.community).read_text())

        resolver = IntelligentConflictResolver()

        if args.ai:
            result = resolver.resolve_with_ai(local_rule, community_rule)
            print(f"AI推荐策略: {result.get('recommended_strategy')}")
            print(f"置信度: {result.get('confidence', 0):.2f}")
        else:
            analysis = resolver.analyze_conflict(local_rule, community_rule)
            print(f"推荐策略: {analysis['recommendation']}")
            print(f"分数差距: {analysis['score_gap']:.1f}")
            print(f"内容相似度: {analysis['content_similarity']:.2f}")

    elif args.command == "dashboard":
        dashboard = ObservabilityDashboard()
        output = dashboard.save_dashboard(args.output)
        print(f"✅ 仪表板已保存: {output}")

        if args.open:
            import webbrowser
            webbrowser.open(f"file://{output}")

    elif args.command == "observe":
        dashboard = ObservabilityDashboard()
        metrics = dashboard.get_system_metrics(force_refresh=args.refresh)

        print(f"""
📊 系统观测报告

系统健康分: {metrics.health_score:.1f}
总规则数: {metrics.total_rules}
总Agent数: {metrics.total_agents}
总采纳数: {metrics.total_adoptions}
平均效能: {metrics.avg_effectiveness:.1f}
活跃冲突: {metrics.active_conflicts}
""")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
