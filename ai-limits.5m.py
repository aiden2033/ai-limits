#!/usr/bin/env python3
# <xbar.title>AI Limits</xbar.title>
# <xbar.version>v4.0.0</xbar.version>
# <xbar.desc>Multi-provider AI subscription limits</xbar.desc>

from pathlib import Path

from ai_limits_core import (
    bar,
    color,
    fetch_all_providers,
    fmt_tokens,
    format_money,
    load_all_providers,
    load_providers,
    time_until_iso,
    time_until_ts,
)

MANAGE_SCRIPT = str(Path.home() / ".ai-limits-bin" / "manage")


def render_manage_menu():
    lines = ["---", "⚙️ Manage Providers", "🔄 Обновить | refresh=true"]
    all_providers = load_all_providers()

    for provider in all_providers:
        status = "✅" if provider.get("enabled") else "❌"
        action = "hide" if provider.get("enabled") else "show"
        action_label = "🚫 Hide" if provider.get("enabled") else "👁 Show"
        lines.append(f'--{status} {provider["icon"]} {provider["name"]}')
        lines.append(
            f'----{action_label} | shell={MANAGE_SCRIPT} '
            f'param1={action} param2={provider["id"]} terminal=false refresh=true'
        )
        lines.append(
            f'----🗑️ Remove | shell={MANAGE_SCRIPT} '
            f'param1=remove param2={provider["id"]} terminal=false refresh=true'
        )

    return lines


def render_provider(provider, data):
    icon, name = provider["icon"], provider["name"]
    if data.get("quota_error"):
        return [
            f"{icon} {name}: quota unavailable | color=#ff9f0a",
            f'  {data["quota_error"]} | size=11 font=:menlo: color=#888',
        ]

    if data.get("balances"):
        totals = " / ".join(format_money(item["total"], item["currency"]) for item in data["balances"])
        balance_color = "#34c759" if data.get("is_available") is not False else "#ff3b30"
        lines = [f"{icon} {name}: {totals} | font=:menlo: color={balance_color}"]
        if data.get("is_available") is False:
            lines.append("  Баланс недостаточен для запросов | size=11 font=:menlo: color=#ff3b30")
        return lines

    lines = []
    h5_pct = data.get("h5_pct")
    week_pct = data.get("week_pct")

    if h5_pct is not None:
        lines.append(
            f"{icon} {name} 5h: {bar(int(h5_pct))} {int(h5_pct)}% left | "
            f"font=:menlo: color={color(h5_pct)}"
        )
    elif "h5_tokens" in data:
        lines.append(f"{icon} {name} 5h: {fmt_tokens(data['h5_tokens'])} ({data['h5_requests']} req) | font=:menlo:")

    if week_pct is not None:
        lines.append(
            f"{icon} {name} 7d: {bar(int(week_pct))} {int(week_pct)}% left | "
            f"font=:menlo: color={color(week_pct)}"
        )
    elif "week_tokens" in data:
        lines.append(f"{icon} {name} 7d: {fmt_tokens(data['week_tokens'])} ({data['week_requests']} req) | font=:menlo:")

    h5_reset = data.get("h5_reset")
    h5_reset_ts = data.get("h5_reset_ts")
    week_reset = data.get("week_reset")
    week_reset_ts = data.get("week_reset_ts")

    if h5_reset:
        lines.append(f'  5h resets in {time_until_iso(h5_reset)} | size=11 font=:menlo: color=#888')
    elif h5_reset_ts:
        lines.append(f'  5h resets in {time_until_ts(h5_reset_ts)} | size=11 font=:menlo: color=#888')

    if week_reset:
        lines.append(f'  7d resets in {time_until_iso(week_reset)} | size=11 font=:menlo: color=#888')
    elif week_reset_ts:
        lines.append(f'  7d resets in {time_until_ts(week_reset_ts)} | size=11 font=:menlo: color=#888')

    return lines


def render():
    providers = load_providers()
    if not providers:
        print("⚙️ | font=:menlo:")
        print("---")
        print("Run: python3 manage.py add openai")
        return

    provider_results = fetch_all_providers(providers)
    lines = [" ".join(provider["icon"] for provider in providers) + " | font=:menlo: size=13"]
    for provider, data in provider_results:
        lines.append("---")
        lines.extend(render_provider(provider, data))

    lines.extend(render_manage_menu())
    print("\n".join(lines))


if __name__ == "__main__":
    render()
