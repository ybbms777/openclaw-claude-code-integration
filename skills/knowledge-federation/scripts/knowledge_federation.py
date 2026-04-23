#!/usr/bin/env python3
"""
知识共享框架 (Knowledge Federation)
多Agent跨项目学习、规则共享、冲突协调、版本管理
"""

import json
import os
import sys
import hashlib
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict
from enum import Enum
import statistics

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oeck.runtime_core.workspace import WorkspaceResolver


class RuleSource(Enum):
    """规则来源"""
    LOCAL = "local"           # 本地生成
    COMMUNITY = "community"   # 社群共享
    VERIFIED = "verified"     # 已验证规则


class ConflictResolution(Enum):
    """冲突解决策略"""
    LOCAL_PRIORITY = "local_priority"       # 本地优先
    COMMUNITY_PRIORITY = "community_priority"  # 社群优先
    MERGE = "merge"                         # 合并
    VERSION = "version"                     # 版本管理


@dataclass
class RuleVersion:
    """规则版本"""
    version_id: str
    rule_id: str
    parent_version: Optional[str]  # 父版本（用于追踪演化）
    author_agent: str
    timestamp: str
    content: Dict
    effectiveness_score: float
    status: str  # draft, published, deprecated

    # 元数据
    tags: List[str] = field(default_factory=list)
    description: str = ""
    breaking_changes: List[str] = field(default_factory=list)


@dataclass
class RuleConflict:
    """规则冲突"""
    conflict_id: str
    local_rule: RuleVersion
    community_rule: RuleVersion
    detected_at: str
    resolution_strategy: ConflictResolution
    resolution_result: Optional[RuleVersion] = None
    user_decision: Optional[str] = None


@dataclass
class CommunityRule:
    """社群规则记录"""
    rule_id: str
    versions: List[RuleVersion] = field(default_factory=list)
    effectiveness_history: List[Tuple[str, float]] = field(default_factory=list)
    adoption_count: int = 0  # 采纳此规则的Agent数
    project_tags: Set[str] = field(default_factory=set)

    # 排行榜数据
    leaderboard_position: Optional[int] = None
    leaderboard_score: float = 0.0


class LocalRuleRegistry:
    """本地规则注册表"""

    def __init__(self, workspace_dir: str, resolver: WorkspaceResolver | None = None):
        self.resolver = resolver or WorkspaceResolver.from_workspace(workspace_dir)
        self.workspace = self.resolver.layout.workspace_root
        self.rules_dir = self.resolver.local_rules_dir()
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self.rules: Dict[str, RuleVersion] = {}

    def register_rule(self, rule_id: str, content: Dict,
                     effectiveness: float, description: str = "") -> RuleVersion:
        """注册本地规则"""
        version_id = str(uuid.uuid4())[:8]

        version = RuleVersion(
            version_id=version_id,
            rule_id=rule_id,
            parent_version=None,
            author_agent=os.environ.get("OPENCLAW_AGENT_ID", "local"),
            timestamp=datetime.now().isoformat(),
            content=content,
            effectiveness_score=effectiveness,
            status="draft",
            description=description
        )

        self.rules[rule_id] = version
        self._persist_rule(version)
        return version

    def _persist_rule(self, version: RuleVersion):
        """持久化规则到本地"""
        rule_file = self.rules_dir / f"{version.rule_id}_{version.version_id}.json"
        with open(rule_file, 'w') as f:
            json.dump(asdict(version), f, indent=2)

    def get_rule(self, rule_id: str) -> Optional[RuleVersion]:
        """获取规则"""
        return self.rules.get(rule_id)

    def list_rules(self) -> List[RuleVersion]:
        """列出所有规则"""
        return list(self.rules.values())


class ConflictResolver:
    """规则冲突解决器"""

    @staticmethod
    def detect_conflicts(local_rule: RuleVersion,
                        community_rule: RuleVersion) -> bool:
        """检测两个规则是否冲突"""
        # 简单的冲突检测：相同规则ID且内容不同
        if local_rule.rule_id == community_rule.rule_id:
            if local_rule.content != community_rule.content:
                return True
        return False

    @staticmethod
    def resolve_conflict(conflict: RuleConflict) -> RuleVersion:
        """解决规则冲突"""

        if conflict.resolution_strategy == ConflictResolution.LOCAL_PRIORITY:
            return conflict.local_rule

        elif conflict.resolution_strategy == ConflictResolution.COMMUNITY_PRIORITY:
            return conflict.community_rule

        elif conflict.resolution_strategy == ConflictResolution.MERGE:
            # 合并两个规则的最优特性
            merged = RuleVersion(
                version_id=str(uuid.uuid4())[:8],
                rule_id=conflict.local_rule.rule_id,
                parent_version=conflict.local_rule.version_id,
                author_agent=conflict.local_rule.author_agent,
                timestamp=datetime.now().isoformat(),
                content={
                    **conflict.local_rule.content,
                    **conflict.community_rule.content  # 社群版本覆盖
                },
                effectiveness_score=max(
                    conflict.local_rule.effectiveness_score,
                    conflict.community_rule.effectiveness_score
                ),
                status="published",
                description=f"Merged from v{conflict.local_rule.version_id} and community rule"
            )
            return merged

        elif conflict.resolution_strategy == ConflictResolution.VERSION:
            # 两个版本并存
            if conflict.local_rule.effectiveness_score >= conflict.community_rule.effectiveness_score:
                return conflict.local_rule
            else:
                return conflict.community_rule

        return conflict.local_rule  # 默认使用本地版本


class CommunityLeaderboard:
    """社群规则排行榜"""

    def __init__(self):
        self.rules: Dict[str, CommunityRule] = {}
        self.rankings: List[Tuple[str, float]] = []

    def add_rule(self, rule: CommunityRule):
        """添加规则到排行榜"""
        self.rules[rule.rule_id] = rule

    def update_effectiveness(self, rule_id: str, score: float):
        """更新规则效能并刷新排行"""
        if rule_id in self.rules:
            self.rules[rule_id].effectiveness_history.append(
                (datetime.now().isoformat(), score)
            )
            if self.rules[rule_id].effectiveness_history:
                avg_score = statistics.mean(
                    [s for _, s in self.rules[rule_id].effectiveness_history[-10:]]
                )
                self.rules[rule_id].leaderboard_score = avg_score

        self._refresh_rankings()

    def record_adoption(self, rule_id: str):
        """记录规则被采纳"""
        if rule_id in self.rules:
            self.rules[rule_id].adoption_count += 1
        self._refresh_rankings()

    def _refresh_rankings(self):
        """刷新排行榜排名"""
        self.rankings = sorted(
            [(rid, r.leaderboard_score) for rid, r in self.rules.items()],
            key=lambda x: x[1],
            reverse=True
        )

        for idx, (rule_id, _) in enumerate(self.rankings):
            self.rules[rule_id].leaderboard_position = idx + 1

    def get_top_rules(self, limit: int = 10) -> List[CommunityRule]:
        """获取排行前N的规则"""
        top_ids = [rid for rid, _ in self.rankings[:limit]]
        return [self.rules[rid] for rid in top_ids if rid in self.rules]

    def get_leaderboard(self) -> List[Dict]:
        """获取排行榜数据"""
        return [
            {
                "position": self.rules[rid].leaderboard_position,
                "rule_id": rid,
                "score": self.rules[rid].leaderboard_score,
                "adoption_count": self.rules[rid].adoption_count,
            }
            for rid, _ in self.rankings
        ]


class KnowledgeFederation:
    """知识共享框架主系统"""

    def __init__(self, workspace_dir: str = None, central_api: str = None):
        """
        初始化知识联邦系统

        Args:
            workspace_dir: OpenClaw工作目录
            central_api: 中央知识库API (如http://localhost:8000)
        """
        self.resolver = WorkspaceResolver.from_workspace(workspace_dir)
        self.workspace = self.resolver.layout.workspace_root
        self.central_api = central_api or os.environ.get("KNOWLEDGE_FEDERATION_API")

        self.agent_id = os.environ.get("OPENCLAW_AGENT_ID", str(uuid.uuid4())[:8])
        self.project_id = os.environ.get("PROJECT_ID", "default")

        # 本地组件
        self.local_registry = LocalRuleRegistry(str(self.workspace), resolver=self.resolver)
        self.conflict_resolver = ConflictResolver()
        self.leaderboard = CommunityLeaderboard()

        # 持久化路径
        self.federation_log = self.resolver.log_file("federation-log")
        self.conflict_log = self.resolver.log_file("conflict-log")
        self.published_rules = self.resolver.log_file("published-rules")

        self.federation_log.parent.mkdir(parents=True, exist_ok=True)

    def publish_rule(self, rule_id: str, content: Dict,
                    effectiveness: float, tags: List[str] = None) -> str:
        """
        发布规则到社群

        Args:
            rule_id: 规则ID
            content: 规则内容
            effectiveness: 效能评分
            tags: 标签列表

        Returns:
            发布ID
        """
        # 1. 注册到本地
        version = self.local_registry.register_rule(
            rule_id, content, effectiveness
        )
        version.tags = tags or []
        version.status = "published"

        # 2. 记录发布
        publish_record = {
            "timestamp": datetime.now().isoformat(),
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "rule_id": rule_id,
            "version_id": version.version_id,
            "effectiveness": effectiveness,
            "tags": tags,
        }

        with open(self.federation_log, 'a') as f:
            f.write(json.dumps(publish_record) + '\n')

        # 3. 如果有中央API，上报到社群
        if self.central_api:
            self._send_to_central(version)

        return version.version_id

    def subscribe_community_rules(self, filters: Dict = None) -> List[CommunityRule]:
        """
        订阅社群规则

        Args:
            filters: 过滤条件 {"tags": [...], "min_score": 75, "project": "..."}

        Returns:
            符合条件的社群规则列表
        """
        filters = filters or {}

        # 如果有中央API，从社群获取
        if self.central_api:
            return self._fetch_from_central(filters)

        # 否则返回本地副本
        return list(self.leaderboard.rules.values())

    def integrate_community_rule(self, community_rule: CommunityRule) -> RuleVersion:
        """
        集成社群规则到本地

        处理冲突、保存版本、更新排行榜

        Args:
            community_rule: 社群规则

        Returns:
            最终集成的规则版本
        """
        latest_version = community_rule.versions[-1] if community_rule.versions else None
        if not latest_version:
            raise ValueError("Community rule has no versions")

        local_rule = self.local_registry.get_rule(community_rule.rule_id)

        # 检测冲突
        if local_rule and self.conflict_resolver.detect_conflicts(local_rule, latest_version):
            conflict = RuleConflict(
                conflict_id=str(uuid.uuid4())[:8],
                local_rule=local_rule,
                community_rule=latest_version,
                detected_at=datetime.now().isoformat(),
                resolution_strategy=ConflictResolution.LOCAL_PRIORITY
            )

            # 解决冲突
            resolved = self.conflict_resolver.resolve_conflict(conflict)
            conflict.resolution_result = resolved

            # 记录冲突
            self._log_conflict(conflict)

            return resolved

        # 没有冲突，直接采纳
        self.leaderboard.add_rule(community_rule)
        self.leaderboard.record_adoption(community_rule.rule_id)

        return latest_version

    def get_rule_genealogy(self, rule_id: str) -> List[RuleVersion]:
        """
        获取规则的完整演化历史

        Args:
            rule_id: 规则ID

        Returns:
            按时间排序的规则版本链
        """
        versions = []
        current = self.local_registry.get_rule(rule_id)

        while current:
            versions.insert(0, current)
            if current.parent_version:
                # 从本地查找父版本
                rule_file = self.local_registry.rules_dir / f"{rule_id}_{current.parent_version}.json"
                if rule_file.exists():
                    with open(rule_file, 'r') as f:
                        parent_data = json.load(f)
                        current = RuleVersion(**parent_data)
                else:
                    break
            else:
                break

        return versions

    def _send_to_central(self, version: RuleVersion):
        """向中央知识库发送规则"""
        if not self.central_api:
            return

        try:
            import urllib.request, urllib.error

            payload = json.dumps({
                "rule_id": version.rule_id,
                "version_id": version.version_id,
                "parent_version": version.parent_version,
                "author_agent": version.author_agent,
                "content": version.content,
                "effectiveness_score": version.effectiveness_score,
                "status": version.status,
                "tags": version.tags,
                "description": version.description,
            }).encode("utf-8")

            url = f"{self.central_api}/federation/publish"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"OpenClaw/{self.agent_id}",
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                logger.info(f"规则 {version.rule_id} 已同步到中央库，排行第 {result.get('leaderboard_position')} 位")

        except urllib.error.HTTPError as e:
            logger.warning(f"中央API HTTP错误 {e.code}: {e.read().decode()}")
        except Exception as e:
            logger.warning(f"发送到中央API失败: {e}")

    def _fetch_from_central(self, filters: Dict) -> List[CommunityRule]:
        """从中央知识库获取规则"""
        if not self.central_api:
            return list(self.leaderboard.rules.values())

        try:
            import urllib.request, urllib.error

            query_parts = []
            if filters.get("tags"):
                query_parts.append(f"tags={','.join(filters['tags'])}")
            if filters.get("min_score") is not None:
                query_parts.append(f"min_score={filters['min_score']}")

            query = "&".join(query_parts)
            url = f"{self.central_api}/federation/subscribe"
            if query:
                url += f"?{query}"

            req = urllib.request.Request(
                url,
                headers={"User-Agent": f"OpenClaw/{self.agent_id}"},
                method="GET"
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                community_rules = []

                for rdata in result:
                    versions = [RuleVersion(**v) for v in rdata.get("versions", [])]
                    community_rule = CommunityRule(
                        rule_id=rdata["rule_id"],
                        versions=versions,
                        effectiveness_history=[],
                        adoption_count=rdata.get("adoption_count", 0),
                        project_tags=set(),
                        leaderboard_position=rdata.get("leaderboard_position"),
                        leaderboard_score=rdata.get("leaderboard_score", 0.0),
                    )
                    community_rules.append(community_rule)

                logger.info(f"从中央库获取 {len(community_rules)} 条社群规则")
                return community_rules

        except urllib.error.HTTPError as e:
            logger.warning(f"中央API HTTP错误 {e.code}: {e.read().decode()}")
        except Exception as e:
            logger.warning(f"从中央API获取规则失败: {e}")

        return list(self.leaderboard.rules.values())

    def _log_conflict(self, conflict: RuleConflict):
        """记录冲突日志"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "conflict_id": conflict.conflict_id,
            "local_rule_id": conflict.local_rule.version_id,
            "community_rule_id": conflict.community_rule.version_id,
            "resolution": conflict.resolution_strategy.value,
        }

        with open(self.conflict_log, 'a') as f:
            f.write(json.dumps(record) + '\n')

    def get_statistics(self) -> Dict:
        """获取联邦系统的统计信息"""
        return {
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "local_rules_count": len(self.local_registry.list_rules()),
            "community_rules_count": len(self.leaderboard.rules),
            "conflicts_detected": self._count_conflicts(),
            "leaderboard_top_10": self.leaderboard.get_leaderboard()[:10],
        }

    def _count_conflicts(self) -> int:
        """计算检测到的冲突数"""
        try:
            if not self.conflict_log.exists():
                return 0

            with open(self.conflict_log, 'r') as f:
                return sum(1 for _ in f)

        except Exception:
            return 0


def main():
    """CLI入口"""
    import argparse

    parser = argparse.ArgumentParser(description="知识共享框架")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # publish
    pub_parser = subparsers.add_parser("publish", help="发布规则")
    pub_parser.add_argument("rule_id", help="规则ID")
    pub_parser.add_argument("--content", required=True, help="规则内容(JSON)")
    pub_parser.add_argument("--effectiveness", type=float, required=True, help="效能评分")
    pub_parser.add_argument("--tags", nargs="+", help="标签列表")
    pub_parser.add_argument("--workspace", help="工作目录")

    # subscribe
    sub_parser = subparsers.add_parser("subscribe", help="订阅社群规则")
    sub_parser.add_argument("--min-score", type=float, help="最低效能评分")
    sub_parser.add_argument("--tags", nargs="+", help="标签过滤")
    sub_parser.add_argument("--workspace", help="工作目录")

    # stats
    stats_parser = subparsers.add_parser("stats", help="显示统计信息")
    stats_parser.add_argument("--workspace", help="工作目录")

    args = parser.parse_args()

    try:
        fed = KnowledgeFederation(args.workspace if hasattr(args, 'workspace') else None)

        if args.command == "publish":
            content = json.loads(args.content)
            version_id = fed.publish_rule(
                args.rule_id,
                content,
                args.effectiveness,
                args.tags
            )
            print(f"✅ 规则已发布: {version_id}")

        elif args.command == "subscribe":
            filters = {}
            if hasattr(args, 'min_score') and args.min_score:
                filters['min_score'] = args.min_score
            if hasattr(args, 'tags') and args.tags:
                filters['tags'] = args.tags

            rules = fed.subscribe_community_rules(filters)
            print(f"✅ 获取 {len(rules)} 条社群规则")
            for rule in rules[:5]:
                print(f"  - {rule.rule_id} (评分: {rule.leaderboard_score})")

        elif args.command == "stats":
            stats = fed.get_statistics()
            print(json.dumps(stats, indent=2))

        return 0

    except Exception as e:
        print(f"[error] 处理失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
