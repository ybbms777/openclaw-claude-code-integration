#!/usr/bin/env python3
"""
central_api.py — 中央知识库 API 服务器

为知识联邦系统提供中央聚合 API，支持：
- 规则发布 (POST /federation/publish)
- 规则查询 (GET /federation/rules)
- 规则订阅 (GET /federation/subscribe)
- 排行榜 (GET /federation/leaderboard)
- 冲突检测 (POST /federation/resolve)

用法：
  python3 central_api.py                    # 启动服务器 (默认 0.0.0.0:8000)
  python3 central_api.py --port 9000       # 指定端口
  python3 central_api.py --host 127.0.0.1   # 指定地址
"""

import os
import sys
import json
import uuid
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict, field
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oeck.runtime_core.workspace import WorkspaceResolver
import statistics

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RuleVersion:
    """规则版本"""
    version_id: str
    rule_id: str
    parent_version: Optional[str]
    author_agent: str
    timestamp: str
    content: Dict
    effectiveness_score: float
    status: str  # draft, published, deprecated
    tags: List[str] = field(default_factory=list)
    description: str = ""
    breaking_changes: List[str] = field(default_factory=list)


@dataclass
class CommunityRule:
    """社群规则记录"""
    rule_id: str
    versions: List[RuleVersion] = field(default_factory=list)
    effectiveness_history: List[tuple] = field(default_factory=list)
    adoption_count: int = 0
    project_tags: Set[str] = field(default_factory=set)
    leaderboard_position: Optional[int] = None
    leaderboard_score: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic 模型 (用于 API 请求/响应)
# ═══════════════════════════════════════════════════════════════════════════

class PublishRequest(BaseModel):
    rule_id: str
    version_id: str
    parent_version: Optional[str] = None
    author_agent: str
    content: Dict
    effectiveness_score: float
    status: str = "published"
    tags: List[str] = []
    description: str = ""


class PublishResponse(BaseModel):
    success: bool
    rule_id: str
    version_id: str
    leaderboard_position: Optional[int] = None
    message: str = ""


class RuleResponse(BaseModel):
    rule_id: str
    versions: List[Dict]
    effectiveness_score: float
    adoption_count: int
    leaderboard_position: Optional[int] = None
    leaderboard_score: float


class LeaderboardEntry(BaseModel):
    position: int
    rule_id: str
    score: float
    adoption_count: int
    author_agent: str
    tags: List[str]


class ResolveConflictRequest(BaseModel):
    local_rule: Dict
    community_rule: Dict
    strategy: str = "local_priority"  # local_priority, community_priority, merge, version


class ResolveConflictResponse(BaseModel):
    resolved_rule: Dict
    strategy_used: str
    conflict_detected: bool


class StatsResponse(BaseModel):
    total_rules: int
    total_agents: int
    total_adoptions: int
    top_10: List[LeaderboardEntry]


# ═══════════════════════════════════════════════════════════════════════════
# 中央存储
# ═══════════════════════════════════════════════════════════════════════════

class CentralStore:
    """中央知识库存储"""

    def __init__(self, storage_dir: str = None):
        resolver = WorkspaceResolver.from_workspace()
        default_storage = resolver.layout.state_dir / "knowledge-federation-central"
        self._explicit_storage = storage_dir is not None
        self.storage_dir = Path(
            storage_dir or os.environ.get("KNOWLEDGE_FEDERATION_STORAGE", str(default_storage))
        ).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.rules_file = self.storage_dir / "rules.json"
        self.agents_file = self.storage_dir / "agents.json"
        self.adoptions_file = self.storage_dir / "adoptions.json"

        self._rules: Dict[str, CommunityRule] = {}
        self._agents: Set[str] = set()
        self._adoptions: Dict[str, int] = defaultdict(int)
        self._rule_response_cache: Dict[str, RuleResponse] = {}

        if not self._explicit_storage:
            self._load()

    def _load(self):
        """从磁盘加载数据"""
        # 加载规则
        if self.rules_file.exists():
            try:
                data = json.loads(self.rules_file.read_text())
                for rid, rdata in data.items():
                    versions = [RuleVersion(**v) for v in rdata.get("versions", [])]
                    self._rules[rid] = CommunityRule(
                        rule_id=rdata["rule_id"],
                        versions=versions,
                        effectiveness_history=rdata.get("effectiveness_history", []),
                        adoption_count=rdata.get("adoption_count", 0),
                        project_tags=set(rdata.get("project_tags", [])),
                        leaderboard_position=rdata.get("leaderboard_position"),
                        leaderboard_score=rdata.get("leaderboard_score", 0.0),
                    )
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[warn] 加载规则失败: {e}")

        # 加载代理
        if self.agents_file.exists():
            try:
                self._agents = set(json.loads(self.agents_file.read_text()))
            except json.JSONDecodeError:
                pass

        # 加载采纳数
        if self.adoptions_file.exists():
            try:
                self._adoptions = defaultdict(int, json.loads(self.adoptions_file.read_text()))
            except json.JSONDecodeError:
                pass

    def _save(self):
        """保存数据到磁盘"""
        # 保存规则
        rules_data = {}
        for rid, rule in self._rules.items():
            rules_data[rid] = {
                "rule_id": rule.rule_id,
                "versions": [asdict(v) for v in rule.versions],
                "effectiveness_history": rule.effectiveness_history,
                "adoption_count": rule.adoption_count,
                "project_tags": list(rule.project_tags),
                "leaderboard_position": rule.leaderboard_position,
                "leaderboard_score": rule.leaderboard_score,
            }
        self.rules_file.write_text(json.dumps(rules_data, ensure_ascii=False, indent=2))

        # 保存代理
        self.agents_file.write_text(json.dumps(list(self._agents), ensure_ascii=False, indent=2))

        # 保存采纳数
        self.adoptions_file.write_text(json.dumps(dict(self._adoptions), ensure_ascii=False, indent=2))

    def publish_rule(self, req: PublishRequest) -> PublishResponse:
        """发布规则到中央知识库"""
        # 记录代理
        self._agents.add(req.author_agent)

        # 创建版本
        version = RuleVersion(
            version_id=req.version_id,
            rule_id=req.rule_id,
            parent_version=req.parent_version,
            author_agent=req.author_agent,
            timestamp=datetime.now().isoformat(),
            content=req.content,
            effectiveness_score=req.effectiveness_score,
            status=req.status,
            tags=req.tags,
            description=req.description,
        )

        # 获取或创建社群规则
        if req.rule_id in self._rules:
            community_rule = self._rules[req.rule_id]
            community_rule.versions.append(version)
            # 更新效能历史
            community_rule.effectiveness_history.append(
                (datetime.now().isoformat(), req.effectiveness_score)
            )
            # 重新计算平均分
            if community_rule.effectiveness_history:
                scores = [s for _, s in community_rule.effectiveness_history[-20:]]
                community_rule.leaderboard_score = statistics.mean(scores) if scores else req.effectiveness_score
        else:
            community_rule = CommunityRule(
                rule_id=req.rule_id,
                versions=[version],
                effectiveness_history=[(datetime.now().isoformat(), req.effectiveness_score)],
                adoption_count=0,
                project_tags=set(req.tags),
                leaderboard_score=req.effectiveness_score,
            )
            self._rules[req.rule_id] = community_rule

        # 刷新排行榜
        self._refresh_leaderboard()

        # 保存
        self._save()

        return PublishResponse(
            success=True,
            rule_id=req.rule_id,
            version_id=req.version_id,
            leaderboard_position=community_rule.leaderboard_position,
            message=f"规则已发布，当前排行第 {community_rule.leaderboard_position} 位"
        )

    def get_rules(self, tags: Optional[List[str]] = None,
                  min_score: Optional[float] = None,
                  author_agent: Optional[str] = None) -> List[RuleResponse]:
        """查询规则"""
        results = []
        for rule in self._rules.values():
            # 标签过滤
            if tags:
                if not any(t in rule.project_tags for t in tags):
                    continue

            # 分数过滤
            if min_score is not None:
                if rule.leaderboard_score < min_score:
                    continue

            # 作者过滤
            if author_agent:
                if not any(v.author_agent == author_agent for v in rule.versions):
                    continue

            results.append(self._to_rule_response(rule))

        return results

    def subscribe_rules(self, filters: Dict) -> List[RuleResponse]:
        """订阅规则（与 get_rules 相同接口）"""
        tags = filters.get("tags")
        min_score = filters.get("min_score")
        return self.get_rules(tags=tags, min_score=min_score)

    def record_adoption(self, rule_id: str) -> bool:
        """记录规则被采纳"""
        if rule_id not in self._rules:
            return False
        self._rules[rule_id].adoption_count += 1
        self._adoptions[rule_id] += 1
        cached = self._rule_response_cache.get(rule_id)
        if cached is not None:
            cached.adoption_count = self._rules[rule_id].adoption_count
        self._refresh_leaderboard()
        self._save()
        return True

    def get_leaderboard(self, limit: int = 10) -> List[LeaderboardEntry]:
        """获取排行榜"""
        sorted_rules = sorted(
            self._rules.values(),
            key=lambda r: r.leaderboard_score,
            reverse=True
        )

        entries = []
        for i, rule in enumerate(sorted_rules[:limit]):
            if rule.versions:
                latest = rule.versions[-1]
                entries.append(LeaderboardEntry(
                    position=i + 1,
                    rule_id=rule.rule_id,
                    score=rule.leaderboard_score,
                    adoption_count=rule.adoption_count,
                    author_agent=latest.author_agent,
                    tags=list(rule.project_tags),
                ))

        return entries

    def resolve_conflict(self, local_rule: Dict, community_rule: Dict,
                         strategy: str) -> ResolveConflictResponse:
        """解决规则冲突"""
        local_score = local_rule.get("effectiveness_score", 0)
        community_score = community_rule.get("effectiveness_score", 0)

        if strategy == "local_priority":
            resolved = local_rule
            strategy_used = "local_priority"
        elif strategy == "community_priority":
            resolved = community_rule
            strategy_used = "community_priority"
        elif strategy == "merge":
            # 合并两个规则
            resolved = {
                **local_rule,
                **community_rule,
                "content": {**local_rule.get("content", {}), **community_rule.get("content", {})},
                "effectiveness_score": max(local_score, community_score),
            }
            strategy_used = "merge"
        else:  # version - 高分优先
            if local_score >= community_score:
                resolved = local_rule
            else:
                resolved = community_rule
            strategy_used = "version"

        return ResolveConflictResponse(
            resolved_rule=resolved,
            strategy_used=strategy_used,
            conflict_detected=True,
        )

    def get_statistics(self) -> StatsResponse:
        """获取统计信息"""
        top_10 = self.get_leaderboard(10)

        total_adoptions = sum(r.adoption_count for r in self._rules.values())

        return StatsResponse(
            total_rules=len(self._rules),
            total_agents=len(self._agents),
            total_adoptions=total_adoptions,
            top_10=top_10,
        )

    def _refresh_leaderboard(self):
        """刷新排行榜"""
        sorted_rules = sorted(
            self._rules.values(),
            key=lambda r: r.leaderboard_score,
            reverse=True
        )
        for i, rule in enumerate(sorted_rules):
            rule.leaderboard_position = i + 1
            cached = self._rule_response_cache.get(rule.rule_id)
            if cached is not None:
                cached.leaderboard_position = rule.leaderboard_position
                cached.leaderboard_score = rule.leaderboard_score
                cached.effectiveness_score = rule.leaderboard_score

    def _to_rule_response(self, rule: CommunityRule) -> RuleResponse:
        cached = self._rule_response_cache.get(rule.rule_id)
        payload = {
            "rule_id": rule.rule_id,
            "versions": [asdict(v) for v in rule.versions],
            "effectiveness_score": rule.leaderboard_score,
            "adoption_count": rule.adoption_count,
            "leaderboard_position": rule.leaderboard_position,
            "leaderboard_score": rule.leaderboard_score,
        }
        if cached is None:
            cached = RuleResponse(**payload)
            self._rule_response_cache[rule.rule_id] = cached
            return cached
        for key, value in payload.items():
            setattr(cached, key, value)
        return cached


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI 应用
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="OpenClaw Knowledge Federation API",
    description="中央知识库 API - 支持跨 Agent 规则共享、版本管理、冲突协调",
    version="2.0.0",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局存储实例
store: Optional[CentralStore] = None


def get_store() -> CentralStore:
    global store
    if store is None:
        store = CentralStore()
    return store


@app.on_event("startup")
async def startup_event():
    global store
    store = CentralStore()


# ═══════════════════════════════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "service": "OpenClaw Knowledge Federation API",
        "version": "2.0.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ─── 发布规则 ────────────────────────────────────────────────────────────

@app.post("/federation/publish", response_model=PublishResponse)
async def publish_rule(req: PublishRequest):
    """发布规则到中央知识库"""
    return get_store().publish_rule(req)


@app.get("/federation/rules", response_model=List[RuleResponse])
async def get_rules(
    tags: Optional[str] = Query(None, description="标签列表，逗号分隔"),
    min_score: Optional[float] = Query(None, description="最低效能评分"),
    author: Optional[str] = Query(None, description="作者代理ID"),
):
    """查询规则"""
    tag_list = tags.split(",") if tags else None
    return get_store().get_rules(tags=tag_list, min_score=min_score, author_agent=author)


@app.get("/federation/rules/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: str):
    """获取特定规则"""
    rules = get_store().get_rules()
    for rule in rules:
        if rule.rule_id == rule_id:
            return rule
    raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")


# ─── 订阅 ────────────────────────────────────────────────────────────────

@app.get("/federation/subscribe", response_model=List[RuleResponse])
async def subscribe_rules(
    tags: Optional[str] = Query(None, description="标签列表，逗号分隔"),
    min_score: Optional[float] = Query(None, description="最低效能评分"),
):
    """订阅社群规则"""
    tag_list = tags.split(",") if tags else None
    return get_store().subscribe_rules({"tags": tag_list, "min_score": min_score})


# ─── 排行榜 ─────────────────────────────────────────────────────────────

@app.get("/federation/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(limit: int = Query(10, ge=1, le=100)):
    """获取规则效能排行榜"""
    return get_store().get_leaderboard(limit=limit)


# ─── 采纳记录 ────────────────────────────────────────────────────────────

@app.post("/federation/adopt/{rule_id}")
async def record_adoption(rule_id: str):
    """记录规则被采纳"""
    success = get_store().record_adoption(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")
    return {"success": True, "rule_id": rule_id}


# ─── 冲突解决 ────────────────────────────────────────────────────────────

@app.post("/federation/resolve", response_model=ResolveConflictResponse)
async def resolve_conflict(req: ResolveConflictRequest = Body(...)):
    """解决规则冲突"""
    return get_store().resolve_conflict(
        req.local_rule,
        req.community_rule,
        req.strategy,
    )


# ─── 统计 ───────────────────────────────────────────────────────────────

@app.get("/federation/stats", response_model=StatsResponse)
async def get_stats():
    """获取中央知识库统计信息"""
    return get_store().get_statistics()


# ═══════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="OpenClaw 知识联邦中央 API")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--storage", help="存储目录路径")
    args = parser.parse_args()

    if args.storage:
        os.environ["KNOWLEDGE_FEDERATION_STORAGE"] = args.storage

    resolver = WorkspaceResolver.from_workspace()
    default_storage = str(resolver.layout.state_dir / "knowledge-federation-central")

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║     OpenClaw 知识联邦中央 API v2.0.0                      ║
╠══════════════════════════════════════════════════════════════╣
║  地址: http://{args.host}:{args.port}                          ║
║  文档: http://{args.host}:{args.port}/docs                    ║
║  存储: {os.environ.get('KNOWLEDGE_FEDERATION_STORAGE', default_storage):<40}  ║
╚══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
