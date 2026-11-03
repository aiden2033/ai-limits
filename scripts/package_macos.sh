#!/bin/bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="$root/dist/ai-limits-macos.zip"
staging_root="$(mktemp -d)"
staging="$staging_root/ai-limits-macos"

mkdir -p "$staging" "$root/dist"
cp "$root/ai-limits.5m.py" "$staging/"
cp "$root/ai_limits_core.py" "$staging/"
cp "$root/manage.py" "$staging/"
cp "$root/config.example.json" "$staging/"
cp "$root/README.md" "$staging/"
chmod +x "$staging/ai-limits.5m.py" "$staging/manage.py"
rm -f "$output"
(cd "$staging_root" && /usr/bin/zip -q -r -X "$output" "$(basename "$staging")")
shasum -a 256 "$output" > "$output.sha256"
