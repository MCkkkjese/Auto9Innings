# 圖像辨識遊戲運行腳本 - 開發規則

## 版本規則（每次更新都要做）

任何對程式的修改完成後，都必須把版本往前推一版並記錄更新內容：

```bash
python3 tools/bump_version.py "新增 XXX 功能" "修正 YYY 問題"
# 較大的功能更新加 --minor，破壞相容的改版加 --major，可用 --title 加上這一版的標題
```

這個指令會更新 `version.py`（`VERSION` 與 `CHANGELOG`）並重新產生 `CHANGELOG.md`。
介面的標題列、版本按鈕與「更新紀錄」視窗都讀取 `version.py`；使用者更新後第一次啟動會自動看到這一版的更新內容。
更新項目請用使用者看得懂的白話描述「更新了哪些功能」，不要寫內部實作細節。

## 架構

- `core/`：不含介面的邏輯。`bot.py`（ADB、OCR、模板比對、循序腳本迴圈）、`mirror_bot.py`（macOS 視窗鏡像）、
  `task_engine.py`（任務流程引擎與積木定義）、`options.py`（選項常數與正規化）、`storage.py`（存檔位置與設定檔讀寫）、
  `imaging.py`、`notify.py`（Telegram）、`textutil.py`。
- `ui/`：`app.py`（主視窗）、`script_page.py`（循序腳本頁，模擬器與視窗鏡像共用）、`step_cards.py`（步驟卡片）、
  `task_page.py`（任務流程頁）、`widgets.py`（共用元件）、`dialogs.py`（共用對話框）、`theme.py`（配色與字型）。
- 共用邏輯只能有一份：圖片讀寫用 `core.imaging`、Telegram 用 `core.notify`、設定檔讀寫與圖片路徑解析用 `core.storage`、
  顏色字型用 `ui.theme`、預覽／日誌／自動換行工具列用 `ui.widgets`、存檔與插入位置對話框用 `ui.dialogs`。新增功能前先找這些模組。

## 介面規則

- 介面文字不使用表情符號（功能性符號 ☰ ✓ ✕ ▸ ▾ ▲ ▼ ● 除外）。
- 工具列一律用 `ui.widgets.FlowFrame`，寬度不足時自動換行，不可讓元件被裁切。
- 不針對單一遊戲寫死邏輯或文字；遊戲專屬的內容放在 `presets/` 的範本檔。
- 舊版存檔的選項值帶表情符號，讀設定檔一律走 `core.storage.load_config()`（會自動清理）。

## 專案沿革

本專案由 Auto9Innings 重構而來，與舊版共用同一個 git 倉庫（remote 仍指向原本的 GitHub repo）。
舊版程式碼只存在於 git 歷史中；舊版存檔的檔名與欄位相容由 `core.storage` 處理。

## 測試

用環境變數 `VGB_STORAGE_DIR=<暫存資料夾>` 啟動，可避免動到使用者真正的存檔資料夾。
