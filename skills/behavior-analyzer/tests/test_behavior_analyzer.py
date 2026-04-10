#!/usr/bin/env python3
"""
行为分析引擎的单元测试
"""

import json
import sys
import tempfile
from pathlib import Path
from datetime import datetime
import pytest

# 添加scripts目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from behavior_analyzer import SessionBehaviorAnalyzer, BehaviorMetrics


@pytest.fixture
def temp_workspace():
    """创建临时工作空间"""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # 创建必要的目录
        (workspace / "agents" / "main" / "sessions").mkdir(parents=True)
        (workspace / "memory" / "lancedb-pro").mkdir(parents=True)
        (workspace / "skills" / "compact-guardian").mkdir(parents=True)

        yield workspace


class TestBehaviorAnalyzer:
    """行为分析器测试"""

    def test_init(self, temp_workspace):
        """测试初始化"""
        analyzer = SessionBehaviorAnalyzer(str(temp_workspace))
        assert analyzer.workspace == temp_workspace
        assert analyzer.behavior_log.exists()

    def test_analyze_session_healthy(self, temp_workspace):
        """测试分析健康的会话"""
        analyzer = SessionBehaviorAnalyzer(str(temp_workspace))
        metrics = analyzer.analyze_session("test_session_1")

        assert isinstance(metrics, BehaviorMetrics)
        assert 0 <= metrics.health_score <= 100
        assert metrics.warning_level in ["none", "warning", "critical"]
        assert isinstance(metrics.anomaly_patterns, list)
        assert isinstance(metrics.recommended_actions, list)

    def test_detect_error_patterns(self, temp_workspace):
        """测试重复犯错检测"""
        analyzer = SessionBehaviorAnalyzer(str(temp_workspace))

        # 创建一个有多个错误的日志
        reflection_log = temp_workspace / ".self-eval-reflections.jsonl"
        with open(reflection_log, 'w') as f:
            for i in range(4):
                record = {
                    "session_id": "test_error_session",
                    "category": "用户纠正",
                    "timestamp": datetime.now().isoformat()
                }
                f.write(json.dumps(record) + '\n')

        score, anomalies = analyzer._detect_error_patterns("test_error_session")
        assert score < 100
        assert any("重复犯错" in a for a in anomalies)

    def test_safe_error_handling(self, temp_workspace):
        """测试错误处理的安全性"""
        analyzer = SessionBehaviorAnalyzer(str(temp_workspace))

        # 即使文件不存在，也应该返回默认值
        score, anomalies = analyzer._detect_error_patterns("nonexistent_session")
        assert score == 100.0
        assert anomalies == []

    def test_health_score_calculation(self, temp_workspace):
        """测试健康分数计算"""
        analyzer = SessionBehaviorAnalyzer(str(temp_workspace))

        # 测试满分
        health = analyzer._calculate_health_score(100, 100, 100, 100)
        assert health == 100.0

        # 测试各个维度的影响
        health = analyzer._calculate_health_score(0, 100, 100, 100)
        assert 30 < health < 70  # 错误占40%权重

    def test_save_metrics(self, temp_workspace):
        """测试保存指标"""
        analyzer = SessionBehaviorAnalyzer(str(temp_workspace))

        metrics = BehaviorMetrics(
            health_score=85.5,
            anomaly_patterns=["test_anomaly"],
            quality_trend="improving",
            warning_level="none",
            recommended_actions=["test_action"],
            session_id="test_save_session",
            timestamp=datetime.now().isoformat(),
            details={}
        )

        analyzer.save_metrics(metrics)

        history_file = temp_workspace / ".behavior-analytics" / "test_save_session_history.json"
        assert history_file.exists()

        with open(history_file, 'r') as f:
            history = json.load(f)
            assert len(history) == 1
            assert history[0]["health_score"] == 85.5

    def test_warning_level_determination(self, temp_workspace):
        """测试警告等级判定"""
        analyzer = SessionBehaviorAnalyzer(str(temp_workspace))

        # 无异常
        level = analyzer._determine_warning_level(90, [])
        assert level == "none"

        # 一个异常但高分数 → none
        level = analyzer._determine_warning_level(60, ["anomaly1"])
        assert level == "none"

        # 一个异常且低分数 → warning
        level = analyzer._determine_warning_level(45, ["anomaly1"])
        assert level == "warning"

        # 多个异常 → warning
        level = analyzer._determine_warning_level(60, ["a1", "a2"])
        assert level == "warning"

        # 多个异常且超低分 → critical
        level = analyzer._determine_warning_level(15, ["a1", "a2", "a3"])
        assert level == "critical"

    def test_recommendations_generation(self, temp_workspace):
        """测试建议生成"""
        analyzer = SessionBehaviorAnalyzer(str(temp_workspace))

        # 测试严重异常的建议
        recommendations = analyzer._generate_recommendations(
            15, ["critical_anomaly"], "critical"
        )
        assert any("暂停" in r for r in recommendations)

        # 测试健康状态的建议
        recommendations = analyzer._generate_recommendations(
            85, [], "none"
        )
        assert any("良好" in r or "继续" in r for r in recommendations)


class TestBehaviorMetrics:
    """行为指标数据类测试"""

    def test_metrics_creation(self):
        """测试指标对象创建"""
        metrics = BehaviorMetrics(
            health_score=75.0,
            anomaly_patterns=["pattern1"],
            quality_trend="stable",
            warning_level="warning",
            recommended_actions=["action1"],
            session_id="test",
            timestamp="2026-04-11T10:00:00",
            details={"key": "value"}
        )

        assert metrics.health_score == 75.0
        assert len(metrics.anomaly_patterns) == 1
        assert metrics.session_id == "test"

    def test_metrics_to_dict(self):
        """测试指标转换为字典"""
        from dataclasses import asdict

        metrics = BehaviorMetrics(
            health_score=80.0,
            anomaly_patterns=[],
            quality_trend="improving",
            warning_level="none",
            recommended_actions=[],
            session_id="test",
            timestamp="2026-04-11T10:00:00",
            details={}
        )

        d = asdict(metrics)
        assert isinstance(d, dict)
        assert d["health_score"] == 80.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
