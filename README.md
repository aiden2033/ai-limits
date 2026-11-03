# AI Limits for xbar

An xbar menu-bar widget for AI provider limits and balances. It shows 5-hour and weekly remaining percentages, reset timers, DeepSeek balance, and token usage for providers tracked by Codex Router.

## Install

1. Install [xbar](https://xbarapp.com/).
2. Copy `ai-limits.5m.py` to `~/Library/Application Support/xbar/plugins/` and make it executable.
3. Copy `manage.py` to `~/.ai-limits-bin/manage` and make it executable.
4. Refresh plugins in xbar.

```bash
mkdir -p "$HOME/Library/Application Support/xbar/plugins" "$HOME/.ai-limits-bin"
cp ai-limits.5m.py "$HOME/Library/Application Support/xbar/plugins/"
cp manage.py "$HOME/.ai-limits-bin/manage"
chmod +x "$HOME/Library/Application Support/xbar/plugins/ai-limits.5m.py" "$HOME/.ai-limits-bin/manage"
```

The provider menu is available under **Manage Providers**. The adjacent **Обновить** item immediately reruns the widget and fetches current limits.

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
