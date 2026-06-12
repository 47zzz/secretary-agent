#!/bin/zsh
# 安裝秘書的 launchd 排程（早晨簡報 / 晚間回顧 / 週計畫）。
# 時間從 profile/profile.json 讀取；改了時間後重跑本腳本即可。
# 所有排程都是「時間到 → 執行幾秒 → 結束」，無常駐程序。
set -euo pipefail

DIR="${0:a:h:h}"          # 工作區根目錄（automation/ 的上一層）
PY="$(command -v python3)"
AGENTS_DIR="$HOME/Library/LaunchAgents"

if [[ -z "$PY" ]]; then
  echo "找不到 python3，請先安裝命令列開發者工具（xcode-select --install）"
  exit 1
fi

mkdir -p "$AGENTS_DIR" "$DIR/logs"

# 從 profile.json 讀排程時間（格式：BH BM RH RM WD WH WM）
TIMES="$("$PY" - "$DIR" <<'EOF'
import json, sys
prof = json.load(open(sys.argv[1] + "/profile/profile.json", encoding="utf-8"))
def hm(s, dh, dm):
    try:
        h, m = s.split(":"); return int(h), int(m)
    except Exception:
        return dh, dm
bh, bm = hm(prof.get("brief_time", "08:00"), 8, 0)
rh, rm = hm(prof.get("review_time", "21:30"), 21, 30)
wp = (prof.get("weekly_plan", "sun 20:00") or "sun 20:00").split()
wd_map = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
wd = wd_map.get(wp[0][:3].lower(), 0)
wh, wm = hm(wp[1] if len(wp) > 1 else "20:00", 20, 0)
print(bh, bm, rh, rm, wd, wh, wm)
EOF
)"
read -r BH BM RH RM WD WH WM <<< "$TIMES"

install_one() {
  local name="$1" hour="$2" minute="$3" weekday="${4:-}"
  local src="$DIR/automation/com.secretary.$name.plist"
  local dst="$AGENTS_DIR/com.secretary.$name.plist"
  sed -e "s|__PYTHON__|$PY|g" \
      -e "s|__DIR__|$DIR|g" \
      -e "s|__HOUR__|$hour|g" \
      -e "s|__MINUTE__|$minute|g" \
      -e "s|__WEEKDAY__|$weekday|g" \
      "$src" > "$dst"
  launchctl bootout "gui/$(id -u)/com.secretary.$name" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dst"
  echo "  ✓ com.secretary.$name"
}

echo "安裝 launchd 排程…"
install_one morning  "$BH" "$BM"
install_one evening  "$RH" "$RM"
install_one weekly   "$WH" "$WM" "$WD"
install_one autosync 0 0   # 監聽 tasks.json：一變動就自動同步（即時感的來源）

echo ""
printf "完成。早晨 %02d:%02d / 晚間 %02d:%02d / 週計畫 週%s %02d:%02d\n" \
  "$BH" "$BM" "$RH" "$RM" "$WD" "$WH" "$WM"
echo "autosync：tasks.json 一有變動秒級觸發；每 30 分鐘也會自動對齊遠端。"
echo "提示：第一次自動執行時，macOS 可能會詢問 python3 的自動化權限，請允許。"
echo "立刻試跑一次：python3 \"$DIR/scripts/secretary.py\" morning"
