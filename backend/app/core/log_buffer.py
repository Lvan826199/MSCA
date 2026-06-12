"""后端运行日志收集。

- RingBufferHandler：内存环形缓冲，保存最近 N 条格式化日志，供 /api/logs 查询
- setup_logging：统一配置根 logger（控制台 + 环形缓冲 + 滚动文件）

日志目录优先级：MSCA_LOG_DIR 环境变量 > backend 根目录/logs。
打包模式下由 Electron BackendManager 传入 userData/logs（resources 目录可能只读）。
"""

import logging
import os
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
RING_BUFFER_CAPACITY = 2000
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 3

_ring_buffer: deque[str] = deque(maxlen=RING_BUFFER_CAPACITY)
_configured = False
_log_file_path: str = ""


class RingBufferHandler(logging.Handler):
    """把格式化日志写入模块级环形缓冲。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _ring_buffer.append(self.format(record))
        except Exception:
            self.handleError(record)


def resolve_log_dir() -> Path:
    env_dir = os.environ.get("MSCA_LOG_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    backend_root = Path(__file__).resolve().parent.parent.parent
    return backend_root / "logs"


def setup_logging() -> None:
    """配置根 logger。可重复调用，仅首次生效。"""
    global _configured, _log_file_path
    if _configured:
        return
    _configured = True

    formatter = logging.Formatter(LOG_FORMAT)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

    ring = RingBufferHandler()
    ring.setFormatter(formatter)
    root.addHandler(ring)

    try:
        log_dir = resolve_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "backend.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        _log_file_path = str(log_file)
    except OSError as err:
        logging.getLogger(__name__).warning("日志文件初始化失败（仅内存日志可用）: %s", err)


def get_recent_logs(lines: int = 500) -> list[str]:
    """返回最近 lines 条日志，时间正序。"""
    if lines <= 0:
        return []
    buffer = list(_ring_buffer)
    return buffer[-lines:]


def get_log_file_path() -> str:
    return _log_file_path
