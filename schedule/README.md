# schedule/ — 產生的視圖

此資料夾的 `today.md`（今日簡報）、`week.md`（週計畫）、`brief_voice.txt`（給 Siri 朗讀的語音版簡報，見 [SIRI.md](../SIRI.md)）由 `scripts/secretary.py` 產生，**請勿手動編輯** —— 下次執行會被覆寫。要更新內容請改 `tasks/tasks.json`（透過 CLI），再重跑 `today` / `week`。

這些檔案刻意納入 git 版控：Mac 每天自動 push 後，iPhone 的捷徑與雲端 session 都從 GitHub 讀取。
