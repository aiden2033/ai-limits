#!/usr/bin/env python3

import json
import math
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MSK = timezone(timedelta(hours=3))
USAGE_EVENTS = Path.home() / ".codex/codex-router/usage-events.jsonl"
CLAUDE_CONFIG = Path.home() / ".claude.json"
MACOS_CODEX_BIN = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
CODEX_BIN = os.environ.get("AI_LIMITS_CODEX_BIN") or shutil.which("codex") or MACOS_CODEX_BIN
CURL_BIN = os.environ.get("AI_LIMITS_CURL_BIN") or shutil.which("curl")
PROVIDERS_CONFIG = Path.home() / ".config/ai-limits/providers.json"
WIDGET_CONFIG = Path.home() / ".config/ai-limits/config.json"
GLM_KEY_FILE = Path.home() / ".codex/codex-router/zai-coding-api-key.secret"
DEEPSEEK_KEY_FILE = Path.home() / ".codex/codex-router/deepseek-api-key.secret"
GLM_QUOTA_PATH = "/api/monitor/usage/quota/limit"
GLM_DOMAINS = {"https://api.z.ai", "https://open.bigmodel.cn"}


def load_json_file(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def load_providers():
    data = load_json_file(PROVIDERS_CONFIG)
    if isinstance(data, list):
        return [provider for provider in data if isinstance(provider, dict) and provider.get("enabled")]
    return []


def load_all_providers():
    data = load_json_file(PROVIDERS_CONFIG)
    return data if isinstance(data, list) else []


def save_providers(providers):
    PROVIDERS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = PROVIDERS_CONFIG.with_name(f".{PROVIDERS_CONFIG.name}.tmp")
    temporary.write_text(json.dumps(providers, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(PROVIDERS_CONFIG)


def set_provider_enabled(provider_id, enabled):
    providers = load_all_providers()
    provider = next((item for item in providers if item.get("id") == provider_id), None)
    if provider is None:
        return False
    provider["enabled"] = enabled
    save_providers(providers)
    return True


def calc_usage(provider_id, usage_events=USAGE_EVENTS):
    now = datetime.now(MSK)
    h5_start = now - timedelta(hours=5)
    week_start = now - timedelta(days=7)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    h5 = {"tokens": 0, "requests": 0}
    week = {"tokens": 0, "requests": 0}
    today = {"tokens": 0, "requests": 0}
    try:
        with open(usage_events, encoding="utf-8") as events:
            for line in events:
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
                except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                    continue
    except (FileNotFoundError, OSError):
        pass
    return {"h5": h5, "week": week, "today": today}


def fmt_tokens(count):
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.0f}K"
    return str(count)


def terminate_process_tree(proc):
    windows = os.name == "nt"
    if windows:
        completed = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode == 0:
            proc.wait(timeout=3)
            return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def get_codex_rpc_limits(codex_bin=CODEX_BIN):
    if not codex_bin:
        return {}
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            [codex_bin, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=creation_flags,
        )
        result = {}

        def send(message):
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()

        send({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "ai-limits", "version": "1.0"}},
        })

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

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()
        time.sleep(2)
        send({"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": {}})
        reader_thread.join(timeout=10)
        terminate_process_tree(proc)

        limits = result.get("rateLimits", {})
        primary = limits.get("primary", {})
        secondary = limits.get("secondary", {})
        return {
            "h5_pct": 100 - primary.get("usedPercent", 100),
            "week_pct": 100 - secondary.get("usedPercent", 100),
            "h5_reset_ts": primary.get("resetsAt"),
            "week_reset_ts": secondary.get("resetsAt"),
        }
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
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
    if not url.startswith("https://"):
        raise ValueError("Поддерживаются только HTTPS-запросы.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    headers.update(extra_headers or {})
    if CURL_BIN:
        try:
            response = subprocess.run(
                [CURL_BIN, "-q", "--silent", "--show-error", "--fail",
                 "--max-time", "12", "--proto", "=https", "--header", "@-",
                 "--write-out", "\n%{http_code}", url],
                input="".join(f"{name}: {value}\n" for name, value in headers.items()),
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("Сервис не ответил. Повтори позже.") from error
        body, separator, status = response.stdout.rpartition("\n")
        if response.returncode:
            messages = {
                "401": "Ключ недействителен или истёк (HTTP 401).",
                "403": "Нет доступа к квоте (HTTP 403).",
                "429": "Сервис ограничил частоту проверок (HTTP 429).",
            }
            raise ValueError(messages.get(status, "Запрос не прошёл. Проверь ключ и сеть."))
        return json.loads(body if separator and len(status) == 3 and status.isdigit() else response.stdout)
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        messages = {
            401: "Ключ недействителен или истёк (HTTP 401).",
            403: "Нет доступа к квоте (HTTP 403).",
            429: "Сервис ограничил частоту проверок (HTTP 429).",
        }
        raise ValueError(messages.get(error.code, "Запрос не прошёл. Проверь ключ и сеть.")) from None
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError("Сервис не ответил. Повтори позже.") from error


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
    domain = str(config.get("base_url", "https://api.z.ai")).rstrip("/")
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
        token = os.environ.get("ZAI_API_KEY") or key_path.read_text(encoding="utf-8").strip()
        return parse_glm_limits(request_json(url, token, headers))
    except FileNotFoundError:
        return {"quota_error": "Добавь API key GLM через Подключения."}
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
                item[target] = str(decimal_value(entry.get(field)))
        balances.append(item)
    if not balances:
        raise ValueError("DeepSeek не вернул баланс в USD или CNY.")
    return {"balances": balances, "is_available": payload["is_available"]}


def get_deepseek_balance():
    try:
        token = os.environ.get("DEEPSEEK_API_KEY") or DEEPSEEK_KEY_FILE.read_text(encoding="utf-8").strip()
        return parse_deepseek_balance(request_json("https://api.deepseek.com/user/balance", token))
    except FileNotFoundError:
        return {"quota_error": "Добавь API key DeepSeek."}
    except (ValueError, OSError, TypeError, AttributeError) as error:
        return {"quota_error": safe_error(error, "DeepSeek")}


def fetch_provider_data(provider):
    source = provider.get("source", "usage_events")
    provider_id = provider["id"]
    return {
        "codex_rpc": lambda: {**get_usage_data("openai"), **get_codex_rpc_limits()},
        "claude_cache": get_claude_data,
        "glm_quota": get_glm_limits,
        "deepseek_balance": get_deepseek_balance,
    }.get(source, lambda: get_usage_data(provider_id))()


def fetch_all_providers(providers):
    result = []
    for provider in providers:
        try:
            data = fetch_provider_data(provider)
        except Exception as error:
            data = {"quota_error": safe_error(error, provider.get("name", provider.get("id", "Provider")))}
        result.append((provider, data))
    return result


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


def provider_status(data):
    if data.get("quota_error"):
        return str(data["quota_error"])
    if data.get("balances"):
        totals = " / ".join(format_money(item["total"], item["currency"]) for item in data["balances"])
        return f"{totals} · unavailable" if data.get("is_available") is False else totals

    parts = []
    if data.get("h5_pct") is not None:
        parts.append(f"5h {data['h5_pct']:.0f}%")
    elif "h5_tokens" in data:
        parts.append(f"5h {fmt_tokens(data['h5_tokens'])}/{data['h5_requests']} req")
    if data.get("week_pct") is not None:
        parts.append(f"7d {data['week_pct']:.0f}%")
    elif "week_tokens" in data:
        parts.append(f"7d {fmt_tokens(data['week_tokens'])}/{data['week_requests']} req")

    reset = data.get("h5_reset") or data.get("h5_reset_ts")
    if reset:
        suffix = time_until_iso(reset) if isinstance(reset, str) else time_until_ts(reset)
        parts.append(f"reset {suffix}")
    return " · ".join(parts) if parts else "нет данных"


def minimum_remaining_percent(provider_results):
    percentages = []
    for _, data in provider_results:
        for field in ("h5_pct", "week_pct"):
            value = number(data.get(field))
            if value is not None:
                percentages.append(value)
    return min(percentages) if percentages else None
