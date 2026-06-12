# SIRI.md — 語音層：用講的跟秘書互動，用聽的接收回覆

> 「嘿 Siri」開口 → 秘書處理 → Siri 唸給你聽。本文件是完整的語音能力地圖與 iPhone 捷徑食譜。
> 全部在 iPhone 內建的「捷徑」App 完成，不安裝任何第三方軟體。

---

## 語音能力地圖（四個層次）

| 層次 | 喚醒語（可自訂） | 做什麼 | 需要 Mac 開機？ | 需要什麼 |
|------|------------------|--------|----------------|----------|
| **0. 語音記事**（已可用） | 「嘿 Siri，提醒我買牛奶」 | 捕捉待辦 → 收件匣 → 自動進系統 | ❌ | 零設定（SETUP.md 的預設清單） |
| **1. 聽今日簡報** | 「嘿 Siri，今日簡報」 | 把秘書產生的語音版簡報唸出來 | ❌ | 捷徑 A ＋ GitHub 唯讀 token |
| **2. 問秘書（對話）** | 「嘿 Siri，問秘書」 | 聽寫問題 → Claude 帶著你的待辦狀態回答 → 朗讀 | ❌ | 捷徑 B（用 Claude app，吃訂閱額度） |
| **3. 全語音對話** | 開 Claude app 點語音 | 連續多輪的語音交談 | ❌ | Claude app 內建語音模式 |

> 🔭 **接下來會更好**：Apple 已預告 iOS 27（2026 秋）的 Siri「Extensions」將開放 Claude 等 AI 直接整合 Siri——屆時層次 2/3 可能不再需要捷徑中轉。本文件的做法現在就能用，之後再簡化。

層次 0 在 [SETUP.md](SETUP.md) 已設定完成。層次 3 打開 Claude app 點語音圖示即可（它也共享你的 claude.ai 帳號記憶）。以下是層次 1 和 2 的捷徑食譜。

---

## 前置：建一個 GitHub 唯讀 token（5 分鐘，層次 1 需要）

捷徑要從私有 repo 讀 `schedule/brief_voice.txt`（秘書每天早上自動產生、自動 push 的語音版簡報）。

1. GitHub → 右上頭像 → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. 設定：
   - **Repository access**：Only select repositories → 勾**你的私有 repo**（SETUP.md 第 0 步建立的那個）
   - **Permissions → Contents：Read-only**（其他全部不給）
   - 期限選最長（到期再換一個）
3. 產生後**複製 token**（`github_pat_` 開頭，只顯示一次），貼進下面捷徑 A 的 Authorization 欄位。

> 這個 token 只能「讀這一個 repo」，權限最小化；就算外洩也改不了任何東西。

---

## 捷徑 A：「今日簡報」——Siri 唸今天的安排（零 AI、零成本）

iPhone 捷徑 App → 新增捷徑，依序加入動作：

1. **「取得 URL 內容」**（Get Contents of URL）
   - URL：`https://api.github.com/repos/你的帳號/你的私有repo/contents/schedule/brief_voice.txt`
   - 方法：`GET`
   - 標頭（Headers）加兩條：
     - `Authorization` → `Bearer github_pat_你的token`
     - `Accept` → `application/vnd.github.raw+json`
2. **「朗讀文字」**（Speak Text）
   - 文字：選上一步的「URL 內容」
   - 語言：中文（台灣），速度依喜好

捷徑命名為「**今日簡報**」→ 之後說「嘿 Siri，今日簡報」就會唸出類似：

> 「6月12日，星期五。今天有3件重點。第一，準備期末報告初稿。第二，回覆教授信件。第三，買牛奶。另外有2件一般待辦。」

戴 AirPods、開車（CarPlay）、出門前都能聽。內容是 Mac 每天早上 `morning` 流程產生並推上 GitHub 的——**Mac 關著也聽得到**（內容是最近一次產生的版本）。

加分：把這個捷徑加進「自動化」→ 每天早上 8:30 或「鬧鐘停止時」自動執行，鬧鐘一關秘書就開始講話。

---

## 捷徑 B：「問秘書」——語音問、語音答（推薦做法：走 Claude app）

Claude iOS app 官方提供「**Ask Claude**」捷徑動作：用你的 Pro/Max 訂閱額度，**不需要 API key**，回應可以接給後續動作朗讀。

捷徑 App → 新增捷徑，依序加入：

1. **「聽寫文字」**（Dictate Text）— 語言：中文（台灣）。這是你開口問問題的入口。
2. **「取得 URL 內容」**— 跟捷徑 A 完全相同的設定（抓 `brief_voice.txt` 當背景脈絡）。
3. **「文字」**（Text）— 組合要丟給 Claude 的內容：
   ```
   你是我的日常秘書。以下是我目前的待辦狀態：
   〔URL 內容〕

   我的問題或指示：〔聽寫文字〕

   請用兩三句口語回答，內容會被語音朗讀，不要用任何條列、符號或 emoji。
   ```
   （〔〕處插入前面步驟的變數）
4. **「Ask Claude」**（在動作搜尋打 Claude 就會出現）— 輸入選上一步的「文字」。
5. **「朗讀文字」**— 文字選 Ask Claude 的回應。

命名「**問秘書**」。效果：

> 你：「嘿 Siri，問秘書」…「我明天有什麼事？週六有空嗎？」
> Siri：「明天就一件，準備期末報告的初稿。週六上午要載媽媽去市場，下午之後都是空的。」

注意事項：
- **查詢、商量、安排建議**用這條；**新增待辦**直接用層次 0（「嘿 Siri 提醒我…」）更快更穩。
- Ask Claude 走你的 claude.ai 帳號，**帳號記憶也會生效**（它認得你），用量計入訂閱額度。
- 第 2、3 步可省略——省略後就是「裸問 Claude」，少了待辦脈絡但設定更簡單。

---

## 捷徑 B 進階版：直連 Claude API（更快、更可控，需要 API key）

不想經過 Claude app、或想壓低延遲，可把捷徑 B 的第 4 步換成直接呼叫 Anthropic Messages API。需要到 [platform.claude.com](https://platform.claude.com) 申請 API key（另外計費，按用量）。

**「取得 URL 內容」**設定：

- URL：`https://api.anthropic.com/v1/messages`
- 方法：`POST`
- 標頭：
  - `x-api-key` → `你的 API key`
  - `anthropic-version` → `2023-06-01`
  - `content-type` → `application/json`
- 請求本文（JSON）：

```json
{
  "model": "claude-opus-4-8",
  "max_tokens": 1024,
  "system": "你是使用者的日常秘書。回答兩三句、口語化、適合語音朗讀，不用條列符號和 emoji。",
  "messages": [
    {"role": "user", "content": "目前待辦狀態：〔URL 內容〕\n\n問題：〔聽寫文字〕"}
  ]
}
```

**解析回應**：加「取得字典值」動作，取 `content` → 第 1 項 → `text`，交給「朗讀文字」。

**模型選擇**（語音助理重點是回得快）：

| 模型 | 何時用 |
|------|--------|
| `claude-opus-4-8` | 預設建議——答案品質最好，秘書類問答的延遲通常可接受 |
| `claude-haiku-4-5` | 追求最低延遲、問題都很簡單（查時間、查行程）時換這個，速度最快、費用最低 |

---

## 限制與誠實說明

- **層次 1 的簡報是「最近一次產生」的版本**：Mac 每天早晚自動更新並 push；如果 Mac 好幾天沒開，內容就會是舊的（但層次 0 的捕捉和 iPhone 原生提醒完全不受影響）。
- **層次 2 的 Claude 看得到狀態、動不了狀態**：它能讀你的待辦回答問題，但不會寫回系統。要改動就用層次 0 捕捉，或開雲端 session（見 [SYNC.md](SYNC.md)）。
- **聽寫對專有名詞較弱**：人名、外文詞可能聽錯；簡短自然的句子效果最好。
- Ask Claude / 語音模式的用量計入你的訂閱方案額度。

## 疑難排解

| 症狀 | 解法 |
|------|------|
| 捷徑 A 回 404 / 401 | token 過期或權限不對：確認 Fine-grained token 勾了這個 repo + Contents Read-only；`Bearer ` 後面要有空格 |
| 唸出來是 JSON 亂碼 | `Accept` 標頭沒設成 `application/vnd.github.raw+json` |
| 找不到 Ask Claude 動作 | 更新 Claude app 到最新版，登入後重開捷徑 App |
| 簡報內容是舊的 | Mac 還沒跑當天的 morning：開 Mac 跑一次 `python3 scripts/secretary.py morning`，或接受「最近一次」的內容 |

---

### 參考來源（2026-06 查證）

- [Using Claude App Intents, Shortcuts, and Widgets on iOS — Claude Help Center](https://support.claude.com/en/articles/10263469-using-claude-app-intents-shortcuts-and-widgets-on-ios)
- [Use voice mode — Claude Help Center](https://support.claude.com/en/articles/11101966-use-voice-mode)
- [iOS 27 將開放 AI chatbot 整合 Siri — 9to5Mac](https://9to5mac.com/2026/03/26/ios-27-apple-will-reportedly-let-claude-and-other-ai-chatbot-apps-integrate-with-siri/)
