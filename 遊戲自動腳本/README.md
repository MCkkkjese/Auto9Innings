# Auto9Innings

MLB 9局職棒手遊的自動掛機工具。透過 ADB 對 Android 模擬器截圖，用本機 OCR 讀取畫面文字（如 `AUTO`、`確定`、`下一頁`），再自動點擊，不需修改遊戲，也不需連網辨識。

**主要功能**
- 自動跑聯賽：開 AUTO、跳過動畫、領獎勵、進下一場
- 本機 OCR（RapidOCR），沒有 API 費用與額度限制
- 比賽結束可推播 Telegram 通知到手機
- 圖形介面，可自訂步驟與關鍵字

---

## 快速開始

**需求**：Python 3.10–3.13、Android 模擬器（BlueStacks / 雷電 / 夜神 / MuMu 等）

```bash
# 在本資料夾內執行
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**模擬器設定**
1. 開啟模擬器，在「設定」➜「進階設定」開啟「Android 偵錯 (ADB)」。
2. 啟動遊戲，停在聯賽模式或主選單。

**執行**
```bash
python3 main.py
```
1. 按「搜尋」找到模擬器序號，按「連線」。
2. 預設會載入 `configs/league_default.json`。
3. 按「開始執行」。

---

## 預設聯賽流程

腳本分兩層：**優先動作**一出現就立刻處理（不論目前在哪一步），**循序步驟**則依序執行。

| 類型 | 關鍵字 | 行為 |
| :--- | :--- | :--- |
| 優先 1 | AUTO, DUTO | 點擊並在打擊區連點，跳過局數過場 |
| 優先 2 | 下一頁, 下一步 | 點擊並連點，同時推播聯賽完成通知 |
| 優先 3 | 參加比賽 | 點擊並在右上角連點 |
| 優先 4 | 確定 | 點擊並連點，處理獎勵與提示視窗 |
| 循序 1 | NEXT SCHEDULE, PLAY BALL, 確定 | 發起對戰 |

在介面調亂了，可用選單「範本」➜「聯賽刷關範本」還原。

---

## Telegram 推播（選用）

1. 在 Telegram 找 @BotFather 建立機器人，取得 Bot Token。
2. 找 @userinfobot 取得你的 Chat ID。
3. 在 GUI「進階」設定填入，或用環境變數：

```bash
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
export TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
python3 main.py
```

---

## 常見問題

**搜尋不到模擬器？**
確認模擬器已開啟 ADB 偵錯，並可執行 `adb devices` 看到裝置。也可用 `diagnostics.py` 檢查連線與套件環境。

**文字一直辨識不到？**
確認模擬器解析度正常、遊戲畫面沒被遮住。關鍵字已自動處理繁簡體差異（如 確定／确定）。

**重複點到錯的按鈕？**
把較重要的條件放進「優先動作」，並檢查關鍵字是否太短而誤觸發。

---

## 專案結構

```text
├── main.py              # 程式進入點
├── gui.py               # 圖形介面
├── bot_core.py          # ADB 驅動、OCR、狀態機核心
├── fast_bot.py          # 輕量快速腳本引擎
├── task_flow.py         # 任務流程
├── batting_assist.py    # 打擊輔助
├── iphone_mirror_bot.py # iPhone 鏡像版本
├── diagnostics.py       # 環境診斷工具
├── configs/             # 設定檔（含 league_default.json）
├── task_presets/        # 任務預設
└── requirements.txt
```

---

<details>
<summary>技術細節（給開發者）</summary>

- **OCR**：RapidOCR（DBNet 偵測 + CRNN 辨識）跑在 ONNX Runtime。針對深藍底白字按鈕將 `box_thresh` 調為 0.3，避免漏檢。
- **關鍵字比對**：內建繁簡對映表；`AUTO` 等短詞限制長度（超過 4 即排除），避免 `AUTOPLAYING` 被模糊比對誤判。
- **連點機制**：連點期間每隔固定次數擷取畫面，一偵測到下一步驟或優先動作就中止，避免卡死。
- **ADB**：以 pure-python-adb 為主，備援為 `exec-out screencap` 與自動端口掃描，截圖中斷時自動重連。
- **GUI**：截圖與辨識在背景執行緒，推送畫面時若上一影格未渲染完就丟棄，避免卡頓與記憶體累積。
- **記憶體**：每 20 輪辨識主動 GC，長時間運行佔用維持穩定。

</details>

## 授權與免責

MIT 授權，詳見 [LICENSE](LICENSE)。本專案僅供自動化與影像處理技術研究，使用時請遵守遊戲服務條款。
