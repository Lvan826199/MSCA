import json
import logging
import os

logger = logging.getLogger(__name__)

_CONFIG_RELPATH = os.path.join("config", "device_aliases.json")


class AliasManager:
    """设备别名管理器，从 JSON 配置文件加载，支持热加载。"""

    def __init__(self):
        self._aliases: dict[str, str] = {}
        self._config_path = ""
        self._last_mtime: float = 0

    def init(self, backend_root: str):
        self._config_path = os.path.join(backend_root, _CONFIG_RELPATH)
        self._load()

    def _load(self):
        if not os.path.isfile(self._config_path):
            logger.warning("别名配置文件不存在: %s", self._config_path)
            self._aliases = {}
            self._last_mtime = 0
            return
        try:
            mtime = os.path.getmtime(self._config_path)
            with open(self._config_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.error("别名配置格式错误，应为 JSON 对象")
                return
            self._aliases = {str(k): str(v) for k, v in data.items()}
            self._last_mtime = mtime
            logger.info("已加载 %d 条设备别名配置", len(self._aliases))
        except Exception:
            logger.exception("加载别名配置失败")

    def check_reload(self):
        """检查配置文件是否变化，变化则重新加载。由设备轮询循环调用。"""
        if not self._config_path:
            return
        try:
            if not os.path.isfile(self._config_path):
                return
            mtime = os.path.getmtime(self._config_path)
            if mtime != self._last_mtime:
                logger.info("检测到别名配置文件变化，重新加载")
                self._load()
        except Exception:
            logger.exception("检查别名配置文件失败")

    def get_alias(self, device_id: str) -> str:
        return self._aliases.get(device_id, "")


alias_manager = AliasManager()
