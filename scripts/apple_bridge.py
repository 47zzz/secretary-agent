#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apple 生態系橋接層 — 透過系統內建 osascript 操作提醒事項/行事曆/備忘錄/通知/iMessage。

設計約束：
- 僅 macOS 可用；其他平台呼叫會拋出 AppleBridgeError。
- 只用 Python 標準函式庫，零安裝。
- 每個函式都是一次 osascript 呼叫、執行完即結束，不留任何常駐程序。
- 推到提醒事項的項目，body 內含 `sec-id:<task-id>` 作為雙向同步的對應鍵。
"""
import datetime as dt
import platform
import re
import subprocess
import sys

IS_MAC = platform.system() == "Darwin"
US = "\x1f"  # 欄位分隔（unit separator），不會出現在一般文字中
RS = "\x1e"  # 紀錄分隔（record separator）
TOKEN_PREFIX = "sec-id:"


class AppleBridgeError(RuntimeError):
    pass


def _run(script, timeout=90):
    if not IS_MAC:
        raise AppleBridgeError("Apple 橋接功能只能在 macOS 上執行")
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise AppleBridgeError(proc.stderr.strip() or "osascript 執行失敗")
    return proc.stdout.rstrip("\n")


def _q(s):
    """轉成 AppleScript 字串常值。"""
    s = (s or "").replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\r\n", "\n").replace("\n", "\\n")
    return '"' + s + '"'


def _as_date(d, var):
    """產生把 datetime 寫進 AppleScript 變數的片段（不依賴系統地區的日期格式）。"""
    secs = d.hour * 3600 + d.minute * 60
    return (
        "set {v} to current date\n"
        "set time of {v} to 0\n"
        "set day of {v} to 1\n"
        "set year of {v} to {y}\n"
        "set month of {v} to {m}\n"
        "set day of {v} to {dd}\n"
        "set time of {v} to {s}\n"
    ).format(v=var, y=d.year, m=d.month, dd=d.day, s=secs)


# ---------------------------------------------------------------- 提醒事項

def ensure_list(name):
    _run(
        'tell application "Reminders"\n'
        '  if not (exists list {n}) then make new list with properties {{name:{n}}}\n'
        'end tell'.format(n=_q(name))
    )


def add_reminder(list_name, title, body="", due=None):
    """在指定清單建立提醒。due 為 datetime（含時間）或 None。"""
    date_part = _as_date(due, "d") if due else ""
    props = "name:{t}, body:{b}".format(t=_q(title), b=_q(body))
    if due:
        props += ", due date:d"
    _run(
        date_part
        + 'tell application "Reminders"\n'
        + '  if not (exists list {n}) then make new list with properties {{name:{n}}}\n'.format(n=_q(list_name))
        + '  tell list {n}\n'.format(n=_q(list_name))
        + '    make new reminder with properties {{{p}}}\n'.format(p=props)
        + '  end tell\n'
        + 'end tell'
    )


def pull_inbox(list_name):
    """讀取收件匣所有未完成提醒並標記為完成（代表已匯入）。

    回傳 [{"title": str, "body": str, "due": datetime|None}, ...]。
    一次 osascript 呼叫完成「讀取＋標記」，避免重複匯入。
    """
    script = (
        'set us to character id 31\n'
        'set rs to character id 30\n'
        'set out to ""\n'
        'tell application "Reminders"\n'
        '  if not (exists list {n}) then return ""\n'
        '  set theItems to (every reminder of list {n} whose completed is false)\n'
        '  repeat with r in theItems\n'
        '    set t to name of r\n'
        '    set b to body of r\n'
        '    if b is missing value then set b to ""\n'
        '    set ds to ""\n'
        '    set dd to due date of r\n'
        '    if dd is not missing value then\n'
        '      set ds to ((year of dd) as string) & "|" & ((month of dd) as integer) '
        '& "|" & (day of dd) & "|" & (hours of dd) & "|" & (minutes of dd)\n'
        '    end if\n'
        '    set out to out & t & us & b & us & ds & rs\n'
        '    set completed of r to true\n'
        '  end repeat\n'
        'end tell\n'
        'return out'
    ).format(n=_q(list_name))
    raw = _run(script, timeout=180)
    items = []
    for rec in raw.split(RS):
        if not rec.strip():
            continue
        parts = rec.split(US)
        if len(parts) < 3:
            continue
        title, body, ds = parts[0].strip(), parts[1], parts[2].strip()
        due = None
        if ds:
            try:
                y, m, d, hh, mm = [int(x) for x in ds.split("|")]
                due = dt.datetime(y, m, d, hh, mm)
            except (ValueError, TypeError):
                due = None
        if title:
            items.append({"title": title, "body": body, "due": due})
    return items


def pull_completed_synced(list_name):
    """取出受管清單中「已完成且帶 sec-id 記號」的提醒，回傳 task id 列表並刪除這些提醒。

    （任務資料都在 tasks.json，刪掉已完成的提醒讓清單保持乾淨、同步保持快速。）
    """
    script = (
        'set rs to character id 30\n'
        'set out to ""\n'
        'tell application "Reminders"\n'
        '  if not (exists list {n}) then return ""\n'
        '  set theItems to (every reminder of list {n} whose completed is true)\n'
        '  repeat with r in theItems\n'
        '    set b to body of r\n'
        '    if b is not missing value then\n'
        '      if b contains "{tok}" then\n'
        '        set out to out & b & rs\n'
        '        delete r\n'
        '      end if\n'
        '    end if\n'
        '  end repeat\n'
        'end tell\n'
        'return out'
    ).format(n=_q(list_name), tok=TOKEN_PREFIX)
    raw = _run(script, timeout=180)
    ids = []
    for rec in raw.split(RS):
        m = re.search(re.escape(TOKEN_PREFIX) + r"(\S+)", rec)
        if m:
            ids.append(m.group(1))
    return ids


def delete_reminder_by_token(list_name, task_id):
    """刪除帶有指定 sec-id 的提醒（任務在系統側被完成/改期時呼叫）。失敗靜默。"""
    script = (
        'tell application "Reminders"\n'
        '  if (exists list {n}) then\n'
        '    try\n'
        '      delete (every reminder of list {n} whose body contains {tok})\n'
        '    end try\n'
        '  end if\n'
        'end tell'
    ).format(n=_q(list_name), tok=_q(TOKEN_PREFIX + task_id))
    try:
        _run(script)
    except AppleBridgeError:
        pass


# ---------------------------------------------------------------- 行事曆

def calendar_exists(name):
    out = _run(
        'tell application "Calendar"\n'
        '  return (exists calendar {n})\n'
        'end tell'.format(n=_q(name))
    )
    return out.strip() == "true"


def add_event(cal_name, title, start, end, description=""):
    """在指定行事曆建立事件。start/end 為 datetime。行事曆不存在會拋錯。"""
    script = (
        _as_date(start, "d1")
        + _as_date(end, "d2")
        + 'tell application "Calendar"\n'
        + '  if not (exists calendar {n}) then error "行事曆不存在"\n'.format(n=_q(cal_name))
        + '  tell calendar {n}\n'.format(n=_q(cal_name))
        + '    make new event with properties '
        + '{{summary:{t}, start date:d1, end date:d2, description:{d}}}\n'.format(
            t=_q(title), d=_q(description))
        + '  end tell\n'
        + 'end tell'
    )
    _run(script)


# ---------------------------------------------------------------- 備忘錄

def set_note(folder, title, html_body):
    """建立或覆寫指定資料夾中的備忘錄。body 是簡單 HTML（<div>/<b>/<br> 等）。"""
    script = (
        'tell application "Notes"\n'
        '  if not (exists folder {f}) then make new folder with properties {{name:{f}}}\n'
        '  tell folder {f}\n'
        '    if exists note {t} then\n'
        '      set body of note {t} to {b}\n'
        '    else\n'
        '      make new note with properties {{name:{t}, body:{b}}}\n'
        '    end if\n'
        '  end tell\n'
        'end tell'
    ).format(f=_q(folder), t=_q(title), b=_q(html_body))
    _run(script, timeout=120)


# ---------------------------------------------------------------- 通知 / iMessage

def notify(message, title="🤖 秘書", subtitle=""):
    script = 'display notification {m} with title {t}'.format(m=_q(message), t=_q(title))
    if subtitle:
        script += ' subtitle {s}'.format(s=_q(subtitle))
    _run(script)


def send_imessage(handle, text):
    """傳 iMessage（可以傳給自己的 Apple ID / 手機號，iPhone 就會收到）。"""
    script = (
        'tell application "Messages"\n'
        '  set s to 1st account whose service type = iMessage\n'
        '  send {t} to participant {h} of s\n'
        'end tell'
    ).format(t=_q(text), h=_q(handle))
    _run(script)


# ---------------------------------------------------------------- 測試入口

def _main(argv):
    """手動測試用：python3 apple_bridge.py notify "哈囉" """
    if not argv:
        print(__doc__)
        print("可用測試指令：")
        print('  notify "訊息"')
        print('  ensure-list "清單名"')
        print('  add-reminder "清單名" "標題"')
        print('  pull-inbox "清單名"')
        print('  calendar-exists "行事曆名"')
        return 0
    cmd = argv[0]
    try:
        if cmd == "notify":
            notify(argv[1])
        elif cmd == "ensure-list":
            ensure_list(argv[1])
        elif cmd == "add-reminder":
            add_reminder(argv[1], argv[2])
        elif cmd == "pull-inbox":
            for item in pull_inbox(argv[1]):
                print(item)
        elif cmd == "calendar-exists":
            print(calendar_exists(argv[1]))
        else:
            print("未知指令：" + cmd)
            return 1
        print("ok")
        return 0
    except AppleBridgeError as e:
        print("AppleBridgeError: {0}".format(e))
        return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
