#!/usr/bin/env python3

import json
import sys
from pathlib import Path

CONFIG = Path.home() / ".config/ai-limits/providers.json"

DEFAULT_PROVIDERS = [
    {"id": "openai", "name": "ChatGPT", "icon": "👾", "source": "codex_rpc", "enabled": True},
    {"id": "claude", "name": "Claude", "icon": "✴️", "source": "claude_cache", "enabled": True},
    {"id": "zai-coding", "name": "GLM", "icon": "ⓩ", "source": "glm_quota", "enabled": True},
    {"id": "deepseek", "name": "DeepSeek", "icon": "🐋", "source": "deepseek_balance", "enabled": False},
    {"id": "gemini", "name": "Gemini", "icon": "💎", "source": "usage_events", "enabled": False},
    {"id": "grok", "name": "Grok", "icon": "𝕏", "source": "usage_events", "enabled": False},
    {"id": "qwen-plan", "name": "Qwen", "icon": "🌐", "source": "usage_events", "enabled": False},
    {"id": "openrouter", "name": "OpenRouter", "icon": "🔀", "source": "usage_events", "enabled": False},
    {"id": "mistral", "name": "Mistral", "icon": "🌪️", "source": "usage_events", "enabled": False},
    {"id": "llama", "name": "Llama", "icon": "🦙", "source": "usage_events", "enabled": False},
]


def load():
    try:
        return json.loads(CONFIG.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        save(DEFAULT_PROVIDERS)
        return DEFAULT_PROVIDERS


def save(providers):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(providers, indent=2, ensure_ascii=False))


def find(providers, provider_id):
    for p in providers:
        if p["id"] == provider_id:
            return p
    return None


def cmd_list():
    providers = load()
    print(f"{'ID':<15} {'NAME':<15} {'ICON':<5} {'VISIBLE':<8}")
    print("-" * 45)
    for p in providers:
        status = "✅" if p["enabled"] else "❌"
        print(f'{p["id"]:<15} {p["name"]:<15} {p["icon"]:<5} {status}')


def cmd_show(provider_id):
    providers = load()
    p = find(providers, provider_id)
    if p:
        p["enabled"] = True
        save(providers)
        print(f'✅ {p["name"]} shown')
    else:
        print(f"❌ not found: {provider_id}")


def cmd_hide(provider_id):
    providers = load()
    p = find(providers, provider_id)
    if p:
        p["enabled"] = False
        save(providers)
        print(f'🚫 {p["name"]} hidden')
    else:
        print(f"❌ not found: {provider_id}")


def cmd_remove(provider_id):
    providers = load()
    p = find(providers, provider_id)
    if p:
        providers.remove(p)
        save(providers)
        print(f'🗑️ {p["name"]} removed')
    else:
        print(f"❌ not found: {provider_id}")


def cmd_add(provider_id, name=None, icon=None, source="usage_events"):
    providers = load()
    if find(providers, provider_id):
        print(f"❌ already exists: {provider_id}")
        return
    p = {
        "id": provider_id,
        "name": name or provider_id.title(),
        "icon": icon or "🔹",
        "source": source,
        "enabled": True,
    }
    providers.append(p)
    save(providers)
    print(f'✅ {p["name"]} added')


def cmd_available():
    existing = {p["id"] for p in load()}
    for p in DEFAULT_PROVIDERS:
        mark = "already" if p["id"] in existing else "available"
        print(f'{p["icon"]} {p["name"]:<15} id={p["id"]:<15} {mark}')


def main():
    if len(sys.argv) < 2:
        print("Usage: manage.py <command> [args]")
        print("Commands: list, available, show <id>, hide <id>, remove <id>, add <id> [name] [icon]")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list()
    elif cmd == "available":
        cmd_available()
    elif cmd == "show" and len(sys.argv) > 2:
        cmd_show(sys.argv[2])
    elif cmd == "hide" and len(sys.argv) > 2:
        cmd_hide(sys.argv[2])
    elif cmd == "remove" and len(sys.argv) > 2:
        cmd_remove(sys.argv[2])
    elif cmd == "add" and len(sys.argv) > 2:
        name = sys.argv[3] if len(sys.argv) > 3 else None
        icon = sys.argv[4] if len(sys.argv) > 4 else None
        cmd_add(sys.argv[2], name, icon)
    else:
        print("Unknown command")


if __name__ == "__main__":
    main()
