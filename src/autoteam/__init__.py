"""AutoTeam - ChatGPT Team 账号自动轮转管理工具"""

__version__ = "0.1.0"

import logging
import os
import sys
import threading
from rich.logging import RichHandler

_thread_log_local = threading.local()

def set_thread_log_prefix(prefix: str):
    """设置当前线程的日志前缀，例如 [Worker-1]"""
    _thread_log_local.prefix = prefix

def get_thread_log_prefix() -> str:
    """获取当前线程的日志前缀"""
    return getattr(_thread_log_local, "prefix", "")

def update_thread_log_prefix(extra: str):
    """更新当前线程的日志前缀，例如 [Worker-1] -> [Worker-1: email]"""
    prefix = get_thread_log_prefix()
    if prefix:
        if ":" not in prefix:
            set_thread_log_prefix(f"{prefix[:-1]}:{extra}]")
        else:
            # 已经有分号，只更新分号后面的部分
            base = prefix.split(":")[0]
            set_thread_log_prefix(f"{base}:{extra}]")

class AutoteamLogger(logging.Logger):
    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
        if self.name.startswith("autoteam"):
            prefix = get_thread_log_prefix()
            if prefix and isinstance(msg, str) and prefix not in msg:
                msg = f"{prefix} {msg}"
        super()._log(level, msg, args, exc_info, extra, stack_info, stacklevel)

# 确保在任何 Logger 实例化之前调用 setLoggerClass
logging.setLoggerClass(AutoteamLogger)

if os.environ.get("AUTOTEAM_PROBE_MODE") == "1":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(message)s",
        stream=sys.stderr,
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%H:%M:%S]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False, markup=True)],
    )
