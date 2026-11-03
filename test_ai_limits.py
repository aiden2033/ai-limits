#!/usr/bin/env python3

import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest


def load_widget():
    path = Path(__file__).with_name("ai-limits.5m.py")
    spec = importlib.util.spec_from_file_location("ai_limits", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WidgetTests(unittest.TestCase):
    def test_manual_refresh_is_next_to_manage_providers(self):
        widget = load_widget()
        providers = [{"id": "test", "name": "Test", "icon": "T", "enabled": True}]
        with patch.object(widget, "load_all_providers", return_value=providers):
            lines = widget.render_manage_menu()

        self.assertEqual(
            lines[:3],
            ["---", "⚙️ Manage Providers", "🔄 Обновить | refresh=true"],
        )

    def test_glm_remaining_percent_uses_usage_and_allowance(self):
        widget = load_widget()
        payload = {
            "success": True,
            "code": 200,
            "data": {
                "limits": [
                    {
                        "type": "TOKENS_LIMIT",
                        "unit": 3,
                        "number": 5,
                        "usage": 250,
                        "currentValue": 125,
                        "nextResetTime": 1762000000000,
                    }
                ]
            },
        }

        result = widget.parse_glm_limits(payload)

        self.assertEqual(result["h5_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
