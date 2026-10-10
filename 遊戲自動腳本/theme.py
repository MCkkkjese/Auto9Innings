"""
棒球手遊自動化腳本 - 全域主題系統 (Theme System)
支援：
1. 柔和深色模式 (Soft Dark Mode, 背景 #21232d，減少黑底對眼睛的壓迫感)
2. 明亮淺色模式 (Clean Light Mode, 背景 #f1f5f9)
3. 跨平台動態切換 (macOS / Windows / Linux) 與 TTK 樣式熱重載
"""
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any

# ==============================================================================
# 🌙 柔和深色主題色彩常數 (Soft Dark Palette) - 柔和護眼，消除死黑
# ==============================================================================
DARK_BG = "#21232d"             # 主視窗與面板背景 (柔和午夜灰藍，非刺眼純黑)
DARK_PANEL_BG = "#272a37"       # 次級區塊/容器底色
DARK_SURFACE = "#2c303e"        # 卡片本體背景
DARK_INPUT_BG = "#1a1c24"       # 輸入框與下拉選單底色
DARK_BORDER = "#3b4054"         # 元件邊框顏色

DARK_FG = "#f3f4f6"             # 主要文字 (柔和白，高可讀性且不刺眼)
DARK_FG_MUTED = "#94a3b8"       # 次要/說明文字 (淺灰藍)
DARK_FG_TIP = "#a1a1aa"         # 提示字元顏色

DARK_ACCENT = "#3b82f6"         # 主色調 (活力藍)
DARK_ACCENT_HOVER = "#2563eb"   # 懸停藍
DARK_SUCCESS = "#22c55e"        # 成功綠
DARK_WARNING = "#f59e0b"        # 警告/優先動作橙
DARK_DANGER = "#ef4444"         # 危險/錯誤紅

# 優先動作卡片配色 (深色調琥珀)
COLOR_PRIORITY_BG = "#2d2417"
COLOR_PRIORITY_BORDER = "#f59e0b"
COLOR_PRIORITY_FG = "#fef3c7"
COLOR_PRIORITY_MUTED = "#fde68a"

# 一般步驟卡片配色 (柔和石板藍)
COLOR_NORMAL_BG = "#262937"
COLOR_NORMAL_FG = "#f8fafc"

# Scratch 積木卡片配色
COLOR_BLOCK_CARD_BG = "#262937"
COLOR_BLOCK_BODY_BG = "#1c1e28"
COLOR_BLOCK_FG = "#f8fafc"


# ==============================================================================
# ☀️ 明亮淺色主題色彩常數 (Clean Light Palette) - 舒適清爽
# ==============================================================================
LIGHT_BG = "#f1f5f9"            # 主視窗底色 (柔和淡石板灰)
LIGHT_PANEL_BG = "#ffffff"      # 容器底色
LIGHT_SURFACE = "#ffffff"       # 卡片底色
LIGHT_INPUT_BG = "#ffffff"      # 輸入框底色
LIGHT_BORDER = "#cbd5e1"        # 邊框灰色

LIGHT_FG = "#0f172a"            # 主要文字 (深石板藍黑，清晰銳利)
LIGHT_FG_MUTED = "#64748b"      # 次要文字 (中灰)
LIGHT_FG_TIP = "#94a3b8"        # 提示文字

LIGHT_ACCENT = "#2563eb"        # 主色調 (湛藍)
LIGHT_ACCENT_HOVER = "#1d4ed8"
LIGHT_SUCCESS = "#16a34a"
LIGHT_WARNING = "#d97706"
LIGHT_DANGER = "#dc2626"

# 淺色模式卡片配色
COLOR_PRIORITY_BG_LIGHT = "#fffbeb"
COLOR_PRIORITY_BORDER_LIGHT = "#f59e0b"
COLOR_PRIORITY_FG_LIGHT = "#92400e"
COLOR_PRIORITY_MUTED_LIGHT = "#b45309"

COLOR_NORMAL_BG_LIGHT = "#ffffff"
COLOR_NORMAL_FG_LIGHT = "#0f172a"

COLOR_BLOCK_CARD_BG_LIGHT = "#ffffff"
COLOR_BLOCK_BODY_BG_LIGHT = "#f8fafc"
COLOR_BLOCK_FG_LIGHT = "#0f172a"


# 全域主題追蹤
_CURRENT_THEME = "dark"


def get_current_theme() -> str:
    """獲取目前啟用的主題名稱 ('dark' 或 'light')"""
    global _CURRENT_THEME
    return _CURRENT_THEME


def get_theme_palette(mode: str = None) -> Dict[str, str]:
    """獲取指定模式的主題調色盤字典"""
    if mode is None:
        mode = get_current_theme()
    if mode == "light":
        return {
            "bg": LIGHT_BG,
            "panel_bg": LIGHT_PANEL_BG,
            "surface": LIGHT_SURFACE,
            "input_bg": LIGHT_INPUT_BG,
            "border": LIGHT_BORDER,
            "fg": LIGHT_FG,
            "fg_muted": LIGHT_FG_MUTED,
            "fg_tip": LIGHT_FG_TIP,
            "accent": LIGHT_ACCENT,
            "priority_bg": COLOR_PRIORITY_BG_LIGHT,
            "priority_border": COLOR_PRIORITY_BORDER_LIGHT,
            "priority_fg": COLOR_PRIORITY_FG_LIGHT,
            "priority_muted": COLOR_PRIORITY_MUTED_LIGHT,
            "normal_bg": COLOR_NORMAL_BG_LIGHT,
            "normal_fg": COLOR_NORMAL_FG_LIGHT,
            "block_card_bg": COLOR_BLOCK_CARD_BG_LIGHT,
            "block_body_bg": COLOR_BLOCK_BODY_BG_LIGHT,
            "block_fg": COLOR_BLOCK_FG_LIGHT,
            "canvas_bg": "#f8fafc",
            "preview_bg": "#e2e8f0",
            "log_bg": "#ffffff",
        }
    else:
        return {
            "bg": DARK_BG,
            "panel_bg": DARK_PANEL_BG,
            "surface": DARK_SURFACE,
            "input_bg": DARK_INPUT_BG,
            "border": DARK_BORDER,
            "fg": DARK_FG,
            "fg_muted": DARK_FG_MUTED,
            "fg_tip": DARK_FG_TIP,
            "accent": DARK_ACCENT,
            "priority_bg": COLOR_PRIORITY_BG,
            "priority_border": COLOR_PRIORITY_BORDER,
            "priority_fg": COLOR_PRIORITY_FG,
            "priority_muted": COLOR_PRIORITY_MUTED,
            "normal_bg": COLOR_NORMAL_BG,
            "normal_fg": COLOR_NORMAL_FG,
            "block_card_bg": COLOR_BLOCK_CARD_BG,
            "block_body_bg": COLOR_BLOCK_BODY_BG,
            "block_fg": COLOR_BLOCK_FG,
            "canvas_bg": DARK_BG,
            "preview_bg": "#161822",
            "log_bg": "#161822",
        }


def apply_theme(root: tk.Tk, mode: str = "dark"):
    """
    動態切換並套用全域主題 (支援 'dark' 或 'light')
    """
    global _CURRENT_THEME
    _CURRENT_THEME = "light" if mode == "light" else "dark"
    p = get_theme_palette(_CURRENT_THEME)

    # 1. 主視窗底色
    try:
        root.configure(bg=p["bg"])
    except Exception:
        pass

    # 2. Tkinter 原生選項資料庫注入 (適用於未綁定 ttk 的基本元件)
    root.option_add("*Background", p["bg"])
    root.option_add("*Foreground", p["fg"])
    root.option_add("*selectBackground", p["accent"])
    root.option_add("*selectForeground", "#ffffff")
    root.option_add("*insertBackground", p["fg"])
    root.option_add("*highlightBackground", p["bg"])
    root.option_add("*highlightColor", p["accent"])

    # 下拉選單彈出清單 (Combobox Popdown Listbox)
    root.option_add("*TCombobox*Listbox.background", p["input_bg"])
    root.option_add("*TCombobox*Listbox.foreground", p["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    # 3. TTK 樣式設定 (基於跨平台可客製化度最高的 clam 主題)
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")

    # 全域基準樣式
    style.configure(".", background=p["bg"], foreground=p["fg"])

    # 容器與面板
    style.configure("TFrame", background=p["bg"])
    style.configure("TLabelframe", background=p["bg"], foreground=p["fg"], bordercolor=p["border"])
    style.configure(
        "TLabelframe.Label",
        background=p["bg"],
        foreground=p["accent"] if _CURRENT_THEME == "light" else "#60a5fa",
        font=("Arial", 10, "bold")
    )
    style.configure("TPanedwindow", background=p["bg"])

    # 標籤 (Label)
    style.configure("TLabel", background=p["bg"], foreground=p["fg"])
    style.configure("Muted.TLabel", background=p["bg"], foreground=p["fg_muted"])

    # 一般按鈕 (Button)
    btn_bg = "#e2e8f0" if _CURRENT_THEME == "light" else "#2c303e"
    btn_active = "#cbd5e1" if _CURRENT_THEME == "light" else "#393e50"
    btn_press = "#94a3b8" if _CURRENT_THEME == "light" else "#1e212b"
    style.configure(
        "TButton",
        background=btn_bg,
        foreground=p["fg"],
        bordercolor=p["border"],
        focuscolor=p["accent"],
        lightcolor=btn_bg,
        darkcolor=btn_bg,
        padding=(6, 3)
    )
    style.map(
        "TButton",
        background=[("pressed", btn_press), ("active", btn_active), ("disabled", btn_bg)],
        foreground=[("disabled", p["fg_muted"])],
        bordercolor=[("active", p["accent"])]
    )

    # 輸入框 (Entry)
    style.configure(
        "TEntry",
        fieldbackground=p["input_bg"],
        foreground=p["fg"],
        bordercolor=p["border"],
        insertcolor=p["fg"],
        lightcolor=p["border"],
        darkcolor=p["border"],
        padding=3
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", p["accent"])],
        fieldbackground=[("disabled", "#e2e8f0" if _CURRENT_THEME == "light" else "#1b1d25")]
    )

    # 下拉選單 (Combobox)
    style.configure(
        "TCombobox",
        fieldbackground=p["input_bg"],
        background=btn_bg,
        foreground=p["fg"],
        arrowcolor=p["fg"],
        bordercolor=p["border"],
        insertcolor=p["fg"],
        lightcolor=p["border"],
        darkcolor=p["border"],
        padding=3
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", p["input_bg"]), ("disabled", "#e2e8f0" if _CURRENT_THEME == "light" else "#1b1d25")],
        foreground=[("readonly", p["fg"]), ("disabled", p["fg_muted"])],
        selectbackground=[("readonly", p["accent"])],
        selectforeground=[("readonly", "#ffffff")],
        bordercolor=[("focus", p["accent"])]
    )

    # 數值調整框 (Spinbox)
    style.configure(
        "TSpinbox",
        fieldbackground=p["input_bg"],
        background=btn_bg,
        foreground=p["fg"],
        arrowcolor=p["fg"],
        bordercolor=p["border"],
        insertcolor=p["fg"],
        lightcolor=p["border"],
        darkcolor=p["border"],
        padding=2
    )

    # 勾選框 (Checkbutton)
    style.configure(
        "TCheckbutton",
        background=p["bg"],
        foreground=p["fg"],
        indicatorbackground=p["input_bg"],
        indicatorforeground=p["accent"],
        indicatorrelief="flat"
    )
    style.map(
        "TCheckbutton",
        background=[("active", p["bg"])],
        indicatorbackground=[("selected", p["accent"]), ("active", p["border"])]
    )

    # 單選框 (Radiobutton)
    style.configure(
        "TRadiobutton",
        background=p["bg"],
        foreground=p["fg"],
        indicatorbackground=p["input_bg"],
        indicatorforeground=p["accent"]
    )
    style.map(
        "TRadiobutton",
        background=[("active", p["bg"])],
        indicatorbackground=[("selected", p["accent"]), ("active", p["border"])]
    )

    # 分頁標籤 (Notebook)
    tab_bg = "#e2e8f0" if _CURRENT_THEME == "light" else "#272a37"
    tab_active = "#cbd5e1" if _CURRENT_THEME == "light" else "#323746"
    style.configure("TNotebook", background=p["bg"], borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=tab_bg,
        foreground=p["fg_muted"],
        bordercolor=p["border"],
        padding=(14, 5),
        font=("Arial", 9, "bold")
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", p["accent"]), ("active", tab_active)],
        foreground=[("selected", "#ffffff"), ("active", "#ffffff")]
    )

    # 滾動條 (Scrollbar)
    sb_bg = "#94a3b8" if _CURRENT_THEME == "light" else "#3b4054"
    sb_active = "#64748b" if _CURRENT_THEME == "light" else "#4e556e"
    style.configure(
        "TScrollbar",
        background=sb_bg,
        troughcolor=p["bg"],
        bordercolor=p["bg"],
        arrowcolor=p["fg"],
        relief="flat"
    )
    style.map("TScrollbar", background=[("active", sb_active)])

    # 滑動軸 (Scale)
    style.configure(
        "Horizontal.TScale",
        background=p["bg"],
        troughcolor=p["input_bg"],
        sliderrelief="flat",
        sliderlength=20
    )

    # 分隔線 (Separator)
    style.configure("TSeparator", background=p["border"])


def apply_dark_theme(root: tk.Tk):
    """套用柔和深色主題 (相容舊函式)"""
    apply_theme(root, "dark")


def apply_light_theme(root: tk.Tk):
    """套用明亮淺色主題"""
    apply_theme(root, "light")


def toggle_theme(root: tk.Tk) -> str:
    """切換深色/淺色主題並回傳新主題名稱 ('dark' 或 'light')"""
    new_theme = "light" if get_current_theme() == "dark" else "dark"
    apply_theme(root, new_theme)
    return new_theme
