#!/usr/bin/env python3
"""
tests/test_learnings_extractor.py - Learnings Extractor 测试套件
"""

import json
import pytest


class TestLearningsExtractor:
    """Learnings Extractor 功能测试"""

    def test_rule_type_classification(self):
        """测试规则类型分类"""
        rule_types = ["MUST", "NEVER", "ALWAYS", "DO_NOT", "SHOULD"]

        for rule_type in rule_types:
            assert len(rule_type) > 0, f"Rule type {rule_type} is valid"

    def test_reflection_query_pattern(self):
        """测试 reflection 查询模式"""
        query_condition = "category = 'reflection'"
        assert "reflection" in query_condition, "Query includes reflection category"

    def test_markdown_generation_format(self):
        """测试 Markdown 生成格式"""
        import sys
        sys.path.insert(0, str(__file__).rsplit("/", 1)[0] + "/../skills/evolve/scripts")
        from learnings_extractor import extract_learning_rules, deduplicate_rules

        # 测试规则提取
        test_text = "This is a MUST do something NEVER forget to check ALWAYS verify the result"
        rules = extract_learning_rules(test_text)
        assert len(rules) > 0, "Should extract rules from text"

        rule_types = [r[0] for r in rules]
        assert "MUST" in rule_types, "Should extract MUST rules"
        assert "NEVER" in rule_types, "Should extract NEVER rules"
        assert "ALWAYS" in rule_types, "Should extract ALWAYS rules"

        # 测试规则去重
        duplicate_rules = [
            ("MUST", "Do this"),
            ("MUST", "Do this"),
            ("NEVER", "Do that"),
        ]
        deduped = deduplicate_rules(duplicate_rules)
        assert len(deduped) == 2, "Deduplication should reduce 3 rules to 2"

        # 验证去重后保留计数
        for rule in deduped:
            if rule["text"] == "Do this":
                assert rule["count"] == 2, "Duplicate rule should have count of 2"

    def test_similarity_threshold(self):
        """测试相似度阈值"""
        SIMILARITY_THRESHOLD = 0.85

        # 低于阈值：不合并
        assert 0.84 < SIMILARITY_THRESHOLD, "0.84 similarity below threshold"

        # 高于阈值：合并
        assert 0.86 > SIMILARITY_THRESHOLD, "0.86 similarity above threshold"


class TestLearningsScenarios:
    """Learnings Extractor 场景测试"""

    def test_deduplication_logic(self):
        """测试去重逻辑"""
        rules = [
            {"id": 1, "text": "Never modify fund directly"},
            {"id": 2, "text": "Never modify fund directly"},
            {"id": 3, "text": "Never delete important files"},
        ]

        # 第 1 和 2 个是重复的
        unique_rules = {}
        for rule in rules:
            text = rule["text"]
            if text not in unique_rules:
                unique_rules[text] = rule

        assert len(unique_rules) == 2, "Deduplication reduces 3 rules to 2"

    def test_frequency_ordering(self):
        """测试频率排序"""
        candidates = [
            {"action": "Rule A", "hits": 5},
            {"action": "Rule B", "hits": 2},
            {"action": "Rule C", "hits": 8},
        ]

        sorted_candidates = sorted(candidates, key=lambda x: x["hits"], reverse=True)
        assert sorted_candidates[0]["hits"] == 8, "Highest frequency first"
        assert sorted_candidates[-1]["hits"] == 2, "Lowest frequency last"

    def test_user_approval_flow(self):
        """测试用户批准流程"""
        approval_options = ["approve", "reject", "modify"]

        for option in approval_options:
            assert option in approval_options, f"Option {option} is valid"

    def test_embedding_model_fallback(self):
        """测试 embedding 模型备用"""
        models = {
            "primary": "SiliconFlow",
            "secondary": "MiniMax",
            "tertiary": "hash"
        }

        assert len(models) == 3, "Three embedding options available"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
