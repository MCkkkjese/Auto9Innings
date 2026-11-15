"""
版本資訊與更新紀錄（全專案唯一來源）。

每次更新程式都必須：
1. 把版本號往前推一版（執行 tools/bump_version.py，或手動修改 VERSION）。
2. 在 CHANGELOG 最前面新增一筆紀錄，列出這次更新了哪些功能。
介面標題列、版本按鈕與「更新紀錄」視窗都直接讀取這裡的資料。
"""

APP_NAME = "圖像辨識遊戲運行腳本"
APP_CODENAME = "VisionGameBot"

VERSION = "2.0.1"

# 由新到舊排列；每筆為 {"version", "date", "title", "changes": [...]}
CHANGELOG = [
    {
        "version": "2.0.1",
        "date": "2026-11-15",
        "title": "專案整併",
        "changes": [
            "舊版 Auto9Innings 程式已由新版完全取代，兩者合併為同一個專案，保留原本的 git 歷史紀錄",
            "新增內建範本「MLB9局_預設聯賽設定」（原舊版 league_default 設定）",
            "重寫 README 說明文件：快速開始、各頁面用法、存檔與範本、從舊版升級",
        ],
    },
    {
        "version": "2.0.0",
        "date": "2026-11-15",
        "title": "重構為通用的圖像辨識遊戲腳本",
        "changes": [
            "專案更名為「圖像辨識遊戲運行腳本」，不再綁定單一遊戲，步驟與範本皆可套用到任何遊戲",
            "原「聯賽自動刷」與「iPhone 鏡像自動刷」合併為同一套循序腳本頁面，兩者功能完全一致（看門狗、等待時連點、Telegram 等設定在視窗鏡像頁也能使用）",
            "優先動作與一般步驟改用同一個步驟卡片元件，新增／刪除／拖曳排序／存檔邏輯只保留一份",
            "圖片讀寫、Telegram 發送、存檔對話框、插入位置對話框、預覽座標換算、日誌面板等重複實作整併為共用模組",
            "預覽畫面改為隨視窗大小自動縮放，步驟卡片與積木編輯區不再被固定寬度的預覽擠壓裁切",
            "積木工具庫改為雙欄排列，一次完整顯示全部 12 種積木，不需捲動",
            "介面重新整理：統一配色與按鈕樣式，移除所有多餘的表情符號",
            "新增版本號顯示與「更新紀錄」視窗，更新後首次啟動會自動顯示本次更新內容",
            "新增「範本」按鈕，可直接載入內建的步驟範本",
            "修正：看門狗重啟時狀態列顏色未定義導致的錯誤；診斷按鈕無法執行的問題",
            "舊版存檔（baseball_last_config.json、iphone_last_config.json、task_flow_save.json）可直接沿用",
        ],
    },
    {
        "version": "1.0.0",
        "date": "2026-10-24",
        "title": "Auto9Innings 原始版本",
        "changes": [
            "ADB 模擬器截圖、RapidOCR 文字辨識與圖片模板比對",
            "聯賽自動刷、iPhone 鏡像自動刷、任務清單積木、Telegram 通知",
        ],
    },
]


def latest_changes() -> dict:
    """回傳最新一版的更新紀錄。"""
    return CHANGELOG[0] if CHANGELOG else {"version": VERSION, "date": "", "title": "", "changes": []}


def version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return (0,)
