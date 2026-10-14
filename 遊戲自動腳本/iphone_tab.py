"""
================================================================================
📱 iPhone 鏡像自動刷 - 獨立分頁介面 (IPhoneMirrorTab)
================================================================================
專為 macOS「iPhone 鏡像輸出 (iPhone Mirroring)」設計的完整自動化控制介面：
1. 鎖定 iPhone 鏡像視窗，完全脫離 ADB 模擬器束縛。
2. 所有邏輯與「聯賽自動刷」100% 對齊：
   - 優先動作步驟列表 + 一般循環步驟列表。
   - 圖片特徵模板多尺度比對 + RapidOCR 多語系文字辨識。
   - 支援展開/折疊、動作、自訂座標、延遲、ROI 搜尋區域、Telegram 通知。
   - 支援獨立存檔與載入（乾淨存檔視窗，自由選擇路徑，不自動建雜項目錄）。
   - 支援即時畫面預覽、拖曳框選「✂️ 裁切截圖」並自動套用至步驟。
3. 專屬滑鼠控制增強：
   - 自動將 iPhone 視窗座標映射至 Mac 螢幕邏輯座標。
   - 支援「⚡ 點擊時移至最前景」與「🎯 點擊後游標自動歸位」，不影響使用者正常辦公。
================================================================================
"""

import os
import sys
import time
import json
import threading
import datetime
from typing import Optional, Dict, Any, List, Tuple
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk

# 匯入 iPhone 鏡像機器人核心
from iphone_mirror_bot import IPhoneMirrorBot, IPhoneWindowController

# 現代化深色調色盤與常數 (完全獨立，消除循環引用)
COLOR_BG = "#1E1E2E"
COLOR_CARD = "#252538"
COLOR_CARD_BORDER = "#313244"
COLOR_CARD_ITEM = "#20222e"
COLOR_INPUT_BG = "#181825"
COLOR_INPUT_BORDER = "#45475A"

COLOR_TEXT_PRIMARY = "#CDD6F4"
COLOR_TEXT_MUTED = "#A6ADC8"
COLOR_TEXT_DIM = "#6C7086"

COLOR_RUNNING = "#22C55E"
COLOR_PAUSED = "#F59E0B"
COLOR_STOPPED = "#EF4444"

COLOR_BTN_START = "#10B981"
COLOR_BTN_START_HOVER = "#059669"
COLOR_BTN_STOP = "#EF4444"
COLOR_BTN_STOP_HOVER = "#DC2626"
COLOR_BTN_PRIMARY = "#3B82F6"
COLOR_BTN_PRIMARY_HOVER = "#2563EB"
COLOR_BTN_DARK = "#313244"
COLOR_BTN_DARK_HOVER = "#45475A"

PREVIEW_CANVAS_W = 800
PREVIEW_CANVAS_H = 450

RECOGNITION_MODES = ["🖼️ 圖片特徵比對模式", "📝 文字辨識模式"]
ACTION_TARGET_IMAGE = "點擊目標中心"
ACTION_TARGET_TEXT = "點擊詞條"
ACTION_CUSTOM_COORD = "點擊自訂座標"
ACTION_TASK_FLOW = "📋 執行任務清單"

def is_target_center_action(act_str: str) -> bool:
    if not act_str: return False
    return "中心" in act_str or "詞條" in act_str

def is_custom_coord_action(act_str: str) -> bool:
    if not act_str: return False
    return "自訂座標" in act_str or "指定座標" in act_str

def imread_unicode(filepath: str, flags: int = cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
    try:
        with open(filepath, "rb") as f:
            bytes_data = bytearray(f.read())
        nparr = np.asarray(bytes_data, dtype=np.uint8)
        return cv2.imdecode(nparr, flags)
    except Exception:
        return None

def imwrite_unicode(filepath: str, img: np.ndarray) -> bool:
    try:
        ext = os.path.splitext(filepath)[1]
        if not ext: ext = ".png"
        ret, buf = cv2.imencode(ext, img)
        if not ret: return False
        with open(filepath, "wb") as f:
            f.write(buf.tobytes())
        return True
    except Exception:
        return False


def _num(var, default, cast=float):
    """安全讀取數值變數 (輸入框暫時為空或格式錯誤時回傳預設值)"""
    try:
        val = var.get() if hasattr(var, "get") else var
        return cast(val)
    except Exception:
        return default


class IPhoneMirrorTab:
    """iPhone 鏡像輸出專屬自動刷關分頁管理器"""

    def __init__(self, gui_parent, tab_container: ctk.CTkFrame):
        self.gui = gui_parent
        self.parent = tab_container

        # 核心機器人引擎 (專屬 iPhone 滑鼠點擊與視窗截圖，100% 複用 BaseballBot 核心)
        self.bot = IPhoneMirrorBot(
            templates_dir=getattr(self.gui, "storage_dir", os.path.dirname(os.path.abspath(__file__))),
            logger_func=self.log_message,
            on_frame_callback=self.on_bot_frame_update
        )

        # 狀態變數
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.current_screen_bgr: Optional[np.ndarray] = None
        self.last_snipped_template: Optional[str] = None
        self.preview_scale = 1.0
        self.preview_img_w = 0
        self.preview_img_h = 0
        self.preview_crop_coords = None
        self.raw_screen_w = 0
        self.raw_screen_h = 0

        # 控制變數
        self.var_status_text = tk.StringVar(value="未連線 (DISCONNECTED)")
        self.var_recognition_mode = tk.StringVar(value="🖼️ 圖片特徵比對模式")
        self.var_window_name = tk.StringVar(value="iPhone Mirroring")
        self.var_auto_activate = tk.BooleanVar(value=True)
        self.var_restore_cursor = tk.BooleanVar(value=True)

        self.var_interval = tk.DoubleVar(value=2.0)
        self.var_confidence = tk.DoubleVar(value=0.75)
        self.var_idle_strategy = tk.StringVar(value="常規等待")
        self.var_preview_interval = tk.StringVar(value="1.5秒")
        self.var_auto_refresh = tk.BooleanVar(value=True)
        self.var_preview_coords = tk.StringVar(value="游標: (0, 0)")

        # 語言辨識勾選 (OCR)
        self.var_lang_tc = tk.BooleanVar(value=True)
        self.var_lang_sc = tk.BooleanVar(value=False)
        self.var_lang_en = tk.BooleanVar(value=True)

        # 超時看門狗與閒置防掛機
        self.var_watchdog_enabled = tk.BooleanVar(value=False)
        self.var_watchdog_seconds = tk.IntVar(value=60)
        self.var_idle_tap_enabled = tk.BooleanVar(value=False)
        self.var_idle_tap_area = tk.StringVar(value="右下角區域")
        self.var_idle_tap_times = tk.IntVar(value=3)
        self.var_idle_tap_interval = tk.IntVar(value=30)
        self.var_idle_tap_custom_x = tk.IntVar(value=600)
        self.var_idle_tap_custom_y = tk.IntVar(value=300)

        # Telegram
        self.var_tg_token = tk.StringVar(value=getattr(self.gui, "var_tg_token", tk.StringVar()).get())
        self.var_tg_chat_id = tk.StringVar(value=getattr(self.gui, "var_tg_chat_id", tk.StringVar()).get())

        # 步驟清單
        self.priority_steps_list: List[Dict[str, Any]] = []
        self.steps_list: List[Dict[str, Any]] = []

        # 專屬存檔設定檔 (預設與專案同目錄)
        base_dir = getattr(self.gui, "storage_dir", os.path.dirname(os.path.abspath(__file__)))
        self.save_file = os.path.join(base_dir, "iphone_last_config.json")

        # 建構介面
        self._build_ui()
        self._init_default_steps()

    # ==========================================================================
    # 🎨 UI 建構 (頂部視窗控制列 + 左右雙欄佈局)
    # ==========================================================================
    def _build_ui(self):
        container = ctk.CTkFrame(self.parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=4, pady=4)

        # 1. 頂部視窗鎖定與控制列
        self._build_top_control_bar(container)

        # 2. 左右主雙欄
        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(6, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0)
        body.grid_rowconfigure(0, weight=1)

        # 左欄：步驟卡片列表 + 進階參數卡片
        left_pane = ctk.CTkFrame(body, fg_color="transparent")
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        self._build_steps_panel(left_pane)
        self._build_advanced_panel(left_pane)

        # 右欄：即時預覽卡片 + 日誌終端視窗 (固定寬度 824px)
        right_pane = ctk.CTkFrame(body, fg_color="transparent", width=824)
        right_pane.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        right_pane.grid_rowconfigure(0, weight=0)
        right_pane.grid_rowconfigure(1, weight=1)
        right_pane.grid_columnconfigure(0, weight=1)

        self._build_preview_panel(right_pane)
        self._build_log_panel(right_pane)

    def _build_top_control_bar(self, parent: ctk.CTkFrame):
        """建構頂部控制列：iPhone 視窗鎖定選單、存檔/載入、啟動/停止按鈕"""
        top_bar = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        top_bar.pack(fill="x", pady=(0, 6))

        inner = ctk.CTkFrame(top_bar, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        # 左側：狀態指示燈 + iPhone 視窗鎖定控制器
        left_box = ctk.CTkFrame(inner, fg_color="transparent")
        left_box.pack(side="left", fill="x", expand=True)

        row1 = ctk.CTkFrame(left_box, fg_color="transparent")
        row1.pack(anchor="w", fill="x")

        self.indicator_light = ctk.CTkLabel(row1, text="●", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_STOPPED)
        self.indicator_light.pack(side="left", padx=(0, 6))

        self.lbl_status = ctk.CTkLabel(row1, textvariable=self.var_status_text, font=ctk.CTkFont(family="Arial", size=13, weight="bold"), text_color=COLOR_STOPPED)
        self.lbl_status.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(row1, text="📱 目標視窗:", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))

        self.combo_windows = ctk.CTkComboBox(
            row1,
            variable=self.var_window_name,
            values=["iPhone Mirroring", "iPhone鏡像輸出", "QuickTime Player"],
            width=160,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11)
        )
        self.combo_windows.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            row1,
            text="🔍 鎖定 iPhone 鏡像",
            width=120,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self.on_lock_window
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            row1,
            text="🔄 刷新視窗",
            width=76,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_refresh_windows
        ).pack(side="left", padx=(0, 10))

        # 視窗資訊顯示與滑鼠點擊設定
        row2 = ctk.CTkFrame(left_box, fg_color="transparent")
        row2.pack(anchor="w", fill="x", pady=(4, 0))

        self.lbl_win_info = ctk.CTkLabel(
            row2,
            text="視窗資訊: 尚未鎖定視窗 (請確保 iPhone 鏡像輸出 App 已開啟)",
            font=ctk.CTkFont(family="Menlo", size=11),
            text_color="#60A5FA"
        )
        self.lbl_win_info.pack(side="left", padx=(0, 14))

        ctk.CTkCheckBox(
            row2,
            text="⚡ 點擊時移至最前景",
            variable=self.var_auto_activate,
            font=ctk.CTkFont(size=11),
            width=120,
            checkbox_width=16,
            checkbox_height=16
        ).pack(side="left", padx=(0, 8))

        ctk.CTkCheckBox(
            row2,
            text="🎯 點擊後游標歸位 (不搶滑鼠)",
            variable=self.var_restore_cursor,
            font=ctk.CTkFont(size=11),
            width=150,
            checkbox_width=16,
            checkbox_height=16
        ).pack(side="left")

        # 右側：存檔、載入、啟動、停止按鈕
        right_box = ctk.CTkFrame(inner, fg_color="transparent")
        right_box.pack(side="right")

        ctk.CTkButton(
            right_box,
            text="💾 儲存設定",
            width=84,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=self.on_save_config_dialog
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            right_box,
            text="📂 載入設定",
            width=84,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_load_config_dialog
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            right_box,
            text="🔄 套用聯賽步驟",
            width=100,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color="#8B5CF6",
            hover_color="#7C3AED",
            command=self.on_apply_league_config
        ).pack(side="left", padx=(0, 10))

        self.btn_start = ctk.CTkButton(
            right_box,
            text="▶ 啟動 iPhone 刷關",
            width=120,
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            fg_color=COLOR_BTN_START,
            hover_color=COLOR_BTN_START_HOVER,
            state="disabled",
            command=self.on_start_bot
        )
        self.btn_start.pack(side="left", padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            right_box,
            text="⏹ 停止刷關",
            width=100,
            height=36,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            fg_color=COLOR_BTN_STOP,
            hover_color=COLOR_BTN_STOP_HOVER,
            state="disabled",
            command=self.on_stop_bot
        )
        self.btn_stop.pack(side="left")

    # ==========================================================================
    # 📋 步驟管理面板 (步驟清單 + 優先動作)
    # ==========================================================================
    def _build_steps_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="both", expand=True, pady=(0, 8))

        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=12, pady=(10, 8))

        # 第一行：標題 + 全域辨識模式開關
        r1 = ctk.CTkFrame(tools, fg_color="transparent")
        r1.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            r1,
            text="📋 步驟與優先動作 (iPhone 鏡像模式)",
            font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        ).pack(side="left")

        self.seg_mode = ctk.CTkSegmentedButton(
            r1,
            values=RECOGNITION_MODES,
            variable=self.var_recognition_mode,
            command=self._on_recognition_mode_changed,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            selected_color=COLOR_BTN_PRIMARY,
            selected_hover_color=COLOR_BTN_PRIMARY_HOVER
        )
        self.seg_mode.pack(side="right")

        # 第二行：步驟新增按鈕群
        r2 = ctk.CTkFrame(tools, fg_color="transparent")
        r2.pack(fill="x")

        ctk.CTkButton(
            r2, text="＋ 優先動作", width=84, height=28, corner_radius=6,
            command=self.on_add_priority_step, fg_color="#F59E0B", hover_color="#D97706",
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            r2, text="⚡ 事件跳轉", width=84, height=28, corner_radius=6,
            command=self.on_add_task_trigger_step, fg_color="#8B5CF6", hover_color="#7C3AED",
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="left", padx=3)

        ctk.CTkButton(
            r2, text="＋ 一般步驟", width=84, height=28, corner_radius=6,
            command=self.on_add_empty_step, fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER,
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="left", padx=3)

        # 滾動步驟區域
        self.step_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", corner_radius=8)
        self.step_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 1. 優先動作區塊
        self.f_prio_header = ctk.CTkFrame(self.step_scroll, fg_color="transparent")
        self.f_prio_header.pack(fill="x", padx=4, pady=(2, 4))
        ctk.CTkLabel(
            self.f_prio_header, text="⚡ 優先動作 (高優先全域中斷，每次循環最先檢查)",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color="#F59E0B"
        ).pack(side="left")

        self.f_priority_list = ctk.CTkFrame(self.step_scroll, fg_color="transparent")
        self.f_priority_list.pack(fill="x", padx=2, pady=(0, 8))

        self.lbl_no_priority = ctk.CTkLabel(
            self.f_priority_list, text="（目前無優先動作，可點擊上方「＋ 優先動作」新增如斷線重連、彈窗關閉等高優先級判斷）",
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_DIM
        )
        self.lbl_no_priority.pack(pady=4)

        # 2. 一般步驟區塊
        self.f_normal_header = ctk.CTkFrame(self.step_scroll, fg_color="transparent")
        self.f_normal_header.pack(fill="x", padx=4, pady=(6, 4))
        ctk.CTkLabel(
            self.f_normal_header, text="🔄 一般步驟清單 (由上至下依序巡檢，命中即執行點擊並換頁)",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color=COLOR_TEXT_PRIMARY
        ).pack(side="left")

        self.f_steps_list = ctk.CTkFrame(self.step_scroll, fg_color="transparent")
        self.f_steps_list.pack(fill="x", padx=2, pady=(0, 4))

        self.lbl_no_steps = ctk.CTkLabel(
            self.f_steps_list, text="（目前無一般步驟，可點擊上方「＋ 一般步驟」新增）",
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_DIM
        )
        self.lbl_no_steps.pack(pady=6)

    # ==========================================================================
    # ⚙️ 進階參數面板
    # ==========================================================================
    def _build_advanced_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="x", pady=(0, 4))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        # 標題行
        r_title = ctk.CTkFrame(inner, fg_color="transparent")
        r_title.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            r_title, text="⚙️ 運行頻率與進階設定",
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"), text_color=COLOR_TEXT_PRIMARY
        ).pack(side="left")

        # 參數控制格
        grid = ctk.CTkFrame(inner, fg_color="transparent")
        grid.pack(fill="x")

        # 巡檢間隔
        ctk.CTkLabel(grid, text="巡檢週期:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).grid(row=0, column=0, sticky="w", pady=3)
        self.slider_sp = ctk.CTkSlider(grid, from_=0.5, to=5.0, number_of_steps=45, variable=self.var_interval, width=130, height=16, command=lambda v: self.lbl_sp_val.configure(text=f"{v:.1f}s"))
        self.slider_sp.grid(row=0, column=1, sticky="w", padx=6, pady=3)
        self.lbl_sp_val = ctk.CTkLabel(grid, text=f"{self.var_interval.get():.1f}s", font=ctk.CTkFont(family="Menlo", size=11, weight="bold"), text_color="#FBBF24", width=36)
        self.lbl_sp_val.grid(row=0, column=2, sticky="w", pady=3)

        # 辨識信心度
        ctk.CTkLabel(grid, text="信心度門檻:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).grid(row=0, column=3, sticky="w", padx=(12, 0), pady=3)
        self.slider_cf = ctk.CTkSlider(grid, from_=0.40, to=0.95, number_of_steps=55, variable=self.var_confidence, width=130, height=16, command=lambda v: self.lbl_cf_val.configure(text=f"{v:.2f}"))
        self.slider_cf.grid(row=0, column=4, sticky="w", padx=6, pady=3)
        self.lbl_cf_val = ctk.CTkLabel(grid, text=f"{self.var_confidence.get():.2f}", font=ctk.CTkFont(family="Menlo", size=11, weight="bold"), text_color="#10B981", width=36)
        self.lbl_cf_val.grid(row=0, column=5, sticky="w", pady=3)

        # 語言設定
        r_lang = ctk.CTkFrame(inner, fg_color="transparent")
        r_lang.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(r_lang, text="OCR 辨識語言:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 8))
        ctk.CTkCheckBox(r_lang, text="繁體中文", variable=self.var_lang_tc, font=ctk.CTkFont(size=11), width=76, checkbox_width=16, checkbox_height=16).pack(side="left", padx=3)
        ctk.CTkCheckBox(r_lang, text="英文 (English)", variable=self.var_lang_en, font=ctk.CTkFont(size=11), width=96, checkbox_width=16, checkbox_height=16).pack(side="left", padx=3)
        ctk.CTkCheckBox(r_lang, text="簡體中文 (過濾誤判)", variable=self.var_lang_sc, font=ctk.CTkFont(size=11), width=120, checkbox_width=16, checkbox_height=16).pack(side="left", padx=3)

    # ==========================================================================
    # 📸 即時畫面預覽卡片
    # ==========================================================================
    def _build_preview_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="x", pady=(0, 6))

        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=12, pady=(10, 6))

        self.btn_capture = ctk.CTkButton(
            tools, text="📸 立即截取", width=84, height=28, corner_radius=6,
            command=self.on_preview_and_detect, fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER, font=ctk.CTkFont(size=12, weight="bold")
        )
        self.btn_capture.pack(side="left")

        ctk.CTkLabel(tools, text="⏱ 刷新:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(8, 3))
        self.combo_preview_interval = ctk.CTkOptionMenu(
            tools, values=["0.5秒", "1.0秒", "1.5秒", "2.0秒", "3.0秒"],
            variable=self.var_preview_interval, width=76, height=28
        )
        self.combo_preview_interval.pack(side="left", padx=(0, 8))

        self.btn_crop_selection = ctk.CTkButton(
            tools, text="✂️ 裁切截圖", width=92, height=28, corner_radius=6,
            state="disabled", fg_color=COLOR_BTN_DARK, hover_color="#D97706",
            font=ctk.CTkFont(size=12, weight="bold"), command=self.on_crop_preview_selection
        )
        self.btn_crop_selection.pack(side="left")

        self.lbl_preview_coords = ctk.CTkLabel(
            tools, textvariable=self.var_preview_coords,
            font=ctk.CTkFont(family="Menlo", size=11, weight="bold"), text_color="#60A5FA", anchor="e"
        )
        self.lbl_preview_coords.pack(side="right", padx=4)

        # 預覽畫布 (Canvas)
        c_frame = ctk.CTkFrame(card, fg_color="#11111B", corner_radius=8, width=PREVIEW_CANVAS_W, height=PREVIEW_CANVAS_H)
        c_frame.pack(padx=12, pady=(0, 10))
        c_frame.pack_propagate(False)

        self.preview_canvas = tk.Canvas(
            c_frame, bg="#11111B", highlightthickness=0,
            width=PREVIEW_CANVAS_W, height=PREVIEW_CANVAS_H, cursor="crosshair"
        )
        self.preview_canvas.pack(fill="both", expand=True)

        self.preview_canvas.create_text(
            PREVIEW_CANVAS_W // 2, PREVIEW_CANVAS_H // 2,
            text="📱 請點擊上方【🔍 鎖定 iPhone 鏡像】連接畫面\n連線後將自動即時刷新遊戲畫面\n可直接在畫面上「按住滑鼠左鍵拖曳框選」按鈕並點擊【✂️ 裁切截圖】",
            fill=COLOR_TEXT_DIM, font=("Arial", 13, "bold"), justify="center", tags="placeholder_text"
        )

        self.preview_canvas.bind("<Button-1>", self._on_preview_canvas_down)
        self.preview_canvas.bind("<B1-Motion>", self._on_preview_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_preview_canvas_up)
        self.preview_canvas.bind("<Motion>", self._on_preview_mouse_move)

    # ==========================================================================
    # 💻 等寬日誌終端面板
    # ==========================================================================
    def _build_log_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="both", expand=True, pady=(0, 2))

        tb = ctk.CTkFrame(card, fg_color="transparent")
        tb.pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkLabel(
            tb, text="💻 iPhone 自動刷運行日誌",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color=COLOR_TEXT_PRIMARY
        ).pack(side="left")

        ctk.CTkButton(
            tb, text="清空日誌", width=60, height=22, corner_radius=4,
            font=ctk.CTkFont(size=10), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER,
            command=self.clear_logs
        ).pack(side="right")

        self.txt_log = ctk.CTkTextbox(
            card, fg_color="#11111B", text_color="#A6ADC8",
            font=ctk.CTkFont(family="Menlo", size=10), corner_radius=8
        )
        self.txt_log.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def log_message(self, msg: str):
        """日誌輸出至終端視窗"""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        if hasattr(self, "txt_log") and self.txt_log:
            try:
                self.txt_log.insert("end", line)
                self.txt_log.see("end")
            except Exception:
                pass

    def clear_logs(self):
        if hasattr(self, "txt_log") and self.txt_log:
            self.txt_log.delete("1.0", "end")

    # ==========================================================================
    # 🔍 視窗鎖定控制
    # ==========================================================================
    def on_refresh_windows(self):
        """重新獲取 macOS 上的視窗清單"""
        self.log_message("正在搜尋 macOS 前台視窗...")
        wins = self.bot.window_ctrl.get_running_windows()
        app_names = sorted(list(set([w["owner"] for w in wins if w.get("owner")])))
        if "iPhone Mirroring" not in app_names:
            app_names.insert(0, "iPhone Mirroring")
        self.combo_windows.configure(values=app_names)
        self.log_message(f"發現 {len(app_names)} 個前台應用程式視窗。")

    def on_lock_window(self):
        """鎖定目標 iPhone 鏡像視窗"""
        target = self.var_window_name.get().strip() or None
        self.log_message(f"正在鎖定視窗: {target or 'iPhone Mirroring (預設)'}...")
        if self.bot.connect(target_serial=target):
            self._set_status("已鎖定 (LOCKED)", COLOR_RUNNING)
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")

            ctrl = self.bot.window_ctrl
            info_str = f"已鎖定: {ctrl.locked_app_name} (位置: {int(ctrl.win_x)}, {int(ctrl.win_y)} | 尺寸: {int(ctrl.win_w)}×{int(ctrl.win_h)})"
            self.lbl_win_info.configure(text=info_str)
            self.log_message(f"✅ {info_str}")

            # 立即截圖並開啟自動刷新
            self.on_preview_and_detect()
            if self.var_auto_refresh.get():
                self._schedule_next_refresh(self._get_preview_interval_ms())
        else:
            self._set_status("未連線 (FAILED)", COLOR_STOPPED)
            self.lbl_win_info.configure(text="未找到 iPhone 鏡像視窗！請先在 Mac 上打開「iPhone 鏡像輸出」App。")
            messagebox.showwarning(
                "未找到視窗",
                "未在 Mac 上找到 iPhone 鏡像輸出視窗！\n\n請確認：\n1. 您的 iPhone 已成功與 Mac 建立「iPhone 鏡像輸出」連線。\n2. 「iPhone 鏡像輸出」App 視窗未被最小化關閉。",
                parent=self.parent
            )

    def _set_status(self, text: str, color: str):
        self.var_status_text.set(text)
        self.lbl_status.configure(text_color=color)
        self.indicator_light.configure(text_color=color)

    # ==========================================================================
    # 📸 預覽畫布與裁切截圖邏輯
    # ==========================================================================
    def on_preview_and_detect(self):
        """手動或定時截取 iPhone 畫面並渲染至預覽畫布"""
        if not self.bot.window_ctrl.locked_app_name:
            if not self.bot.connect():
                return
        img_bgr = self.bot.capture_screen()
        if img_bgr is not None:
            self.current_screen_bgr = img_bgr
            self._render_preview(img_bgr)

    def _schedule_next_refresh(self, delay_ms: int):
        if not hasattr(self, "parent") or not self.parent:
            return
        self.parent.after(delay_ms, self._auto_refresh_callback)

    def _auto_refresh_callback(self):
        if self.var_auto_refresh.get() and not self.is_running and self.bot.window_ctrl.locked_app_name:
            self.on_preview_and_detect()
            self._schedule_next_refresh(self._get_preview_interval_ms())

    def _get_preview_interval_ms(self) -> int:
        try:
            val = float(self.var_preview_interval.get().replace("秒", "").strip())
            return max(300, int(val * 1000))
        except Exception:
            return 1500

    def _render_preview(self, img_bgr: np.ndarray):
        h, w = img_bgr.shape[:2]
        self.raw_screen_w, self.raw_screen_h = w, h
        scale = min(PREVIEW_CANVAS_W / w, PREVIEW_CANVAS_H / h)
        self.preview_scale = scale
        disp_w, disp_h = int(w * scale), int(h * scale)
        self.preview_img_w, self.preview_img_h = disp_w, disp_h

        resized = cv2.resize(img_bgr, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        self.preview_photo = ImageTk.PhotoImage(pil_img)

        self.preview_canvas.delete("placeholder_text")
        self.preview_canvas.delete("screen_img")
        self.preview_canvas.create_image(
            PREVIEW_CANVAS_W // 2, PREVIEW_CANVAS_H // 2,
            image=self.preview_photo, anchor="center", tags="screen_img"
        )
        self.preview_canvas.tag_lower("screen_img")

    def _preview_to_real(self, cx: int, cy: int) -> Tuple[Optional[int], Optional[int]]:
        if not self.raw_screen_w or not self.preview_scale:
            return None, None
        w_offset = max(0, (PREVIEW_CANVAS_W - self.preview_img_w) // 2)
        h_offset = max(0, (PREVIEW_CANVAS_H - self.preview_img_h) // 2)
        img_x = cx - w_offset
        img_y = cy - h_offset
        if 0 <= img_x <= self.preview_img_w and 0 <= img_y <= self.preview_img_h:
            rx = int(img_x / self.preview_scale)
            ry = int(img_y / self.preview_scale)
            return min(self.raw_screen_w, max(0, rx)), min(self.raw_screen_h, max(0, ry))
        return None, None

    def _on_preview_mouse_move(self, e):
        rx, ry = self._preview_to_real(e.x, e.y)
        if rx is not None and ry is not None:
            ctrl = self.bot.window_ctrl
            screen_x = int(ctrl.win_x + (rx / ctrl.scale_x))
            screen_y = int(ctrl.win_y + (ry / ctrl.scale_y))
            self.var_preview_coords.set(f"iPhone: ({rx}, {ry}) | Mac螢幕: ({screen_x}, {screen_y})")

    def _on_preview_canvas_down(self, e):
        self.crop_start_x = e.x
        self.crop_start_y = e.y
        self.preview_canvas.delete("selection_box")
        self.preview_canvas.delete("selection_text")
        self.preview_crop_coords = None

    def _on_preview_canvas_drag(self, e):
        self.preview_canvas.delete("selection_box")
        self.preview_canvas.create_rectangle(
            self.crop_start_x, self.crop_start_y, e.x, e.y,
            outline="#F59E0B", width=2, dash=(4, 2), tags="selection_box"
        )

    def _on_preview_canvas_up(self, e):
        rx1, ry1 = self._preview_to_real(min(self.crop_start_x, e.x), min(self.crop_start_y, e.y))
        rx2, ry2 = self._preview_to_real(max(self.crop_start_x, e.x), max(self.crop_start_y, e.y))
        if rx1 is not None and rx2 is not None and abs(rx2 - rx1) >= 6 and abs(ry2 - ry1) >= 6:
            self.preview_crop_coords = (min(rx1, rx2), min(ry1, ry2), max(rx1, rx2), max(ry1, ry2))
            rw = abs(rx2 - rx1)
            rh = abs(ry2 - ry1)
            self.btn_crop_selection.configure(
                state="normal", text=f"✂️ 裁切截圖 ({rw}×{rh})", fg_color="#F59E0B"
            )
            self.var_preview_coords.set(f"已選取範圍: {rw}×{rh}，請按【✂️ 裁切截圖】")
        else:
            self.preview_canvas.delete("selection_box")
            self.preview_crop_coords = None
            self.btn_crop_selection.configure(state="disabled", text="✂️ 裁切截圖", fg_color=COLOR_BTN_DARK)

    def on_crop_preview_selection(self):
        """將在預覽畫面上框選的區域裁切儲存為模板圖片，詢問使用者儲存位置，並自動套用至步驟"""
        if self.current_screen_bgr is None or not self.preview_crop_coords:
            messagebox.showwarning("提示", "尚未在預覽畫面上框選任何區域！", parent=self.parent)
            return

        rx1, ry1, rx2, ry2 = self.preview_crop_coords
        crop_bgr = self.current_screen_bgr[ry1:ry2, rx1:rx2].copy()
        ch, cw = crop_bgr.shape[:2]
        if cw < 4 or ch < 4:
            return

        # 找出當前展開之步驟
        active_step = None
        for p in self.priority_steps_list:
            if p.get("expanded") and p["expanded"].get():
                active_step = p
                break
        if not active_step:
            for s in self.steps_list:
                if s.get("expanded") and s["expanded"].get():
                    active_step = s
                    break

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if active_step:
            step_name = active_step["name"].get().strip()
            clean_name = "".join(c for c in step_name if c.isalnum() or c in ("_", "-")).strip()
            init_fname = f"{clean_name}.png" if clean_name else f"iphone_snip_{ts}.png"
        else:
            init_fname = f"iphone_template_{ts}.png"

        init_dir = getattr(self.gui, "storage_dir", os.path.dirname(os.path.abspath(__file__)))
        save_path = filedialog.asksaveasfilename(
            parent=self.parent,
            title="✂️ 儲存圖片模板 (請選擇儲存位置與檔名)",
            initialdir=init_dir,
            initialfile=init_fname,
            defaultextension=".png",
            filetypes=[("PNG 圖片", "*.png"), ("所有檔案", "*.*")]
        )
        if not save_path:
            return

        try:
            success = imwrite_unicode(save_path, crop_bgr)
            if not success:
                messagebox.showerror("錯誤", f"無法寫入圖檔至:\n{save_path}", parent=self.parent)
                return

            self.last_snipped_template = save_path
            fname = os.path.basename(save_path)
            tpl_ref = fname if (self.gui.storage_dir and os.path.commonpath([os.path.abspath(save_path), os.path.abspath(self.gui.storage_dir)]) == os.path.abspath(self.gui.storage_dir)) else os.path.abspath(save_path)

            applied_msg = ""
            target_step = active_step
            if not target_step and self.steps_list:
                target_step = self.steps_list[0]

            if target_step:
                target_step["template_image"].set(tpl_ref)
                if "target_type" in target_step:
                    target_step["target_type"].set("🖼️ 圖片特徵 (模板比對)")
                applied_msg = f"\n\n已自動套用至步驟：「{target_step['name'].get()}」！"

            self.auto_save_current_config()
            self._refresh_all_step_thumbs()
            self.log_message(f"✂️ 截圖儲存成功: {save_path} ({cw}×{ch}){applied_msg.replace(chr(10), ' ')}")

            self.preview_canvas.delete("selection_box")
            self.preview_crop_coords = None
            self.btn_crop_selection.configure(state="disabled", text="✂️ 裁切截圖", fg_color=COLOR_BTN_DARK)
            messagebox.showinfo("截圖成功", f"✅ 圖片模板已成功儲存至：\n{save_path}{applied_msg}", parent=self.parent)
        except Exception as ex:
            self.log_message(f"❌ 截圖儲存失敗: {ex}")
            messagebox.showerror("截圖失敗", f"無法儲存截圖: {ex}", parent=self.parent)

    # ==========================================================================
    # ➕ 步驟卡片生成與操作
    # ==========================================================================
    def on_add_priority_step(self):
        p = self.gui._create_priority_step_widget_impl(
            container=self.f_priority_list,
            steps_collection=self.priority_steps_list,
            lbl_empty=self.lbl_no_priority,
            name=f"優先動作 {len(self.priority_steps_list) + 1}",
            on_changed=self.auto_save_current_config
        )
        self.auto_save_current_config()

    def on_add_task_trigger_step(self):
        p = self.gui._create_priority_step_widget_impl(
            container=self.f_priority_list,
            steps_collection=self.priority_steps_list,
            lbl_empty=self.lbl_no_priority,
            name="事件跳轉",
            action=ACTION_TASK_FLOW,
            on_changed=self.auto_save_current_config
        )
        self.auto_save_current_config()

    def on_add_empty_step(self):
        s = self.gui._create_step_widget_impl(
            container=self.f_steps_list,
            steps_collection=self.steps_list,
            lbl_empty=self.lbl_no_steps,
            name=f"步驟 {len(self.steps_list) + 1}",
            on_changed=self.auto_save_current_config
        )
        self.auto_save_current_config()

    def _on_recognition_mode_changed(self, val):
        is_img = ("圖片" in val)
        for p in self.priority_steps_list:
            if "target_type" in p:
                p["target_type"].set("🖼️ 圖片特徵 (模板比對)" if is_img else "📝 文字辨識 (OCR)")
        for s in self.steps_list:
            if "target_type" in s:
                s["target_type"].set("🖼️ 圖片特徵 (模板比對)" if is_img else "📝 文字辨識 (OCR)")
        self.auto_save_current_config()

    def _refresh_all_step_thumbs(self):
        for p in self.priority_steps_list:
            if "template_image" in p:
                try: p["template_image"].set(p["template_image"].get())
                except Exception: pass
        for s in self.steps_list:
            if "template_image" in s:
                try: s["template_image"].set(s["template_image"].get())
                except Exception: pass

    # ==========================================================================
    # 💾 存檔與載入 (純粹乾淨存檔視窗，不生成額外資料夾)
    # ==========================================================================
    def on_save_config_dialog(self):
        """開啟專屬存檔視窗：詢問使用者要存到哪裡，可直接自訂路徑與檔名儲存"""
        dlg = ctk.CTkToplevel(self.parent)
        dlg.title("💾 儲存 iPhone 自動刷設定")
        dlg.geometry("580x300")
        dlg.resizable(False, False)
        dlg.configure(fg_color=COLOR_BG)
        dlg.grab_set()
        dlg.transient(self.parent)

        card = ctk.CTkFrame(dlg, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        header_box = ctk.CTkFrame(card, fg_color="transparent")
        header_box.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            header_box,
            text="💾 儲存 iPhone 自動刷設定 (Save Config)",
            font=ctk.CTkFont(family="Arial", size=16, weight="bold"),
            text_color="#FBBF24"
        ).pack(anchor="w")

        ctk.CTkLabel(
            header_box,
            text="請選擇或輸入設定檔要儲存到哪裡（.json 檔案）：",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_PRIMARY
        ).pack(anchor="w", pady=(4, 0))

        sec_path = ctk.CTkFrame(card, fg_color=COLOR_INPUT_BG, corner_radius=8, border_width=1, border_color=COLOR_CARD_BORDER)
        sec_path.pack(fill="x", padx=16, pady=(8, 12))

        sec_path_inner = ctk.CTkFrame(sec_path, fg_color="transparent")
        sec_path_inner.pack(fill="x", padx=12, pady=12)

        var_save_file = tk.StringVar(value=self.save_file)
        entry_save_file = ctk.CTkEntry(
            sec_path_inner, textvariable=var_save_file,
            font=ctk.CTkFont(family="Menlo", size=11), height=32, corner_radius=6,
            fg_color="#181825", border_color="#334155"
        )
        entry_save_file.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _do_browse():
            curr = var_save_file.get().strip()
            init_d = os.path.dirname(curr) if curr and os.path.isdir(os.path.dirname(curr)) else os.getcwd()
            init_f = os.path.basename(curr) if curr else "iphone_config.json"
            if not init_f.endswith(".json"): init_f += ".json"
            f = filedialog.asksaveasfilename(
                parent=dlg, title="選擇存檔位置與檔案名稱",
                initialdir=init_d, initialfile=init_f, defaultextension=".json",
                filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
            )
            if f:
                var_save_file.set(os.path.abspath(f))

        ctk.CTkButton(
            sec_path_inner, text="📁 選擇位置", width=88, height=32,
            corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, command=_do_browse
        ).pack(side="left")

        def _do_save():
            p = var_save_file.get().strip()
            if not p:
                messagebox.showwarning("提示", "請輸入儲存路徑！", parent=dlg)
                return
            if not p.lower().endswith(".json"):
                p += ".json"

            target_path = os.path.abspath(p)
            try:
                parent_dir = os.path.dirname(target_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)

                cfg = self.serialize_config()
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)

                self.save_file = target_path
                self.log_message(f"💾 iPhone 設定已成功儲存至: {target_path}")
                messagebox.showinfo("成功", f"✅ 設定檔已成功儲存至：\n{target_path}", parent=dlg)
                dlg.destroy()
            except Exception as ex:
                self.log_message(f"❌ 儲存失敗: {ex}")
                messagebox.showerror("錯誤", f"儲存失敗: {ex}", parent=dlg)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(10, 16))

        ctk.CTkButton(
            btn_row, text="確認儲存", width=100, height=32, corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"), fg_color="#10B981", hover_color="#059669",
            command=_do_save
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row, text="取消", width=72, height=32, corner_radius=6,
            font=ctk.CTkFont(size=12), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER,
            command=dlg.destroy
        ).pack(side="right")

    def on_load_config_dialog(self):
        """開啟載入設定對話框 (支援選擇任何 iPhone 或聯賽自動刷的 JSON 存檔)"""
        init_dir = getattr(self.gui, "storage_dir", os.getcwd())
        if not os.path.isdir(init_dir):
            init_dir = os.getcwd()
        path = filedialog.askopenfilename(
            parent=self.parent, title="載入設定檔 (支援 iPhone 或聯賽存檔 JSON)",
            initialdir=init_dir,
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.apply_config(cfg)
                self.save_file = path
                self.auto_save_current_config()
                self.log_message(f"📂 已成功載入設定檔: {os.path.basename(path)}")
                messagebox.showinfo("成功", f"✅ 已成功載入設定檔:\n{path}", parent=self.parent)
            except Exception as ex:
                self.log_message(f"❌ 載入失敗: {ex}")
                messagebox.showerror("錯誤", f"載入失敗: {ex}", parent=self.parent)

    def on_apply_league_config(self):
        """一鍵將「🏆 聯賽自動刷」目前的所有步驟與設定帶入至本 iPhone 鏡像分頁"""
        try:
            cfg = self.gui.serialize_current_config()
            self.apply_config(cfg)
            self.auto_save_current_config()
            self.log_message("📥 已成功同步並套用「🏆 聯賽自動刷」的所有步驟設定！")
            messagebox.showinfo(
                "同步成功",
                "✅ 已成功將「🏆 聯賽自動刷」的所有步驟、優先動作與辨識模式套用至 iPhone 鏡像！",
                parent=self.parent
            )
        except Exception as ex:
            self.log_message(f"❌ 套用聯賽設定失敗: {ex}")
            messagebox.showerror("錯誤", f"套用聯賽設定失敗: {ex}", parent=self.parent)

    def auto_save_current_config(self):
        """定時或操作後靜默自動存檔"""
        try:
            cfg = self.serialize_config()
            parent_d = os.path.dirname(self.save_file)
            if parent_d and not os.path.exists(parent_d):
                os.makedirs(parent_d, exist_ok=True)
            with open(self.save_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def serialize_config(self) -> dict:
        """將目前分頁中所有設定與步驟序列化為 dict (相容聯賽存檔格式)"""
        return {
            "version": "2.0",
            "type": "iphone_mirror",
            "recognition_mode": self.var_recognition_mode.get(),
            "window_name": self.var_window_name.get(),
            "auto_activate": self.var_auto_activate.get(),
            "restore_cursor": self.var_restore_cursor.get(),
            "interval": self.var_interval.get(),
            "confidence": self.var_confidence.get(),
            "idle_strategy": self.var_idle_strategy.get(),
            "allowed_languages": {
                "tc": self.var_lang_tc.get(),
                "sc": self.var_lang_sc.get(),
                "en": self.var_lang_en.get(),
            },
            "lang_tc": self.var_lang_tc.get(),
            "lang_sc": self.var_lang_sc.get(),
            "lang_en": self.var_lang_en.get(),
            "watchdog_enabled": self.var_watchdog_enabled.get(),
            "watchdog_seconds": self.var_watchdog_seconds.get(),
            "watchdog": {
                "enabled": self.var_watchdog_enabled.get(),
                "seconds": self.var_watchdog_seconds.get(),
            },
            "idle_tap": {
                "enabled": self.var_idle_tap_enabled.get(),
                "area": self.var_idle_tap_area.get(),
                "times": self.var_idle_tap_times.get(),
                "interval": self.var_idle_tap_interval.get(),
                "custom_x": self.var_idle_tap_custom_x.get(),
                "custom_y": self.var_idle_tap_custom_y.get(),
            },
            "tg_token": self.var_tg_token.get(),
            "tg_chat_id": self.var_tg_chat_id.get(),
            "telegram_global": {
                "token": self.var_tg_token.get(),
                "chat_id": self.var_tg_chat_id.get(),
            },
            "priority_steps": self.gui._serialize_priority_steps_data(self.priority_steps_list),
            "steps": self.gui._serialize_steps_data(self.steps_list)
        }

    def apply_config(self, cfg: dict):
        """將 dict 設定反序列化載入回本分頁 (完全相容聯賽自動刷與 iPhone 鏡像所有格式)"""
        if not isinstance(cfg, dict):
            return

        # 1. 辨識模式
        if "recognition_mode" in cfg:
            self.var_recognition_mode.set(str(cfg["recognition_mode"]))
        else:
            has_img = any(
                (s.get("template_image") or "圖片" in str(s.get("target_type", "")))
                for s in (cfg.get("steps", []) + cfg.get("priority_steps", []))
            )
            self.var_recognition_mode.set("🖼️ 圖片特徵比對模式" if has_img else "📝 文字辨識模式")

        if "window_name" in cfg:
            self.var_window_name.set(str(cfg["window_name"]))
        if "auto_activate" in cfg:
            self.var_auto_activate.set(bool(cfg["auto_activate"]))
        if "restore_cursor" in cfg:
            self.var_restore_cursor.set(bool(cfg["restore_cursor"]))
        if "interval" in cfg:
            try: self.var_interval.set(float(cfg["interval"]))
            except Exception: pass
        if "confidence" in cfg:
            try: self.var_confidence.set(float(cfg["confidence"]))
            except Exception: pass
        if "idle_strategy" in cfg:
            self.var_idle_strategy.set(str(cfg["idle_strategy"]))

        # 語言設定 (相容 allowed_languages 字典結構或直接布林值)
        if "allowed_languages" in cfg and isinstance(cfg["allowed_languages"], dict):
            langs = cfg["allowed_languages"]
            self.var_lang_tc.set(bool(langs.get("tc", True)))
            self.var_lang_sc.set(bool(langs.get("sc", False)))
            self.var_lang_en.set(bool(langs.get("en", True)))
        else:
            if "lang_tc" in cfg: self.var_lang_tc.set(bool(cfg["lang_tc"]))
            if "lang_sc" in cfg: self.var_lang_sc.set(bool(cfg["lang_sc"]))
            if "lang_en" in cfg: self.var_lang_en.set(bool(cfg["lang_en"]))

        # 看門狗防卡死設定 (相容 watchdog 字典結構或直接布林值)
        if "watchdog" in cfg and isinstance(cfg["watchdog"], dict):
            wd = cfg["watchdog"]
            self.var_watchdog_enabled.set(bool(wd.get("enabled", False)))
            self.var_watchdog_seconds.set(int(wd.get("seconds", 60)))
        else:
            if "watchdog_enabled" in cfg: self.var_watchdog_enabled.set(bool(cfg["watchdog_enabled"]))
            if "watchdog_seconds" in cfg: self.var_watchdog_seconds.set(int(cfg["watchdog_seconds"]))

        # 閒置防卡死連點設定 (相容 idle_tap 字典結構)
        if "idle_tap" in cfg and isinstance(cfg["idle_tap"], dict):
            it = cfg["idle_tap"]
            self.var_idle_tap_enabled.set(bool(it.get("enabled", False)))
            self.var_idle_tap_area.set(str(it.get("area", "右下角區域")))
            self.var_idle_tap_times.set(int(it.get("times", 3)))
            self.var_idle_tap_interval.set(int(it.get("interval", 30)))
            self.var_idle_tap_custom_x.set(int(it.get("custom_x", 600)))
            self.var_idle_tap_custom_y.set(int(it.get("custom_y", 300)))

        # Telegram 通知 (相容 telegram_global 字典結構)
        if "telegram_global" in cfg and isinstance(cfg["telegram_global"], dict):
            tg_g = cfg["telegram_global"]
            self.var_tg_token.set(str(tg_g.get("token", "")))
            self.var_tg_chat_id.set(str(tg_g.get("chat_id", "")))
        else:
            if "tg_token" in cfg: self.var_tg_token.set(str(cfg["tg_token"]))
            if "tg_chat_id" in cfg: self.var_tg_chat_id.set(str(cfg["tg_chat_id"]))

        # 載入步驟
        self._clear_all_steps()
        p_list = cfg.get("priority_steps")
        if p_list is None and "priority" in cfg and isinstance(cfg["priority"], dict):
            p_old = cfg["priority"]
            if p_old.get("keywords") or p_old.get("enabled") or p_old.get("template_image"):
                p_list = [p_old]

        if isinstance(p_list, list):
            for p_data in p_list:
                self.gui._create_priority_step_from_dict(
                    container=self.f_priority_list,
                    steps_collection=self.priority_steps_list,
                    lbl_empty=self.lbl_no_priority,
                    p_data=p_data,
                    on_changed=self.auto_save_current_config
                )

        if isinstance(cfg.get("steps"), list):
            for s_data in cfg["steps"]:
                self.gui._create_step_from_dict(
                    container=self.f_steps_list,
                    steps_collection=self.steps_list,
                    lbl_empty=self.lbl_no_steps,
                    s_data=s_data,
                    on_changed=self.auto_save_current_config
                )

        self._refresh_all_step_thumbs()
        self._on_recognition_mode_changed(self.var_recognition_mode.get())

    def _clear_all_steps(self):
        for p in self.priority_steps_list:
            if "frame" in p and p["frame"]:
                p["frame"].destroy()
        self.priority_steps_list.clear()

        for s in self.steps_list:
            if "frame" in s and s["frame"]:
                s["frame"].destroy()
        self.steps_list.clear()

        if hasattr(self, "lbl_no_priority"):
            self.lbl_no_priority.pack(pady=4)
        if hasattr(self, "lbl_no_steps"):
            self.lbl_no_steps.pack(pady=6)

    def _init_default_steps(self):
        """若有 iPhone 歷史存檔則優先載入；若無則自動讀取聯賽自動刷歷史存檔 (baseball_last_config.json)"""
        # 1. 嘗試讀取專屬 iPhone 設定檔
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.apply_config(cfg)
                self.log_message(f"自動載入 iPhone 歷史設定: {os.path.basename(self.save_file)}")
                return
            except Exception:
                pass

        # 2. 嘗試自動吃聯賽自動刷存檔 (baseball_last_config.json)
        cand_league_files = []
        if hasattr(self.gui, "auto_save_file") and self.gui.auto_save_file:
            cand_league_files.append(self.gui.auto_save_file)
        base_dir = getattr(self.gui, "storage_dir", os.path.dirname(os.path.abspath(__file__)))
        cand_league_files.append(os.path.join(base_dir, "baseball_last_config.json"))
        cand_league_files.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseball_last_config.json"))

        for l_file in cand_league_files:
            if l_file and os.path.exists(l_file):
                try:
                    with open(l_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    self.apply_config(cfg)
                    self.log_message(f"📥 已自動吃到聯賽自動刷存檔: {os.path.basename(l_file)}")
                    return
                except Exception:
                    pass

        # 3. 嘗試直接繼承 gui 目前已載入的步驟
        if hasattr(self.gui, "steps_list") and (self.gui.steps_list or getattr(self.gui, "priority_steps_list", [])):
            try:
                cfg = self.gui.serialize_current_config()
                self.apply_config(cfg)
                self.log_message("📥 已自動帶入目前聯賽自動刷的步驟設定！")
                return
            except Exception:
                pass

        # 4. 預設經典步驟 (最後防線)
        self.gui._create_priority_step_widget_impl(
            container=self.f_priority_list,
            steps_collection=self.priority_steps_list,
            lbl_empty=self.lbl_no_priority,
            name="異常連線中斷",
            keywords="連線中斷, 重新連線, 網路異常, 伺服器維護, 請重新登入",
            action="點擊詞條",
            delay=3.0,
            roi_name="中央區域",
            on_changed=self.auto_save_current_config
        )
        defaults = [
            ("結算確認", "確認, 確定, 領取, 結算, 結束", 3.0, "右下角區域"),
            ("繼續下一場", "繼續, 下一步, 再來一場, 返回", 2.5, "右下角區域"),
            ("準備比賽", "準備, 挑戰, 出戰, 進入", 2.5, "右半側螢幕"),
            ("開始比賽", "開始, 確定開始, 比賽開始, 開打", 4.0, "右下角區域"),
        ]
        for name, kw, d, r in defaults:
            self.gui._create_step_widget_impl(
                container=self.f_steps_list,
                steps_collection=self.steps_list,
                lbl_empty=self.lbl_no_steps,
                name=name, keywords=kw, delay=d, roi_name=r,
                on_changed=self.auto_save_current_config
            )

    # ==========================================================================
    # 🧵 背景巡檢執行緒 (Worker Loop - 滑鼠點擊驅動，與聯賽自動刷 100% 邏輯一致)
    # ==========================================================================
    def _map_roi_name_to_tuple(self, roi_name: str):
        """範圍名稱 -> (ymin, xmin, ymax, xmax) 比例"""
        return {
            "右下角區域": (0.45, 0.45, 1.0, 1.0),
            "右半側螢幕": (0.0, 0.45, 1.0, 1.0),
            "下半部區域": (0.50, 0.0, 1.0, 1.0),
            "中央區域": (0.25, 0.25, 0.75, 0.75),
            "全畫面比對": (0.0, 0.0, 1.0, 1.0),
        }.get(roi_name, (0.0, 0.0, 1.0, 1.0))

    def _get_active_steps_config(self) -> list:
        cfg = []
        is_img_mode = ("圖片" in self.var_recognition_mode.get())
        for s in self.steps_list:
            raw_kws = s["keywords"].get() if "keywords" in s else ""
            kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
            raw_ex = s["exclude_keywords"].get() if "exclude_keywords" in s else ""
            ex_kws = [k.strip() for k in raw_ex.replace("，", ",").split(",") if k.strip()]
            delay = _num(s["delay"], 2.5) if "delay" in s else 2.5
            rep_on = s["repeat_enabled"].get() if "repeat_enabled" in s else False
            tt = "🖼️ 圖片特徵 (模板比對)" if is_img_mode else "📝 文字辨識 (OCR)"
            is_img = is_img_mode
            is_sym = ("打勾" in tt or "叉叉" in tt)
            tpl_img = s["template_image"].get().strip() if "template_image" in s else ""
            img_th = _num(s.get("image_threshold", 0.80), 0.80)
            img_ms = bool(s["image_multiscale"].get()) if "image_multiscale" in s else False

            is_valid_target = (is_img and bool(tpl_img)) or (not is_img and (bool(kws) or is_sym))
            act_val = s["action"].get() if "action" in s else "點擊目標"
            roi_val = s["roi"].get() if "roi" in s else "全畫面比對"

            cfg.append({
                "name": s["name"].get().strip() if "name" in s else "步驟",
                "target_type": tt,
                "template_image": tpl_img,
                "image_threshold": img_th,
                "image_multiscale": img_ms,
                "keywords": kws,
                "exclude_keywords": ex_kws,
                "action": "custom_coord" if is_custom_coord_action(act_val) else act_val,
                "custom_x": _num(s.get("custom_x", 0), 0, int),
                "custom_y": _num(s.get("custom_y", 0), 0, int),
                "delay": delay,
                "delay_min": max(0.05, delay - 0.15),
                "delay_max": delay + 0.15,
                "enabled": (s["enabled"].get() if "enabled" in s else True) and is_valid_target,
                "roi": self._map_roi_name_to_tuple(roi_val),
                "roi_name": roi_val,
                "repeat_enabled": rep_on,
                "repeat_mode": "count" if (s.get("repeat_mode") and s["repeat_mode"].get() == "指定次數") else "until_next",
                "repeat_count": _num(s["repeat_count"], 15, int) if rep_on and "repeat_count" in s else 1,
                "repeat_speed": _num(s["repeat_speed"], 0.3) if "repeat_speed" in s else 0.3,
                "repeat_area": s["repeat_area"].get() if "repeat_area" in s else "右下角區域",
                "repeat_custom_x": _num(s.get("repeat_custom_x", 0), 0, int),
                "repeat_custom_y": _num(s.get("repeat_custom_y", 0), 0, int),
                "repeat_custom_coord": (_num(s.get("repeat_custom_x", 0), 0, int), _num(s.get("repeat_custom_y", 0), 0, int)),
                "timeout_enabled": s["timeout_enabled"].get() if "timeout_enabled" in s else False,
                "timeout_seconds": _num(s["timeout_seconds"], 15, int) if "timeout_seconds" in s else 15,
                "telegram": {
                    "enabled": s["tg_enabled"].get() if "tg_enabled" in s else False,
                    "message": s["tg_message"].get().strip() if "tg_message" in s else "",
                    "token": self.var_tg_token.get().strip(),
                    "chat_id": self.var_tg_chat_id.get().strip(),
                },
            })
        return cfg

    def _get_active_priority_steps_config(self) -> list:
        cfg = []
        is_img_mode = ("圖片" in self.var_recognition_mode.get())
        for p in self.priority_steps_list:
            raw_kws = p["keywords"].get() if "keywords" in p else ""
            kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
            raw_ex = p["exclude_keywords"].get() if "exclude_keywords" in p else ""
            ex_kws = [k.strip() for k in raw_ex.replace("，", ",").split(",") if k.strip()]
            rep_on = p["repeat_enabled"].get() if "repeat_enabled" in p else False
            tt = "🖼️ 圖片特徵 (模板比對)" if is_img_mode else "📝 文字辨識 (OCR)"
            is_img = is_img_mode
            is_sym = ("打勾" in tt or "叉叉" in tt)
            tpl_img = p["template_image"].get().strip() if "template_image" in p else ""
            img_th = _num(p.get("image_threshold", 0.80), 0.80)
            img_ms = bool(p["image_multiscale"].get()) if "image_multiscale" in p else False

            is_valid_target = (is_img and bool(tpl_img)) or (not is_img and (bool(kws) or is_sym))
            delay = _num(p["delay"], 1.0) if "delay" in p else 1.0
            act_val = p["action"].get() if "action" in p else "點擊目標"
            roi_val = p["roi"].get() if "roi" in p else "全畫面比對"

            cfg.append({
                "type": "priority",
                "name": p["name"].get().strip() if "name" in p else "優先動作",
                "target_type": tt,
                "template_image": tpl_img,
                "image_threshold": img_th,
                "image_multiscale": img_ms,
                "keywords": kws,
                "exclude_keywords": ex_kws,
                "action": "custom_coord" if is_custom_coord_action(act_val) else act_val,
                "custom_x": _num(p.get("custom_x", 0), 0, int),
                "custom_y": _num(p.get("custom_y", 0), 0, int),
                "delay": delay,
                "delay_min": max(0.05, delay - 0.15),
                "delay_max": delay + 0.15,
                "roi": self._map_roi_name_to_tuple(roi_val),
                "roi_name": roi_val,
                "while_condition": p["while_condition"].get() if "while_condition" in p else True,
                "repeat_enabled": rep_on,
                "repeat_mode": "count" if (p.get("repeat_mode") and p["repeat_mode"].get() == "指定次數") else "until_next",
                "repeat_count": _num(p["repeat_count"], 15, int) if rep_on and "repeat_count" in p else 1,
                "repeat_speed": _num(p["repeat_speed"], 0.3) if "repeat_speed" in p else 0.3,
                "repeat_area": p["repeat_area"].get() if "repeat_area" in p else "右下角區域",
                "repeat_custom_x": _num(p.get("repeat_custom_x", 0), 0, int),
                "repeat_custom_y": _num(p.get("repeat_custom_y", 0), 0, int),
                "repeat_custom_coord": (_num(p.get("repeat_custom_x", 0), 0, int), _num(p.get("repeat_custom_y", 0), 0, int)),
                "telegram": {
                    "enabled": p["tg_enabled"].get() if "tg_enabled" in p else False,
                    "message": p["tg_message"].get().strip() if "tg_message" in p else "",
                    "token": self.var_tg_token.get().strip(),
                    "chat_id": self.var_tg_chat_id.get().strip(),
                },
            })
        return cfg

    def on_start_bot(self):
        """啟動 iPhone 鏡像自動刷背景執行緒 (委託 self.bot.run_loop)"""
        if self.is_running:
            return
        if not self.bot.window_ctrl.locked_app_name:
            if not self.bot.connect(target_serial=self.var_window_name.get()):
                messagebox.showwarning("提示", "請先確認 iPhone 鏡像輸出 App 已開啟並成功鎖定！", parent=self.parent)
                return

        steps = self._get_active_steps_config()
        priority_steps = self._get_active_priority_steps_config()
        if not any(s["enabled"] for s in steps) and not any(p["enabled"] for p in priority_steps):
            messagebox.showwarning("提示", "請至少啟用一個步驟或優先動作！", parent=self.parent)
            return

        self.auto_save_current_config()

        self.is_running = True
        self.bot.is_running = True
        self.bot.restore_cursor = self.var_restore_cursor.get()
        self.bot.auto_activate = self.var_auto_activate.get()
        self.bot.set_allowed_languages(self.var_lang_tc.get(), self.var_lang_sc.get(), self.var_lang_en.get())
        self.bot.confidence_threshold = float(self.var_confidence.get())

        interval = _num(self.var_interval, 2.0)
        strat = self.var_idle_strategy.get()
        idle = "skip" if "跳過" in strat else "stop" if "停止" in strat else "wait"

        idle_tap_cfg = {
            "enabled": self.var_idle_tap_enabled.get(),
            "area": self.var_idle_tap_area.get(),
            "times": _num(self.var_idle_tap_times, 3, int),
            "interval": _num(self.var_idle_tap_interval, 30, int),
            "custom_x": _num(self.var_idle_tap_custom_x, 600, int),
            "custom_y": _num(self.var_idle_tap_custom_y, 300, int),
            "custom_coord": (_num(self.var_idle_tap_custom_x, 600, int), _num(self.var_idle_tap_custom_y, 300, int)),
        }
        watchdog_cfg = {
            "enabled": self.var_watchdog_enabled.get(),
            "seconds": _num(self.var_watchdog_seconds, 60, int),
        }

        self._set_status("運行中 (RUNNING)", COLOR_RUNNING)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.log_message("🚀 iPhone 鏡像自動刷關已啟動！")

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(interval, steps, idle, idle_tap_cfg, priority_steps, watchdog_cfg),
            daemon=True
        )
        self.worker_thread.start()

    def on_stop_bot(self):
        """停止 iPhone 鏡像自動刷"""
        self.log_message("🛑 正在停止 iPhone 鏡像自動刷關...")
        self.is_running = False
        self.bot.stop()
        self._set_status("已停止 (STOPPED)", COLOR_STOPPED)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _run_worker(self, interval: float, steps: list, idle: str, idle_tap_cfg: dict, priority_steps: list, watchdog_cfg: dict = None):
        """背景執行緒迴圈：委託 self.bot.run_loop 運行完整比對與動作引擎 (macOS iPhone 滑鼠點擊)"""
        try:
            self.bot.run_loop(
                poll_interval=interval,
                custom_steps=steps,
                idle_strategy=idle,
                idle_tap_config=idle_tap_cfg,
                priority_steps=priority_steps,
                watchdog_config=watchdog_cfg,
            )
        except Exception as e:
            self.log_message(f"iPhone 自動刷執行緒異常: {e}")
        finally:
            self.is_running = False
            self.bot.is_running = False
            self.parent.after(0, self._on_worker_stopped)

    def _on_worker_stopped(self):
        self.is_running = False
        self.bot.is_running = False
        self._set_status("已停止 (STOPPED)", COLOR_STOPPED)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.log_message("⏹ iPhone 鏡像自動刷工作執行緒已終止。")
        if self.var_auto_refresh.get():
            self._schedule_next_refresh(500)

    def on_bot_frame_update(self, screen_bgr, detected_items, matched_result=None):
        """接收來自機器人核心的即時畫面更新回呼並推播至預覽視窗"""
        if screen_bgr is not None and self.is_running:
            self.current_screen_bgr = screen_bgr
            try:
                self.parent.after(0, lambda img=screen_bgr: self._render_preview(img))
            except Exception:
                pass
