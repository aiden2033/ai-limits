import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_limits_core as core
from test_ai_limits import load_widget


class ClaudeLimitsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, filename in [("CLAUDE_QUOTA_CACHE", "quota.json"), ("CLAUDE_CREDENTIALS", "credentials.json")]:
            replacement = patch.object(core, name, self.root / filename)
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_account_usage_becomes_remaining_percentages_and_reset_times(self):
        result = core.parse_claude_limits({
            "five_hour": {"utilization": 94.0, "resets_at": "2026-11-04T00:30:00Z"},
            "seven_day": {"utilization": 2.0, "resets_at": "2026-11-10T19:00:00Z"},
        })

        self.assertEqual(result, {
            "h5_pct": 6.0, "week_pct": 98.0,
            "h5_reset": "2026-11-04T00:30:00Z", "week_reset": "2026-11-10T19:00:00Z",
        })
        lines = load_widget().render_provider({"icon": "C", "name": "Claude Code"}, result)
        self.assertIn("6% left", lines[0])
        self.assertIn("98% left", lines[1])

    def test_zero_usage_is_a_full_allowance_and_full_usage_is_zero_left(self):
        result = core.parse_claude_limits({
            "five_hour": {"utilization": 0}, "seven_day": {"utilization": 100},
        })

        self.assertEqual(result, {"h5_pct": 100.0, "week_pct": 0.0})

    def test_limits_array_uses_session_and_all_models_weekly_windows(self):
        result = core.parse_claude_limits({"five_hour": None, "seven_day": None, "limits": [
            {"kind": "weekly_sonnet", "percent": 80},
            {"kind": "session", "percent": 94, "resets_at": "2026-11-04T00:30:00Z"},
            {"kind": "weekly_all", "percent": 2, "is_active": False},
        ]})

        self.assertEqual(result["h5_pct"], 6)
        self.assertEqual(result["week_pct"], 98)

    def test_missing_windows_do_not_invent_full_allowance(self):
        self.assertEqual(core.parse_claude_limits({"seven_day": {"utilization": 2}}), {"week_pct": 98})
        for invalid in [None, {}, {"five_hour": {"utilization": None}}, {"five_hour": {"utilization": True}},
                        {"five_hour": {"utilization": float("nan")}}]:
            with self.subTest(payload=invalid), self.assertRaises(ValueError):
                core.parse_claude_limits(invalid)

    def test_usage_outside_percentage_bounds_is_clamped(self):
        self.assertEqual(core.parse_claude_limits({
            "five_hour": {"utilization": -5}, "seven_day": {"utilization": 105},
        }), {"h5_pct": 100, "week_pct": 0})

    def test_credentials_file_works_without_accessing_keychain(self):
        core.CLAUDE_CREDENTIALS.write_text(json.dumps({"claudeAiOauth": {"accessToken": "file-token"}}))
        with patch.dict(os.environ, {}, clear=True), patch.object(core, "load_claude_keychain_credentials") as keychain:
            self.assertEqual(core.get_claude_access_token(), "file-token")
        keychain.assert_not_called()

    def test_macos_uses_existing_claude_code_keychain_login(self):
        completed = subprocess.CompletedProcess([], 0, json.dumps({"claudeAiOauth": {"accessToken": "keychain-token"}}))
        with patch.dict(os.environ, {}, clear=True), patch.object(core.sys, "platform", "darwin"), patch.object(
            core.subprocess, "run", return_value=completed,
        ) as run:
            self.assertEqual(core.get_claude_access_token(), "keychain-token")
        self.assertEqual(run.call_args.args[0], [
            "/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w",
        ])

    def test_explicit_oauth_token_takes_precedence(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "environment-token"}), patch.object(
            core, "load_claude_keychain_credentials",
        ) as keychain:
            self.assertEqual(core.get_claude_access_token(), "environment-token")
        keychain.assert_not_called()

    def test_missing_login_produces_visible_error(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(core, "load_claude_keychain_credentials", return_value=None):
            result = core.get_claude_data()
        self.assertIn("claude auth login", result["quota_error"])
        lines = load_widget().render_provider({"icon": "C", "name": "Claude Code"}, result)
        self.assertIn("quota unavailable", lines[0])

    def test_legacy_and_new_provider_settings_fetch_live_account_quota(self):
        for source in ["claude_cache", "claude_oauth"]:
            with self.subTest(source=source), patch.object(core, "get_claude_access_token", return_value="test-token"), patch.object(
                core, "request_json", return_value={"five_hour": {"utilization": 94}, "seven_day": {"utilization": 2}},
            ) as request:
                result = core.fetch_provider_data({"id": "claude-code", "source": source})
            self.assertEqual(result, {"h5_pct": 6, "week_pct": 98})
            request.assert_called_once_with(core.CLAUDE_USAGE_URL, "test-token", {"anthropic-beta": "oauth-2025-04-20"})
        self.assertNotIn("test-token", core.CLAUDE_QUOTA_CACHE.read_text())

    def test_temporary_failure_keeps_recent_percentages_with_a_warning(self):
        core.save_claude_quota_cache("test-token", {"h5_pct": 6, "week_pct": 98})
        with patch.object(core, "get_claude_access_token", return_value="test-token"), patch.object(
            core, "request_json", side_effect=ValueError("HTTP 429"),
        ):
            result = core.get_claude_data()
        self.assertEqual(result["h5_pct"], 6)
        self.assertIn("HTTP 429", result["quota_warning"])
        self.assertNotIn("h5_tokens", result)
        self.assertIn("HTTP 429", core.provider_status(result))
        self.assertIn("HTTP 429", load_widget().render_provider({"icon": "C", "name": "Claude Code"}, result)[-1])

    def test_cached_limits_are_not_shared_with_another_credential(self):
        core.save_claude_quota_cache("first-account-token", {"h5_pct": 6})
        self.assertEqual(core.load_claude_quota_cache("second-account-token"), {})

    def test_old_cache_and_finished_windows_are_discarded(self):
        with patch.object(core.time, "time", return_value=1000):
            core.save_claude_quota_cache("test-token", {
                "h5_pct": 6, "h5_reset": "1970-01-01T00:20:00Z", "week_pct": 98,
            })
        with patch.object(core.time, "time", return_value=1300):
            self.assertEqual(core.load_claude_quota_cache("test-token"), {"week_pct": 98})
        with patch.object(core.time, "time", return_value=1000 + core.CLAUDE_QUOTA_CACHE_MAX_AGE + 1):
            self.assertEqual(core.load_claude_quota_cache("test-token"), {})

    def test_quota_failure_without_cache_is_an_error(self):
        with patch.object(core, "get_claude_access_token", return_value="test-token"), patch.object(
            core, "request_json", side_effect=ValueError("HTTP 401"),
        ):
            self.assertEqual(core.get_claude_data(), {"quota_error": "HTTP 401"})

    def test_xbar_imports_helper_outside_its_plugins_folder(self):
        plugins = self.root / "Library/Application Support/xbar/plugins"
        helpers = self.root / ".ai-limits-bin"
        plugins.mkdir(parents=True)
        helpers.mkdir()
        source = Path(__file__).parent
        shutil.copyfile(source / "ai-limits.5m.py", plugins / "ai-limits.5m.py")
        shutil.copyfile(source / "ai_limits_core.py", helpers / "ai_limits_core.py")
        env = {**os.environ, "HOME": str(self.root)}
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, str(plugins / "ai-limits.5m.py")], cwd=self.root,
            env=env, capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Run: python3 manage.py add openai", result.stdout)
        self.assertFalse((plugins / "ai_limits_core.py").exists())

    def test_adding_claude_code_uses_subscription_source(self):
        spec = importlib.util.spec_from_file_location("manage", Path(__file__).with_name("manage.py"))
        manage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manage)
        with patch.object(manage, "CONFIG", self.root / "providers.json"), patch.object(manage, "load", return_value=[]):
            manage.cmd_add("claude-code")
            provider = json.loads(manage.CONFIG.read_text())[0]
        self.assertEqual(provider["source"], "claude_oauth")
        self.assertEqual(provider["name"], "Claude Code")

    def test_existing_legacy_claude_provider_does_not_offer_a_duplicate(self):
        widget = load_widget()
        with patch.object(widget, "load_all_providers", return_value=[{
            "id": "claude", "name": "Claude", "icon": "C", "enabled": True, "source": "claude_cache",
        }]):
            self.assertNotIn("--➕ Подключить", widget.render_manage_menu())


if __name__ == "__main__":
    unittest.main()
