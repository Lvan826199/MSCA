"""后端入口端口探测逻辑测试。"""

import importlib.util
import socket
import unittest
from pathlib import Path


def _load_entry_module():
    """加载 backend/__main__.py（避开 __main__ 名称冲突）。"""
    entry_path = Path(__file__).resolve().parents[1] / "__main__.py"
    spec = importlib.util.spec_from_file_location("backend_entry", entry_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


entry = _load_entry_module()


class PortProbeTests(unittest.TestCase):
    def test_port_available_detects_occupied_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            occupied = s.getsockname()[1]
            self.assertFalse(entry.port_available("127.0.0.1", occupied))

    def test_find_available_port_skips_occupied(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            occupied = s.getsockname()[1]
            # 从被占用端口开始探测，应跳过它返回后续端口
            port = entry.find_available_port(occupied, attempts=5, host="127.0.0.1")
            self.assertNotEqual(port, occupied)
            self.assertTrue(occupied < port <= occupied + 4)

    def test_port_file_write_and_remove(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            port_file = Path(tmpdir) / ".backend-port"
            entry.write_port_file(port_file, 18001)
            self.assertEqual(port_file.read_text(encoding="utf-8"), "18001")
            entry.remove_port_file(port_file)
            self.assertFalse(port_file.exists())
            # 重复删除不应抛异常
            entry.remove_port_file(port_file)


if __name__ == "__main__":
    unittest.main()
