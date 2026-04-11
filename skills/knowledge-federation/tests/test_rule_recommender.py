#!/usr/bin/env python3
"""
test_rule_recommender.py - 规则推荐引擎测试
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path

from skills.knowledge_federation.scripts.rule_recommender import (
    ProjectAnalyzer, ProjectProfile, RuleRecommender,
    MultiDimensionalLeaderboard, VersionRollbackManager,
    RecommendationCandidate, PROJECT_TYPES,
)


class TestProjectAnalyzer:
    """项目分析器测试"""

    def test_analyze_python_project(self, tmp_path):
        """测试分析Python项目"""
        # 创建Python项目结构
        (tmp_path / "requirements.txt").touch()
        (tmp_path / "setup.py").touch()
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()

        analyzer = ProjectAnalyzer(str(tmp_path))
        profile = analyzer.analyze()

        assert profile.project_type in ["python", "web", "api"]
        assert len(profile.detected_tags) > 0
        assert "python" in profile.language_hints or "setup.py" in profile.language_hints

    def test_analyze_javascript_project(self, tmp_path):
        """测试分析JavaScript项目"""
        # 创建JS项目结构
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "node_modules").mkdir()

        analyzer = ProjectAnalyzer(str(tmp_path))
        profile = analyzer.analyze()

        assert profile.project_type == "javascript"
        assert "frontend" in profile.detected_tags or "javascript" in profile.detected_tags

    def test_analyze_bdx_project(self, tmp_path):
        """测试分析BDX项目"""
        # 创建BDX项目结构
        (tmp_path / "main.py").write_text('import akshare')
        (tmp_path / "回测.py").touch()

        analyzer = ProjectAnalyzer(str(tmp_path))
        profile = analyzer.analyze()

        assert profile.project_type == "bdx"
        assert profile.confidence > 0.3

    def test_analyze_empty_directory(self, tmp_path):
        """测试分析空目录"""
        analyzer = ProjectAnalyzer(str(tmp_path))
        profile = analyzer.analyze()

        assert profile.project_type == "unknown"
        assert profile.confidence == 0.0


class TestRuleRecommender:
    """规则推荐器测试"""

    def test_calculate_match_tag_overlap(self):
        """测试标签匹配计算"""
        recommender = RuleRecommender()

        rule = {
            "rule_id": "test_rule",
            "versions": [{
                "version_id": "v1",
                "tags": ["python", "security"],
                "content": {},
                "effectiveness_score": 85.0,
            }],
            "project_tags": ["python", "security"],
            "adoption_count": 10,
        }

        profile = ProjectProfile(
            project_type="python",
            confidence=0.8,
            detected_tags=["python", "backend"],
            language_hints=["python"],
            structure_hints=["src"],
        )

        result = recommender._calculate_match(rule, profile)

        assert result["score"] > 0
        assert len(result["reasons"]) > 0

    def test_calculate_match_bdx_special(self):
        """测试BDX特殊加权"""
        recommender = RuleRecommender()

        rule = {
            "rule_id": "bdx_strategy",
            "versions": [{
                "version_id": "v1",
                "tags": ["量化", "finance"],
                "content": {"strategy": "momentum"},
                "effectiveness_score": 90.0,
            }],
            "project_tags": ["量化", "finance"],
            "adoption_count": 5,
        }

        profile = ProjectProfile(
            project_type="bdx",
            confidence=0.9,
            detected_tags=["量化", "finance"],
            language_hints=["python"],
            structure_hints=["回测"],
        )

        result = recommender._calculate_match(rule, profile)

        assert "BDX/量化专属规则" in result["reasons"]

    def test_recommend_filters_low_score(self):
        """测试最低分数过滤"""
        recommender = RuleRecommender()

        profile = ProjectProfile(
            project_type="python",
            confidence=0.8,
            detected_tags=["python"],
            language_hints=[],
            structure_hints=[],
        )

        rules = [
            {
                "rule_id": "high_score",
                "versions": [{"tags": ["python"], "effectiveness_score": 90.0}],
                "project_tags": ["python"],
                "adoption_count": 10,
                "leaderboard_score": 90.0,
            },
            {
                "rule_id": "low_score",
                "versions": [{"tags": ["python"], "effectiveness_score": 20.0}],
                "project_tags": ["python"],
                "adoption_count": 1,
                "leaderboard_score": 20.0,
            },
        ]

        candidates = recommender.recommend(profile, rules, top_k=10, min_score=0.5)

        assert len(candidates) == 1
        assert candidates[0].rule_id == "high_score"

    def test_recommend_top_k(self):
        """测试返回数量限制"""
        recommender = RuleRecommender()

        profile = ProjectProfile(
            project_type="python",
            confidence=0.8,
            detected_tags=["python"],
            language_hints=[],
            structure_hints=[],
        )

        rules = [
            {
                "rule_id": f"rule_{i}",
                "versions": [{"tags": ["python"], "effectiveness_score": 70 + i}],
                "project_tags": ["python"],
                "adoption_count": 10,
                "leaderboard_score": 70 + i,
            }
            for i in range(20)
        ]

        candidates = recommender.recommend(profile, rules, top_k=5, min_score=0.1)

        assert len(candidates) == 5


class TestMultiDimensionalLeaderboard:
    """多维度排行榜测试"""

    def test_add_rule(self):
        """测试添加规则"""
        board = MultiDimensionalLeaderboard()

        rule = {
            "rule_id": "test_rule",
            "versions": [{"effectiveness_score": 85.0}],
            "project_tags": ["python"],
            "adoption_count": 10,
            "leaderboard_score": 85.0,
        }

        board.add_rule(rule)

        assert "test_rule" in board.rules

    def test_sort_overall(self):
        """测试综合排序"""
        board = MultiDimensionalLeaderboard()

        for i in range(5):
            rule = {
                "rule_id": f"rule_{i}",
                "versions": [{"effectiveness_score": 70 + i * 5}],
                "project_tags": ["python"],
                "adoption_count": 10 + i,
                "leaderboard_score": 70 + i * 5,
            }
            board.add_rule(rule)

        results = board.get_leaderboard(dimension="overall", limit=3)

        assert len(results) == 3
        # rule_4 应该排第一（最高分）
        assert results[0]["rule_id"] == "rule_4"

    def test_sort_by_tag(self):
        """测试按标签排序"""
        board = MultiDimensionalLeaderboard()

        rules = [
            {
                "rule_id": "python_rule",
                "versions": [{"tags": ["python"], "effectiveness_score": 80.0}],
                "project_tags": ["python"],
                "adoption_count": 10,
                "leaderboard_score": 80.0,
            },
            {
                "rule_id": "js_rule",
                "versions": [{"tags": ["javascript"], "effectiveness_score": 90.0}],
                "project_tags": ["javascript"],
                "adoption_count": 5,
                "leaderboard_score": 90.0,
            },
        ]

        for r in rules:
            board.add_rule(r)

        results = board.get_leaderboard(dimension="by_tag", filters={"tag": "python"}, limit=10)

        assert len(results) == 1
        assert results[0]["rule_id"] == "python_rule"

    def test_filter_min_score(self):
        """测试最低分数过滤"""
        board = MultiDimensionalLeaderboard()

        for i in range(5):
            rule = {
                "rule_id": f"rule_{i}",
                "versions": [{"effectiveness_score": 60 + i * 10}],
                "project_tags": ["python"],
                "adoption_count": 10,
                "leaderboard_score": 60 + i * 10,
            }
            board.add_rule(rule)

        results = board.get_leaderboard(
            dimension="overall",
            filters={"min_score": 75},
            limit=10
        )

        assert all(r.get("leaderboard_score", 0) >= 75 for r in results)


class TestVersionRollbackManager:
    """版本回滚管理器测试"""

    def test_snapshot_rule(self, tmp_path):
        """测试规则快照"""
        manager = VersionRollbackManager(str(tmp_path))

        version = {
            "version_id": "v1",
            "rule_id": "test_rule",
            "content": {"action": "test"},
            "effectiveness_score": 85.0,
        }

        snapshot_id = manager.snapshot_rule("test_rule", version)

        assert snapshot_id.startswith("test_rule_v1_")
        assert (manager.versions_dir / f"{snapshot_id}.json").exists()

    def test_rollback_to(self, tmp_path):
        """测试回滚到指定版本"""
        manager = VersionRollbackManager(str(tmp_path))

        version = {
            "version_id": "v1",
            "rule_id": "test_rule",
            "content": {"action": "test_v1"},
            "effectiveness_score": 85.0,
        }

        snapshot_id = manager.snapshot_rule("test_rule", version)
        result = manager.rollback_to("test_rule", "v1")

        assert result is not None
        assert result["content"]["action"] == "test_v1"

    def test_rollback_not_found(self, tmp_path):
        """测试回滚不存在的版本"""
        manager = VersionRollbackManager(str(tmp_path))

        result = manager.rollback_to("nonexistent", "v1")

        assert result is None

    def test_get_available_versions(self, tmp_path):
        """测试获取可用版本"""
        manager = VersionRollbackManager(str(tmp_path))

        # 创建多个版本
        for i in range(3):
            version = {
                "version_id": f"v{i}",
                "rule_id": "test_rule",
                "content": {"action": f"test_v{i}"},
                "effectiveness_score": 70 + i * 5,
            }
            manager.snapshot_rule("test_rule", version)

        versions = manager.get_available_versions("test_rule")

        assert len(versions) == 3
        # 按时间倒序
        assert versions[0]["version_id"] == "v2"

    def test_get_rollback_history(self, tmp_path):
        """测试获取回滚历史"""
        manager = VersionRollbackManager(str(tmp_path))

        # 创建快照并回滚
        version = {
            "version_id": "v1",
            "rule_id": "test_rule",
            "content": {"action": "test"},
            "effectiveness_score": 85.0,
        }
        manager.snapshot_rule("test_rule", version)
        manager.rollback_to("test_rule", "v1")

        history = manager.get_rollback_history()

        assert len(history) == 1
        assert history[0]["rule_id"] == "test_rule"
        assert history[0]["target_version_id"] == "v1"


class TestProjectTypes:
    """项目类型定义测试"""

    def test_project_types_has_required_fields(self):
        """测试项目类型定义完整性"""
        required_fields = ["keywords", "tags", "weight"]

        for ptype, spec in PROJECT_TYPES.items():
            for field in required_fields:
                assert field in spec, f"{ptype} missing {field}"

    def test_bdx_has_high_weight(self):
        """测试BDX类型有权重加成"""
        assert PROJECT_TYPES["bdx"]["weight"] == 2.0

    def test_all_types_have_tags(self):
        """测试所有类型都有标签"""
        for ptype, spec in PROJECT_TYPES.items():
            assert len(spec["tags"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])