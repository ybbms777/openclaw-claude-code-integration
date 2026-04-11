#!/usr/bin/env python3
"""
hook_integration.py — OpenClaw 2.0 钩子系统集成 (v2026.4.x 兼容)

官方 Hook 接口（v2026.4.5+）：
- before_tool_call   → { block: true } 阻止, { requireApproval: true } 暂停
- before_install     → { block: true } 阻止
- reply_dispatch     → { handled: true } 终止
- message_sending    → { cancel: true } 终止

用法：
  python3 hook_integration.py --setup    # 生成钩子配置文件
  python3 hook_integration.py --check    # 检查钩子状态
  python3 hook_integration.py --test    # 测试钩子调用
"""

import os
import sys
import json
import time
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum

from skills.shared.logger import get_logger

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# OpenClaw 2.0 官方钩子类型
# ═══════════════════════════════════════════════════════════════════════════

class OpenClawHook(Enum):
    """OpenClaw 2.0 官方钩子 (v2026.4.x)"""
    BEFORE_TOOL_CALL = "before_tool_call"       # 工具调用前
    BEFORE_INSTALL = "before_install"           # 安装前
    REPLY_DISPATCH = "reply_dispatch"          # 回复分发
    MESSAGE_SENDING = "message_sending"         # 消息发送


@dataclass
class HookResponse:
    """OpenClaw 钩子响应格式"""
    block: bool = False                    # 阻止操作
    requireApproval: bool = False           # 请求用户确认
    handled: bool = False                  # 已处理（终止传播）
    cancel: bool = False                   # 取消操作
    modified: bool = False                # 是否修改了上下文
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallContext:
    """before_tool_call 上下文"""
    tool: str                              # 工具名
    args: Dict[str, Any]                   # 工具参数
    session_id: str = ""
    agent_id: str = ""
    timestamp: str = ""


@dataclass
class InstallContext:
    """before_install 上下文"""
    package: str                            # 包名
    source: str = ""                       # 来源


# ═══════════════════════════════════════════════════════════════════════════
# 知识联邦钩子处理器
# ═══════════════════════════════════════════════════════════════════════════

class KnowledgeFederationHookHandler:
    """知识联邦钩子处理器基类"""

    def __init__(self, priority: int = 100):
        self.priority = priority
        self.enabled = True

    async def handle(self, context: Any) -> HookResponse:
        """处理钩子，返回 OpenClaw 格式响应"""
        return HookResponse()


class BeforeToolCallHandler(KnowledgeFederationHookHandler):
    """before_tool_call 钩子处理器

    官方接口：返回 { block: true } 或 { requireApproval: true }
    """

    def __init__(self, knowledge_fed=None, fusion_engine=None, rule_optimizer=None):
        super().__init__(priority=100)
        self.knowledge_fed = knowledge_fed
        self.fusion_engine = fusion_engine
        self.rule_optimizer = rule_optimizer

    async def handle(self, context: ToolCallContext) -> HookResponse:
        """工具调用决策"""
        response = HookResponse()

        # 1. 检查危险命令模式
        dangerous_patterns = [
            (r"rm\s+-rf", "危险删除操作"),
            (r"chmod\s+777", "高危权限设置"),
            (r"git\s+push\s+--force", "强制推送"),
            (r">\s*/dev/sd", "直接写入磁盘设备"),
        ]

        for pattern, reason in dangerous_patterns:
            import re
            if context.tool == "bash" and "args" in context.args:
                command = context.args.get("command", "")
                if re.search(pattern, command, re.IGNORECASE):
                    logger.warning(f"检测到危险命令: {reason}")
                    response.requireApproval = True
                    response.metadata["reason"] = reason
                    response.metadata["command"] = command[:100]
                    return response

        # 2. 获取适用的社群规则
        if self.knowledge_fed:
            try:
                community_rules = self.knowledge_fed.subscribe_community_rules(
                    filters={"min_score": 75}
                )
                if community_rules:
                    response.metadata["community_rules_count"] = len(community_rules)
                    response.metadata["top_rule_score"] = community_rules[0].leaderboard_score if community_rules else 0
            except Exception as e:
                logger.warning(f"获取社群规则失败: {e}")

        # 3. 融合引擎评估
        if self.fusion_engine:
            try:
                if context.tool == "bash" and "args" in context.args:
                    command = context.args.get("command", "")
                    fusion_result = self.fusion_engine.fuse_decision_context(
                        context.tool,
                        context.args
                    )
                    response.metadata["fusion_score"] = fusion_result.score if hasattr(fusion_result, 'score') else 0
                    response.metadata["fusion_decision"] = fusion_result.decision if hasattr(fusion_result, 'decision') else "allow"

                    # 根据融合决策设置响应
                    if fusion_result.decision == "block":
                        response.block = True
                        return response
                    elif fusion_result.decision == "request_confirm":
                        response.requireApproval = True
                        return response
            except Exception as e:
                logger.warning(f"融合引擎评估失败: {e}")

        # 默认：允许执行
        response.block = False
        response.requireApproval = False
        return response


class BeforeInstallHandler(KnowledgeFederationHookHandler):
    """before_install 钩子处理器

    官方接口：返回 { block: true } 阻止安装
    """

    def __init__(self):
        super().__init__(priority=50)

    async def handle(self, context: InstallContext) -> HookResponse:
        """安装前检查"""
        response = HookResponse()

        # 检查恶意包
        malicious_packages = [
            "system-attack",
            "credential-stealer",
            "cryptominer",
        ]

        for pkg in malicious_packages:
            if pkg in context.package.lower():
                logger.error(f"检测到恶意包: {context.package}")
                response.block = True
                response.metadata["reason"] = f"恶意包: {pkg}"
                return response

        # 检查未批准的包（需要用户确认）
        unapproved_sources = ["npm-untrusted", "pip-unverified"]
        for source in unapproved_sources:
            if source in context.source.lower():
                response.requireApproval = True
                response.metadata["reason"] = f"未验证来源: {context.source}"
                return response

        return response


class ReplyDispatchHandler(KnowledgeFederationHookHandler):
    """reply_dispatch 钩子处理器

    官方接口：返回 { handled: true } 终止传播
    """

    def __init__(self, knowledge_fed=None):
        super().__init__(priority=75)
        self.knowledge_fed = knowledge_fed

    async def handle(self, context: Any) -> HookResponse:
        """回复分发处理"""
        response = HookResponse()

        if not self.knowledge_fed:
            return response

        # 检查是否需要拦截重复回复
        try:
            # 这里可以实现重复回复检测逻辑
            pass
        except Exception as e:
            logger.warning(f"回复处理失败: {e}")

        return response


class MessageSendingHandler(KnowledgeFederationHookHandler):
    """message_sending 钩子处理器

    官方接口：返回 { cancel: true } 取消发送
    """

    def __init__(self):
        super().__init__(priority=80)

    async def handle(self, context: Any) -> HookResponse:
        """消息发送前检查"""
        response = HookResponse()

        # 检查敏感内容
        sensitive_patterns = [
            (r"api[_-]?key", "API密钥"),
            (r"password", "密码"),
            (r"secret", "密钥"),
            (r"token", "令牌"),
        ]

        message = context.get("message", "") if isinstance(context, dict) else str(context)

        for pattern, reason in sensitive_patterns:
            import re
            if re.search(pattern, message, re.IGNORECASE):
                logger.warning(f"检测到敏感内容: {reason}")
                response.requireApproval = True
                response.metadata["reason"] = f"包含敏感信息: {reason}"
                return response

        return response


# ═══════════════════════════════════════════════════════════════════════════
# 钩子调度器
# ═══════════════════════════════════════════════════════════════════════════

class HookDispatcher:
    """OpenClaw 2.0 钩子调度器"""

    def __init__(self):
        self.handlers: Dict[OpenClawHook, List[KnowledgeFederationHookHandler]] = {
            OpenClawHook.BEFORE_TOOL_CALL: [],
            OpenClawHook.BEFORE_INSTALL: [],
            OpenClawHook.REPLY_DISPATCH: [],
            OpenClawHook.MESSAGE_SENDING: [],
        }
        self.call_log: List[Dict] = []

    def register(self, hook: OpenClawHook, handler: KnowledgeFederationHookHandler) -> None:
        """注册钩子处理器"""
        self.handlers[hook].append(handler)
        self.handlers[hook].sort(key=lambda h: h.priority, reverse=True)
        logger.info(f"注册钩子处理器: {hook.value} -> {type(handler).__name__}")

    def unregister(self, hook: OpenClawHook, handler: KnowledgeFederationHookHandler) -> None:
        """注销钩子处理器"""
        if handler in self.handlers[hook]:
            self.handlers[hook].remove(handler)
            logger.info(f"注销钩子处理器: {hook.value} -> {type(handler).__name__}")

    async def dispatch(self, hook: OpenClawHook, context: Any) -> HookResponse:
        """调度钩子并返回 OpenClaw 格式响应"""
        handlers = self.handlers.get(hook, [])
        if not handlers:
            return HookResponse()

        response = HookResponse()
        for handler in handlers:
            if not handler.enabled:
                continue

            try:
                result = await handler.handle(context)
                if result.block or result.requireApproval or result.handled or result.cancel:
                    return result
                # 合并 metadata
                if result.metadata:
                    response.metadata.update(result.metadata)
            except Exception as e:
                logger.error(f"钩子 {hook.value} 执行失败: {e}")

        # 记录调用
        self.call_log.append({
            "hook": hook.value,
            "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        })

        return response

    def get_statistics(self) -> Dict:
        """获取钩子调用统计"""
        return {
            "total_calls": len(self.call_log),
            "by_type": self._count_by_type(),
            "handlers": {h.value: len(handlers) for h, handlers in self.handlers.items()},
        }

    def _count_by_type(self) -> Dict[str, int]:
        counts = {}
        for log in self.call_log:
            h = log["hook"]
            counts[h] = counts.get(h, 0) + 1
        return counts


# ═══════════════════════════════════════════════════════════════════════════
# OpenClaw 插件配置生成器
# ═══════════════════════════════════════════════════════════════════════════

def generate_openclaw_plugin_config(central_api: str = None) -> Dict:
    """生成 OpenClaw 2.0 插件配置 (manifest.json)"""

    workspace = Path.home() / ".openclaw" / "workspace"
    plugin_dir = workspace / "plugins" / "knowledge-federation"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": "knowledge-federation",
        "version": "2.0.0",
        "description": "跨Agent知识联邦与规则共享系统",
        "author": "OpenClaw Community",
        "hooks": {
            "before_tool_call": "hooks/before_tool_call.py",
            "before_install": "hooks/before_install.py",
            "reply_dispatch": "hooks/reply_dispatch.py",
            "message_sending": "hooks/message_sending.py",
        },
        "permissions": [
            "tool:call",
            "memory:read",
            "memory:write",
            "network:fetch",
        ],
        "environment": {
            "KNOWLEDGE_FEDERATION_API": central_api or "",
        },
    }

    return manifest, plugin_dir


def generate_hook_script(hook: OpenClawHook, output_path: Path, central_api: str = None) -> None:
    """生成 OpenClaw 2.0 钩子脚本"""

    workspace = Path.home() / ".openclaw" / "workspace"

    if hook == OpenClawHook.BEFORE_TOOL_CALL:
        content = f'''#!/usr/bin/env python3
"""before_tool_call.py - OpenClaw before_tool_call hook

官方接口: 返回 {{ block: true }} 阻止, {{ requireApproval: true }} 暂停
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from skills.knowledge_federation.scripts.hook_integration import (
    HookDispatcher, OpenClawHook, BeforeToolCallHandler, ToolCallContext, HookResponse
)
from skills.fusion_engine.scripts.fusion_engine import MultiSourceFusionEngine
from skills.rule_optimizer.scripts.rule_optimizer import RuleOptimizer
from skills.knowledge_federation.scripts.knowledge_federation import KnowledgeFederation
from datetime import datetime, timezone, timedelta

async def main():
    data = json.loads(sys.stdin.read())

    # 构建上下文
    context = ToolCallContext(
        tool=data.get("tool", ""),
        args=data.get("args", {{}}),
        session_id=data.get("sessionId", "unknown"),
        agent_id=data.get("agentId", "unknown"),
        timestamp=datetime.now(timezone(timedelta(hours=8))).isoformat(),
    )

    # 初始化组件
    central_api = "{central_api}" or data.get("KNOWLEDGE_FEDERATION_API")

    fusion = MultiSourceFusionEngine()
    optimizer = RuleOptimizer()
    fed = KnowledgeFederation(workspace_dir=str(Path.home() / ".openclaw" / "workspace"), central_api=central_api)

    # 创建调度器
    dispatcher = HookDispatcher()
    dispatcher.register(OpenClawHook.BEFORE_TOOL_CALL, BeforeToolCallHandler(
        knowledge_fed=fed,
        fusion_engine=fusion,
        rule_optimizer=optimizer,
    ))

    # 执行钩子
    response = await dispatcher.dispatch(OpenClawHook.BEFORE_TOOL_CALL, context)

    # 输出 OpenClaw 格式响应
    output = {{
        "block": response.block,
        "requireApproval": response.requireApproval,
        "metadata": response.metadata,
    }}

    print(json.dumps(output, ensure_ascii=False))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
'''
    elif hook == OpenClawHook.BEFORE_INSTALL:
        content = f'''#!/usr/bin/env python3
"""before_install.py - OpenClaw before_install hook"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from skills.knowledge_federation.scripts.hook_integration import (
    HookDispatcher, OpenClawHook, BeforeInstallHandler, InstallContext
)

async def main():
    data = json.loads(sys.stdin.read())

    context = InstallContext(
        package=data.get("package", ""),
        source=data.get("source", ""),
    )

    dispatcher = HookDispatcher()
    dispatcher.register(OpenClawHook.BEFORE_INSTALL, BeforeInstallHandler())

    response = await dispatcher.dispatch(OpenClawHook.BEFORE_INSTALL, context)

    print(json.dumps({{"block": response.block, "metadata": response.metadata}}, ensure_ascii=False))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
'''
    elif hook == OpenClawHook.REPLY_DISPATCH:
        content = f'''#!/usr/bin/env python3
"""reply_dispatch.py - OpenClaw reply_dispatch hook"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from skills.knowledge_federation.scripts.hook_integration import (
    HookDispatcher, OpenClawHook, ReplyDispatchHandler
)

async def main():
    data = json.loads(sys.stdin.read())

    fed = None
    try:
        from skills.knowledge_federation.scripts.knowledge_federation import KnowledgeFederation
        fed = KnowledgeFederation(workspace_dir=str(Path.home() / ".openclaw" / "workspace"))
    except Exception:
        pass

    dispatcher = HookDispatcher()
    dispatcher.register(OpenClawHook.REPLY_DISPATCH, ReplyDispatchHandler(knowledge_fed=fed))

    response = await dispatcher.dispatch(OpenClawHook.REPLY_DISPATCH, data)

    print(json.dumps({{"handled": response.handled, "metadata": response.metadata}}, ensure_ascii=False))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
'''
    elif hook == OpenClawHook.MESSAGE_SENDING:
        content = f'''#!/usr/bin/env python3
"""message_sending.py - OpenClaw message_sending hook"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from skills.knowledge_federation.scripts.hook_integration import (
    HookDispatcher, OpenClawHook, MessageSendingHandler
)

async def main():
    data = json.loads(sys.stdin.read())

    dispatcher = HookDispatcher()
    dispatcher.register(OpenClawHook.MESSAGE_SENDING, MessageSendingHandler())

    response = await dispatcher.dispatch(OpenClawHook.MESSAGE_SENDING, data)

    print(json.dumps({{"cancel": response.cancel, "requireApproval": response.requireApproval, "metadata": response.metadata}}, ensure_ascii=False))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
'''
    else:
        content = f'''#!/usr/bin/env python3
"""hook.py - OpenClaw hook"""
import json
import sys

def main():
    data = json.loads(sys.stdin.read())
    print(json.dumps({{"status": "ok"}}, ensure_ascii=False))

if __name__ == "__main__":
    main()
'''

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    output_path.chmod(0o755)


# ═══════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="OpenClaw 2.0 钩子集成 (v2026.4.x)")
    parser.add_argument("--setup", action="store_true", help="生成插件配置")
    parser.add_argument("--check", action="store_true", help="检查钩子状态")
    parser.add_argument("--test", action="store_true", help="测试钩子调用")
    parser.add_argument("--central-api", help="中央API地址")
    args = parser.parse_args()

    if args.setup:
        manifest, plugin_dir = generate_openclaw_plugin_config(args.central_api)

        # 保存 manifest
        manifest_file = plugin_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        print(f"✅ 插件配置已生成: {manifest_file}")

        # 生成钩子脚本
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        for hook in OpenClawHook:
            script_path = hooks_dir / f"{hook.value}.py"
            generate_hook_script(hook, script_path, args.central_api)
            print(f"✅ 钩子脚本已生成: {script_path}")

        print("\n📝 下一步:")
        print("1. 将插件目录复制到 ~/.openclaw/plugins/knowledge-federation/")
        print("2. 运行 openclaw doctor --fix 进行迁移")
        print("3. 使用 --check 验证钩子状态")

    elif args.check:
        workspace = Path.home() / ".openclaw" / "workspace"
        plugin_dir = workspace / "plugins" / "knowledge-federation"
        manifest_file = plugin_dir / "manifest.json"

        if not manifest_file.exists():
            print("❌ 插件未配置，请先运行 --setup")
            sys.exit(1)

        manifest = json.loads(manifest_file.read_text())
        print("✅ OpenClaw 2.0 插件配置:")
        print(json.dumps(manifest, indent=2, ensure_ascii=False))

    elif args.test:
        print("🧪 测试 OpenClaw 2.0 钩子调用...")

        dispatcher = HookDispatcher()
        dispatcher.register(OpenClawHook.BEFORE_TOOL_CALL, BeforeToolCallHandler())

        import asyncio

        async def run_test():
            context = ToolCallContext(
                tool="bash",
                args={"command": "ls -la"},
                session_id="test_session",
                agent_id="test_agent",
                timestamp=datetime.now(timezone(timedelta(hours=8))).isoformat(),
            )

            response = await dispatcher.dispatch(OpenClawHook.BEFORE_TOOL_CALL, context)
            print(f"✅ before_tool_call 响应: block={response.block}, requireApproval={response.requireApproval}")

            print(f"📊 钩子统计: {dispatcher.get_statistics()}")

        asyncio.run(run_test())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()