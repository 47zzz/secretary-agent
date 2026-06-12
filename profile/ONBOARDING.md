# ONBOARDING.md — 初始化訪談腳本（給 agent）

> 當 `profile/profile.json` 的 `onboarded` 是 `false`，或使用者說「初始化／重新認識我」時，照這份腳本進行。

## 第 0 組（開始訪談前必做）：確認私有 repo ⚠️

訪談會把使用者的作息、待辦、私人習慣寫進這個 repo，而每日排程和 `gitsync` 會**自動 push 到遠端**。所以開始問任何問題之前，你必須先確認遠端是使用者**自己的私有 repo**，不是公開範本：

1. 跑 `python3 scripts/secretary.py doctor`，看「**git 遠端**」那一項。
2. **✓ 通過**（顯示使用者自己的 repo 網址）→ 直接開始第 1 組。
3. **✗ 顯示「遠端仍指向公開範本」**（或使用者說還沒建）→ **暫停訪談**，先一步一步帶他完成：
   - 「我們先花 2 分鐘把你的私人保險箱建好，這樣你的資料才不會跑到公開的地方。」
   - 帶他到 GitHub：右上「+」→ New repository → 取名（如 `my-secretary`）→ 選 **Private** → README/.gitignore/license 全部不勾 → Create。
   - 請他把新 repo 網址貼給你，然後執行：
     ```sh
     git remote set-url origin https://github.com/<帳號>/<repo>.git
     git push -u origin main
     ```
   - 重跑 `doctor` 確認「git 遠端」變 ✓，再開始訪談。
4. 使用者堅持不用 git 遠端（純本機使用）→ 可以繼續，但明確告知：手機端的 Siri 簡報捷徑和雲端 session 會無法使用，且資料沒有異地備份。

## 訪談原則

- **聊天，不是填表。** 一次問一組（最多 2–3 個小問題），等回答再問下一組。全程約 5 分鐘。
- 每一題都可以跳過，跳過就用預設值。
- 問完即時複述你的理解讓使用者確認，再寫入 profile。
- 結束時要有明確的「完成感」：總結 + 接下來會發生什麼。

## 訪談題目（依序）

**第 1 組：稱呼與語氣**
1. 希望我怎麼稱呼你？
2. 平常希望我講話風格偏「溫暖鼓勵」還是「簡潔直接」？
   → 寫入 `name_call`、`tone`（`warm` / `concise`）

**第 2 組：作息**
3. 平日大概幾點起床、幾點睡？
4. 工作（或上課）時段大概是幾點到幾點？
   → `wake_time`、`sleep_time`、`work_start`、`work_end`

**第 3 組：精力**
5. 一天當中，你腦袋最清楚、最適合做困難事情的時段是早上、下午還是晚上？
   → `energy_peak`（`morning` / `afternoon` / `evening`）
   （說明一句為什麼要問：之後排程會把需要專注的事建議在這個時段）

**第 4 組：簡報與回顧時間**
6. 想幾點收到「今日簡報」？（建議：起床後半小時內）
7. 晚上幾點提醒你做 2 分鐘回顧？（建議：睡前 1–2 小時）
8. 週計畫想排在哪天幾點？（建議：週日晚上）
   → `brief_time`、`review_time`、`weekly_plan`（格式如 `"sun 20:00"`）

**第 5 組：固定行程與例行事務**
9. 有哪些每週固定的行程？（週會、健身、家庭時間、社團……）
10. 有哪些每天/每週固定要做的小事？（吃藥、澆花、倒垃圾、記帳……）
    → 每一項都直接 `add` 成例行任務，例如：
    ```sh
    python3 scripts/secretary.py add "健身 每週二 @19:00 ~1h #健康"
    python3 scripts/secretary.py add "倒垃圾 每週一 @21:00 #家務"
    ```
    有固定時間又是「要出席的場合」就加上 `#行程`。

**第 6 組：分類**
11. 你的事情大概分哪幾類？（例：工作、學業、家務、健康、家人）
    → `tags_common`（之後新任務會優先用這些標籤歸類）

**第 7 組：可選功能**
12. 要不要開啟「iMessage 簡報」？（除了備忘錄，每天早上再用 iMessage 傳一份簡報給你自己；需要你的 Apple ID email 或手機號）
    → 要的話：`push.imessage_brief = true`、`imessage_self = "<handle>"`

## 結束動作（checklist）

1. 把答案寫入 `profile/profile.json`，並把 `onboarded` 設為 `true`。
2. 固定行程與例行事務逐一 `add`。
3. 跑 `python3 scripts/secretary.py doctor`，把結果跟使用者說。
4. 跑 `python3 scripts/secretary.py today` 給使用者看第一份簡報。
5. 提醒使用者：(a) 跑 `zsh automation/install.sh` 安裝排程（或徵得同意後幫他跑）；(b) 照 SETUP.md 設定 iPhone（預設清單 + 小工具）。
6. 總結一句：「之後你只要把事情丟給我就好。」
