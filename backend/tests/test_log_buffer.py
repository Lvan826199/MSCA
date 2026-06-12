"""后端日志环形缓冲与查询测试。"""

import logging
import unittest

from app.core import log_buffer
from app.core.log_buffer import RingBufferHandler, get_recent_logs


class LogBufferTests(unittest.TestCase):
    def setUp(self):
        log_buffer._ring_buffer.clear()
        self.handler = RingBufferHandler()
        self.handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        self.logger = logging.getLogger("test_log_buffer")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.addHandler(self.handler)

    def tearDown(self):
        self.logger.removeHandler(self.handler)
        log_buffer._ring_buffer.clear()

    def test_recent_logs_in_order(self):
        self.logger.info("第一条")
        self.logger.warning("第二条")

        lines = get_recent_logs(10)
        self.assertEqual(lines, ["INFO 第一条", "WARNING 第二条"])

    def test_lines_limit_returns_tail(self):
        for i in range(10):
            self.logger.info("消息 %s", i)

        lines = get_recent_logs(3)
        self.assertEqual(lines, ["INFO 消息 7", "INFO 消息 8", "INFO 消息 9"])

    def test_non_positive_lines_returns_empty(self):
        self.logger.info("任意")
        self.assertEqual(get_recent_logs(0), [])

    def test_capacity_bounded(self):
        for i in range(log_buffer.RING_BUFFER_CAPACITY + 100):
            self.logger.info("溢出 %s", i)

        lines = get_recent_logs(log_buffer.RING_BUFFER_CAPACITY * 2)
        self.assertEqual(len(lines), log_buffer.RING_BUFFER_CAPACITY)
        self.assertTrue(lines[-1].endswith(f"溢出 {log_buffer.RING_BUFFER_CAPACITY + 99}"))


if __name__ == "__main__":
    unittest.main()
