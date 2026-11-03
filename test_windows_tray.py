#!/usr/bin/env python3

import importlib.util
import threading
from pathlib import Path
from unittest.mock import patch
import unittest


def load_tray_module():
    path = Path(__file__).with_name("windows") / "ai_limits_tray.py"
    spec = importlib.util.spec_from_file_location("ai_limits_tray", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsTrayTests(unittest.TestCase):
    def test_refresh_replaces_provider_statuses(self):
        tray = load_tray_module()
        state = tray.TrayState()
        provider = {"id": "test", "name": "Test", "enabled": True}
        results = [(provider, {"h5_pct": 42.5, "week_pct": 75})]

        self.assertTrue(state.refresh(lambda _: results))
        self.assertEqual(tray.status_lines(state.snapshot()), ["Test: 5h 42% · 7d 75%"])

    def test_overlapping_refresh_is_ignored(self):
        tray = load_tray_module()
        state = tray.TrayState()
        entered = threading.Event()
        release = threading.Event()

        def fetch(_):
            entered.set()
            release.wait(2)
            return []

        first = threading.Thread(target=lambda: state.refresh(fetch))
        first.start()
        entered.wait(2)
        self.assertFalse(state.refresh(lambda _: []))
        release.set()
        first.join(2)

    def test_tooltip_is_windows_safe(self):
        tray = load_tray_module()
        provider = {"name": "Very Long Provider Name", "enabled": True}
        snapshot = {
            "provider_results": [(provider, {"quota_error": "x" * 180})],
            "refreshing": False,
            "last_error": None,
            "last_updated": None,
        }

        result = tray.tooltip(snapshot)

        self.assertLessEqual(len(result), 127)
        self.assertTrue(result.endswith("..."))

    def test_icon_label_uses_minimum_remaining_percent(self):
        tray = load_tray_module()
        providers = [{"name": "One", "enabled": True}, {"name": "Two", "enabled": True}]
        results = [
            (providers[0], {"h5_pct": 70, "week_pct": 80}),
            (providers[1], {"h5_pct": 40, "week_pct": 90}),
        ]

        self.assertEqual(
            tray.icon_label({
                "provider_results": results,
                "refreshing": False,
                "last_error": None,
                "last_updated": None,
            }),
            "40",
        )

    def test_publish_replaces_status_menu_and_toggle_labels(self):
        tray = load_tray_module()

        class FakeMenuItem:
            def __init__(self, text, action=None, **_):
                self.text = text
                self.action = action

        class FakeMenu:
            def __init__(self, *items):
                self.items = items

        class Pystray:
            MenuItem = FakeMenuItem
            Menu = FakeMenu

        class Icon:
            def __init__(self):
                self.menu = None
                self.updates = 0

            def update_menu(self):
                self.updates += 1

        def menu_texts(menu):
            return [item.text for item in menu.items]

        def toggle_label(menu):
            manage = next(item for item in menu.items if item.text == "Manage providers")
            return manage.action.items[0].text

        state = tray.TrayState()
        provider = {"id": "test", "name": "Test", "enabled": True}
        state.refresh(lambda _: [(provider, {"h5_pct": 20, "week_pct": 80})])
        app = tray.TrayApplication(state=state)
        icon = Icon()
        app._icon = icon

        with patch.object(tray, "pystray", Pystray), patch.object(tray, "icon_image", return_value=object()), patch.object(tray, "icon_label", return_value="20"), patch.object(tray, "load_all_providers", return_value=[provider]):
            app.publish()
            first_menu = icon.menu
            provider["enabled"] = False
            state.refresh(lambda _: [(provider, {"h5_pct": 75, "week_pct": 80})])
            app.publish()

        self.assertIsNot(icon.menu, first_menu)
        self.assertTrue(any(text.startswith("Test: 5h 20%") for text in menu_texts(first_menu)))
        self.assertTrue(any(text.startswith("Test: 5h 75%") for text in menu_texts(icon.menu)))
        self.assertEqual(toggle_label(first_menu), "Скрыть: Test")
        self.assertEqual(toggle_label(icon.menu), "Показать: Test")
        self.assertEqual(icon.updates, 2)


if __name__ == "__main__":
    unittest.main()
