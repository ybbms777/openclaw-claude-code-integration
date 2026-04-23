"""Compatibility package for hyphenated skill directories."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent

ALIASES = {
    "behavior_analyzer": "behavior-analyzer",
    "cache_monitor": "cache-monitor",
    "compact_guardian": "compact-guardian",
    "fusion_engine": "fusion-engine",
    "knowledge_federation": "knowledge-federation",
    "memory_compaction": "memory-compaction",
    "rule_optimizer": "rule-optimizer",
    "safe_command_execution": "safe-command-execution",
    "self_eval": "self-eval",
    "smart_compact": "smart-compact",
    "yolo_permissions": "yolo-permissions",
}


def _register_package(alias: str, actual: str) -> None:
    package_name = f"{__name__}.{alias}"
    if package_name in sys.modules:
        return
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT / actual)]
    sys.modules[package_name] = package

    scripts_name = f"{package_name}.scripts"
    scripts_package = types.ModuleType(scripts_name)
    scripts_package.__path__ = [str(ROOT / actual / "scripts")]
    sys.modules[scripts_name] = scripts_package

    tests_name = f"{package_name}.tests"
    tests_package = types.ModuleType(tests_name)
    tests_package.__path__ = [str(ROOT / actual / "tests")]
    sys.modules[tests_name] = tests_package


for alias_name, actual_name in ALIASES.items():
    _register_package(alias_name, actual_name)

