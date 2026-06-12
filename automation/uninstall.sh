#!/bin/zsh
# 移除秘書的所有 launchd 排程。
set -uo pipefail

for name in morning evening weekly; do
  launchctl bootout "gui/$(id -u)/com.secretary.$name" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/com.secretary.$name.plist"
  echo "  ✓ 已移除 com.secretary.$name"
done
echo "完成。資料（tasks/、journal/ 等）都還在，只是不再自動執行。"
