# SYNC.md — 跨裝置策略：一個大腦，三種 Claude，加上 Apple

> 核心問題：「我在 Mac 上更新了待辦和記憶，手機上的 Claude 怎麼知道？Mac 又不常開機。」
> 答案一句話：**大腦不放在 Mac 上，放在 GitHub 上。** Mac 只是其中一份 clone。

---

## 大腦放哪裡

```
                  ┌────────────────────────────┐
                  │  GitHub（你的私有 repo）     │ ← 永遠在線的唯一共享真相
                  │  （SETUP.md 第 0 步建立）    │
                  └────┬──────────────┬────────┘
              git pull/push      cloud session clone/push
                       │              │
        ┌──────────────▼───┐   ┌──────▼──────────────────┐
        │ MacBook（clone） │   │ Claude Code 雲端 session │ ← Mac 關機也能用
        │ Cowork / Code    │   │（從手機 app 啟動/監看）   │
        │ + osascript 橋接 │   └─────────────────────────┘
        └──────┬───────────┘
          osascript│
        ┌──────────▼───────────────┐      ┌──────────────────┐
        │ Apple 層（iCloud 同步）   │◄────►│ iPhone           │
        │ 提醒事項/行事曆/備忘錄     │      │ Siri、小工具、通知 │
        └──────────────────────────┘      └──────────────────┘
```

三個原則：

1. **GitHub 是唯一共享真相**。tasks.json、profile、journal、所有記憶都在 repo 裡。任何裝置上的任何 Claude，「讀大腦」＝ clone/pull 這個 repo，「寫大腦」＝ commit + push。
2. **Apple 層負責「即時」**。Siri 捕捉、提醒通知、簡報小工具走 iCloud，跟 Mac 開不開機無關——這層涵蓋了你在手機上 90% 的需求。
3. **Mac 醒著時自動對齊**。`morning`/`evening`/`weekly` 流程頭尾自動 `git pull` / `git push`（已內建於 secretary.py）；agent 工作階段開始與結束跑 `gitsync`。Mac 一醒來就會追上世界，睡前會把世界更新。

---

## 四種力量的優劣比較（研究結論，2026-06）

| | 🍎 Apple 生態系（Siri/提醒/備忘錄） | 💻 Mac 上的 Claude（Cowork / Claude Code） | 📲 Dispatch（手機 → 桌機） | ☁️ 雲端 session + claude.ai |
|---|---|---|---|---|
| **需要 Mac 開機？** | ❌ 不用 | ✅ 要 | ✅ 要（且 Claude Desktop 開著） | ❌ 不用 |
| **智力** | 無（純規則） | 完整 agent | 完整 agent（用桌機的能力） | 完整 agent |
| **能碰本機檔案/App** | — | ✅ 全部（含 osascript→提醒/行事曆/備忘錄） | ✅ 全部 | ❌ 只有 GitHub repo 內容 |
| **速度/摩擦** | ⚡ 2 秒（Siri 一句話） | 打字對話 | 打字＋等桌機跑完推播回報 | 打字＋等雲端 clone |
| **資源/成本** | 零 token、零電力負擔 | 本機算力 + token | 桌機算力 + token | 雲端算力 + token |
| **已知限制** | 不會思考、不會整理 | 人要在電腦前（或配 Dispatch） | 單一對話串、不能開多執行緒；電腦必須醒著 | 摸不到 Apple App；目前為 research preview |

另外：**claude.ai 帳號層級的記憶**（對話、偏好、Projects）本來就跨裝置自動同步——那是「Claude 對你的印象」；這個 repo 是「秘書的工作資料」。兩者互補，repo 是可檢視、可版控、任何 agent 都能讀的那一份。

---

## 決策樹：什麼情境用哪個

| 情境 | 用什麼 | 為什麼 |
|------|--------|--------|
| 路上想到一件事 | 🍎 「嘿 Siri，提醒我…」 | 2 秒完成，Mac 開不開機無關，下次同步自動進系統 |
| 看今天要幹嘛 | 🍎 備忘錄/提醒小工具 | 早上 Mac 跑完 morning 已推上 iCloud，離線可看 |
| 在 Mac 前工作 | 💻 跟本機 Claude 對話 | 全能力：排程、改檔案、推 Apple、推 GitHub |
| 人在外，Mac 醒著 | 📲 Dispatch | 例如「幫我把收件匣整理掉、重排明天」——桌機代勞，跑完推播通知你 |
| 人在外，Mac 關機，需要動腦整理 | ☁️ 手機 Claude app 開雲端 session 對 repo 工作 | 讀寫 tasks.json/journal 都行，push 後 Mac 下次醒來自動接上 |
| 人在外，只是想問「我下週有什麼」 | ☁️ claude.ai 聊天（連 GitHub 讀 repo）或直接看 🍎 行事曆 | 唯讀查詢不必開 session |
| 每天固定的簡報/回顧 | 💻 launchd（已裝） | 本機零成本；Mac 沒開就順延到下次醒來，而 Siri/行事曆通知不受影響 |

**你的使用模式讓這套特別順**：你說「開電腦時就是用電腦的時候，那時幾乎不用手機」——代表兩台裝置的使用時間天然互斥，git 衝突幾乎不會發生；而手機時刻的需求九成是「記下」和「看一眼」，這兩件事 Apple 層即時搞定，根本不需要 Mac 在線。剩下一成需要動腦的，交給雲端 session。

---

## 同步協定（所有 agent 必須遵守）

1. **工作階段開始**：先 `python3 scripts/secretary.py gitsync`（或至少 `git pull --rebase`）再動手。
2. **工作階段結束**：commit + push（`gitsync` 一條搞定）。沒推上去的工作，其他裝置就看不見。
3. **快速捕捉永遠走 Apple，不走 git**：Siri → 收件匣 → iCloud，等 Mac 下次 sync 匯入。這條路零衝突、零依賴。
4. **雲端 session 的特殊規則**：雲端環境不是 macOS，CLI 會自動略過 Apple 推送——這是正常的。雲端新增的任務 `reminder_synced` 保持 `false`，Mac 下次醒來執行 morning 時會自動補推到提醒事項/行事曆。**雲端 session 結束前必須 push**，若平台只允許推分支，回到 Mac 時由本機 agent merge 回 main。
5. **萬一衝突**（極少數）：tasks.json 以「聯集」為原則——雙方新增的任務都保留，同一任務的狀態以較新的 `completed`/修改為準。

---

## 一次性設定（啟用手機端完整能力）

1. **Dispatch（Mac 醒著時的遠端遙控）**：Mac 的 Claude Desktop 與 iPhone 的 Claude app 都更新到最新版（需 Pro/Max 方案）；在 Cowork 開啟工作階段後，手機 app 同一個對話串就能继续指派。記住它的兩個限制：單一對話串、桌機必須醒著且 app 開著。
2. **雲端 session（Mac 關機時的完整秘書）**：到 [claude.ai/code](https://claude.ai/code) 用 GitHub 帳號授權存取**你的私有 repo**（私有 repo 需明確授權）。之後手機 Claude app 就能對這個 repo 開雲端工作階段。
3. **Mac 端**（已內建，無需設定）：morning/evening/weekly 自動 git pull/push；想手動同步就說「同步一下」或跑 `gitsync`。
4. **省電小訣竅**：如果想要「出門時也能 Dispatch」，Mac 接電源時可在 系統設定 → 能源 開啟「防止自動進入睡眠」，並讓 Claude Desktop 留在背景——但這是可選的；這套架構的設計前提就是 Mac 不常開也能運作。

---

## 誠實的限制（設計時已考量）

- **雲端 session 摸不到 Apple App**：雲端改了任務，iPhone 的「提醒事項」不會立刻多一條——要等 Mac 下次醒來補推。但別忘了：你在手機上本來就能直接看 repo 裡的 `schedule/`、或用 Siri 直接建提醒，所以實際體感影響很小。
- **Dispatch 目前單一對話串**：不能同時派多件事；要併發就用雲端 session。
- **launchd 排程在 Mac 闔蓋時不執行**：會在下次醒來後的整點補上節奏；而「準時提醒你某件事」這個職責本來就由 iPhone 的提醒事項/行事曆負責（iCloud 端），不受影響。

---

### 參考來源（2026-06 查證）

- [Assign tasks from anywhere in Claude Cowork — Claude Help Center](https://support.claude.com/en/articles/13947068-assign-tasks-from-anywhere-in-claude-cowork)
- [Dispatch in Claude Cowork — Claude 官方教學](https://claude.com/resources/tutorials/dispatch-in-claude-cowork)
- [Get started with Claude Cowork — Claude Help Center](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork)
- [Claude Code on the web — 官方文件](https://code.claude.com/docs/en/claude-code-on-the-web)
- [Use the GitHub integration — Claude Help Center](https://support.claude.com/en/articles/10167454-use-the-github-integration)
