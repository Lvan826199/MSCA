import unittest

from app.drivers.adapters.base import diagnose_wda_failure


class WdaDiagnosticsTests(unittest.TestCase):
    def test_formatted_unknown_failure_is_not_reclassified_by_suggestion_text(self):
        hint = diagnose_wda_failure(
            "WDA 启动或控制失败。排障建议：查看后端日志中的原始错误，重点检查 WDA 签名、设备信任、端口占用和适配器启动状态"
        )

        self.assertEqual(hint.category, "wda_unknown")

    def test_real_port_occupied_message_is_still_classified(self):
        hint = diagnose_wda_failure("端口 8100 被占用")

        self.assertEqual(hint.category, "port_occupied")

    def test_formatted_chinese_pairing_failure_stays_device_not_trusted(self):
        hint = diagnose_wda_failure(
            "iOS 设备未信任电脑或配对凭证不可用。排障建议：解锁设备并点击“信任此电脑”"
        )

        self.assertEqual(hint.category, "device_not_trusted")


if __name__ == "__main__":
    unittest.main()
