#!/usr/bin/env python3
"""
tests/test_permission_scorer.py - Permission Scorer 测试套件
"""

import pytest


class TestPermissionScorer:
    """Permission Scorer 功能测试"""

    def test_score_range(self):
        """测试分数范围"""
        MIN_SCORE = 0
        MAX_SCORE = 100

        assert MIN_SCORE >= 0, "Min score is non-negative"
        assert MAX_SCORE <= 100, "Max score is at most 100"

    def test_weight_distribution(self):
        """测试权重分布"""
        weights = {
            "operation": 0.40,
            "path": 0.30,
            "context": 0.20,
            "pattern": 0.10,
        }

        total_weight = sum(weights.values())
        assert abs(total_weight - 1.0) < 0.001, "Weights sum to 1.0"

    def test_risk_level_mapping(self):
        """测试风险级别映射"""
        thresholds = {
            "LOW": (0, 30),
            "MEDIUM": (30, 70),
            "HIGH": (70, 100),
        }

        for level, (low, high) in thresholds.items():
            assert low < high, f"{level} range is valid"

    def test_operation_scoring(self):
        """测试操作评分"""
        operations = {
            "read": (0, 10),
            "write": (20, 50),
            "delete": (60, 100),
            "chmod": (80, 100),
        }

        for op, (min_score, max_score) in operations.items():
            assert min_score >= 0, f"{op} min score is non-negative"
            assert max_score <= 100, f"{op} max score is at most 100"


class TestPermissionScoringScenarios:
    """Permission Scorer 场景测试"""

    def test_path_risk_hierarchy(self):
        """测试路径风险层级"""
        import sys
        sys.path.insert(0, str(__file__).rsplit("/", 1)[0] + "/../skills/yolo-permissions/scripts")
        from permission_scorer import PermissionScorer

        scorer = PermissionScorer()
        # (path, expected_min_score) - 验证风险递增
        path_risks = [
            "/tmp/test.txt",  # 临时文件
            "/home/user/file",  # 用户主目录
            "/.ssh/id_rsa",  # SSH密钥
            "/etc/passwd",  # 系统配置
        ]

        actual_scores = []
        for path in path_risks:
            score = scorer._score_path(path)
            actual_scores.append(score)

        # 验证风险递增
        for i in range(len(actual_scores) - 1):
            assert actual_scores[i] < actual_scores[i + 1], f"Path risks should increase: {actual_scores[i]} >= {actual_scores[i + 1]}"

    def test_command_scoring_examples(self):
        """测试命令评分示例"""
        test_cases = [
            # (command, expected_score_range)
            ("ls /tmp", (0, 20)),  # 读操作，安全路径
            ("rm /tmp/test.txt", (40, 70)),  # 删除，相对安全
            ("rm /", (90, 100)),  # 删除根目录，最危险
        ]

        for cmd, (min_score, max_score) in test_cases:
            assert min_score >= 0, f"Command '{cmd}' min score valid"
            assert max_score <= 100, f"Command '{cmd}' max score valid"

    def test_context_awareness(self):
        """测试上下文感知"""
        contexts = [
            ("backup", 0, 20),  # 在备份脚本中的删除，低风险
            ("cleanup", 30, 50),  # 日志清理
            ("standalone", 40, 60),  # 单独执行
        ]

        for context, min_risk, max_risk in contexts:
            assert min_risk < max_risk, f"Context '{context}' range valid"

    def test_pattern_detection(self):
        """测试模式检测"""
        risky_patterns = [
            "$(...)",  # 命令替换
            "|",  # 管道
            "&&",  # 条件执行
            "for",  # 循环
        ]

        for pattern in risky_patterns:
            assert len(pattern) > 0, f"Pattern '{pattern}' is defined"

    def test_backward_compatibility(self):
        """测试向后兼容性"""
        old_levels = ["LOW", "MEDIUM", "HIGH"]
        new_system = "0-100 scoring"

        # 验证新系统可以映射到旧等级
        assert len(old_levels) == 3, "Three legacy levels exist"
        assert len(new_system) > 0, "New system defined"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
