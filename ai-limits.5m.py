#!/usr/bin/env python3
# <xbar.title>AI Limits</xbar.title>
# <xbar.version>v3.2.0</xbar.version>
# <xbar.desc>Multi-provider AI subscription limits</xbar.desc>

import json
import math
import os
import subprocess
import threading
import time
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
from pathlib import Path

MSK = timezone(timedelta(hours=3))
USAGE_EVENTS = Path.home() / ".codex/codex-router/usage-events.jsonl"
CLAUDE_CONFIG = Path.home() / ".claude.json"
CODEX_BIN = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
PROVIDERS_CONFIG = Path.home() / ".config/ai-limits/providers.json"
MANAGE_SCRIPT = str(Path.home() / ".ai-limits-bin" / "manage")
WIDGET_CONFIG = Path.home() / ".config/ai-limits/config.json"
GLM_KEY_FILE = Path.home() / ".codex/codex-router/zai-coding-api-key.secret"
DEEPSEEK_KEY_FILE = Path.home() / ".codex/codex-router/deepseek-api-key.secret"
GLM_QUOTA_PATH = "/api/monitor/usage/quota/limit"
GLM_DOMAINS = {"https://api.z.ai", "https://open.bigmodel.cn"}


def load_json_file(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_providers():
    data = load_json_file(PROVIDERS_CONFIG)
    if data and isinstance(data, list):
        return [p for p in data if p.get("enabled")]
    return []


def load_all_providers():
    data = load_json_file(PROVIDERS_CONFIG)
    return data if isinstance(data, list) else []


def calc_usage(provider_id):
    now = datetime.now(MSK)
    h5_start = now - timedelta(hours=5)
    week_start = now - timedelta(days=7)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    h5 = {"tokens": 0, "requests": 0}
    week = {"tokens": 0, "requests": 0}
    today = {"tokens": 0, "requests": 0}
    try:
        with open(USAGE_EVENTS) as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get("provider") != provider_id:
                        continue
                    at = datetime.fromisoformat(event["at"].replace("Z", "+00:00")).astimezone(MSK)
                    tokens = event.get("totalTokens", 0)
                    if at >= h5_start:
                        h5["tokens"] += tokens
                        h5["requests"] += 1
                    if at >= week_start:
                        week["tokens"] += tokens
                        week["requests"] += 1
                    if at >= today_start:
                        today["tokens"] += tokens
                        today["requests"] += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except FileNotFoundError:
        pass
    return {"h5": h5, "week": week, "today": today}


def fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def get_codex_rpc_limits():
    try:
        proc = subprocess.Popen(
            [CODEX_BIN, "app-server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
        )
        result = {}

        def send(msg):
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "ai-limits", "version": "1.0"}}})

        def reader():
            nonlocal result
            for line in proc.stdout:
                try:
                    data = json.loads(line.strip())
                    if data.get("id") == 2:
                        result = data.get("result", {})
                        break
                except (json.JSONDecodeError, ValueError):
                    continue

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        time.sleep(2)
        send({"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": {}})
        t.join(timeout=10)
        proc.terminate()
        proc.wait(timeout=3)

        limits = result.get("rateLimits", {})
        primary = limits.get("primary", {})
        secondary = limits.get("secondary", {})
        return {
            "h5_pct": 100 - primary.get("usedPercent", 100),
            "week_pct": 100 - secondary.get("usedPercent", 100),
            "h5_reset_ts": primary.get("resetsAt"),
            "week_reset_ts": secondary.get("resetsAt"),
        }
    except Exception:
        return {}


def get_claude_data():
    config = load_json_file(CLAUDE_CONFIG) or {}
    usage = config.get("cachedUsageUtilization", {}).get("utilization", {})
    five_hour = usage.get("five_hour", {})
    seven_day = usage.get("seven_day", {})
    h5_used = five_hour.get("utilization", 0)
    week_used = seven_day.get("utilization", 0)
    return {
        "h5_pct": 100 - h5_used if h5_used else None,
        "week_pct": 100 - week_used if week_used else None,
        "h5_reset": five_hour.get("resets_at"),
        "week_reset": seven_day.get("resets_at"),
    }


def get_usage_data(provider_id):
    usage = calc_usage(provider_id)
    return {
        "h5_tokens": usage["h5"]["tokens"],
        "h5_requests": usage["h5"]["requests"],
        "week_tokens": usage["week"]["tokens"],
        "week_requests": usage["week"]["requests"],
        "today_tokens": usage["today"]["tokens"],
        "today_requests": usage["today"]["requests"],
    }


def number(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (ValueError, TypeError):
        return None


def safe_error(error, provider):
    if isinstance(error, json.JSONDecodeError):
        return f"{provider}: некорректный ответ сервиса."
    return str(error)


def request_json(url, token, extra_headers=None):
    if not token or any(char.isspace() for char in token):
        raise ValueError("Некорректный ключ или токен.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    headers.update(extra_headers or {})
    response = subprocess.run(
        ["/usr/bin/curl", "-q", "--silent", "--show-error", "--fail",
         "--max-time", "12", "--proto", "=https", "--header", "@-",
         "--write-out", "\n%{http_code}", url],
        input="".join(f"{name}: {value}\n" for name, value in headers.items()),
        capture_output=True, text=True, timeout=15,
    )
    body, separator, status = response.stdout.rpartition("\n")
    if response.returncode:
        errors = {
            "401": "Ключ недействителен или истёк (HTTP 401).",
            "403": "Нет доступа к квоте (HTTP 403).",
            "429": "Сервис ограничил частоту проверок (HTTP 429).",
        }
        raise ValueError(errors.get(status, "Запрос не прошёл. Проверь ключ и сеть."))
    return json.loads(body if separator and len(status) == 3 and status.isdigit() else response.stdout)


def parse_glm_limits(payload):
    if not isinstance(payload, dict):
        raise ValueError("Invalid quota response")
    if payload.get("success") is not True or payload.get("code") != 200:
        if "coding plan" in str(payload.get("msg", "")).lower():
            raise ValueError("Квота не найдена для выбранного типа плана. Для Team нужны организация и проект.")
        raise ValueError("Z.ai rejected the quota request")
    result = {}
    for limit in (payload.get("data") or {}).get("limits", []):
        if not isinstance(limit, dict) or limit.get("type") not in {"TOKENS_LIMIT", "CREDIT_LIMIT"}:
            continue
        window = (number(limit.get("unit")), number(limit.get("number")))
        prefix = {(3, 5): "h5", (6, 1): "week"}.get(window)
        if prefix is None and "unit" not in limit and "number" not in limit:
            prefix = "h5" if limit.get("type") == "TOKENS_LIMIT" else None
        if prefix is None:
            continue
        used = number(limit.get("percentage"))
        allowance, consumed = number(limit.get("usage")), number(limit.get("currentValue"))
        if allowance is not None and allowance > 0 and consumed is not None:
            used = consumed / allowance * 100
        if used is None:
            continue
        result[f"{prefix}_pct"] = round(100 - min(100, max(0, used)), 1)
        reset = number(limit.get("nextResetTime"))
        if reset is not None and reset > 0:
            result[f"{prefix}_reset_ts"] = reset / 1000
    if not result:
        raise ValueError("No supported quota windows returned")
    return result


def glm_quota_request(config):
    domain = config.get("base_url", "https://api.z.ai").rstrip("/")
    if domain not in GLM_DOMAINS:
        raise ValueError("Unsupported GLM quota host")
    plan_type = config.get("plan_type", "personal")
    if plan_type == "personal":
        return domain + GLM_QUOTA_PATH, {}
    if plan_type != "team":
        raise ValueError("Неизвестный тип GLM Coding Plan.")
    headers = {}
    for field, header in [("organization_id", "Bigmodel-Organization"), ("project_id", "Bigmodel-Project")]:
        value = config.get(field)
        if not isinstance(value, str) or not value or any(char.isspace() for char in value):
            raise ValueError("Для Team Plan укажи organization_id и project_id в настройках виджета.")
        headers[header] = value
    return domain + GLM_QUOTA_PATH + "?type=2", headers


def get_glm_limits():
    try:
        config = (load_json_file(WIDGET_CONFIG) or {}).get("glm", {})
        url, headers = glm_quota_request(config)
        key_path = Path(config.get("api_key_file", str(GLM_KEY_FILE))).expanduser()
        token = os.environ.get("ZAI_API_KEY") or key_path.read_text().strip()
        return parse_glm_limits(request_json(url, token, headers))
    except FileNotFoundError:
        return {"quota_error": "Добавь API key GLM через Подключения."}
    except subprocess.TimeoutExpired:
        return {"quota_error": "GLM не ответил. Повтори позже."}
    except (ValueError, OSError, TypeError, AttributeError) as error:
        return {"quota_error": safe_error(error, "GLM")}


def decimal_value(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Сервис вернул некорректный баланс.")
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation()
        return result
    except InvalidOperation:
        raise ValueError("Сервис вернул некорректный баланс.") from None


def format_money(value, currency):
    amount = decimal_value(value)
    digits = 6 if 0 < abs(amount) < Decimal("0.01") else 2
    symbol = {"USD": "$", "CNY": "¥"}[currency]
    return f"{symbol}{amount:.{digits}f}"


def parse_deepseek_balance(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("is_available"), bool):
        raise ValueError("DeepSeek не вернул баланс аккаунта.")
    balances = []
    for entry in payload.get("balance_infos") or []:
        if not isinstance(entry, dict) or entry.get("currency") not in {"USD", "CNY"}:
            continue
        item = {"currency": entry["currency"], "total": str(decimal_value(entry.get("total_balance")))}
        for field, target in [("granted_balance", "granted"), ("topped_up_balance", "topped_up")]:
            if entry.get(field) is not None:
                item[target] = str(decimal_value(entry[field]))
        balances.append(item)
    if not balances:
        raise ValueError("DeepSeek не вернул баланс в USD или CNY.")
    return {"balances": balances, "is_available": payload["is_available"]}


def get_deepseek_balance():
    try:
        token = os.environ.get("DEEPSEEK_API_KEY") or DEEPSEEK_KEY_FILE.read_text().strip()
        return parse_deepseek_balance(request_json("https://api.deepseek.com/user/balance", token))
    except FileNotFoundError:
        return {"quota_error": "Добавь API key DeepSeek."}
    except subprocess.TimeoutExpired:
        return {"quota_error": "DeepSeek не ответил. Повтори позже."}
    except (ValueError, OSError, TypeError, AttributeError) as error:
        return {"quota_error": safe_error(error, "DeepSeek")}


def fetch_provider_data(provider):
    source = provider.get("source", "usage_events")
    provider_id = provider["id"]

    if source == "codex_rpc":
        return {**get_usage_data("openai"), **get_codex_rpc_limits()}
    elif source == "claude_cache":
        return get_claude_data()
    elif source == "glm_quota":
        return get_glm_limits()
    elif source == "deepseek_balance":
        return get_deepseek_balance()
    else:
        return get_usage_data(provider_id)


def time_until_iso(iso_str):
    try:
        reset = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        diff = reset - datetime.now(timezone.utc)
        if diff.total_seconds() <= 0:
            return "now"
        hours = diff.total_seconds() / 3600
        if hours < 1:
            return f"{int(hours * 60)}m"
        if hours < 24:
            return f"{int(hours)}h"
        return f"{hours / 24:.1f}d"
    except (ValueError, TypeError):
        return "?"


def time_until_ts(ts):
    try:
        return time_until_iso(datetime.fromtimestamp(ts, tz=timezone.utc).isoformat())
    except (ValueError, TypeError, OSError):
        return "?"


def color(remaining_pct):
    if remaining_pct > 50:
        return "#34c759"
    if remaining_pct > 20:
        return "#ff9f0a"
    return "#ff3b30"


def bar(pct):
    return "█" * (pct // 10) + "░" * (10 - pct // 10)


def render_manage_menu():
    lines = ["---", "⚙️ Manage Providers", "🔄 Обновить | refresh=true"]
    all_providers = load_all_providers()

    for p in all_providers:
        status = "✅" if p.get("enabled") else "❌"
        action = "hide" if p.get("enabled") else "show"
        action_label = "🚫 Hide" if p.get("enabled") else "👁 Show"
        lines.append(f'--{status} {p["icon"]} {p["name"]}')
        lines.append(f'----{action_label} | shell={MANAGE_SCRIPT} param1={action} param2={p["id"]} terminal=false refresh=true')
        lines.append(f'----🗑️ Remove | shell={MANAGE_SCRIPT} param1=remove param2={p["id"]} terminal=false refresh=true')

    return lines


def render():
    providers = load_providers()
    if not providers:
        print("⚙️ | font=:menlo:")
        print("---")
        print("Run: python3 manage.py add openai")
        return

    lines = []
    bar_parts = []
    provider_data = []

    for p in providers:
        data = fetch_provider_data(p)
        provider_data.append((p, data))

        bar_parts.append(p["icon"])

    lines.append(" ".join(bar_parts) + " | font=:menlo: size=13")

    for p, data in provider_data:
        lines.append("---")
        icon, name = p["icon"], p["name"]

        if data.get("quota_error"):
            lines.append(f"{icon} {name}: quota unavailable | color=#ff9f0a")
            lines.append(f'  {data["quota_error"]} | size=11 font=:menlo: color=#888')
            continue

        if data.get("balances"):
            totals = " / ".join(format_money(b["total"], b["currency"]) for b in data["balances"])
            balance_color = "#34c759" if data.get("is_available") is not False else "#ff3b30"
            lines.append(f"{icon} {name}: {totals} | font=:menlo: color={balance_color}")
            if data.get("is_available") is False:
                lines.append("  Баланс недостаточен для запросов | size=11 font=:menlo: color=#ff3b30")
            continue

        h5_pct = data.get("h5_pct")
        week_pct = data.get("week_pct")

        if h5_pct is not None:
            lines.append(f"{icon} {name} 5h: {bar(int(h5_pct))} {int(h5_pct)}% left | font=:menlo: color={color(h5_pct)}")
        elif "h5_tokens" in data:
            lines.append(f"{icon} {name} 5h: {fmt_tokens(data['h5_tokens'])} ({data['h5_requests']} req) | font=:menlo:")

        if week_pct is not None:
            lines.append(f"{icon} {name} 7d: {bar(int(week_pct))} {int(week_pct)}% left | font=:menlo: color={color(week_pct)}")
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

    lines.extend(render_manage_menu())
    print("\n".join(lines))


if __name__ == "__main__":
    render()
