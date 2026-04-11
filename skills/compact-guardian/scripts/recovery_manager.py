#!/usr/bin/env python3
"""
recovery_manager.py — 记忆压缩失败恢复管理器

功能：
  1. 记录失败：每次 memory_compaction 异常时调用 record_failure()
  2. 恢复备份：根据失败次数决定是否触发恢复逻辑
  3. 重试计划：失败1-3次用指数退避，第4次熔断
  4. 状态跟踪：failures.json 记录所有尝试和结果

用法：
  python3 recovery_manager.py [--check] [--recover] [--reset]
"""

import os
import sys
import json
import time
import shutil
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from skills.shared.logger import get_logger

logger = get_logger(__name__)

# ─── 配置 ──────────────────────────────────────────────────────────────────

WORKSPACE = Path.home() / ".openclaw" / "workspace"
RECOVERY_DIR = WORKSPACE / ".recovery"
FAILURES_FILE = RECOVERY_DIR / "failures.json"
LANCE_DB_PATH = Path.home() / ".openclaw" / "memory" / "lancedb-pro"
BACKUP_DIR = LANCE_DB_PATH / "backups"

TELEGRAM_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

# 重试策略：失败1-3次时的延迟秒数
RETRY_DELAYS = [0, 300, 1800]  # 0s, 5m, 30m
MAX_FAILURES_BEFORE_CIRCUIT = 4  # 第4次失败触发熔断
CIRCUIT_TRIP_DURATION = 3600  # 熔断持续1小时


# ─── Telegram 通知 ──────────────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    """发送 Telegram 通知"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode()).get("ok", False)
    except urllib.error.HTTPError as e:
        logger.error(f"Telegram HTTP error {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def send_telegram_safe(text: str) -> None:
    """安全的 Telegram 发送（忽略错误）"""
    try:
        send_telegram(text)
    except Exception:
        pass


# ─── 状态管理 ──────────────────────────────────────────────────────────────

class RecoveryManager:
    """记忆恢复管理器"""

    def __init__(self):
        """初始化恢复管理器"""
        self.recovery_dir = RECOVERY_DIR
        self.failures_file = FAILURES_FILE
        self._ensure_dirs()
        self.state = self._load_state()

    def _ensure_dirs(self) -> None:
        """确保必要的目录存在"""
        try:
            self.recovery_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"无法创建恢复目录 {self.recovery_dir}: {e}")

    def _load_state(self) -> dict:
        """加载失败状态文件"""
        if not self.failures_file.exists():
            return {
                "failures": [],
                "circuit_tripped": False,
                "circuit_trip_at": 0,
                "last_recovery_at": 0,
                "last_failure_at": 0,
            }

        try:
            with open(self.failures_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"读取状态文件失败: {e}")
            return {
                "failures": [],
                "circuit_tripped": False,
                "circuit_trip_at": 0,
                "last_recovery_at": 0,
                "last_failure_at": 0,
            }

    def _save_state(self) -> None:
        """保存失败状态文件"""
        try:
            with open(self.failures_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"保存状态文件失败: {e}")

    def _is_circuit_tripped(self) -> bool:
        """检查熔断器是否已触发"""
        if not self.state.get("circuit_tripped"):
            return False

        circuit_at = self.state.get("circuit_trip_at", 0)
        now = time.time()

        # 检查熔断是否已过期
        if now - circuit_at > CIRCUIT_TRIP_DURATION:
            logger.info(f"熔断已恢复（持续 {int(now - circuit_at)} 秒）")
            self.state["circuit_tripped"] = False
            self._save_state()
            return False

        return True

    def record_failure(self, error_msg: str = "", exception: Optional[Exception] = None) -> None:
        """
        记录一次失败

        Args:
            error_msg: 错误消息
            exception: 异常对象
        """
        now = time.time()
        now_ts = datetime.fromtimestamp(now, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

        # 解析异常
        if exception:
            error_msg = f"{type(exception).__name__}: {str(exception)}"

        failure_count = len(self.state.get("failures", []))

        # 添加失败记录
        failure_record = {
            "timestamp": now,
            "count": failure_count + 1,
            "error": error_msg,
            "ts_str": now_ts,
        }
        self.state["failures"].append(failure_record)
        self.state["last_failure_at"] = now

        logger.warning(f"记录失败 #{failure_record['count']}: {error_msg[:100]}")

        # 检查是否达到熔断阈值
        if failure_record["count"] >= MAX_FAILURES_BEFORE_CIRCUIT:
            self.circuit_trip(error_msg)
            return

        # 计算下次重试延迟
        if failure_record["count"] <= len(RETRY_DELAYS):
            delay_idx = failure_record["count"] - 1
            delay_s = RETRY_DELAYS[delay_idx]
            next_retry = now + delay_s
            next_retry_ts = datetime.fromtimestamp(next_retry, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

            msg = (
                f"🔄 <b>Memory Compaction 失败恢复通知</b>\n"
                f"{now_ts}\n\n"
                f"<b>--- 失败记录 ---</b>\n"
                f"第 <b>{failure_record['count']}</b> 次失败\n"
                f"错误: {error_msg[:80]}\n\n"
                f"<b>--- 重试计划 ---</b>\n"
                f"延迟: {delay_s}s\n"
                f"下次重试: {next_retry_ts}\n"
                f"策略: 指数退避"
            )
            logger.info(f"下次重试在 {delay_s}s 后（{next_retry_ts}）")
        else:
            msg = (
                f"⚠️ <b>Memory Compaction 即将熔断</b>\n"
                f"{now_ts}\n\n"
                f"已失败 {failure_record['count']} 次"
            )

        self._save_state()
        send_telegram_safe(msg)

    def circuit_trip(self, reason: str = "") -> None:
        """
        触发熔断器

        Args:
            reason: 熔断原因
        """
        now = time.time()
        now_ts = datetime.fromtimestamp(now, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        recovery_until = now + CIRCUIT_TRIP_DURATION
        recovery_until_ts = datetime.fromtimestamp(recovery_until, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

        self.state["circuit_tripped"] = True
        self.state["circuit_trip_at"] = now
        self._save_state()

        logger.error(f"熔断触发！将停止重试直到 {recovery_until_ts}")

        msg = (
            f"🚫 <b>Memory Compaction 已熔断</b>\n"
            f"{now_ts}\n\n"
            f"<b>--- 熔断详情 ---</b>\n"
            f"失败次数: <b>{len(self.state.get('failures', []))}</b>\n"
            f"原因: {reason[:100]}\n\n"
            f"<b>--- 恢复时间 ---</b>\n"
            f"熔断持续: {CIRCUIT_TRIP_DURATION}s\n"
            f"恢复时间: {recovery_until_ts}\n\n"
            f"期间将停止所有重试。恢复后自动重启。"
        )
        send_telegram_safe(msg)

    def get_failure_count(self) -> int:
        """获取当前失败次数"""
        return len(self.state.get("failures", []))

    def get_next_retry_delay(self) -> int:
        """获取下次重试延迟（秒）"""
        count = self.get_failure_count()
        if count >= MAX_FAILURES_BEFORE_CIRCUIT:
            return -1  # 表示已熔断
        if count > len(RETRY_DELAYS):
            return RETRY_DELAYS[-1]
        return RETRY_DELAYS[min(count, len(RETRY_DELAYS) - 1)]

    def should_retry(self) -> bool:
        """判断是否应该重试"""
        if self._is_circuit_tripped():
            return False
        return self.get_failure_count() < MAX_FAILURES_BEFORE_CIRCUIT

    def try_restore_from_backup(self, backup_date: Optional[str] = None) -> bool:
        """
        尝试从备份恢复

        Args:
            backup_date: 备份日期（YYYY-MM-DD），默认使用最近备份

        Returns:
            是否恢复成功
        """
        now = time.time()
        now_ts = datetime.fromtimestamp(now, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

        try:
            # 找到要恢复的备份
            if backup_date:
                backup_path = BACKUP_DIR / backup_date
            else:
                # 找最近的备份
                all_backups = sorted(
                    [d for d in BACKUP_DIR.iterdir() if d.is_dir()],
                    key=lambda d: d.name,
                    reverse=True
                )
                if not all_backups:
                    msg = f"❌ 无可用备份，恢复失败 ({now_ts})"
                    logger.error(msg)
                    send_telegram_safe(msg)
                    return False
                backup_path = all_backups[0]

            if not backup_path.exists():
                msg = f"❌ 备份不存在: {backup_path} ({now_ts})"
                logger.error(msg)
                send_telegram_safe(msg)
                return False

            # 备份现有数据库
            corrupted_path = LANCE_DB_PATH.parent / f"corrupted_{int(now)}"
            if LANCE_DB_PATH.exists():
                if LANCE_DB_PATH.is_dir():
                    shutil.move(str(LANCE_DB_PATH), str(corrupted_path))
                else:
                    shutil.copy2(str(LANCE_DB_PATH), str(corrupted_path))
                    LANCE_DB_PATH.unlink()
                logger.info(f"已将损坏数据库移至 {corrupted_path}")

            # 确保目标目录存在
            LANCE_DB_PATH.mkdir(parents=True, exist_ok=True)

            # 恢复备份内容
            for item in backup_path.iterdir():
                dest = LANCE_DB_PATH / item.name
                if item.is_dir():
                    shutil.copytree(str(item), str(dest))
                else:
                    shutil.copy2(str(item), str(dest))

            self.state["last_recovery_at"] = now
            self._save_state()

            msg = (
                f"✅ <b>Memory 恢复成功</b>\n"
                f"{now_ts}\n\n"
                f"<b>--- 恢复详情 ---</b>\n"
                f"备份日期: {backup_path.name}\n"
                f"恢复位置: {LANCE_DB_PATH}\n"
                f"损坏数据: {corrupted_path}\n\n"
                f"失败计数已重置，将重新启动 memory_compaction"
            )
            logger.info(f"恢复成功，使用备份 {backup_path.name}")
            send_telegram_safe(msg)

            # 重置失败计数
            self.state["failures"] = []
            self.state["circuit_tripped"] = False
            self._save_state()

            return True

        except Exception as e:
            msg = f"❌ 恢复失败: {str(e)[:80]} ({now_ts})"
            logger.error(msg)
            send_telegram_safe(msg)
            return False

    def schedule_retry(self) -> Optional[float]:
        """
        返回建议的下次重试时间戳

        Returns:
            Unix 时间戳，若已熔断则返回 None
        """
        if not self.should_retry():
            return None

        delay = self.get_next_retry_delay()
        if delay < 0:
            return None

        return time.time() + delay

    def reset(self) -> None:
        """重置所有失败记录（仅用于测试或手动恢复）"""
        self.state = {
            "failures": [],
            "circuit_tripped": False,
            "circuit_trip_at": 0,
            "last_recovery_at": 0,
            "last_failure_at": 0,
        }
        self._save_state()
        logger.info("已重置所有失败记录和熔断器")

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "failure_count": self.get_failure_count(),
            "circuit_tripped": self._is_circuit_tripped(),
            "should_retry": self.should_retry(),
            "next_retry_delay": self.get_next_retry_delay(),
            "next_retry_at": self.schedule_retry(),
            "last_failure_at": self.state.get("last_failure_at", 0),
            "last_recovery_at": self.state.get("last_recovery_at", 0),
            "failures": self.state.get("failures", [])[-5:],  # 最后5条
        }


# ─── 命令行接口 ──────────────────────────────────────────────────────────────

def main() -> None:
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Memory Recovery Manager")
    parser.add_argument("--check", action="store_true", help="检查当前状态")
    parser.add_argument("--recover", action="store_true", help="尝试从备份恢复")
    parser.add_argument("--reset", action="store_true", help="重置所有失败记录")
    parser.add_argument("--record-failure", metavar="MSG", help="记录一次失败")
    parser.add_argument("--backup-date", metavar="YYYY-MM-DD", help="指定恢复的备份日期")
    args = parser.parse_args()

    rm = RecoveryManager()

    if args.check:
        status = rm.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
        return

    if args.recover:
        if rm.try_restore_from_backup(backup_date=args.backup_date):
            sys.exit(0)
        else:
            sys.exit(1)

    if args.reset:
        rm.reset()
        return

    if args.record_failure:
        rm.record_failure(error_msg=args.record_failure)
        return

    # 默认显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
