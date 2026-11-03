# AI Limits for xbar and Windows

AI Limits shows AI provider limits and balances on macOS and Windows. It displays 5-hour and weekly remaining percentages, reset timers, DeepSeek balance, and token usage for providers tracked by Codex Router.

## Install

1. Install [xbar](https://xbarapp.com/).
2. Copy `ai-limits.5m.py` to `~/Library/Application Support/xbar/plugins/` and make it executable.
3. Copy `ai_limits_core.py` to `~/.ai-limits-bin/` and `manage.py` to `~/.ai-limits-bin/manage`, then make `manage` executable.
4. Refresh plugins in xbar.

```bash
mkdir -p "$HOME/Library/Application Support/xbar/plugins" "$HOME/.ai-limits-bin"
cp ai-limits.5m.py "$HOME/Library/Application Support/xbar/plugins/"
cp ai_limits_core.py "$HOME/.ai-limits-bin/"
cp manage.py "$HOME/.ai-limits-bin/manage"
chmod +x "$HOME/Library/Application Support/xbar/plugins/ai-limits.5m.py" "$HOME/.ai-limits-bin/manage"
```

The provider menu is available under **Manage Providers**. The adjacent **Обновить** item immediately reruns the widget and fetches current limits.

When upgrading an older install, move any `ai_limits_core.py` from the xbar plugins folder to `~/.ai-limits-bin/`. xbar otherwise tries to execute this helper as another widget and reports a permission error.

## Claude Code

Sign in with `claude auth login`, then use **Manage Providers → Подключить → Claude Code**, or run `~/.ai-limits-bin/manage add claude-code`.

Claude percentages and reset times come from the account usage endpoint, using the existing Claude Code OAuth login. On macOS the widget reads the `Claude Code-credentials` Keychain item. It also supports `~/.claude/.credentials.json` (or `CLAUDE_CONFIG_DIR/.credentials.json`) and the `CLAUDE_CODE_OAUTH_TOKEN` environment variable. Credentials stay on the machine.

Both bars show **remaining** quota: 94% used in Claude means **6% left** in the widget. Zero usage means 100% left. Local transcript token counts are not subscription percentages.

Each refresh requests current limits. If the request fails, the widget can show saved percentages for up to 15 minutes, with a warning. Saved data is tied to the current credential and is discarded for a window once its reset time passes. Missing authorization or unavailable quota appears as an error instead of hiding Claude or substituting token counts. Existing `claude_cache` provider settings remain supported.

## Windows install

1. Download `ai-limits-windows.zip` from [releases](https://github.com/aiden2033/ai-limits/releases).
2. Extract `ai-limits.exe`.
3. Run the extracted executable.
4. Use the tray icon menu to refresh limits or manage providers.

Windows SmartScreen may show a confirmation for a newly published unsigned executable. Select **More info** → **Run anyway** only if you trust the release source.

## Configuration

Provider visibility is stored in `~/.config/ai-limits/providers.json` and is managed by `manage.py`:

```bash
~/.ai-limits-bin/manage list
~/.ai-limits-bin/manage show zai-coding
~/.ai-limits-bin/manage hide deepseek
```

Optional GLM settings are documented in `config.example.json`. API keys are read only from local secret files; no keys belong in this repository.

## Tests

```bash
python3 -m unittest -v
```

## Release builds

Tests, macOS packaging, and Windows packaging run automatically for tags starting with `v`. A published tag creates a GitHub Release with:

- `ai-limits-macos.zip`
- `ai-limits-windows.zip`
- SHA-256 checksums

You can also build both artifacts manually from GitHub → **Actions** → **AI Limits Release** → **Run workflow**. Manual runs upload workflow artifacts but do not publish a release.
