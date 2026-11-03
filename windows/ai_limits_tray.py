#!/usr/bin/env python3

import sys
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_limits_core import (  # noqa: E402
    fetch_all_providers,
    load_all_providers,
    load_providers,
    minimum_remaining_percent,
    provider_status,
    set_provider_enabled,
)

try:
    import pystray
except ImportError:
    pystray = None


class TrayState:
    def __init__(self):
        self._lock = threading.Lock()
        self._provider_results = []
        self._refreshing = False
        self._last_error = None
        self._last_updated = None

    def refresh(self, fetcher=fetch_all_providers):
        with self._lock:
            if self._refreshing:
                return False
            self._refreshing = True
        try:
            provider_results = fetcher(load_providers())
            with self._lock:
                self._provider_results = list(provider_results)
                self._last_error = None
                self._last_updated = datetime.now()
            return True
        except Exception as error:
            with self._lock:
                self._last_error = str(error)
            return True
        finally:
            with self._lock:
                self._refreshing = False

    def snapshot(self):
        with self._lock:
            return {
                "provider_results": list(self._provider_results),
                "refreshing": self._refreshing,
                "last_error": self._last_error,
                "last_updated": self._last_updated,
            }


def status_lines(snapshot):
    if snapshot["refreshing"]:
        return ["Обновление лимитов…"]
    if snapshot["last_error"]:
        return [f"Ошибка обновления: {snapshot['last_error']}"]
    if not snapshot["provider_results"]:
        return ["Провайдеры не настроены"]
    return [
        f'{provider["name"]}: {provider_status(data)}'
        for provider, data in snapshot["provider_results"]
    ]


def tooltip(snapshot):
    lines = status_lines(snapshot)
    if snapshot["last_updated"]:
        updated = snapshot["last_updated"].strftime("%H:%M")
        lines.append(f"Обновлено {updated}")
    result = "AI Limits\n" + "\n".join(lines)
    return result if len(result) <= 127 else result[:124] + "..."


def icon_label(snapshot):
    if snapshot["last_error"] or any(data.get("quota_error") for _, data in snapshot["provider_results"]):
        return "!"
    remaining = minimum_remaining_percent(snapshot["provider_results"])
    return f"{remaining:.0f}" if remaining is not None else "AI"


def icon_image(label):
    from PIL import Image, ImageDraw, ImageFont

    size = (64, 64)
    image = Image.new("RGBA", size, (22, 22, 28, 255))
    draw = ImageDraw.Draw(image)
    if label == "!":
        color = (255, 159, 10, 255)
    elif label == "AI":
        color = (52, 199, 89, 255)
    else:
        value = int(label)
        color = (52, 199, 89, 255) if value > 50 else (255, 159, 10, 255) if value > 20 else (255, 59, 48, 255)
    font = ImageFont.truetype("arial.ttf", 36 if len(label) <= 2 else 24)
    box = draw.textbbox((0, 0), label, font=font)
    position = ((size[0] - box[2] + box[0]) / 2, (size[1] - box[3] + box[1]) / 2)
    draw.text(position, label, fill=color, font=font)
    return image


class TrayApplication:
    def __init__(self, refresh_interval=300, state=None):
        self.refresh_interval = refresh_interval
        self.state = state or TrayState()
        self._stop = threading.Event()
        self._icon = None

    def start_refresh(self):
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        if self.state.refresh():
            self.publish()

    def _periodic_worker(self):
        while not self._stop.wait(self.refresh_interval):
            if self.state.refresh():
                self.publish()

    def request_refresh(self, *_):
        self.start_refresh()

    def publish(self):
        if self._icon is None:
            return
        snapshot = self.state.snapshot()
        self._icon.title = tooltip(snapshot)
        self._icon.icon = icon_image(icon_label(snapshot))
        self._icon.menu = self.build_menu()
        self._icon.update_menu()

    def build_menu(self):
        return pystray.Menu(*self.menu_items())

    def menu_items(self):
        snapshot = self.state.snapshot()
        items = [pystray.MenuItem(text, None, enabled=False) for text in status_lines(snapshot)]
        if snapshot["last_updated"]:
            updated = snapshot["last_updated"].strftime("%H:%M")
            items.append(pystray.MenuItem(f"Обновлено {updated}", None, enabled=False))
        items.extend(self.manage_items())
        items.extend([
            pystray.MenuItem("Обновить", self.request_refresh, default=True),
            pystray.MenuItem("Выход", self.stop),
        ])
        return items

    def manage_items(self):
        items = []
        for provider in load_all_providers():
            action = "Скрыть" if provider.get("enabled") else "Показать"
            items.append(pystray.MenuItem(
                f'{action}: {provider["name"]}',
                lambda icon, item, provider_id=provider["id"], enabled=not provider.get("enabled"): (
                    self.toggle_provider(provider_id, enabled)
                ),
            ))
        return [pystray.MenuItem("Manage providers", pystray.Menu(*items))] if items else []

    def toggle_provider(self, provider_id, enabled):
        set_provider_enabled(provider_id, enabled)
        self.start_refresh()

    def stop(self, *_):
        self._stop.set()
        if self._icon is not None:
            self._icon.stop()

    def run(self):
        if pystray is None:
            raise RuntimeError("Установи зависимости: pip install -r windows/requirements.txt")
        initial = self.state.snapshot()
        self._icon = pystray.Icon(
            "AI Limits",
            title=tooltip(initial),
            icon=icon_image(icon_label(initial)),
            menu=self.build_menu(),
        )
        self.start_refresh()
        threading.Thread(target=self._periodic_worker, daemon=True).start()
        try:
            self._icon.run()
        finally:
            self._stop.set()


def print_once():
    state = TrayState()
    state.refresh()
    print("\n".join(status_lines(state.snapshot())))


if __name__ == "__main__":
    if "--once" in sys.argv:
        print_once()
    else:
        TrayApplication().run()
