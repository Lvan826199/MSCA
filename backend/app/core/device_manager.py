class DeviceManager:
    """设备管理器，负责设备发现、注册、状态监控。"""

    def __init__(self):
        self._devices = {}

    def get_all_devices(self):
        return list(self._devices.values())

    def add_device(self, device_id, info):
        self._devices[device_id] = info

    def remove_device(self, device_id):
        self._devices.pop(device_id, None)


device_manager = DeviceManager()
