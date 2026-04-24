from pydantic import BaseModel


class DeviceInfo(BaseModel):
    """设备信息统一模型，Android/iOS 共用。"""

    id: str
    platform: str  # "android" | "ios"
    model: str = ""
    version: str = ""
    resolution: str = ""
    status: str = "online"  # "online" | "offline" | "mirroring"
