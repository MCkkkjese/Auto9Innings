"""
介面配色與字型（全專案唯一來源）。

所有頁面都從這裡取得顏色與字型，不在各檔案重複定義調色盤。
"""
import sys

import customtkinter as ctk

# ------------------------------------------------------------------ 底色與邊框
COLOR_BG = "#1E1E2E"            # 主視窗背景
COLOR_CARD = "#252538"          # 卡片／面板
COLOR_CARD_BORDER = "#313244"   # 卡片邊框
COLOR_CARD_ITEM = "#20222E"     # 卡片內的項目底色（步驟卡片、狀態列）
COLOR_INPUT_BG = "#181825"      # 輸入框、日誌
COLOR_INPUT_BORDER = "#45475A"  # 輸入框邊框
COLOR_CANVAS_BG = "#11111B"     # 預覽畫布

# ------------------------------------------------------------------ 文字
COLOR_TEXT_PRIMARY = "#CDD6F4"
COLOR_TEXT_MUTED = "#A6ADC8"
COLOR_TEXT_DIM = "#6C7086"
COLOR_TEXT_INFO = "#60A5FA"       # 座標、資訊數值
COLOR_TEXT_HIGHLIGHT = "#FBBF24"  # 標題強調

# ------------------------------------------------------------------ 狀態
COLOR_RUNNING = "#22C55E"
COLOR_PAUSED = "#F59E0B"
COLOR_STOPPED = "#EF4444"
COLOR_TASK = "#8B5CF6"

# ------------------------------------------------------------------ 按鈕
COLOR_BTN_PRIMARY = "#3B82F6"
COLOR_BTN_PRIMARY_HOVER = "#2563EB"
COLOR_BTN_START = "#10B981"
COLOR_BTN_START_HOVER = "#059669"
COLOR_BTN_STOP = "#EF4444"
COLOR_BTN_STOP_HOVER = "#DC2626"
COLOR_BTN_WARN = "#F59E0B"
COLOR_BTN_WARN_HOVER = "#D97706"
COLOR_BTN_VIOLET = "#8B5CF6"
COLOR_BTN_VIOLET_HOVER = "#7C3AED"
COLOR_BTN_DARK = "#313244"
COLOR_BTN_DARK_HOVER = "#45475A"

BUTTON_KINDS = {
    "primary": (COLOR_BTN_PRIMARY, COLOR_BTN_PRIMARY_HOVER),
    "success": (COLOR_BTN_START, COLOR_BTN_START_HOVER),
    "danger": (COLOR_BTN_STOP, COLOR_BTN_STOP_HOVER),
    "warning": (COLOR_BTN_WARN, COLOR_BTN_WARN_HOVER),
    "violet": (COLOR_BTN_VIOLET, COLOR_BTN_VIOLET_HOVER),
    "neutral": (COLOR_BTN_DARK, COLOR_BTN_DARK_HOVER),
}

# 一般步驟卡片的邊框色（依序循環）
STEP_COLORS = ["#3B82F6", "#22C55E", "#F59E0B", "#EF4444", "#A855F7", "#06B6D4"]
COLOR_PRIORITY = "#F59E0B"

# ------------------------------------------------------------------ 字型
if sys.platform == "darwin":
    FONT_FAMILY = "PingFang TC"
    MONO_FAMILY = "Menlo"
elif sys.platform == "win32":
    FONT_FAMILY = "Microsoft JhengHei UI"
    MONO_FAMILY = "Consolas"
else:
    FONT_FAMILY = "Noto Sans CJK TC"
    MONO_FAMILY = "DejaVu Sans Mono"

_font_cache = {}


def font(size: int = 12, bold: bool = False) -> ctk.CTkFont:
    """介面字型（依平台選用適合中文的字體）。"""
    key = ("ui", size, bold)
    if key not in _font_cache:
        _font_cache[key] = ctk.CTkFont(family=FONT_FAMILY, size=size, weight="bold" if bold else "normal")
    return _font_cache[key]


def mono(size: int = 11, bold: bool = False) -> ctk.CTkFont:
    """等寬字型（座標、數值、日誌）。"""
    key = ("mono", size, bold)
    if key not in _font_cache:
        _font_cache[key] = ctk.CTkFont(family=MONO_FAMILY, size=size, weight="bold" if bold else "normal")
    return _font_cache[key]


def apply_appearance() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
