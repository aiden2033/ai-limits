# AI Limits for xbar and Windows

AI Limits shows AI provider limits and balances on macOS and Windows. It displays 5-hour and weekly remaining percentages, reset timers, DeepSeek balance, and token usage for providers tracked by Codex Router.

## Install

1. Install [xbar](https://xbarapp.com/).
2. Copy `ai-limits.5m.py` and `ai_limits_core.py` to `~/Library/Application Support/xbar/plugins/`, then make `ai-limits.5m.py` executable.
3. Copy `manage.py` to `~/.ai-limits-bin/manage` and make it executable.
4. Refresh plugins in xbar.

```bash
mkdir -p "$HOME/Library/Application Support/xbar/plugins" "$HOME/.ai-limits-bin"
cp ai-limits.5m.py ai_limits_core.py "$HOME/Library/Application Support/xbar/plugins/"
cp manage.py "$HOME/.ai-limits-bin/manage"
chmod +x "$HOME/Library/Application Support/xbar/plugins/ai-limits.5m.py" "$HOME/.ai-limits-bin/manage"
```

The provider menu is available under **Manage Providers**. The adjacent **Обновить** item immediately reruns the widget and fetches current limits.

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
