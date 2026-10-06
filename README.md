# Auto9Innings

Auto9Innings 是一款專為棒球手遊（MLB 9局職棒系列）設計的高效、輕量化、基於電腦視覺與狀態機架構的全自動聯賽掛機系統。系統透過 Android Debug Bridge (ADB) 底層通訊協定與本地神經網絡 OCR 引擎（RapidOCR ONNX Runtime），在不修改遊戲本體與記憶體的前提下，實現完全非侵入式、跨解析度適應的智慧自動化流程。

---

## 系統架構與技術特點

### 1. 本地神經網絡 OCR 視覺比對（RapidOCR ONNX）
* **免聯網與零額度限制**：整合 DBNet 文本檢測模型與 CRNN 文本識別模型，以 ONNX Runtime 在本機進行推理運算，無需呼叫任何外部雲端 API，杜絕網路延遲與辨識費用。
* **低對比度與特殊底色調校**：針對遊戲中常見的深藍底白色字按鈕（如結算確認按鈕），微調文本邊界門檻（box_thresh=0.3），解決傳統 OCR 在特定光影與按鈕邊界漏檢的問題。
* **繁簡體異體字正規化引擎**：內建中文字元對映表（如「確定」與「确定」、「下一頁」與「下一页」等），實現 100% 雙向對應，避免因字型差異造成比對失敗。
* **關鍵字長度約束防護**：針對「AUTO」等高頻短詞寫死嚴格長度限制（長度大於 4 之一律排除），防止「AUTOPLAYING」等長字串因滑動視窗模糊相似度誤判。

### 2. 階層式狀態機與突發中斷機制（Priority Interceptor）
* **雙層控制邏輯（Priority ➜ Sequential）**：
  * **優先動作（Priority Steps）**：採用 If-Elif-Else 頂層攔截邏輯。無論目前處於循環步驟的哪一個階段，一旦畫面上出現指定優先條件（如 AUTO、下一頁、參加比賽、確定），立即中斷當前流程並執行優先處置。
  * **循序步驟（Sequential Steps）**：標準狀態機設計，按照自訂順序依序前進，支援逾時跳過與異常保護。
* **動畫與過場背景連點（Continuous Background Tapping）**：支援在等待或命中後於指定座標高頻敲擊以快速跳過打擊與結算過場；連點期間每隔固定敲擊次數主動擷取畫面，一旦偵測到下一步驟或優先動作立即平滑結束連點，杜絕死卡或超時。

### 3. 通訊與多線程 GUI 預覽引擎
* **ADB 多管道備援與斷線修復**：以 pure-python-adb 原生 Socket 為主，並內建 exec-out screencap 與自動端口掃描備援，截圖通訊微中斷時自動重連與修復。
* **GUI 影格節流與丟棄機制（Frame-Dropping）**：多線程架構下，背景辨識與截圖線程向 Tkinter 主介面推送畫面時，內建佇列防堵機制。若上一影格尚未渲染完畢則自動丟棄過時畫面，確保每秒渲染幀率穩定，防止長跑時記憶體洩漏與主介面卡死。
* **定時記憶體回收（GC Tuning）**：每 20 輪辨識主動執行垃圾回收，明確釋放二進位 bytes 緩衝區與 NumPy 影像矩陣，確保連續運行數十小時系統佔用記憶體維持穩定。

### 4. 遠端狀態推播（Telegram Bot API）
* 支援自訂事件觸發 Telegram 推播通知（例如：單場聯賽結束、腳本開始、異常卡點），使用者可在手機端隨時監控掛機進度。
* 敏感憑證脫敏機制：支援環境變數讀取與本地獨立存檔，代碼庫提交至公開平台時不包含任何個人私人資訊。

---

## 快速開始

### 1. 環境需求
* 作業系統：macOS / Windows / Linux
* Python 版本：Python 3.10 至 3.13
* 模擬器：BlueStacks / 雷電模擬器 / 夜神模擬器 / MuMu 等主流 Android 模擬器

### 2. 安裝步驟
```bash
# 複製專案庫
git clone https://github.com/<你的使用者名稱>/Auto9Innings.git
cd Auto9Innings

# 建議建立虛擬環境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安裝依賴套件
pip install -r requirements.txt
