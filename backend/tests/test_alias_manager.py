import json
import tempfile
import unittest
from pathlib import Path

from app.core.alias_manager import AliasManager


class AliasManagerTests(unittest.TestCase):
    def test_set_alias_persists_update_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = AliasManager()
            manager.init(tmp)

            self.assertEqual(manager.get_alias("device-1"), "")

            manager.set_alias("device-1", "  QA Phone  ")

            config_path = Path(tmp) / "config" / "device_aliases.json"
            self.assertEqual(manager.get_alias("device-1"), "QA Phone")
            self.assertEqual(
                json.loads(config_path.read_text(encoding="utf-8")),
                {"device-1": "QA Phone"},
            )

            manager.set_alias("device-1", "")

            self.assertEqual(manager.get_alias("device-1"), "")
            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8")), {})


if __name__ == "__main__":
    unittest.main()
