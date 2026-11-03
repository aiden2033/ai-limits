#!/usr/bin/env python3

import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import patch
import unittest


def load_widget():
    path = Path(__file__).with_name("ai-limits.5m.py")
    spec = importlib.util.spec_from_file_location("ai_limits", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_core():
    path = Path(__file__).with_name("ai_limits_core.py")
    spec = importlib.util.spec_from_file_location("ai_limits_core", path)
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
        core = load_core()
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

        result = core.parse_glm_limits(payload)

        self.assertEqual(result["h5_pct"], 50.0)

    def test_windows_codex_shutdown_terminates_process_tree(self):
        core = load_core()

        class FakeProcess:
            pid = 4815

            def wait(self, timeout=None):
                return 0

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(core.os, "name", "nt"), patch.object(
            core.subprocess,
            "run",
            return_value=completed,
        ) as run:
            core.terminate_process_tree(FakeProcess())

        run.assert_called_once_with(
            ["taskkill", "/T", "/F", "/PID", "4815"],
            stdout=core.subprocess.DEVNULL,
            stderr=core.subprocess.DEVNULL,
            check=False,
            creationflags=0,
        )


if __name__ == "__main__":
    unittest.main()
