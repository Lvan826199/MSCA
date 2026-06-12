"""go-ios 共享 tunnel agent 应用级清理测试。"""

import unittest

from app.drivers.adapters import goios_adapter
from app.drivers.adapters.goios_adapter import shutdown_tunnel_agents


class FakeProc:
    def __init__(self, exited=False, terminate_raises=False):
        self.pid = 12345
        self._exited = exited
        self._terminate_raises = terminate_raises
        self.terminate_called = False
        self.kill_called = False

    def poll(self):
        return 0 if self._exited else None

    def terminate(self):
        self.terminate_called = True
        if self._terminate_raises:
            raise OSError("terminate failed")

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.kill_called = True


class ShutdownTunnelAgentsTests(unittest.TestCase):
    def setUp(self):
        goios_adapter._shared_agent_processes.clear()

    def tearDown(self):
        goios_adapter._shared_agent_processes.clear()

    def test_terminates_registered_agents_and_clears_registry(self):
        proc = FakeProc()
        goios_adapter._shared_agent_processes.append(proc)

        shutdown_tunnel_agents()

        self.assertTrue(proc.terminate_called)
        self.assertEqual(goios_adapter._shared_agent_processes, [])

    def test_skips_already_exited_agent(self):
        proc = FakeProc(exited=True)
        goios_adapter._shared_agent_processes.append(proc)

        shutdown_tunnel_agents()

        self.assertFalse(proc.terminate_called)
        self.assertEqual(goios_adapter._shared_agent_processes, [])

    def test_falls_back_to_kill_when_terminate_fails(self):
        proc = FakeProc(terminate_raises=True)
        goios_adapter._shared_agent_processes.append(proc)

        shutdown_tunnel_agents()

        self.assertTrue(proc.kill_called)
        self.assertEqual(goios_adapter._shared_agent_processes, [])

    def test_noop_on_empty_registry(self):
        shutdown_tunnel_agents()
        self.assertEqual(goios_adapter._shared_agent_processes, [])


if __name__ == "__main__":
    unittest.main()
