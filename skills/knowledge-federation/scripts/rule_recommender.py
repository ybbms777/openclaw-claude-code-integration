#!/usr/bin/env python3
"""
rule_recommender.py — 规则推荐引擎

基于项目类型、标签、效能历史推荐适用规则。

功能：
  1. 项目画像 - 从项目结构推断项目类型
  2. 标签匹配 - 根据标签相似度推荐规则
  3. 效能预测 - 基于历史数据预测规则效能
  4. 个性化排序 - 综合多维度排序推荐

用法：
  python3 rule_recommender.py --project-dir . --recommend
  python3 rule_recommender.py --analyze-project /path/to/project
"""

import json
import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict, field
from collections import Counter, defaultdict
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oeck.runtime_core.workspace import WorkspaceResolver

# ═══════════════════════════════════════════════════════════════════════════
# 项目类型定义
# ═══════════════════════════════════════════════════════════════════════════

PROJECT_TYPES = {
    "python": {
        "keywords": ["python", "py", "pip", "venv", "requirements.txt", "setup.py", "pyproject.toml"],
        "tags": ["python", "backend"],
        "weight": 1.0,
    },
    "javascript": {
        "keywords": ["javascript", "js", "node_modules", "package.json", "npm", "yarn", "webpack"],
        "tags": ["javascript", "frontend", "web"],
        "weight": 1.0,
    },
    "typescript": {
        "keywords": ["typescript", "ts", "tsconfig.json", ".tsx", ".ts"],
        "tags": ["typescript", "frontend", "web"],
        "weight": 1.2,
    },
    "rust": {
        "keywords": ["rust", "cargo", "rs", "Cargo.toml", "Cargo.lock"],
        "tags": ["rust", "systems", "backend"],
        "weight": 1.2,
    },
    "go": {
        "keywords": ["golang", "go.mod", "go.sum", ".go"],
        "tags": ["go", "backend", "cloud"],
        "weight": 1.2,
    },
    "java": {
        "keywords": ["java", "maven", "gradle", "pom.xml", "build.gradle", ".jar"],
        "tags": ["java", "backend", "enterprise"],
        "weight": 1.0,
    },
    "docker": {
        "keywords": ["dockerfile", "docker-compose.yml", ".dockerignore"],
        "tags": ["docker", "devops", "infrastructure"],
        "weight": 1.0,
    },
    "kubernetes": {
        "keywords": ["k8s", "kubernetes", "kubectl", "helm", "ingress.yaml", "deployment.yaml"],
        "tags": ["kubernetes", "devops", "cloud", "infrastructure"],
        "weight": 1.3,
    },
    "ml": {
        "keywords": ["pytorch", "tensorflow", "sklearn", "numpy", "pandas", "jupyter", "model"],
        "tags": ["machine-learning", "python", "data-science"],
        "weight": 1.5,
    },
    "bdx": {
        "keywords": ["bdx", "qmt", "akshare", "baostock", "回测", "因子", "策略"],
        "tags": ["量化", "finance", "bdx"],
        "weight": 2.0,
    },
    "security": {
        "keywords": ["auth", "jwt", "oauth", "ssl", "tls", "password", "encryption", "security"],
        "tags": ["security", "auth", "compliance"],
        "weight": 1.5,
    },
    "web": {
        "keywords": ["html", "css", "react", "vue", "angular", "next.js", "nuxt", "django", "flask"],
        "tags": ["web", "frontend", "backend"],
        "weight": 1.0,
    },
    "api": {
        "keywords": ["rest", "graphql", "grpc", "swagger", "openapi", "endpoint", "api"],
        "tags": ["api", "backend", "microservice"],
        "weight": 1.0,
    },
    "database": {
        "keywords": ["postgres", "mysql", "mongodb", "redis", "sqlite", "sql", "orm"],
        "tags": ["database", "backend", "storage"],
        "weight": 1.0,
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# 推荐候选结构
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RecommendationCandidate:
    """推荐候选规则"""
    rule_id: str
    version_id: str
    content: Dict
    effectiveness_score: float
    adoption_count: int
    project_tags: Set[str]
    match_score: float  # 综合匹配分
    match_reasons: List[str] = field(default_factory=list)
    author_agent: str = ""
    timestamp: str = ""


@dataclass
class ProjectProfile:
    """项目画像"""
    project_type: str
    confidence: float
    detected_tags: List[str]
    language_hints: List[str]
    structure_hints: List[str]


# ═══════════════════════════════════════════════════════════════════════════
# 项目分析器
# ═══════════════════════════════════════════════════════════════════════════

class ProjectAnalyzer:
    """分析项目结构，推断项目类型"""

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.type_scores: Dict[str, float] = defaultdict(float)

    def analyze(self) -> ProjectProfile:
        """分析项目并返回画像"""
        if not self.project_dir.exists():
            return ProjectProfile(
                project_type="unknown",
                confidence=0.0,
                detected_tags=[],
                language_hints=[],
                structure_hints=[]
            )

        # 扫描项目文件
        files = self._scan_files()
        dirs = self._scan_dirs()
        contents = self._scan_contents()

        # 匹配项目类型
        all_items = files + dirs + contents
        for item in all_items:
            item_lower = item.lower()
            for ptype, spec in PROJECT_TYPES.items():
                for kw in spec["keywords"]:
                    if kw.lower() in item_lower:
                        self.type_scores[ptype] += spec["weight"]

        # 确定主类型
        if not self.type_scores:
            return ProjectProfile(
                project_type="unknown",
                confidence=0.0,
                detected_tags=[],
                language_hints=files[:20],
                structure_hints=dirs[:10]
            )

        main_type = max(self.type_scores.items(), key=lambda x: x[1])
        total_score = sum(self.type_scores.values())
        confidence = main_type[1] / total_score if total_score > 0 else 0

        # 收集标签
        detected_tags = set()
        for ptype, score in self.type_scores.items():
            if score > 0:
                detected_tags.update(PROJECT_TYPES[ptype]["tags"])

        return ProjectProfile(
            project_type=main_type[0],
            confidence=min(confidence * main_type[1], 1.0),
            detected_tags=list(detected_tags),
            language_hints=files[:20],
            structure_hints=dirs[:10]
        )

    def _scan_files(self) -> List[str]:
        """扫描项目文件"""
        files = []
        try:
            for root, _, filenames in os.walk(self.project_dir):
                # 跳过常见忽略目录
                if any(skip in root for skip in [".git", "node_modules", "__pycache__", ".venv", "venv"]):
                    continue
                for f in filenames:
                    if not f.startswith("."):
                        files.append(f)
        except PermissionError:
            pass
        return files

    def _scan_dirs(self) -> List[str]:
        """扫描项目目录"""
        dirs = []
        try:
            for item in self.project_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    dirs.append(item.name)
        except PermissionError:
            pass
        return dirs

    def _scan_contents(self) -> List[str]:
        """扫描少量文件内容关键词"""
        snippets = []
        try:
            for path in self.project_dir.rglob("*"):
                if not path.is_file():
                    continue
                if any(skip in path.parts for skip in [".git", "node_modules", "__pycache__", ".venv", "venv"]):
                    continue
                if path.suffix not in {".py", ".js", ".ts", ".rs", ".md", ".json", ".yaml", ".yml"}:
                    continue
                try:
                    snippets.append(path.read_text(encoding="utf-8", errors="ignore")[:400])
                except OSError:
                    continue
                if len(snippets) >= 20:
                    break
        except OSError:
            return []
        return snippets


# ═══════════════════════════════════════════════════════════════════════════
# 规则推荐器
# ═══════════════════════════════════════════════════════════════════════════

class RuleRecommender:
    """基于项目类型和历史数据推荐规则"""

    def __init__(self, central_api: str = None):
        self.central_api = central_api or os.environ.get("KNOWLEDGE_FEDERATION_API")
        self.cache: Dict[str, List[RecommendationCandidate]] = {}
        self.cache_time: Dict[str, float] = {}
        self.cache_ttl = 300  # 5分钟缓存

    def recommend(
        self,
        project_profile: ProjectProfile,
        rules: List[Dict],
        top_k: int = 10,
        min_score: float = 0.3,
    ) -> List[RecommendationCandidate]:
        """
        推荐规则

        Args:
            project_profile: 项目画像
            rules: 社群规则列表
            top_k: 返回前k条
            min_score: 最低匹配分

        Returns:
            排序后的推荐列表
        """
        candidates = []

        for rule in rules:
            match_result = self._calculate_match(rule, project_profile)
            latest_version = rule.get("versions", [{}])[-1] if rule.get("versions") else {}
            effectiveness = rule.get("leaderboard_score", 0) or latest_version.get("effectiveness_score", 0)

            if match_result["score"] >= min_score and effectiveness >= 50:
                candidate = RecommendationCandidate(
                    rule_id=rule.get("rule_id", ""),
                    version_id=latest_version.get("version_id", ""),
                    content=latest_version.get("content", {}),
                    effectiveness_score=effectiveness,
                    adoption_count=rule.get("adoption_count", 0),
                    project_tags=set(rule.get("project_tags", [])),
                    match_score=match_result["score"],
                    match_reasons=match_result["reasons"],
                    author_agent=latest_version.get("author_agent", ""),
                    timestamp=latest_version.get("timestamp", ""),
                )
                candidates.append(candidate)

        # 综合排序
        candidates.sort(key=lambda x: (
            x.match_score * 0.4 +
            x.effectiveness_score * 0.3 +
            min(x.adoption_count / 100, 1.0) * 0.2 +
            self._recency_score(x.timestamp) * 0.1
        ), reverse=True)

        return candidates[:top_k]

    def _calculate_match(
        self,
        rule: Dict,
        profile: ProjectProfile,
    ) -> Dict:
        """计算规则与项目的匹配度"""
        score = 0.0
        reasons = []

        latest_version = rule.get("versions", [{}])[-1] if rule.get("versions") else {}
        rule_tags = set(latest_version.get("tags", [])) or rule.get("project_tags", set())
        rule_content = latest_version.get("content", {})

        # 1. 标签匹配 (40%)
        if rule_tags and profile.detected_tags:
            tag_overlap = len(rule_tags & set(profile.detected_tags))
            if tag_overlap > 0:
                tag_score = min(tag_overlap / len(profile.detected_tags), 1.0) * 0.4
                score += tag_score
                reasons.append(f"标签匹配: {tag_overlap}个 ({rule_tags & set(profile.detected_tags)})")

        # 2. 项目类型匹配 (30%)
        if profile.project_type in PROJECT_TYPES:
            type_tags = set(PROJECT_TYPES[profile.project_type]["tags"])
            if rule_tags & type_tags:
                type_score = 0.3 * profile.confidence
                score += type_score
                reasons.append(f"项目类型匹配: {profile.project_type}")

        # 3. 内容关键词匹配 (20%)
        content_text = json.dumps(rule_content).lower()
        for tag in profile.detected_tags:
            if tag.lower() in content_text:
                score += 0.05
                reasons.append(f"内容关键词: {tag}")

        # 4. BDX/量化特殊加权
        if profile.project_type == "bdx" or "量化" in profile.detected_tags:
            if any(t in rule_tags for t in ["量化", "finance", "bdx"]):
                score += 0.2
                reasons.append("BDX/量化专属规则")

        return {"score": min(score, 1.0), "reasons": reasons}

    def _recency_score(self, timestamp: str) -> float:
        """计算时效性分数"""
        if not timestamp:
            return 0.5

        try:
            rule_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            now = datetime.now(rule_time.tzinfo)
            days_old = (now - rule_time).days

            if days_old <= 7:
                return 1.0
            elif days_old <= 30:
                return 0.8
            elif days_old <= 90:
                return 0.6
            else:
                return 0.4
        except (ValueError, TypeError):
            return 0.5

    def recommend_for_project(
        self,
        project_dir: str,
        top_k: int = 10,
    ) -> List[RecommendationCandidate]:
        """一步完成项目分析和推荐"""
        # 分析项目
        analyzer = ProjectAnalyzer(project_dir)
        profile = analyzer.analyze()

        # 获取规则
        rules = self._fetch_community_rules()

        # 推荐
        return self.recommend(profile, rules, top_k)

    def _fetch_community_rules(self) -> List[Dict]:
        """从中央API获取社群规则"""
        if not self.central_api:
            return []

        try:
            import urllib.request, urllib.error

            url = f"{self.central_api}/federation/rules"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "RuleRecommender/1.0"},
                method="GET"
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())

        except Exception as e:
            print(f"[warn] 获取社群规则失败: {e}", file=sys.stderr)
            return []


# ═══════════════════════════════════════════════════════════════════════════
# 多维度排行榜
# ═══════════════════════════════════════════════════════════════════════════

class MultiDimensionalLeaderboard:
    """多维度社群排行榜"""

    def __init__(self):
        self.rules: Dict[str, Dict] = {}

    def add_rule(self, rule: Dict) -> None:
        """添加规则到排行榜"""
        rule_id = rule.get("rule_id")
        if not rule_id:
            return

        self.rules[rule_id] = rule

    def get_leaderboard(
        self,
        dimension: str = "overall",
        filters: Dict = None,
        limit: int = 10,
    ) -> List[Dict]:
        """
        获取排行榜

        Args:
            dimension: 维度 ("overall", "by_tag", "by_project", "by_time")
            filters: 过滤条件
            limit: 返回数量
        """
        filters = filters or {}
        rules = list(self.rules.values())

        # 按维度排序
        if dimension == "by_tag":
            return self._sort_by_tag(rules, filters, limit)
        elif dimension == "by_project":
            return self._sort_by_project(rules, filters, limit)
        elif dimension == "by_time":
            return self._sort_by_time(rules, filters, limit)
        else:  # overall
            return self._sort_overall(rules, filters, limit)

    def _sort_overall(
        self,
        rules: List[Dict],
        filters: Dict,
        limit: int,
    ) -> List[Dict]:
        """综合排序"""
        # 过滤
        rules = self._apply_filters(rules, filters)

        # 排序：综合分数 = 效能分 * 0.5 + 采纳数 * 0.3 + 时效性 * 0.2
        scored = []
        for r in rules:
            latest = r.get("versions", [{}])[-1] if r.get("versions") else {}
            effectiveness = r.get("leaderboard_score", 0) or latest.get("effectiveness_score", 0)
            adoption = r.get("adoption_count", 0)

            score = effectiveness * 0.5 + min(adoption / 50, 1.0) * 30 + self._recency_weight(latest) * 20
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def _sort_by_tag(
        self,
        rules: List[Dict],
        filters: Dict,
        limit: int,
    ) -> List[Dict]:
        """按标签分组排序"""
        target_tag = filters.get("tag", "")
        if not target_tag:
            return []

        filtered = []
        for r in rules:
            versions = r.get("versions", [])
            for v in versions:
                if target_tag in v.get("tags", []):
                    filtered.append(r)
                    break

        # 按该标签下的效能排序
        scored = []
        for r in filtered:
            latest = r.get("versions", [{}])[-1] if r.get("versions") else {}
            score = latest.get("effectiveness_score", 0)
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def _sort_by_project(
        self,
        rules: List[Dict],
        filters: Dict,
        limit: int,
    ) -> List[Dict]:
        """按项目分组排序"""
        target_project = filters.get("project", "")
        if not target_project:
            return []

        filtered = []
        for r in rules:
            if target_project in r.get("project_tags", []):
                filtered.append(r)

        scored = []
        for r in filtered:
            score = r.get("leaderboard_score", 0)
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def _sort_by_time(
        self,
        rules: List[Dict],
        filters: Dict,
        limit: int,
    ) -> List[Dict]:
        """按时效排序"""
        period = filters.get("period", "week")  # week, month, quarter

        now = datetime.now()
        if period == "week":
            cutoff = 7
        elif period == "month":
            cutoff = 30
        else:  # quarter
            cutoff = 90

        filtered = []
        for r in rules:
            versions = r.get("versions", [])
            if not versions:
                continue
            latest = versions[-1]
            try:
                ts = datetime.fromisoformat(latest.get("timestamp", "").replace("Z", "+00:00"))
                if (now - ts).days <= cutoff:
                    filtered.append((ts, r))
            except (ValueError, TypeError):
                continue

        filtered.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in filtered[:limit]]

    def _apply_filters(self, rules: List[Dict], filters: Dict) -> List[Dict]:
        """应用过滤条件"""
        filtered = rules

        # 最低分数
        min_score = filters.get("min_score")
        if min_score:
            filtered = [r for r in filtered if r.get("leaderboard_score", 0) >= min_score]

        # 标签
        tags = filters.get("tags")
        if tags:
            filtered = [r for r in filtered if any(t in r.get("project_tags", []) for t in tags)]

        # 作者
        author = filters.get("author")
        if author:
            filtered = [
                r for r in filtered
                if any(v.get("author_agent") == author for v in r.get("versions", []))
            ]

        return filtered

    def _recency_weight(self, version: Dict) -> float:
        """计算时效性权重"""
        try:
            ts = datetime.fromisoformat(version.get("timestamp", "").replace("Z", "+00:00"))
            now = datetime.now(ts.tzinfo)
            days_old = (now - ts).days

            if days_old <= 7:
                return 1.0
            elif days_old <= 30:
                return 0.8
            elif days_old <= 90:
                return 0.6
            else:
                return 0.4
        except (ValueError, TypeError):
            return 0.5


# ═══════════════════════════════════════════════════════════════════════════
# 版本回滚管理器
# ═══════════════════════════════════════════════════════════════════════════

class VersionRollbackManager:
    """规则版本回滚管理器"""

    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir)
        self.versions_dir = self.workspace / ".rule-versions"
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.rollback_log = self.workspace / ".rollback-log.jsonl"

    def snapshot_rule(
        self,
        rule_id: str,
        version: Dict,
    ) -> str:
        """
        为规则创建快照

        Returns:
            快照ID
        """
        snapshot_id = f"{rule_id}_{version.get('version_id', 'unknown')}_{int(datetime.now().timestamp())}"
        snapshot_file = self.versions_dir / f"{snapshot_id}.json"

        snapshot = {
            "snapshot_id": snapshot_id,
            "rule_id": rule_id,
            "version": version,
            "created_at": datetime.now().isoformat(),
        }

        with open(snapshot_file, "w") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

        return snapshot_id

    def rollback_to(
        self,
        rule_id: str,
        target_version_id: str,
    ) -> Optional[Dict]:
        """
        回滚规则到指定版本

        Args:
            rule_id: 规则ID
            target_version_id: 目标版本ID

        Returns:
            回滚后的版本数据，失败返回None
        """
        # 查找快照
        snapshot_file = self._find_snapshot(rule_id, target_version_id)
        if not snapshot_file:
            return None

        with open(snapshot_file) as f:
            snapshot = json.load(f)

        # 记录回滚日志
        rollback_record = {
            "timestamp": datetime.now().isoformat(),
            "rule_id": rule_id,
            "target_version_id": target_version_id,
            "snapshot_id": snapshot.get("snapshot_id"),
        }

        with open(self.rollback_log, "a") as f:
            f.write(json.dumps(rollback_record, ensure_ascii=False) + "\n")

        return snapshot.get("version")

    def get_available_versions(
        self,
        rule_id: str,
    ) -> List[Dict]:
        """
        获取规则的所有可用版本快照

        Returns:
            版本列表
        """
        versions = []
        pattern = f"{rule_id}_*.json"

        for snapshot_file in self.versions_dir.glob(pattern):
            try:
                with open(snapshot_file) as f:
                    snapshot = json.load(f)
                    versions.append({
                        "snapshot_id": snapshot.get("snapshot_id"),
                        "version_id": snapshot.get("version", {}).get("version_id"),
                        "created_at": snapshot.get("created_at"),
                        "effectiveness_score": snapshot.get("version", {}).get("effectiveness_score", 0),
                    })
            except (json.JSONDecodeError, OSError):
                continue

        # 按时间排序
        versions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return versions

    def get_rollback_history(
        self,
        rule_id: Optional[str] = None,
    ) -> List[Dict]:
        """获取回滚历史"""
        if not self.rollback_log.exists():
            return []

        history = []
        with open(self.rollback_log) as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if rule_id is None or record.get("rule_id") == rule_id:
                        history.append(record)
                except json.JSONDecodeError:
                    continue

        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return history

    def _find_snapshot(
        self,
        rule_id: str,
        version_id: str,
    ) -> Optional[Path]:
        """查找指定版本的快照文件"""
        pattern = f"{rule_id}_{version_id}_*.json"
        matches = list(self.versions_dir.glob(pattern))
        return matches[0] if matches else None


# ═══════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="规则推荐引擎")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # recommend
    rec_parser = subparsers.add_parser("recommend", help="推荐规则")
    rec_parser.add_argument("--project-dir", default=".", help="项目目录")
    rec_parser.add_argument("--top-k", type=int, default=10, help="返回数量")
    rec_parser.add_argument("--central-api", help="中央API地址")

    # analyze
    ana_parser = subparsers.add_parser("analyze", help="分析项目")
    ana_parser.add_argument("--project-dir", required=True, help="项目目录")

    # leaderboard
    board_parser = subparsers.add_parser("leaderboard", help="多维度排行榜")
    board_parser.add_argument("--dimension", choices=["overall", "by_tag", "by_project", "by_time"], default="overall")
    board_parser.add_argument("--tag", help="按标签过滤")
    board_parser.add_argument("--project", help="按项目过滤")
    board_parser.add_argument("--period", choices=["week", "month", "quarter"], default="week")
    board_parser.add_argument("--limit", type=int, default=10)

    # rollback
    roll_parser = subparsers.add_parser("rollback", help="版本回滚")
    roll_parser.add_argument("--rule-id", required=True, help="规则ID")
    roll_parser.add_argument("--version-id", required=True, help="目标版本ID")
    roll_parser.add_argument("--workspace", default=None, help="工作目录")

    # history
    hist_parser = subparsers.add_parser("history", help="回滚历史")
    hist_parser.add_argument("--rule-id", help="规则ID")
    hist_parser.add_argument("--workspace", default=None, help="工作目录")

    args = parser.parse_args()

    if args.command == "recommend":
        recommender = RuleRecommender(central_api=args.central_api)
        candidates = recommender.recommend_for_project(args.project_dir, top_k=args.top_k)

        print(f"\n🎯 为项目推荐 {len(candidates)} 条规则:\n")
        for i, c in enumerate(candidates, 1):
            print(f"{i}. {c.rule_id}")
            print(f"   匹配分: {c.match_score:.2f} | 效能: {c.effectiveness_score:.1f} | 采纳: {c.adoption_count}")
            print(f"   原因: {', '.join(c.match_reasons[:3])}")
            print()

    elif args.command == "analyze":
        analyzer = ProjectAnalyzer(args.project_dir)
        profile = analyzer.analyze()

        print(f"\n📊 项目分析结果:\n")
        print(f"项目类型: {profile.project_type}")
        print(f"置信度: {profile.confidence:.2f}")
        print(f"检测到的标签: {', '.join(profile.detected_tags)}")
        print(f"语言提示: {', '.join(profile.language_hints[:10])}")
        print(f"结构提示: {', '.join(profile.structure_hints[:10])}")

    elif args.command == "leaderboard":
        # 简化：只打印占位信息
        print("多维度排行榜需要中央API支持")
        print(f"维度: {args.dimension}")

    elif args.command == "rollback":
        workspace = WorkspaceResolver.from_workspace(args.workspace).layout.workspace_root
        manager = VersionRollbackManager(str(workspace))

        result = manager.rollback_to(args.rule_id, args.version_id)
        if result:
            print(f"✅ 已回滚 {args.rule_id} 到版本 {args.version_id}")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"❌ 未找到版本 {args.version_id}")

    elif args.command == "history":
        workspace = WorkspaceResolver.from_workspace(args.workspace).layout.workspace_root
        manager = VersionRollbackManager(str(workspace))

        history = manager.get_rollback_history(args.rule_id)
        print(f"\n📜 回滚历史 ({len(history)} 条):\n")
        for h in history:
            print(f"- {h['timestamp']} | {h['rule_id']} → {h['target_version_id']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
