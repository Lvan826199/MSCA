from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class MirrorOptions:
    width: int = 0
    height: int = 0
    max_fps: int = 30
    bitrate: int = 8_000_000
    video_codec: str = "h264"


@dataclass
class ControlEvent:
    action: str  # tap, swipe, keyevent, text
    params: dict = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}


@dataclass
class InstallResult:
    success: bool
    message: str = ""
    package_name: str = ""


class AbstractDeviceDriver(ABC):
    """设备驱动抽象基类，所有平台驱动必须实现此接口。"""

    @abstractmethod
    async def start_mirroring(self, options: MirrorOptions) -> str:
        """启动投屏，返回流标识符。"""

    @abstractmethod
    async def stop_mirroring(self) -> None:
        """停止投屏，释放资源。"""

    @abstractmethod
    async def send_event(self, event: ControlEvent) -> bool:
        """发送控制指令，返回是否成功。"""

    @abstractmethod
    async def get_screenshot(self) -> bytes:
        """获取当前屏幕截图。"""

    async def install_app(
        self, file_path: str, callback: Callable[[str], None] | None = None
    ) -> InstallResult:
        """安装应用到设备。子类可选实现。"""
        return InstallResult(success=False, message="此设备不支持应用安装")
