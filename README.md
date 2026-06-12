# 🤖 日常秘書工作區（Secretary Agent Workspace）

> 一個用「純文字檔案」當大腦、用「Apple 原生 App」當手腳的個人日常秘書。
> 你只要用講的，秘書幫你記下來、排好、提醒你 —— Mac 和 iPhone 自動同步，全程不離開 Apple 生態系。

> 📌 **這個公開 repo 是「範本」**：只含程式與空白資料，歡迎 clone。實際使用的第一步是照 [SETUP.md](SETUP.md) **第 0 步**把它變成你自己的**私有 repo**——你的作息、待辦、日記只會存在那裡，跟這個範本無關。

---

## 這是什麼

這個資料夾是秘書的**完整工作區**：資料、程式、排程、文件全部在這裡。
任何 AI agent（Claude Code 或其他）只要讀過 [AGENTS.md](AGENTS.md)，就能接手當你的秘書。

核心理念只有三條：

1. **檔案是唯一事實來源** — 所有任務存在 [tasks/tasks.json](tasks/tasks.json)，人看的視圖（今日簡報、週計畫）由程式產生。任何 agent、任何工具都能讀寫。
2. **Apple 原生 App 是同步層** — 不裝任何第三方服務。提醒事項、行事曆、備忘錄透過 iCloud 自動出現在 iPhone 上；iPhone 上用 Siri 講一句話，下次同步就進到系統裡。
3. **零常駐、極低資源** — 沒有任何背景常駐程式。launchd 在固定時間喚醒腳本，跑幾秒鐘就結束。整天的 CPU 用量以「秒」計。

---

## 架構一覽

```
你（講話/打字）                         iPhone
   │                                      │ Siri「提醒我買牛奶」
   ▼                                      ▼
 AI 秘書 (agent)                    📥 收件匣（提醒事項）
   │  讀寫                                │
   ▼                                      │ iCloud 自動同步
 tasks/tasks.json  ◄──── sync ────────────┘
   │
   ├─► schedule/today.md、week.md（給人看的視圖）
   ├─► 🤖 秘書（提醒事項清單）──iCloud──► iPhone 通知
   ├─► 秘書（行事曆）──────────iCloud──► iPhone 行事曆
   └─► 📋 今日簡報（備忘錄）────iCloud──► iPhone 備忘錄/小工具
```

每天的節奏（時間都可在 [profile/profile.json](profile/profile.json) 調整）：

| 時間 | 發生什麼 | 怎麼跑 |
|------|----------|--------|
| 隨時（秒級） | 任何 agent 改了任務 → 自動推上提醒事項/行事曆/遠端，**不需要任何手動操作** | launchd `autosync`（監聽 tasks.json） |
| 每 30 分鐘 | 自動拉取遠端變更（接住手機端推上來的） | launchd `autosync` |
| 早上 08:00 | 同步 iPhone 收件匣 → 產生今日簡報 → 推到備忘錄 → Mac 通知 | launchd `morning` |
| 晚上 21:30 | 同步完成狀態 → 統計今天成果 → 提醒你做 2 分鐘回顧 | launchd `evening` |
| 週日 20:00 | 產生下週計畫 → 推到備忘錄 | launchd `weekly` |
| 隨時 | 跟秘書講話：「記一下…」「我這週有什麼」「做完了」 | agent 對話 |
| 出門在外 | Mac 醒著→Dispatch 遠端指派；Mac 關機→手機開雲端 session 對 repo 工作 | 見 [SYNC.md](SYNC.md) |

大腦本體放在 GitHub 私有 repo（不是放在某一台機器上）——Mac 醒著時每日流程自動 pull/push，所以「Mac 不常開機」不影響手機端讀寫最新狀態。完整的跨裝置分工見 [SYNC.md](SYNC.md)。

---

## 快速開始（在 Mac 上）

1. **建立你的私有 repo 並 clone 到 Mac**（照 [SETUP.md](SETUP.md) 第 0 步：clone 範本 → `git remote set-url` 指向自己的私有 repo → push）。
2. **跑健康檢查**（會自動建立提醒事項清單、觸發權限詢問）：
   ```sh
   python3 scripts/secretary.py doctor
   ```
3. **做一次初始化訪談** — 打開 Claude Code，說「我們來做初始化」，agent 會照 [profile/ONBOARDING.md](profile/ONBOARDING.md) 問你作息，寫好 profile。
4. **安裝每日排程**：
   ```sh
   zsh automation/install.sh
   ```
5. **設定 iPhone**（5 分鐘，照 [SETUP.md](SETUP.md) 的 iPhone 段落）：把提醒事項預設清單設成「📥 收件匣」、釘選簡報備忘錄小工具。

之後日常使用就只剩「講話」：

```
你：幫我記一下，週六早上 10 點要載媽媽去市場，大概一小時
秘書：好的 ✓ 已加入：載媽媽去市場 · 6/14（六）10:00 · 約 1 小時
      已同步到提醒事項，iPhone 會在當天提醒你。

你：我這週還有什麼？
秘書：（顯示本週視圖，標出哪天比較滿）

你：牛奶買了
秘書：✅ 已完成：買牛奶。今天第 3 件了，不錯。
```

---

## 資料夾地圖

| 路徑 | 內容 | 誰寫入 |
|------|------|--------|
| [AGENTS.md](AGENTS.md) | **agent 的工作契約**（必讀） | 人類維護 |
| [SETUP.md](SETUP.md) | Mac + iPhone 安裝指南 | 人類維護 |
| [SYNC.md](SYNC.md) | 跨裝置策略：GitHub 大腦、Dispatch、雲端 session 的分工 | 人類維護 |
| [SIRI.md](SIRI.md) | 語音層：Siri 唸簡報、語音問答的捷徑食譜 | 人類維護 |
| [profile/](profile/) | 使用者作息與偏好（profile.json）、初始化訪談腳本 | 初始化時 agent 寫 |
| [tasks/tasks.json](tasks/tasks.json) | ✅ 所有任務的唯一事實來源（只放「還活著的事」） | `secretary.py` / agent |
| [tasks/archive/](tasks/) | 結案 14 天後的任務自動歸檔於此（依年份分檔） | `secretary.py` 自動 |
| [inbox/inbox.md](inbox/inbox.md) | 快速捕捉的暫存區，一行一件事 | 人類隨手寫，秘書清空 |
| [schedule/](schedule/) | 產生的視圖：today.md、week.md（**不要手改**） | `secretary.py` |
| [journal/](journal/) | 每日回顧紀錄 | 晚間回顧時 agent 寫 |
| [scripts/](scripts/) | `secretary.py`（核心 CLI）、`apple_bridge.py`（Apple 橋接） | 人類/agent 維護 |
| [automation/](automation/) | launchd 排程定義與安裝腳本 | 安裝時使用 |
| [logs/](logs/) | launchd 執行紀錄 | 系統寫入 |

---

## 設計原則

**使用者心理學**
- **三件事法則**：今日簡報永遠只突顯 3 件核心事項。選擇太多會癱瘓行動（決策疲勞），3 件做完的成就感比 15 件做一半強得多。
- **捕捉零摩擦**：想到什麼，一句 Siri 或一行字就丟進收件匣，「整理」是秘書的事，不是你的事（GTD 的捕捉/釐清分離）。
- **不羞辱拖延**：逾期任務的措辭永遠是「順延也沒關係，挑一件處理就好」，不是紅色驚嘆號轟炸。罪惡感不會提高完成率，只會讓人不敢打開清單。
- **閉環儀式**：晚間 2 分鐘回顧利用蔡格尼效應 —— 把未完成的事「寫下來交給明天」，大腦才肯放手休息。
- **精力匹配**：初始化時記下你的精力高峰，需要專注的事建議排在高峰時段，雜事填低谷。
- **系統會自我清理**：結案任務 14 天後自動歸檔，清單上永遠只有還活著的事——清單可信，你才會一直回來看它。放超過一週沒動的短期事項，簡報會溫和點名：排期、拆小、或放下。
- **長短分流**：短期事項（天的尺度）和長期計畫（週/月的尺度）分開對待——長期計畫不被每日催促，集中在週計畫追蹤推進，每週一小步就好。

**美學與知覺**
- 一致的視覺語彙：📥 收件匣、📌 重點、🗓 行程、✅ 完成、🔁 例行 —— 看圖示就懂，不用讀字。
- 簡報版面有留白、有層次（重點 → 時程 → 其餘），掃一眼 5 秒抓到全貌。
- 語氣溫暖簡短，像可靠的朋友，不像系統通知。

**資源最小化**
- 無常駐程序：launchd 準時喚醒 → 腳本跑 2–5 秒 → 結束。一天總共執行 3 次。
- 排程都標記 `ProcessType: Background` + 低 I/O 優先權 + nice 10，不跟你的前景工作搶資源。
- 純 Python 標準函式庫，零依賴、零安裝；Apple 互動走系統內建的 `osascript`。
- 資料是幾 KB 的文字檔，沒有資料庫、沒有伺服器、沒有網路請求。

---

## 隱私

所有資料都留在你的裝置和你的 iCloud。這個工作區不呼叫任何第三方 API、不上傳任何內容。
