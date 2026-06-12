# 秘書工作區

這是使用者的日常秘書工作區。**開始任何工作前，先讀 [AGENTS.md](AGENTS.md)** —— 角色、檔案讀寫規則、常見情境的標準作法都在那裡。

最重要的幾條：

- 對話用繁體中文（台灣），語氣依 `profile/profile.json` 的 `tone`。
- 任務一律透過 `python3 scripts/secretary.py` 操作，`tasks/tasks.json` 是唯一事實來源。
- `schedule/` 是產生的視圖，不要手改。
- Apple 同步（提醒事項/行事曆/備忘錄）只在 macOS 上有效；其他平台 CLI 會自動只操作檔案。
- `profile/profile.json` 的 `onboarded` 是 `false` 時，主動提議照 `profile/ONBOARDING.md` 做初始化訪談。
