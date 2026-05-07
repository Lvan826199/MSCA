import socket
import unittest

from app.drivers import ios


class PortAllocationTests(unittest.TestCase):
    def setUp(self):
        self.original_counter = ios._port_counter
        ios._port_counter = 0

    def tearDown(self):
        ios._port_counter = self.original_counter

    def test_allocate_wda_ports_skips_occupied_mjpeg_ports_until_free(self):
        busy_one = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy_two = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy_one.bind(("127.0.0.1", ios.IOS_WDA_BASE_PORT + 1))
        busy_two.bind(("127.0.0.1", ios.IOS_WDA_BASE_PORT + 2))
        try:
            wda_port, mjpeg_port = ios._allocate_wda_ports()
        finally:
            busy_one.close()
            busy_two.close()

        self.assertEqual(wda_port, ios.IOS_WDA_BASE_PORT)
        self.assertEqual(mjpeg_port, ios.IOS_WDA_BASE_PORT + 3)

    def test_release_wda_port_does_not_reuse_live_previous_allocation(self):
        first = ios._allocate_wda_ports()
        second = ios._allocate_wda_ports()

        ios._release_wda_port()
        third = ios._allocate_wda_ports()

        self.assertNotEqual(third, first)
        self.assertNotEqual(third, second)


if __name__ == "__main__":
    unittest.main()
