#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秘書核心 CLI — 任務管理、簡報產生、Apple 雙向同步。

用法：python3 scripts/secretary.py <指令>，詳見 AGENTS.md。
設計約束：
- 只用標準函式庫（相容 macOS 內建 python3 / 3.9+），零安裝。
- 所有指令執行完即結束，無常駐程序。
- tasks/tasks.json 是唯一事實來源；schedule/ 下的檔案由本程式產生。
- 非 macOS 平台自動略過 Apple 同步，只操作檔案（方便在任何機器上開發測試）。
"""
import argparse
import datetime as dt
import html as _html
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys

# Windows 主控台預設編碼可能非 UTF-8，先行修正
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_PATH = os.path.join(BASE, "tasks", "tasks.json")
ARCHIVE_DIR = os.path.join(BASE, "tasks", "archive")
PROFILE_PATH = os.path.join(BASE, "profile", "profile.json")
SCHEDULE_DIR = os.path.join(BASE, "schedule")
INBOX_PATH = os.path.join(BASE, "inbox", "inbox.md")
IS_MAC = platform.system() == "Darwin"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ZH_WD = ["一", "二", "三", "四", "五", "六", "日"]

DEFAULT_PROFILE = {
    "onboarded": False,
    "name_call": "",
    "tone": "warm",
    "timezone": "Asia/Taipei",
    "wake_time": "08:00",
    "sleep_time": "00:00",
    "work_start": "09:30",
    "work_end": "18:00",
    "energy_peak": "morning",
    "brief_time": "08:00",
    "review_time": "21:30",
    "weekly_plan": "sun 20:00",
    "reminder_default_time": "09:00",
    "archive_after_days": 14,
    "stale_after_days": 7,
    "tags_common": [],
    "imessage_self": "",
    "push": {"reminders": True, "calendar": True, "notes_brief": True, "imessage_brief": False},
    "apple": {
        "list_inbox": "📥 收件匣",
        "list_managed": "🤖 秘書",
        "calendar": "秘書",
        "notes_folder": "秘書",
        "note_today": "📋 今日簡報",
        "note_week": "🗓 本週計畫",
    },
}

TAGLINES = [
    "把今天過好就夠了。",
    "先從最小的一步開始。",
    "完成比完美重要。",
    "留一點空白給意外。",
    "一次只做一件事。",
    "困難的事，趁精神好的時候做。",
    "小事立刻做，大事拆開做。",
]

PRAISES = [
    "做得好。",
    "又解決一件 ✨",
    "穩穩前進中。",
    "清單越來越輕了。",
    "不錯，繼續。",
]


# ================================================================ 檔案存取

def load_json(path, fallback):
    if not os.path.exists(path):
        return fallback
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_db():
    return load_json(TASKS_PATH, {"version": 1, "tasks": []})


def save_db(db):
    save_json_atomic(TASKS_PATH, db)


def _merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_profile():
    return _merge(DEFAULT_PROFILE, load_json(PROFILE_PATH, {}))


# ================================================================ 日期時間解析

WEEK_ZH_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
WEEK_EN_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def parse_date_token(s, today):
    """把日期記號轉成 date；解析失敗回傳 None。"""
    s = (s or "").strip().lower()
    if not s:
        return None
    if s in ("今天", "today"):
        return today
    if s in ("明天", "tomorrow", "tmr"):
        return today + dt.timedelta(days=1)
    if s in ("後天", "后天"):
        return today + dt.timedelta(days=2)
    if s in ("大後天", "大后天"):
        return today + dt.timedelta(days=3)
    m = re.fullmatch(r"(\d+)天[後后]", s)
    if m:
        return today + dt.timedelta(days=int(m.group(1)))
    m = re.fullmatch(r"(下)?(?:週|周|星期|禮拜)([一二三四五六日天])", s)
    if m:
        w = WEEK_ZH_MAP[m.group(2)]
        if m.group(1):  # 下週X＝下個日曆週的X
            next_mon = today + dt.timedelta(days=7 - today.weekday())
            return next_mon + dt.timedelta(days=w)
        return today + dt.timedelta(days=(w - today.weekday()) % 7)
    if s[:3] in WEEK_EN_MAP and re.fullmatch(r"[a-z]+", s):
        w = WEEK_EN_MAP[s[:3]]
        return today + dt.timedelta(days=(w - today.weekday()) % 7)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})", s)
    if m:
        try:
            d = dt.date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
        if d < today:
            d = dt.date(today.year + 1, d.month, d.day)
        return d
    return None


def parse_time_token(s):
    """把時間記號轉成 (hh, mm)；解析失敗回傳 None。"""
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if hh < 24 and mm < 60:
            return (hh, mm)
        return None
    m = re.fullmatch(r"(上午|早上|中午|下午|晚上)?(\d{1,2})[點点](半)?", s)
    if m:
        pre, hh, half = m.group(1), int(m.group(2)), m.group(3)
        if hh > 23:
            return None
        if pre in ("下午", "晚上") and hh < 12:
            hh += 12
        if pre == "中午" and hh == 12:
            hh = 12
        return (hh, 30 if half else 0)
    return None


def parse_when_token(body, today):
    """解析 @ 記號內容：可能是日期、時間、或「日期+時間」連寫。

    回傳 (date|None, (hh,mm)|None, 是否成功解析)。
    """
    t = parse_time_token(body)
    if t:
        return (None, t, True)
    d = parse_date_token(body, today)
    if d:
        return (d, None, True)
    m = re.fullmatch(r"(.*?)(\d{1,2}:\d{2})", body)
    if m and m.group(1):
        d = parse_date_token(m.group(1), today)
        t = parse_time_token(m.group(2))
        if d and t:
            return (d, t, True)
    m = re.fullmatch(r"(.*?)((?:上午|早上|中午|下午|晚上)?\d{1,2}[點点]半?)", body)
    if m and m.group(1):
        d = parse_date_token(m.group(1), today)
        t = parse_time_token(m.group(2))
        if d and t:
            return (d, t, True)
    return (None, None, False)


def parse_recur_token(s):
    if s in ("每天", "每日"):
        return "daily"
    m = re.fullmatch(r"每(?:週|周|星期|禮拜)([一二三四五六日天])", s)
    if m:
        return "weekly:{0}".format(WEEK_ZH_MAP[m.group(1)])
    m = re.fullmatch(r"每月(\d{1,2})[號号日]?", s)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            return "monthly:{0}".format(day)
    return None


def _month_day(year, month, day):
    """回傳該月的第 day 天，超出月底就取月底。"""
    if month > 12:
        year += (month - 1) // 12
        month = (month - 1) % 12 + 1
    next_month = dt.date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
    last = (next_month - dt.timedelta(days=1)).day
    return dt.date(year, month, min(day, last))


def recur_first_due(recur, today):
    kind, _, arg = recur.partition(":")
    if kind == "daily":
        return today
    if kind == "weekly":
        w = int(arg)
        return today + dt.timedelta(days=(w - today.weekday()) % 7)
    if kind == "monthly":
        d = _month_day(today.year, today.month, int(arg))
        if d < today:
            d = _month_day(today.year, today.month + 1, int(arg))
        return d
    return today


def recur_next_due(recur, after):
    """完成例行任務後，計算「嚴格在 after 之後」的下一次日期。"""
    kind, _, arg = recur.partition(":")
    if kind == "daily":
        return after + dt.timedelta(days=1)
    if kind == "weekly":
        w = int(arg)
        delta = (w - after.weekday()) % 7
        return after + dt.timedelta(days=delta or 7)
    if kind == "monthly":
        day = int(arg)
        d = _month_day(after.year, after.month, day)
        if d <= after:
            d = _month_day(after.year, after.month + 1, day)
        return d
    return after + dt.timedelta(days=1)


# ================================================================ 歸檔（保持系統乾淨）

def archive_old(db, prof, now=None):
    """把結案超過 archive_after_days 天的任務搬到 tasks/archive/<年>.json。

    tasks.json 上只留「還活著的事」＋近期結案（供統計回顧用），歷史紀錄不丟失。
    回傳歸檔件數。
    """
    now = now or dt.datetime.now()
    days = int(prof.get("archive_after_days", 14))
    cutoff = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    keep, old = [], []
    for t in db["tasks"]:
        if t.get("status") in ("done", "dropped") and (t.get("completed") or "") < cutoff \
                and t.get("completed"):
            old.append(t)
        else:
            keep.append(t)
    if not old:
        return 0
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    by_year = {}
    for t in old:
        by_year.setdefault(t["completed"][:4], []).append(t)
    for year, items in by_year.items():
        path = os.path.join(ARCHIVE_DIR, year + ".json")
        data = load_json(path, {"version": 1, "tasks": []})
        data["tasks"].extend(items)
        save_json_atomic(path, data)
    db["tasks"] = keep
    return len(old)


def task_age_days(t, today):
    try:
        return (today - dt.date.fromisoformat((t.get("created") or "")[:10])).days
    except ValueError:
        return 0


# ================================================================ git 同步（跨裝置的大腦同步，見 SYNC.md）

def _git(args_list, timeout=60):
    return subprocess.run(["git", "-C", BASE] + args_list,
                          capture_output=True, text=True, timeout=timeout)


def git_available():
    if not os.path.isdir(os.path.join(BASE, ".git")) or not shutil.which("git"):
        return False
    try:
        return bool(_git(["remote"]).stdout.strip())
    except Exception:
        return False


def git_pull(verbose=True):
    """工作開始前拉取遠端（手機端雲端 session 可能推過新狀態）。離線/失敗不阻擋。"""
    if not git_available():
        return False
    try:
        r = _git(["pull", "--rebase", "--autostash", "--quiet"], timeout=90)
        if r.returncode != 0:
            print("⚠️ git pull 失敗（離線？）：{0}".format((r.stderr or "").strip()[:150]))
            return False
        if verbose:
            print("🔄 已從遠端拉取最新狀態")
        return True
    except Exception as e:
        print("⚠️ git pull 失敗：{0}".format(e))
        return False


def git_commit_push(message, verbose=True):
    """工作結束後提交並推送，讓其他裝置上的 Claude 讀得到最新狀態。離線/失敗不阻擋。"""
    if not git_available():
        return False
    try:
        _git(["add", "-A"])
        staged = _git(["diff", "--cached", "--quiet"])
        if staged.returncode != 0:  # 有變更才 commit
            r = _git(["commit", "-m", message, "--quiet"])
            if r.returncode != 0:
                print("⚠️ git commit 失敗：{0}".format((r.stderr or "").strip()[:150]))
                return False
        r = _git(["push", "--quiet"], timeout=90)
        if r.returncode != 0:
            print("⚠️ git push 失敗（離線？下次會再試）")
            return False
        if verbose:
            print("☁️ 已推送到遠端（其他裝置的 Claude 可讀到最新狀態）")
        return True
    except Exception as e:
        print("⚠️ git push 失敗：{0}".format(e))
        return False


# ================================================================ 快速語法

def parse_quickadd(text, today=None):
    """解析「事情 @日期 @時間 !優先 #標籤 ~時長 每週X」快速語法。"""
    today = today or dt.date.today()
    title_words, tags = [], []
    due, time_, priority, duration, recur = None, None, 2, None, None
    for w in (text or "").split():
        if w.startswith("@") and len(w) > 1:
            d, t, ok = parse_when_token(w[1:], today)
            if ok:
                if d:
                    due = d
                if t:
                    time_ = "{0:02d}:{1:02d}".format(t[0], t[1])
                continue
            title_words.append(w)
        elif re.fullmatch(r"![123]", w):
            priority = int(w[1])
        elif w.startswith("#") and len(w) > 1:
            tags.append(w[1:])
        elif w.startswith("~") and len(w) > 1:
            m = re.fullmatch(r"~(\d+(?:\.\d+)?)(m|min|分鐘|分|h|hr|小時)?", w)
            if m:
                val = float(m.group(1))
                unit = m.group(2) or "m"
                duration = int(round(val * 60)) if unit in ("h", "hr", "小時") else int(round(val))
            else:
                title_words.append(w)
        elif w.startswith("每"):
            r = parse_recur_token(w)
            if r:
                recur = r
            else:
                title_words.append(w)
        else:
            title_words.append(w)
    if recur and due is None:
        due = recur_first_due(recur, today)
    return {
        "title": " ".join(title_words).strip(),
        "due": due.isoformat() if due else None,
        "time": time_,
        "duration_min": duration,
        "priority": priority,
        "tags": tags,
        "recur": recur,
        "type": "event" if ("行程" in tags) else "task",
        "horizon": "long" if ("長期" in tags or "長期計畫" in tags) else "short",
    }


def new_task(parsed, source="chat", now=None):
    now = now or dt.datetime.now()
    return {
        "id": "t-{0}-{1}".format(now.strftime("%m%d"), secrets.token_hex(2)),
        "title": parsed["title"],
        "notes": parsed.get("notes", ""),
        "due": parsed.get("due"),
        "time": parsed.get("time"),
        "duration_min": parsed.get("duration_min"),
        "type": parsed.get("type", "task"),
        "horizon": parsed.get("horizon", "short"),
        "priority": parsed.get("priority", 2),
        "energy": parsed.get("energy"),
        "tags": parsed.get("tags", []),
        "status": "open",
        "created": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "completed": None,
        "recur": parsed.get("recur"),
        "reminder_synced": False,
        "calendar_synced": False,
        "source": source,
    }


# ================================================================ 任務操作

def task_due_date(t):
    if not t.get("due"):
        return None
    try:
        return dt.date.fromisoformat(t["due"])
    except ValueError:
        return None


def open_tasks(db):
    return [t for t in db["tasks"] if t.get("status") == "open"]


def find_task(db, fragment):
    frag = (fragment or "").strip().lower()
    hits = [t for t in db["tasks"] if frag and frag in t["id"].lower()]
    open_hits = [t for t in hits if t.get("status") == "open"]
    pool = open_hits or hits
    if not pool:
        # 也允許用標題片段找（限未完成任務）
        pool = [t for t in open_tasks(db) if frag in t["title"].lower()]
    if len(pool) == 1:
        return pool[0]
    if not pool:
        raise SystemExit("找不到符合「{0}」的任務，先用 list 看看 id。".format(fragment))
    lines = ["「{0}」符合多筆，請更明確：".format(fragment)]
    for t in pool[:8]:
        lines.append("  {0}  {1}".format(t["id"], t["title"]))
    raise SystemExit("\n".join(lines))


def mark_done(db, task, now=None):
    """完成任務；例行任務自動產生下一次。回傳新產生的任務（或 None）。"""
    now = now or dt.datetime.now()
    task["status"] = "done"
    task["completed"] = now.strftime("%Y-%m-%dT%H:%M:%S")
    if not task.get("recur"):
        return None
    base = task_due_date(task) or now.date()
    nxt = dict(task)
    nxt["id"] = "t-{0}-{1}".format(now.strftime("%m%d"), secrets.token_hex(2))
    nxt["due"] = recur_next_due(task["recur"], base).isoformat()
    nxt["status"] = "open"
    nxt["created"] = now.strftime("%Y-%m-%dT%H:%M:%S")
    nxt["completed"] = None
    nxt["reminder_synced"] = False
    nxt["calendar_synced"] = False
    db["tasks"].append(nxt)
    return nxt


# ================================================================ 顯示輔助

def fmt_date(d, today=None):
    s = "{0}/{1}（{2}）".format(d.month, d.day, ZH_WD[d.weekday()])
    if today:
        if d == today:
            s += " 今天"
        elif d == today + dt.timedelta(days=1):
            s += " 明天"
    return s


def fmt_task_line(t, show_date=False, today=None):
    bits = []
    if t.get("time"):
        bits.append("⏰" + t["time"])
    if show_date and task_due_date(t):
        bits.insert(0, fmt_date(task_due_date(t), today))
    if t.get("duration_min"):
        m = t["duration_min"]
        bits.append("~{0}".format("{0:g}h".format(m / 60) if m >= 60 else "{0}分".format(m)))
    if t.get("recur"):
        bits.append("🔁")
    for tag in t.get("tags", []):
        bits.append("#" + tag)
    prefix = "🗓 " if t.get("type") == "event" else ""
    if t.get("horizon") == "long":
        prefix = "🎯 " + prefix
    suffix = ("  " + " ".join(bits)) if bits else ""
    pri = {1: "❗", 3: "·"}.get(t.get("priority", 2), "")
    return "{0}{1}{2}{3}".format(pri, prefix, t["title"], suffix)


def greeting_word(now):
    h = now.hour
    if h < 5:
        return "夜深了"
    if h < 11:
        return "早安"
    if h < 14:
        return "午安"
    if h < 18:
        return "午後好"
    return "晚上好"


def energy_hint(prof):
    peak = prof.get("energy_peak", "morning")
    return {
        "morning": "你的精力高峰在上午——最難的那件事，趁早上處理。",
        "afternoon": "你的精力高峰在下午——上午先清雜事，下午留給硬仗。",
        "evening": "你的精力高峰在晚上——白天排雜事，晚上做需要專注的事。",
    }.get(peak, "")


# ================================================================ 今日簡報

def build_today(db, prof, now=None):
    now = now or dt.datetime.now()
    today = now.date()
    opens = open_tasks(db)
    overdue = [t for t in opens if task_due_date(t) and task_due_date(t) < today]
    due_today = [t for t in opens if task_due_date(t) == today]
    timeline = sorted(
        [t for t in due_today if t.get("time")],
        key=lambda t: t["time"],
    )
    candidates = [t for t in overdue + due_today if t.get("type") != "event"]
    candidates.sort(key=lambda t: (
        t.get("priority", 2),
        0 if t in overdue else 1,
        t.get("time") or "99:99",
        t.get("created") or "",
    ))
    top3 = candidates[:3]
    others = [t for t in due_today if t not in top3 and t not in timeline]
    done_today = [
        t for t in db["tasks"]
        if t.get("status") == "done" and (t.get("completed") or "")[:10] == today.isoformat()
    ]
    # 放太久的短期事項：逾期超過 stale_after_days，或未排程且建立超過 stale_after_days。
    # 長期計畫（horizon=long）與例行任務不算——它們本來就以週/月為尺度。
    stale_days = int(prof.get("stale_after_days", 7))
    stale, overdue_recent = [], []
    for t in overdue:
        if t in top3:
            continue
        late = (today - task_due_date(t)).days
        if late >= stale_days and t.get("horizon") != "long" and not t.get("recur"):
            stale.append((late, t))
        else:
            overdue_recent.append(t)
    for t in opens:
        if t.get("due") or t.get("recur") or t.get("horizon") == "long":
            continue
        age = task_age_days(t, today)
        if age >= stale_days:
            stale.append((age, t))
    stale.sort(key=lambda p: -p[0])
    return {
        "now": now, "today": today,
        "top3": top3, "timeline": timeline, "others": others,
        "overdue": overdue_recent, "stale": stale,
        "done_today": done_today,
        "tagline": TAGLINES[now.timetuple().tm_yday % len(TAGLINES)],
    }


def render_today_md(data, prof):
    now, today = data["now"], data["today"]
    name = prof.get("name_call") or ""
    hello = greeting_word(now) + ("，" + name if name else "")
    lines = []
    lines.append("# 🗓 {0}月{1}日 · 週{2}".format(today.month, today.day, ZH_WD[today.weekday()]))
    lines.append("")
    lines.append("> {0}。{1}".format(hello, data["tagline"]))
    lines.append("")
    lines.append("## 📌 今日三件事")
    lines.append("")
    if data["top3"]:
        for i, t in enumerate(data["top3"], 1):
            lines.append("{0}. **{1}**".format(i, fmt_task_line(t)))
    else:
        lines.append("今天沒有排定事項。留白也是一種安排 ☁️")
    lines.append("")
    if data["timeline"]:
        lines.append("## 🕐 今日時程")
        lines.append("")
        for t in data["timeline"]:
            dur = ""
            if t.get("duration_min"):
                dur = "（約 {0} 分鐘）".format(t["duration_min"])
            lines.append("- **{0}** {1}{2}".format(t["time"], t["title"], dur))
        lines.append("")
    if data["others"]:
        lines.append("## 📋 其他待辦（{0} 件）".format(len(data["others"])))
        lines.append("")
        for t in data["others"][:7]:
            lines.append("- " + fmt_task_line(t))
        if len(data["others"]) > 7:
            lines.append("- …還有 {0} 件，用 `list` 查看".format(len(data["others"]) - 7))
        lines.append("")
    if data["overdue"]:
        lines.append("## ⏮ 之前順延（{0} 件）".format(len(data["overdue"])))
        lines.append("")
        for t in data["overdue"][:5]:
            d = task_due_date(t)
            lines.append("- {0}（原訂 {1}/{2}）".format(t["title"], d.month, d.day))
        if len(data["overdue"]) > 5:
            lines.append("- …還有 {0} 件".format(len(data["overdue"]) - 5))
        lines.append("")
        lines.append("> 順延也沒關係，今天挑一件處理就好。")
        lines.append("")
    if data["stale"]:
        lines.append("## 🕰 放了一陣子（{0} 件）".format(len(data["stale"])))
        lines.append("")
        for age, t in data["stale"][:5]:
            lines.append("- {0} — 已放 {1} 天".format(t["title"], age))
        if len(data["stale"]) > 5:
            lines.append("- …還有 {0} 件".format(len(data["stale"]) - 5))
        lines.append("")
        lines.append("> 放很久的事通常是卡在「太大」或「不想做」。排個時間、拆小一點、或放下（drop）都行，跟秘書說一聲就好。")
        lines.append("")
    lines.append("---")
    hint = energy_hint(prof)
    if hint:
        lines.append("💡 " + hint)
    return "\n".join(lines) + "\n"


def render_today_html(data, prof):
    """給備忘錄用的簡單 HTML 版本（iPhone 上閱讀）。"""
    e = _html.escape
    today = data["today"]
    out = []
    out.append("<div><h1>📋 {0}/{1}（{2}）今日簡報</h1></div>".format(
        today.month, today.day, ZH_WD[today.weekday()]))
    out.append("<div>{0}</div>".format(e(data["tagline"])))
    out.append("<div><br></div>")
    out.append("<div><b>📌 今日三件事</b></div>")
    if data["top3"]:
        for i, t in enumerate(data["top3"], 1):
            extra = " ⏰" + t["time"] if t.get("time") else ""
            out.append("<div>{0}. {1}{2}</div>".format(i, e(t["title"]), extra))
    else:
        out.append("<div>今天沒有排定事項 ☁️</div>")
    if data["timeline"]:
        out.append("<div><br></div>")
        out.append("<div><b>🕐 時程</b></div>")
        for t in data["timeline"]:
            out.append("<div>{0} · {1}</div>".format(t["time"], e(t["title"])))
    if data["others"]:
        out.append("<div><br></div>")
        out.append("<div><b>📋 其他（{0} 件）</b></div>".format(len(data["others"])))
        for t in data["others"][:7]:
            out.append("<div>· {0}</div>".format(e(t["title"])))
    if data["overdue"]:
        out.append("<div><br></div>")
        out.append("<div>⏮ 順延 {0} 件，挑一件處理就好。</div>".format(len(data["overdue"])))
    if data["stale"]:
        out.append("<div><br></div>")
        out.append("<div>🕰 有 {0} 件放了一陣子：{1}。要排期、拆小、還是放下？</div>".format(
            len(data["stale"]), e("、".join(t["title"] for _, t in data["stale"][:3]))))
    return "".join(out)


# ================================================================ 週計畫

def build_week(db, prof, now=None):
    now = now or dt.datetime.now()
    today = now.date()
    opens = open_tasks(db)
    days = []
    for i in range(7):
        d = today + dt.timedelta(days=i)
        items = sorted(
            [t for t in opens if task_due_date(t) == d],
            key=lambda t: (t.get("time") or "99:99", t.get("priority", 2)),
        )
        days.append((d, items))
    overdue = [t for t in opens if task_due_date(t) and task_due_date(t) < today]
    unscheduled = sorted(
        [t for t in opens if not t.get("due") and t.get("horizon") != "long"],
        key=lambda t: (t.get("priority", 2), t.get("created") or ""),
    )
    long_term = sorted(
        [t for t in opens if t.get("horizon") == "long"],
        key=lambda t: (t.get("priority", 2), t.get("created") or ""),
    )
    return {"now": now, "today": today, "days": days,
            "overdue": overdue, "unscheduled": unscheduled, "long_term": long_term}


def render_week_md(data, prof):
    today = data["today"]
    end = today + dt.timedelta(days=6)
    total = sum(len(items) for _, items in data["days"])
    busiest = max(data["days"], key=lambda p: len(p[1]))
    lines = []
    lines.append("# 🗓 本週計畫（{0}/{1} – {2}/{3}）".format(
        today.month, today.day, end.month, end.day))
    lines.append("")
    summary = "接下來 7 天共 {0} 件排定事項".format(total)
    if total and busiest[1]:
        summary += "，最滿的是 {0}/{1}（週{2}）".format(
            busiest[0].month, busiest[0].day, ZH_WD[busiest[0].weekday()])
    lines.append("> {0}。".format(summary))
    lines.append("")
    for d, items in data["days"]:
        label = "## 週{0} · {1}/{2}".format(ZH_WD[d.weekday()], d.month, d.day)
        if d == today:
            label += "（今天）"
        lines.append(label)
        lines.append("")
        if items:
            for t in items:
                lines.append("- " + fmt_task_line(t))
            if len(items) > 5:
                lines.append("")
                lines.append("> ⚠️ 這天排了 {0} 件，考慮搬一兩件到別天。".format(len(items)))
        else:
            lines.append("（空）")
        lines.append("")
    if data["overdue"]:
        lines.append("## ⏮ 逾期未完成（{0} 件）".format(len(data["overdue"])))
        lines.append("")
        for t in data["overdue"][:8]:
            d = task_due_date(t)
            lines.append("- {0}（原訂 {1}/{2}）".format(t["title"], d.month, d.day))
        lines.append("")
    if data["unscheduled"]:
        lines.append("## 💤 未排程（{0} 件）— 挑幾件放進空檔？".format(len(data["unscheduled"])))
        lines.append("")
        for t in data["unscheduled"][:10]:
            lines.append("- " + fmt_task_line(t))
        if len(data["unscheduled"]) > 10:
            lines.append("- …還有 {0} 件".format(len(data["unscheduled"]) - 10))
        lines.append("")
    if data["long_term"]:
        lines.append("## 🎯 長期計畫（{0} 件）".format(len(data["long_term"])))
        lines.append("")
        for t in data["long_term"]:
            lines.append("- {0}（進行 {1} 天）".format(t["title"], task_age_days(t, data["today"])))
        lines.append("")
        lines.append("> 長期計畫不求快，每週推進一小步就好。回顧時想想：這週各推進了什麼？下一步是什麼？")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_week_html(data, prof):
    e = _html.escape
    today = data["today"]
    end = today + dt.timedelta(days=6)
    out = []
    out.append("<div><h1>🗓 本週計畫 {0}/{1}–{2}/{3}</h1></div>".format(
        today.month, today.day, end.month, end.day))
    for d, items in data["days"]:
        out.append("<div><br></div>")
        out.append("<div><b>週{0} {1}/{2}</b></div>".format(ZH_WD[d.weekday()], d.month, d.day))
        if items:
            for t in items:
                tm = t.get("time")
                out.append("<div>· {0}{1}</div>".format((tm + " ") if tm else "", e(t["title"])))
        else:
            out.append("<div>（空）</div>")
    if data["unscheduled"]:
        out.append("<div><br></div>")
        out.append("<div><b>💤 未排程 {0} 件</b></div>".format(len(data["unscheduled"])))
        for t in data["unscheduled"][:8]:
            out.append("<div>· {0}</div>".format(e(t["title"])))
    if data["long_term"]:
        out.append("<div><br></div>")
        out.append("<div><b>🎯 長期計畫</b></div>")
        for t in data["long_term"]:
            out.append("<div>· {0}（{1} 天）</div>".format(
                e(t["title"]), task_age_days(t, data["today"])))
    return "".join(out)


def write_schedule(filename, content):
    os.makedirs(SCHEDULE_DIR, exist_ok=True)
    path = os.path.join(SCHEDULE_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ================================================================ Apple 同步

def _hhmm(s, fallback=(9, 0)):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", (s or "").strip())
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return fallback


def task_due_datetime(t, prof):
    d = task_due_date(t)
    if not d:
        return None
    if t.get("time"):
        hh, mm = _hhmm(t["time"])
    else:
        hh, mm = _hhmm(prof.get("reminder_default_time", "09:00"))
    return dt.datetime(d.year, d.month, d.day, hh, mm)


def sync_pull(db, prof, verbose=True):
    """iPhone → 系統：匯入收件匣、回寫完成狀態。回傳 (匯入數, 完成數)。"""
    import apple_bridge as ab
    apple = prof["apple"]
    imported = 0
    for item in ab.pull_inbox(apple["list_inbox"]):
        parsed = parse_quickadd(item["title"])
        if not parsed["title"]:
            continue
        if item.get("due") and not parsed["due"]:
            parsed["due"] = item["due"].date().isoformat()
            if (item["due"].hour, item["due"].minute) != (0, 0):
                parsed["time"] = item["due"].strftime("%H:%M")
        t = new_task(parsed, source="iphone")
        db["tasks"].append(t)
        imported += 1
        if verbose:
            print("  📥 匯入：{0}".format(fmt_task_line(t, show_date=True)))
    completed = 0
    open_by_id = {t["id"]: t for t in open_tasks(db)}
    for tid in ab.pull_completed_synced(apple["list_managed"]):
        t = open_by_id.get(tid)
        if t:
            mark_done(db, t)
            completed += 1
            if verbose:
                print("  ✅ iPhone 上已完成：{0}".format(t["title"]))
    return imported, completed


def sync_push(db, prof, verbose=True):
    """系統 → Apple：推新任務到提醒事項、行程到行事曆。回傳 (提醒數, 事件數)。"""
    import apple_bridge as ab
    apple = prof["apple"]
    push = prof["push"]
    n_rem, n_evt = 0, 0
    cal_ok = None
    for t in open_tasks(db):
        due_dt = task_due_datetime(t, prof)
        if not due_dt:
            continue
        if push.get("reminders") and not t.get("reminder_synced"):
            body = ab.TOKEN_PREFIX + t["id"]
            if t.get("notes"):
                body += "\n" + t["notes"]
            ab.add_reminder(apple["list_managed"], t["title"], body, due_dt)
            t["reminder_synced"] = True
            n_rem += 1
        if (t.get("type") == "event" and t.get("time")
                and push.get("calendar") and not t.get("calendar_synced")):
            if cal_ok is None:
                cal_ok = ab.calendar_exists(apple["calendar"])
                if not cal_ok and verbose:
                    print("  ⚠️ 行事曆「{0}」不存在，略過事件推送（見 SETUP.md）".format(
                        apple["calendar"]))
            if cal_ok:
                end = due_dt + dt.timedelta(minutes=t.get("duration_min") or 60)
                ab.add_event(apple["calendar"], t["title"], due_dt, end,
                             ab.TOKEN_PREFIX + t["id"])
                t["calendar_synced"] = True
                n_evt += 1
    return n_rem, n_evt


def do_sync(db, prof, verbose=True):
    if not IS_MAC:
        if verbose:
            print("（非 macOS，略過 Apple 同步）")
        return False
    try:
        imported, completed = sync_pull(db, prof, verbose)
        n_rem, n_evt = sync_push(db, prof, verbose)
        if verbose:
            print("同步完成：匯入 {0}、回寫完成 {1}、推送提醒 {2}、推送行程 {3}".format(
                imported, completed, n_rem, n_evt))
        return True
    except Exception as e:
        print("⚠️ Apple 同步失敗：{0}".format(e))
        return False


# ================================================================ 指令

def cmd_add(args):
    db, prof = load_db(), load_profile()
    parsed = parse_quickadd(" ".join(args.text))
    if not parsed["title"]:
        raise SystemExit("沒有任務內容。用法：add \"買牛奶 @明天 !2 #家務\"")
    t = new_task(parsed, source="chat")
    db["tasks"].append(t)
    if IS_MAC and t.get("due"):
        try:
            sync_push(db, prof, verbose=False)
        except Exception as e:
            print("⚠️ 推送提醒失敗（任務已記下）：{0}".format(e))
    save_db(db)
    print("好的 ✓ 已加入：{0}".format(fmt_task_line(t, show_date=True, today=dt.date.today())))
    print("   id: {0}".format(t["id"]))


def cmd_list(args):
    db = load_db()
    today = dt.date.today()
    opens = open_tasks(db)
    if not opens:
        print("清單是空的 ☁️")
        return
    groups = [("🔴 逾期", []), ("📌 今天", []), ("📅 本週", []), ("🗓 之後", []), ("💤 未排程", [])]
    for t in sorted(opens, key=lambda x: (x.get("due") or "9999", x.get("time") or "99:99",
                                          x.get("priority", 2))):
        d = task_due_date(t)
        if d is None:
            groups[4][1].append(t)
        elif d < today:
            groups[0][1].append(t)
        elif d == today:
            groups[1][1].append(t)
        elif d <= today + dt.timedelta(days=6):
            groups[2][1].append(t)
        else:
            groups[3][1].append(t)
    for label, items in groups:
        if not items:
            continue
        print("\n{0}（{1}）".format(label, len(items)))
        for t in items:
            print("  {0}  {1}".format(t["id"], fmt_task_line(t, show_date=True, today=today)))
    if args.all:
        done = [t for t in db["tasks"] if t.get("status") != "open"]
        if done:
            print("\n✅ 已結案（最近 10 件）")
            for t in done[-10:]:
                mark = "✅" if t["status"] == "done" else "✖"
                print("  {0}  {1} {2}".format(t["id"], mark, t["title"]))


def cmd_show(args):
    db = load_db()
    t = find_task(db, args.id)
    print(json.dumps(t, ensure_ascii=False, indent=2))


def cmd_done(args):
    db, prof = load_db(), load_profile()
    t = find_task(db, args.id)
    nxt = mark_done(db, t)
    if IS_MAC:
        try:
            import apple_bridge as ab
            ab.delete_reminder_by_token(prof["apple"]["list_managed"], t["id"])
        except Exception:
            pass
        if nxt:
            try:
                sync_push(db, prof, verbose=False)
            except Exception:
                pass
    save_db(db)
    done_count = sum(
        1 for x in db["tasks"]
        if x.get("status") == "done"
        and (x.get("completed") or "")[:10] == dt.date.today().isoformat()
    )
    print("✅ 已完成：{0}  —— {1}（今天第 {2} 件）".format(
        t["title"], PRAISES[done_count % len(PRAISES)], done_count))
    if nxt:
        print("🔁 下一次：{0}".format(fmt_task_line(nxt, show_date=True, today=dt.date.today())))


def cmd_drop(args):
    db = load_db()
    prof = load_profile()
    t = find_task(db, args.id)
    t["status"] = "dropped"
    t["completed"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if IS_MAC:
        try:
            import apple_bridge as ab
            ab.delete_reminder_by_token(prof["apple"]["list_managed"], t["id"])
        except Exception:
            pass
    save_db(db)
    print("已放下：{0}。放掉不重要的事，也是一種前進。".format(t["title"]))


def cmd_postpone(args):
    db, prof = load_db(), load_profile()
    t = find_task(db, args.id)
    today = dt.date.today()
    new_due, new_time = None, None
    for token in args.when:
        token = token.lstrip("@")
        d, tm, ok = parse_when_token(token, today)
        if d:
            new_due = d
        if tm:
            new_time = "{0:02d}:{1:02d}".format(tm[0], tm[1])
    if not new_due and not new_time:
        raise SystemExit("看不懂新時間。例：postpone {0} 明天 / 下週三 14:00".format(t["id"]))
    if new_due:
        t["due"] = new_due.isoformat()
    if new_time:
        t["time"] = new_time
    t["reminder_synced"] = False
    if t.get("type") == "event":
        t["calendar_synced"] = False
    if IS_MAC:
        try:
            import apple_bridge as ab
            ab.delete_reminder_by_token(prof["apple"]["list_managed"], t["id"])
            sync_push(db, prof, verbose=False)
        except Exception as e:
            print("⚠️ 重新推送提醒失敗：{0}".format(e))
    save_db(db)
    print("已改期 ✓ {0}".format(fmt_task_line(t, show_date=True, today=today)))


def cmd_today(args):
    db, prof = load_db(), load_profile()
    data = build_today(db, prof)
    md = render_today_md(data, prof)
    write_schedule("today.md", md)
    print(md)


def cmd_week(args):
    db, prof = load_db(), load_profile()
    data = build_week(db, prof)
    md = render_week_md(data, prof)
    write_schedule("week.md", md)
    print(md)


def cmd_sync(args):
    db, prof = load_db(), load_profile()
    if do_sync(db, prof):
        save_db(db)


def cmd_inbox(args):
    db, prof = load_db(), load_profile()
    if not os.path.exists(INBOX_PATH):
        print("找不到 inbox/inbox.md")
        return
    with open(INBOX_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r"## 待整理\n(.*?)(?=\n## |\Z)", content, re.S)
    if not m:
        print("inbox.md 裡找不到「## 待整理」區塊")
        return
    captured = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("- ") and line[2:].strip():
            captured.append(line[2:].strip())
    if not captured:
        print("收件匣是空的 ✓")
        return
    for text in captured:
        parsed = parse_quickadd(text)
        if not parsed["title"]:
            continue
        t = new_task(parsed, source="inbox")
        db["tasks"].append(t)
        print("📥 匯入：{0}".format(fmt_task_line(t, show_date=True, today=dt.date.today())))
    new_content = content[:m.start(1)] + "\n- \n" + content[m.end(1):]
    if IS_MAC:
        try:
            sync_push(db, prof, verbose=False)
        except Exception:
            pass
    save_db(db)
    with open(INBOX_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("完成，共 {0} 件。inbox.md 已清空。".format(len(captured)))


def cmd_morning(args):
    """launchd 早晨進入點：git 拉取 → Apple 同步 → 簡報 → 備忘錄 → 通知 → git 推送。"""
    git_pull()
    db, prof = load_db(), load_profile()
    synced = do_sync(db, prof, verbose=True)
    archived = archive_old(db, prof)
    if archived:
        print("🧹 自動歸檔 {0} 件結案任務 → tasks/archive/".format(archived))
    if synced or archived:
        save_db(db)
    data = build_today(db, prof)
    md = render_today_md(data, prof)
    write_schedule("today.md", md)
    if IS_MAC:
        try:
            import apple_bridge as ab
            if prof["push"].get("notes_brief"):
                ab.set_note(prof["apple"]["notes_folder"], prof["apple"]["note_today"],
                            render_today_html(data, prof))
            first = data["top3"][0]["title"] if data["top3"] else "今天沒有排定事項"
            ab.notify("今日簡報已更新：{0} 件重點、{1} 個時程".format(
                len(data["top3"]), len(data["timeline"])), subtitle=first)
            if prof["push"].get("imessage_brief") and prof.get("imessage_self"):
                text_lines = ["📋 今日簡報 {0}/{1}".format(data["today"].month, data["today"].day)]
                for i, t in enumerate(data["top3"], 1):
                    text_lines.append("{0}. {1}{2}".format(
                        i, t["title"], (" ⏰" + t["time"]) if t.get("time") else ""))
                ab.send_imessage(prof["imessage_self"], "\n".join(text_lines))
        except Exception as e:
            print("⚠️ 推送簡報失敗：{0}".format(e))
    git_commit_push("auto-sync: morning " + dt.date.today().isoformat())
    print(md)


def cmd_evening(args):
    """launchd 晚間進入點：git 拉取 → 同步完成狀態 → 統計 → 回顧提醒 → git 推送。"""
    git_pull()
    db, prof = load_db(), load_profile()
    synced = do_sync(db, prof, verbose=True)
    archived = archive_old(db, prof)
    if archived:
        print("🧹 自動歸檔 {0} 件結案任務 → tasks/archive/".format(archived))
    if synced or archived:
        save_db(db)
    today = dt.date.today()
    done_today = [
        t for t in db["tasks"]
        if t.get("status") == "done" and (t.get("completed") or "")[:10] == today.isoformat()
    ]
    remain = [t for t in open_tasks(db) if task_due_date(t) == today]
    msg = "今天完成 {0} 件 ✓".format(len(done_today))
    if remain:
        msg += " 還有 {0} 件未完，順延也沒關係。".format(len(remain))
    msg += " 睡前 2 分鐘想想：明天最重要的是哪一件？"
    if IS_MAC:
        try:
            import apple_bridge as ab
            ab.notify(msg, subtitle="🌙 晚間回顧時間")
        except Exception as e:
            print("⚠️ 通知失敗：{0}".format(e))
    git_commit_push("auto-sync: evening " + dt.date.today().isoformat())
    print(msg)


def cmd_weekly(args):
    """launchd 週計畫進入點。"""
    git_pull()
    db, prof = load_db(), load_profile()
    synced = do_sync(db, prof, verbose=True)
    archived = archive_old(db, prof)
    if archived:
        print("🧹 自動歸檔 {0} 件結案任務 → tasks/archive/".format(archived))
    if synced or archived:
        save_db(db)
    data = build_week(db, prof)
    md = render_week_md(data, prof)
    write_schedule("week.md", md)
    if IS_MAC:
        try:
            import apple_bridge as ab
            if prof["push"].get("notes_brief"):
                ab.set_note(prof["apple"]["notes_folder"], prof["apple"]["note_week"],
                            render_week_html(data, prof))
            ab.notify("下週計畫已準備好，打開備忘錄看看，或跟秘書聊聊怎麼調整。",
                      subtitle="🗓 每週計畫")
        except Exception as e:
            print("⚠️ 推送週計畫失敗：{0}".format(e))
    git_commit_push("auto-sync: weekly " + dt.date.today().isoformat())
    print(md)


def cmd_review(args):
    db = load_db()
    today = dt.date.today()
    done_today = [
        t for t in db["tasks"]
        if t.get("status") == "done" and (t.get("completed") or "")[:10] == today.isoformat()
    ]
    remain = [t for t in open_tasks(db) if task_due_date(t) and task_due_date(t) <= today]
    print("🌙 晚間回顧 · {0}".format(fmt_date(today)))
    print("")
    print("今天完成（{0} 件）：".format(len(done_today)))
    for t in done_today:
        print("  ✅ " + t["title"])
    if remain:
        print("未完成 / 逾期（{0} 件）：".format(len(remain)))
        for t in remain[:8]:
            print("  ⏳ " + t["title"])
    print("")
    print("三個問題（agent：對話式問完，摘要寫進 journal/{0}.md）：".format(today.isoformat()))
    print("  1. 今天完成的事裡，哪件最有感？")
    print("  2. 明天最重要的一件事是什麼？（順手 add 成 !1）")
    print("  3. 有什麼想記下來的？")


def cmd_gitsync(args):
    """拉取＋推送遠端。agent 在每次工作階段開始/結束時呼叫（見 SYNC.md）。"""
    if not git_available():
        print("（沒有 git 遠端設定，略過）")
        return
    git_pull()
    git_commit_push("sync: " + dt.datetime.now().strftime("%Y-%m-%d %H:%M"))


def cmd_archive(args):
    db, prof = load_db(), load_profile()
    n = archive_old(db, prof)
    if n:
        save_db(db)
        print("🧹 已歸檔 {0} 件結案任務 → tasks/archive/，tasks.json 保持輕量。".format(n))
    else:
        print("沒有需要歸檔的任務 ✓")


def cmd_notify(args):
    if not IS_MAC:
        print("（非 macOS，無法發通知）")
        return
    import apple_bridge as ab
    ab.notify(" ".join(args.text))


def cmd_doctor(args):
    prof = load_profile()
    results = []

    def check(name, fn):
        try:
            detail = fn()
            results.append(("✓", name, detail or ""))
        except Exception as e:
            results.append(("✗", name, str(e)))

    check("Python 版本", lambda: "{0}.{1}.{2}".format(*sys.version_info[:3]))
    results.append(("✓" if IS_MAC else "–", "平台",
                    platform.system() + ("" if IS_MAC else "（非 macOS：Apple 同步停用，僅檔案操作）")))
    check("tasks.json", lambda: "{0} 筆任務".format(len(load_db()["tasks"])))
    check("profile.json", lambda: "onboarded={0}".format(prof.get("onboarded")))

    def writable():
        os.makedirs(SCHEDULE_DIR, exist_ok=True)
        probe = os.path.join(SCHEDULE_DIR, ".probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return "可寫入"
    check("schedule/ 寫入", writable)

    if IS_MAC:
        import apple_bridge as ab
        check("osascript", lambda: shutil.which("osascript") or (_ for _ in ()).throw(
            RuntimeError("找不到 osascript")))
        apple = prof["apple"]
        check("提醒事項：清單「{0}」".format(apple["list_inbox"]),
              lambda: ab.ensure_list(apple["list_inbox"]) or "存在/已建立")
        check("提醒事項：清單「{0}」".format(apple["list_managed"]),
              lambda: ab.ensure_list(apple["list_managed"]) or "存在/已建立")

        def cal():
            if ab.calendar_exists(apple["calendar"]):
                return "存在"
            raise RuntimeError("不存在 — 請在行事曆 App 手動建立「{0}」（見 SETUP.md）".format(
                apple["calendar"]))
        check("行事曆「{0}」".format(apple["calendar"]), cal)
        check("備忘錄存取", lambda: ab._run('tell application "Notes" to return "ok"'))
        check("通知", lambda: ab.notify("健康檢查通過 ✓") or "已發送測試通知")

        def launchd():
            out = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
            n = out.stdout.count("com.secretary.")
            if n:
                return "已安裝 {0} 個排程".format(n)
            return "尚未安裝（zsh automation/install.sh）"
        check("launchd 排程", launchd)

    print("🩺 健康檢查")
    print("")
    ok = True
    for mark, name, detail in results:
        if mark == "✗":
            ok = False
        print("  {0} {1}{2}".format(mark, name, ("：" + detail) if detail else ""))
    print("")
    print("全部正常 ✓" if ok else "有項目需要處理，見上方 ✗（多半是權限或手動建立行事曆）。")


# ================================================================ 入口

def main():
    p = argparse.ArgumentParser(prog="secretary", description="日常秘書 CLI（詳見 AGENTS.md）")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("add", help="新增任務（快速語法）")
    sp.add_argument("text", nargs="+")
    sp.set_defaults(fn=cmd_add)

    sp = sub.add_parser("list", help="列出任務")
    sp.add_argument("--all", action="store_true", help="包含已結案")
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("show", help="顯示任務細節")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_show)

    sp = sub.add_parser("done", help="完成任務")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_done)

    sp = sub.add_parser("drop", help="放棄任務")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_drop)

    sp = sub.add_parser("postpone", help="改期：postpone <id> 明天 [14:00]")
    sp.add_argument("id")
    sp.add_argument("when", nargs="+")
    sp.set_defaults(fn=cmd_postpone)

    for name, fn, help_ in [
        ("today", cmd_today, "產生並顯示今日簡報"),
        ("week", cmd_week, "產生並顯示週計畫"),
        ("sync", cmd_sync, "與 Apple 提醒事項雙向同步"),
        ("inbox", cmd_inbox, "匯入 inbox/inbox.md 的待整理項目"),
        ("morning", cmd_morning, "早晨流程（launchd 進入點）"),
        ("evening", cmd_evening, "晚間流程（launchd 進入點）"),
        ("weekly", cmd_weekly, "週計畫流程（launchd 進入點）"),
        ("review", cmd_review, "晚間回顧模板與統計"),
        ("archive", cmd_archive, "歸檔結案多日的任務（每日流程也會自動執行）"),
        ("gitsync", cmd_gitsync, "git 拉取＋推送（跨裝置同步大腦，見 SYNC.md）"),
        ("doctor", cmd_doctor, "健康檢查"),
    ]:
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)

    sp = sub.add_parser("notify", help="發 Mac 通知")
    sp.add_argument("text", nargs="+")
    sp.set_defaults(fn=cmd_notify)

    args = p.parse_args()
    if not getattr(args, "fn", None):
        p.print_help()
        return
    args.fn(args)


if __name__ == "__main__":
    main()
