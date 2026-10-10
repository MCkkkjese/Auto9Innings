"""
棒球手遊自動化腳本 - 現代化 CustomTkinter 圖形化介面 (Modern GUI)
完全重構特色：
1. 全域 macOS 深色控制面板風格 (ctk.set_appearance_mode("dark"))，採用低飽和度配色 (#1E1E2E 背景，#252538 卡片)。
2. 大字體狀態指示燈：彩色呼吸指示燈 (綠：運作中 / 橘：未連線/暫停 / 紅：已停止) 與大字體狀態文字。
3. 主控制大按鈕：圓角 corner_radius=8 大按鈕 (啟動刷關 / 停止刷關 / 連線 / 搜尋)。
4. 參數設定格 (Settings Grid)：以卡片式 CTkFrame 封裝，內部對齊輸入框與間距留白充足。
5. 等寬即時日誌終端 (Log Console)：等寬字體 (Menlo/Consolas) 唯讀 CTkTextbox，附帶時間戳記與自動滾動。
6. 保留所有使用邏輯：聯賽刷關、OCR步驟比對、優先動作、自訂座標、即時預覽ROI、Scratch積木任務、打擊輔助 100% 完整相容！
"""
import os
import sys
import time
import threading
import json
import queue
import datetime
import subprocess
from typing import Optional, Dict, Any, List, Tuple

import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk

import cv2
import numpy as np
from PIL import Image, ImageTk

# 內部核心模組
from bot_core import BaseballBot
from batting_tab import BattingAssistTab
from task_flow import TaskFlowTab


# ==============================================================================
# 🎨 現代化深色主題調色盤 (Low-Saturation Modern Dark Palette)
# ==============================================================================
COLOR_BG = "#1E1E2E"           # 主視窗背景 (Catppuccin Mocha Base)
COLOR_CARD = "#252538"         # 卡片/容器底色
COLOR_CARD_BORDER = "#313244"  # 卡片邊框
COLOR_CARD_ITEM = "#20222e"    # 步驟卡片內部底色
COLOR_INPUT_BG = "#181825"     # 輸入框/終端文字底色
COLOR_INPUT_BORDER = "#45475A" # 輸入框邊框

# 狀態指示色彩 (Status Indicator Lights)
COLOR_RUNNING = "#22C55E"      # 綠色：運作中 (Running)
COLOR_PAUSED = "#F59E0B"       # 橙黃色：暫停/未連線
COLOR_STOPPED = "#EF4444"      # 紅色：已停止 (Stopped)

# 按鈕色彩配置 (圓角 corner_radius=8)
COLOR_BTN_START = "#10B981"    # 啟動大按鈕 (Emerald Green)
COLOR_BTN_START_HOVER = "#059669"
COLOR_BTN_STOP = "#EF4444"     # 停止大按鈕 (Rose Red)
COLOR_BTN_STOP_HOVER = "#DC2626"
COLOR_BTN_PRIMARY = "#3B82F6"  # 主要操作按鈕 (Blue)
COLOR_BTN_PRIMARY_HOVER = "#2563EB"
COLOR_BTN_DARK = "#313244"     # 次要灰底按鈕
COLOR_BTN_DARK_HOVER = "#45475A"

# 文字排版色彩
COLOR_TEXT_PRIMARY = "#CDD6F4" # 主要文字亮白
COLOR_TEXT_MUTED = "#A6ADC8"   # 次要說明文字淺灰
COLOR_TEXT_DIM = "#6C7086"     # 邊緣提示資訊


# ==============================================================================
# 📋 步驟與辨識選項常數
# ==============================================================================
ROI_OPTIONS = ["右下角區域", "右半側螢幕", "下半部區域", "中央區域", "全畫面比對", "自訂特定區塊"]
REPEAT_MODES = ["持續連點", "指定次數"]
REPEAT_AREAS = ["右下角區域", "中央區域", "右上角 (Skip)", "右半側中央", "跟隨命中目標", "自訂座標"]
ACTION_OPTIONS = ["點擊詞條", "自訂座標", "自訂特定區塊", "持續連點", "無動作(僅等待)", "📋 執行任務清單"]
IDLE_STRATEGIES = ["常規等待", "快速跳過", "自動停止"]
TARGET_TYPES = ["📝 僅文字", "✅ 勾選方塊 (打勾)", "❌ 關閉按鈕 (叉叉)"]

# 步驟卡片專屬邊框色 (拖曳時色彩跟隨)
STEP_COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4"]

# 預設 Telegram 設定
DEFAULT_TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DEFAULT_TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _num(var, default, cast=float):
    """安全讀取數值變數 (輸入框暫時為空或格式錯誤時回傳預設值)"""
    try:
        val = var.get() if hasattr(var, "get") else var
        return cast(val)
    except Exception:
        return default


# ==============================================================================
# 🏆 核心 GUI 類別：BaseballBotGUI
# ==============================================================================
class BaseballBotGUI:
    """現代化 CustomTkinter 遊戲自動化控制面板與進階步驟編輯器"""

    def __init__(self, root: ctk.CTk, instance_id: int = 1):
        self.root = root
        self.instance_id = instance_id

        # 1. 外觀主題初始化
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        title_suffix = f" (視窗 #{instance_id})" if instance_id > 1 else ""
        self.root.title(f"⚾ Auto9Innings 自動刷關控制中心{title_suffix}")
        self.root.geometry("1260x860")
        self.root.minsize(1060, 720)
        self.root.configure(fg_color=COLOR_BG)

        self.config_dir = os.path.dirname(os.path.abspath(__file__))
        save_name = "autosave_last_config.json" if instance_id == 1 else f"autosave_last_config_{instance_id}.json"
        self.auto_save_file = os.path.join(self.config_dir, save_name)

        # 2. 自動化核心與工作執行緒
        self.bot = BaseballBot(log_callback=self.log_message, on_frame_callback=self.on_bot_frame_update)
        self.worker_thread = None
        self.is_running = False

        # 統計指標
        self.start_time: Optional[float] = None
        self.total_uptime_seconds = 0
        self.loop_count = 0
        self.hit_count = 0

        # 非同步日誌佇列
        self.log_queue = queue.Queue()
        self.auto_scroll_logs = True

        # 預覽畫面狀態
        self.current_screen_bgr = None
        self._last_detected = None
        self._display_full = None
        self.preview_image_tk = None
        self.preview_scale = 1.0
        self.preview_img_w = 0
        self.preview_img_h = 0
        self.canvas_w = 480
        self.canvas_h = 270
        self.raw_screen_w = 0
        self.raw_screen_h = 0
        self._capturing = False
        self._resize_job = None
        self._preview_update_pending = False
        self._last_preview_time = 0.0
        self._preview_frame_count = 0
        self.auto_refresh_job = None

        # 3. 綁定變數
        self.var_device = tk.StringVar()
        self.var_status_text = tk.StringVar(value="未連線 (DISCONNECTED)")
        self.var_interval = tk.DoubleVar(value=2.5)
        self.var_confidence = tk.DoubleVar(value=0.65)
        self.var_idle_strategy = tk.StringVar(value=IDLE_STRATEGIES[0])
        self.var_auto_refresh = tk.BooleanVar(value=True)
        self.var_preview_coords = tk.StringVar(value="")

        # 語言辨識與過濾 (預設繁中+英文開啟，簡中關閉杜絕誤判)
        self.var_lang_tc = tk.BooleanVar(value=True)
        self.var_lang_sc = tk.BooleanVar(value=False)
        self.var_lang_en = tk.BooleanVar(value=True)

        def _on_lang_changed(*_):
            self.bot.set_allowed_languages(
                self.var_lang_tc.get(),
                self.var_lang_sc.get(),
                self.var_lang_en.get()
            )
            self.auto_save_current_config()

        self.var_lang_tc.trace_add("write", _on_lang_changed)
        self.var_lang_sc.trace_add("write", _on_lang_changed)
        self.var_lang_en.trace_add("write", _on_lang_changed)
        self.bot.set_allowed_languages(True, False, True)

        # 看門狗防卡死守護參數
        self.var_watchdog_enabled = tk.BooleanVar(value=False)
        self.var_watchdog_seconds = tk.IntVar(value=60)
        self._watchdog_restart_job = None

        # 等待時連點參數
        self.var_idle_tap_enabled = tk.BooleanVar(value=False)
        self.var_idle_tap_area = tk.StringVar(value="右下角區域")
        self.var_idle_tap_times = tk.IntVar(value=3)
        self.var_idle_tap_interval = tk.DoubleVar(value=0.4)
        self.var_idle_tap_custom_x = tk.IntVar(value=983)
        self.var_idle_tap_custom_y = tk.IntVar(value=1023)

        # Telegram Bot 通知全域設定
        self.var_tg_token = tk.StringVar(value=DEFAULT_TG_TOKEN)
        self.var_tg_chat_id = tk.StringVar(value=DEFAULT_TG_CHAT_ID)

        # 步驟清單
        self.priority_steps_list = []  # 最高優先動作 (if/elif 條件中斷)
        self.steps_list = []           # 一般循序步驟
        self._adv_open = False

        # 4. 建立現代化介面排版
        self._build_ui()
        self._init_default_steps()
        self.on_refresh_devices()

        # 5. 計時排程與視窗事件
        self.root.after(50, self._process_log_queue)
        self.root.after(1000, self._update_uptime_timer)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

        # 啟動初始日誌
        self.log_message("✨ 現代化控制面板初始化完成！")

    # ==========================================================================
    # 📐 介面排版建構 (Layout Structure)
    # ==========================================================================
    def _build_ui(self):
        """建構主容器：頂部狀態導覽卡片 + 主內容 Tabview 分頁"""
        # 主外層容器 (Padding 16)
        main_box = ctk.CTkFrame(self.root, fg_color="transparent")
        main_box.pack(fill="both", expand=True, padx=14, pady=12)

        # 1. 頂部狀態與控制卡片
        self._build_topbar(main_box)

        # 2. 分頁標籤管理器 (CTkTabview)
        self.tabview = ctk.CTkTabview(
            main_box,
            corner_radius=10,
            fg_color=COLOR_BG,
            segmented_button_fg_color=COLOR_CARD,
            segmented_button_selected_color=COLOR_BTN_PRIMARY,
            segmented_button_selected_hover_color=COLOR_BTN_PRIMARY_HOVER
        )
        self.tabview.pack(fill="both", expand=True, pady=(10, 0))

        # 頁籤 1: 🏆 聯賽自動刷
        tab_league = self.tabview.add("🏆 聯賽自動刷")
        self._build_league_tab(tab_league)

        # 頁籤 2: ⚡ 即時打擊輔助
        tab_batting = self.tabview.add("⚡ 即時打擊輔助")
        self.batting_tab = BattingAssistTab(
            tab_batting,
            bot_instance=self.bot,
            gui_parent=self,
            log_callback=self.log_message
        )

        # 頁籤 3: 📋 任務清單 (Scratch 積木)
        tab_tasks = self.tabview.add("📋 任務清單 (Scratch 積木)")
        self.task_tab = TaskFlowTab(
            tab_tasks,
            bot_instance=self.bot,
            gui_parent=self,
            log_callback=self.log_message,
            instance_id=self.instance_id
        )
        self.bot.set_task_flow_handler(self._execute_task_flow_for_event)

    # --------------------------------------------------------------------------
    # 頂部狀態列 (大字體指示燈、統計數據、裝置連線與主控制大按鈕)
    # --------------------------------------------------------------------------
    def _build_topbar(self, parent: ctk.CTkFrame):
        bar = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        bar.pack(fill="x", ipady=4)

        # 左側：狀態指示燈與大字體狀態
        left_box = ctk.CTkFrame(bar, fg_color="transparent")
        left_box.pack(side="left", padx=16, pady=8)

        self.indicator_light = ctk.CTkLabel(
            left_box,
            text="●",
            font=ctk.CTkFont(family="Arial", size=24, weight="bold"),
            text_color=COLOR_STOPPED,
            width=24
        )
        self.indicator_light.pack(side="left", padx=(0, 8))

        status_text_box = ctk.CTkFrame(left_box, fg_color="transparent")
        status_text_box.pack(side="left")

        self.lbl_status = ctk.CTkLabel(
            status_text_box,
            textvariable=self.var_status_text,
            font=ctk.CTkFont(family="Arial", size=17, weight="bold"),
            text_color=COLOR_STOPPED
        )
        self.lbl_status.pack(anchor="w")

        self.lbl_metrics_inline = ctk.CTkLabel(
            status_text_box,
            text="⏱ 運行: 00:00:00   |   🔄 輪次: 0 次   |   🎯 命中: 0 次",
            font=ctk.CTkFont(family="Menlo", size=11),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_metrics_inline.pack(anchor="w")

        # 右側：裝置選取、連線與主操作大按鈕
        right_box = ctk.CTkFrame(bar, fg_color="transparent")
        right_box.pack(side="right", padx=14, pady=8)

        # 裝置選取 Combobox
        self.combo_devices = ctk.CTkComboBox(
            right_box,
            variable=self.var_device,
            width=175,
            height=34,
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            state="readonly"
        )
        self.combo_devices.pack(side="left", padx=(0, 6))

        self.btn_refresh = ctk.CTkButton(
            right_box,
            text="🔍 搜尋",
            width=68,
            height=34,
            corner_radius=8,
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_refresh_devices
        )
        self.btn_refresh.pack(side="left", padx=(0, 6))

        self.btn_connect = ctk.CTkButton(
            right_box,
            text="⚡ 連線",
            width=68,
            height=34,
            corner_radius=8,
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self.on_connect_device
        )
        self.btn_connect.pack(side="left", padx=(0, 10))

        # 開新視窗
        self.btn_new_win = ctk.CTkButton(
            right_box,
            text="＋ 開新視窗",
            width=85,
            height=34,
            corner_radius=8,
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_open_new_window
        )
        self.btn_new_win.pack(side="left", padx=(0, 12))

        # 主控制大按鈕：啟動 (Start)
        self.btn_start = ctk.CTkButton(
            right_box,
            text="▶ 啟動刷關",
            width=100,
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            fg_color=COLOR_BTN_START,
            hover_color=COLOR_BTN_START_HOVER,
            state="disabled",
            command=self.on_start_bot
        )
        self.btn_start.pack(side="left", padx=(0, 6))

        # 主控制大按鈕：停止 (Stop)
        self.btn_stop = ctk.CTkButton(
            right_box,
            text="⏹ 停止刷關",
            width=100,
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            fg_color=COLOR_BTN_STOP,
            hover_color=COLOR_BTN_STOP_HOVER,
            state="disabled",
            command=self.on_stop_bot
        )
        self.btn_stop.pack(side="left")

    # --------------------------------------------------------------------------
    # 聯賽自動刷頁籤 (左右雙欄佈局)
    # --------------------------------------------------------------------------
    def _build_league_tab(self, parent: ctk.CTkFrame):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=4, pady=4)
        container.grid_columnconfigure(0, weight=6)
        container.grid_columnconfigure(1, weight=5)
        container.grid_rowconfigure(0, weight=1)

        # 左欄：步驟與優先動作卡片列表 + 進階參數格
        left_pane = ctk.CTkFrame(container, fg_color="transparent")
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        self._build_steps_panel(left_pane)
        self._build_advanced_panel(left_pane)

        # 右欄：即時截圖預覽卡片 + 等寬日誌終端
        right_pane = ctk.CTkFrame(container, fg_color="transparent")
        right_pane.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        right_pane.grid_rowconfigure(0, weight=5)
        right_pane.grid_rowconfigure(1, weight=5)
        right_pane.grid_columnconfigure(0, weight=1)

        self._build_preview_panel(right_pane)
        self._build_log_panel(right_pane)

    # --------------------------------------------------------------------------
    # 步驟與優先動作清單卡片 (左側上半部，支援滾動)
    # --------------------------------------------------------------------------
    def _build_steps_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="both", expand=True, pady=(0, 8))

        # 頂部工具列
        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=12, pady=(10, 8))

        lbl_title = ctk.CTkLabel(
            tools,
            text="📋 步驟與優先動作",
            font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        lbl_title.pack(side="left")

        btn_box = ctk.CTkFrame(tools, fg_color="transparent")
        btn_box.pack(side="right")

        ctk.CTkButton(btn_box, text="＋ 優先動作", width=76, height=28, corner_radius=6, command=self.on_add_priority_step, fg_color="#F59E0B", hover_color="#D97706", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=2)
        ctk.CTkButton(btn_box, text="⚡ 事件跳轉", width=76, height=28, corner_radius=6, command=self.on_add_task_trigger_step, fg_color="#8B5CF6", hover_color="#7C3AED", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=2)
        ctk.CTkButton(btn_box, text="＋ 一般步驟", width=76, height=28, corner_radius=6, command=self.on_add_empty_step, fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=2)
        ctk.CTkButton(btn_box, text="💡 常用範本", width=76, height=28, corner_radius=6, command=self.on_reset_baseball_template, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=11)).pack(side="left", padx=2)
        ctk.CTkButton(btn_box, text="💾 儲存", width=52, height=28, corner_radius=6, command=self.on_save_config_manual, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=11)).pack(side="left", padx=2)
        ctk.CTkButton(btn_box, text="📂 載入", width=52, height=28, corner_radius=6, command=self.on_load_config_manual, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=11)).pack(side="left", padx=2)

        # 滾動步驟區域 (CTkScrollableFrame)
        self.step_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", corner_radius=8)
        self.step_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 1. 優先動作區塊
        self.frame_priority_section = ctk.CTkFrame(self.step_scroll, fg_color="transparent")
        self.frame_priority_section.pack(fill="x", pady=(0, 6))

        hdr_p = ctk.CTkFrame(self.frame_priority_section, fg_color="transparent")
        hdr_p.pack(fill="x", pady=(2, 4))
        self.lbl_hdr_p = ctk.CTkLabel(hdr_p, text="⚡ 優先動作（由上而下比對，符合即中斷並執行）", font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color="#FBBF24")
        self.lbl_hdr_p.pack(side="left")
        self.lbl_p_count = ctk.CTkLabel(hdr_p, text="(0)", font=ctk.CTkFont(family="Arial", size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_p_count.pack(side="left", padx=4)

        self.frame_priority_cards = ctk.CTkFrame(self.frame_priority_section, fg_color="transparent")
        self.frame_priority_cards.pack(fill="x")

        self.lbl_no_priority = ctk.CTkLabel(
            self.frame_priority_section,
            text="（尚無優先動作，點擊上方「＋ 優先動作」或「⚡ 事件跳轉」新增）",
            font=ctk.CTkFont(family="Arial", size=11),
            text_color=COLOR_TEXT_DIM
        )
        self.lbl_no_priority.pack(pady=4)

        # 2. 一般步驟區塊
        self.frame_normal_section = ctk.CTkFrame(self.step_scroll, fg_color="transparent")
        self.frame_normal_section.pack(fill="x", pady=(6, 0))

        hdr_n = ctk.CTkFrame(self.frame_normal_section, fg_color="transparent")
        hdr_n.pack(fill="x", pady=(2, 4))
        self.lbl_hdr_n = ctk.CTkLabel(hdr_n, text="🔄 一般步驟（依序循環執行）", font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color="#60A5FA")
        self.lbl_hdr_n.pack(side="left")
        self.lbl_n_count = ctk.CTkLabel(hdr_n, text="(0)", font=ctk.CTkFont(family="Arial", size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_n_count.pack(side="left", padx=4)

        self.frame_normal_cards = ctk.CTkFrame(self.frame_normal_section, fg_color="transparent")
        self.frame_normal_cards.pack(fill="x")

    # --------------------------------------------------------------------------
    # 參數設定格 (Settings Grid / Advanced Panel，可展開收合)
    # --------------------------------------------------------------------------
    def _build_advanced_panel(self, parent: ctk.CTkFrame):
        self.adv_card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        self.adv_card.pack(fill="x", pady=(0, 0))

        # 展開/收合開關按鈕列
        toggle_bar = ctk.CTkFrame(self.adv_card, fg_color="transparent")
        toggle_bar.pack(fill="x", padx=12, pady=8)

        self.btn_adv = ctk.CTkButton(
            toggle_bar,
            text="⚙️ 進階參數設定 ▸",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            corner_radius=6,
            height=30,
            command=self._toggle_advanced
        )
        self.btn_adv.pack(side="left")

        # 內部設定網格 (預設隱藏)
        self.adv_content = ctk.CTkFrame(self.adv_card, fg_color="transparent")

        grid = ctk.CTkFrame(self.adv_content, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=(0, 10))
        grid.grid_columnconfigure((0, 2), weight=0, minsize=100)
        grid.grid_columnconfigure((1, 3), weight=1)

        # 1. 掃描間隔秒數
        ctk.CTkLabel(grid, text="⏱ 掃描間隔 (秒):", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=0, column=0, sticky="w", pady=4)
        row_speed = ctk.CTkFrame(grid, fg_color="transparent")
        row_speed.grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=4)
        lbl_sp_val = ctk.CTkLabel(row_speed, text=f"{self.var_interval.get():.1f}s", width=42, font=ctk.CTkFont(family="Menlo", size=11))
        slider_sp = ctk.CTkSlider(row_speed, from_=0.5, to=8.0, number_of_steps=75, variable=self.var_interval, height=16)
        slider_sp.pack(side="left", fill="x", expand=True)
        lbl_sp_val.pack(side="left", padx=4)
        slider_sp.configure(command=lambda v: [lbl_sp_val.configure(text=f"{v:.1f}s"), self.auto_save_current_config()])

        # 2. 辨識信心門檻
        ctk.CTkLabel(grid, text="🎯 辨識門檻:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=0, column=2, sticky="w", pady=4)
        row_conf = ctk.CTkFrame(grid, fg_color="transparent")
        row_conf.grid(row=0, column=3, sticky="ew", padx=(6, 0), pady=4)
        lbl_cf_val = ctk.CTkLabel(row_conf, text=f"{self.var_confidence.get():.2f}", width=40, font=ctk.CTkFont(family="Menlo", size=11))
        slider_cf = ctk.CTkSlider(row_conf, from_=0.4, to=0.95, number_of_steps=55, variable=self.var_confidence, height=16)
        slider_cf.pack(side="left", fill="x", expand=True)
        lbl_cf_val.pack(side="left", padx=4)
        slider_cf.configure(command=lambda v: [lbl_cf_val.configure(text=f"{v:.2f}"), setattr(self.bot, "confidence_threshold", float(v)), self.auto_save_current_config()])

        # 3. 語言辨識過濾 Checkboxes
        ctk.CTkLabel(grid, text="🔤 語言過濾:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=1, column=0, sticky="w", pady=4)
        lang_box = ctk.CTkFrame(grid, fg_color="transparent")
        lang_box.grid(row=1, column=1, sticky="w", padx=(6, 12), pady=4)
        ctk.CTkCheckBox(lang_box, text="繁中", variable=self.var_lang_tc, corner_radius=4, height=18, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(lang_box, text="英文", variable=self.var_lang_en, corner_radius=4, height=18, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(lang_box, text="簡中 (過濾)", variable=self.var_lang_sc, corner_radius=4, height=18, font=ctk.CTkFont(size=11)).pack(side="left")

        # 4. 看門狗防卡死
        ctk.CTkLabel(grid, text="🐕 看門狗守護:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=1, column=2, sticky="w", pady=4)
        wd_box = ctk.CTkFrame(grid, fg_color="transparent")
        wd_box.grid(row=1, column=3, sticky="w", padx=(6, 0), pady=4)
        ctk.CTkCheckBox(wd_box, text="超時重啟", variable=self.var_watchdog_enabled, corner_radius=4, height=18, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        ctk.CTkEntry(wd_box, textvariable=self.var_watchdog_seconds, width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=11)).pack(side="left")
        ctk.CTkLabel(wd_box, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=2)

        # 5. Telegram 通知設定
        ctk.CTkLabel(grid, text="📱 Telegram:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#38BDF8").grid(row=2, column=0, sticky="w", pady=4)
        tg_box = ctk.CTkFrame(grid, fg_color="transparent")
        tg_box.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=4)
        ctk.CTkLabel(tg_box, text="Token:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(tg_box, textvariable=self.var_tg_token, width=150, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(tg_box, text="Chat ID:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(tg_box, textvariable=self.var_tg_chat_id, width=110, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(tg_box, text="測試發送", width=68, height=24, corner_radius=4, command=self.on_test_telegram_message, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=10)).pack(side="left")

    def _toggle_advanced(self):
        """展開或收合進階參數設定"""
        self._adv_open = not self._adv_open
        if self._adv_open:
            self.adv_content.pack(fill="x")
            self.btn_adv.configure(text="⚙️ 進階參數設定 ▾")
        else:
            self.adv_content.pack_forget()
            self.btn_adv.configure(text="⚙️ 進階參數設定 ▸")

    # --------------------------------------------------------------------------
    # 即時截圖預覽卡片 (右側上半部)
    # --------------------------------------------------------------------------
    def _build_preview_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.grid(row=0, column=0, sticky="nsew", pady=(0, 6))

        # 頂部控制列
        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=12, pady=(10, 6))

        self.btn_capture = ctk.CTkButton(
            tools,
            text="📸 擷取畫面",
            width=90,
            height=28,
            corner_radius=6,
            command=self.on_preview_and_detect,
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.btn_capture.pack(side="left")

        self.sw_auto_refresh = ctk.CTkSwitch(
            tools,
            text="自動刷新",
            variable=self.var_auto_refresh,
            font=ctk.CTkFont(size=11),
            command=self.on_toggle_auto_refresh
        )
        self.sw_auto_refresh.pack(side="left", padx=(12, 0))

        # 即時座標顯示 (Menlo 11 等寬藍字)
        self.lbl_preview_coords = ctk.CTkLabel(
            tools,
            textvariable=self.var_preview_coords,
            font=ctk.CTkFont(family="Menlo", size=12, weight="bold"),
            text_color="#60A5FA"
        )
        self.lbl_preview_coords.pack(side="right")

        # 嵌入式畫布容器
        holder = ctk.CTkFrame(card, fg_color=COLOR_INPUT_BG, corner_radius=8, border_width=1, border_color=COLOR_CARD_BORDER)
        holder.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        holder.bind("<Configure>", self._on_preview_resize)
        self.preview_holder = holder

        self.lbl_canvas = tk.Label(
            holder,
            text="連線後按「擷取畫面」\n點擊畫面任意處即可快速選取自訂座標",
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_INPUT_BG,
            cursor="crosshair",
            anchor=tk.CENTER
        )
        self.lbl_canvas.pack(fill=tk.BOTH, expand=True)
        self.lbl_canvas.bind("<Motion>", self._on_preview_mouse_move)
        self.lbl_canvas.bind("<Leave>", lambda e: self.var_preview_coords.set(""))
        self.lbl_canvas.bind("<Button-1>", self._on_preview_click)

    # --------------------------------------------------------------------------
    # 等寬即時日誌終端卡片 (右側下半部)
    # --------------------------------------------------------------------------
    def _build_log_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        # 頂部控制列
        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=12, pady=(10, 6))

        lbl_log = ctk.CTkLabel(
            tools,
            text="📜 即時執行日誌 (Log Console)",
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        lbl_log.pack(side="left")

        # 自動捲動 Switch
        self.sw_log_scroll = ctk.CTkSwitch(
            tools,
            text="自動捲動",
            font=ctk.CTkFont(size=11),
            command=self._toggle_auto_scroll
        )
        self.sw_log_scroll.select()
        self.sw_log_scroll.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            tools, text="儲存", width=54, height=24, corner_radius=4,
            command=self._export_logs, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=10)
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            tools, text="清除", width=54, height=24, corner_radius=4,
            command=self.on_clear_log, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=10)
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            tools, text="診斷", width=54, height=24, corner_radius=4,
            command=self.on_run_diagnostics, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=10)
        ).pack(side="right", padx=2)

        # 等寬字體唯讀 CTkTextbox (Menlo / Consolas)
        mono_family = "Menlo" if sys.platform == "darwin" else "Consolas"
        self.txt_log = ctk.CTkTextbox(
            card,
            font=ctk.CTkFont(family=mono_family, size=11),
            fg_color=COLOR_INPUT_BG,
            text_color=COLOR_TEXT_PRIMARY,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
            corner_radius=8,
            wrap="char"
        )
        self.txt_log.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    # ==========================================================================
    # 🧩 步驟卡片生成與事件綁定 (Priority & Normal Steps)
    # ==========================================================================
    def on_add_priority_step(self):
        n = len(self.priority_steps_list) + 1
        self._create_priority_step_widget(name=f"優先 {n}", keywords="", expanded=True)

    def on_add_task_trigger_step(self):
        n = len(self.priority_steps_list) + 1
        self._create_priority_step_widget(
            name=f"任務跳轉 {n}",
            keywords="",
            action="📋 執行任務清單",
            task_target_mode="📋 完整任務清單",
            task_cooldown=60.0,
            expanded=True
        )

    def on_delete_priority_step(self, p_step):
        if p_step in self.priority_steps_list:
            self.priority_steps_list.remove(p_step)
            p_step["frame"].destroy()
            self._renumber_priority_steps()
            self.auto_save_current_config()

    def _clear_all_priority_steps(self):
        for p in self.priority_steps_list:
            p["frame"].destroy()
        self.priority_steps_list.clear()
        self.lbl_p_count.configure(text="(0)")
        self.lbl_no_priority.pack(pady=4)

    def _renumber_priority_steps(self):
        for i, p in enumerate(self.priority_steps_list, start=1):
            if "lbl_num" in p:
                p["lbl_num"].configure(text=f"P{i}")
        self.lbl_p_count.configure(text=f"({len(self.priority_steps_list)})")
        if self.priority_steps_list:
            self.lbl_no_priority.pack_forget()
        else:
            self.lbl_no_priority.pack(pady=4)

    def _create_priority_step_widget(
        self,
        name: str = "",
        keywords: str = "",
        target_type: str = "📝 僅文字",
        exclude_keywords: str = "",
        action: str = "點擊詞條",
        custom_x: int = 960,
        custom_y: int = 540,
        delay: float = 2.0,
        roi_name: str = "全畫面比對",
        while_condition: bool = False,
        repeat_enabled: bool = False,
        repeat_mode: str = "持續連點",
        repeat_count: int = 5,
        repeat_speed: float = 0.25,
        repeat_area: str = "右下角區域",
        repeat_custom_x: int = 960,
        repeat_custom_y: int = 540,
        tg_enabled: bool = False,
        tg_message: str = "",
        task_target_mode: str = "📋 完整任務清單",
        task_target_item: str = "",
        task_cooldown: float = 60.0,
        enabled: bool = True,
        expanded: bool = False
    ):
        color = "#F59E0B"
        card = ctk.CTkFrame(self.frame_priority_cards, fg_color=COLOR_CARD_ITEM, corner_radius=8, border_width=1, border_color=color)
        card.pack(fill="x", pady=4, padx=2)

        if action not in ACTION_OPTIONS:
            action = "點擊詞條"
        if target_type not in TARGET_TYPES:
            target_type = "📝 僅文字"

        p = {
            "type": "priority",
            "enabled": tk.BooleanVar(value=enabled),
            "name": tk.StringVar(value=name),
            "target_type": tk.StringVar(value=target_type),
            "keywords": tk.StringVar(value=keywords),
            "exclude_keywords": tk.StringVar(value=exclude_keywords),
            "action": tk.StringVar(value=action),
            "custom_x": tk.IntVar(value=custom_x),
            "custom_y": tk.IntVar(value=custom_y),
            "delay": tk.DoubleVar(value=delay),
            "roi": tk.StringVar(value=roi_name),
            "while_condition": tk.BooleanVar(value=while_condition),
            "repeat_enabled": tk.BooleanVar(value=repeat_enabled),
            "repeat_mode": tk.StringVar(value=repeat_mode),
            "repeat_count": tk.IntVar(value=repeat_count),
            "repeat_speed": tk.DoubleVar(value=repeat_speed),
            "repeat_area": tk.StringVar(value=repeat_area),
            "repeat_custom_x": tk.IntVar(value=repeat_custom_x),
            "repeat_custom_y": tk.IntVar(value=repeat_custom_y),
            "tg_enabled": tk.BooleanVar(value=tg_enabled),
            "tg_message": tk.StringVar(value=tg_message),
            "task_target_mode": tk.StringVar(value=task_target_mode),
            "task_target_item": tk.StringVar(value=task_target_item),
            "task_cooldown": tk.DoubleVar(value=task_cooldown),
            "expanded": tk.BooleanVar(value=expanded),
            "frame": card,
        }
        self.priority_steps_list.append(p)

        # 標題列
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=6)

        handle = ctk.CTkLabel(head, text="☰", font=ctk.CTkFont(family="Arial", size=13, weight="bold"), text_color=color, width=16)
        handle.pack(side="left", padx=(0, 4))
        self._bind_drag_priority_events(handle, p)

        ctk.CTkCheckBox(head, text="", variable=p["enabled"], width=18, height=18, corner_radius=4).pack(side="left", padx=(0, 4))
        lbl_num = ctk.CTkLabel(head, text=f"P{len(self.priority_steps_list)}", font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color=color, width=28)
        lbl_num.pack(side="left")
        p["lbl_num"] = lbl_num

        ctk.CTkEntry(head, textvariable=p["name"], width=80, height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))

        ctk.CTkOptionMenu(head, variable=p["target_type"], values=TARGET_TYPES, width=110, height=26, corner_radius=6, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))

        btn_toggle = ctk.CTkButton(head, text="▸", width=26, height=26, corner_radius=4, command=lambda: p["expanded"].set(not p["expanded"].get()), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER)
        btn_toggle.pack(side="right", padx=2)

        ctk.CTkButton(head, text="✕", width=26, height=26, corner_radius=4, command=lambda: self.on_delete_priority_step(p), fg_color=COLOR_STOPPED, hover_color="#DC2626").pack(side="right", padx=2)

        def _add_p_sym(tag):
            k = p["keywords"].get().strip()
            p["keywords"].set(f"{k}, {tag}" if k else tag)
        ctk.CTkButton(head, text="✓", width=26, height=26, corner_radius=4, command=lambda: _add_p_sym("[打勾]"), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER).pack(side="right", padx=1)
        ctk.CTkButton(head, text="✕", width=26, height=26, corner_radius=4, command=lambda: _add_p_sym("[叉叉]"), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER).pack(side="right", padx=1)

        ctk.CTkEntry(head, textvariable=p["keywords"], height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", fill="x", expand=True)

        # 展開設定內容
        lbl_sum = ctk.CTkLabel(card, text="", font=ctk.CTkFont(family="Arial", size=11), text_color=COLOR_TEXT_MUTED, anchor="w")
        detail = ctk.CTkFrame(card, fg_color="transparent")

        # 動作列
        ra = ctk.CTkFrame(detail, fg_color="transparent")
        ra.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(ra, text="動作:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(ra, variable=p["action"], values=ACTION_OPTIONS, width=120, height=24, corner_radius=6, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))

        box_act_xy = ctk.CTkFrame(ra, fg_color="transparent")
        ctk.CTkLabel(box_act_xy, text="X:", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkEntry(box_act_xy, textvariable=p["custom_x"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
        ctk.CTkLabel(box_act_xy, text="Y:", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkEntry(box_act_xy, textvariable=p["custom_y"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 6))

        ctk.CTkLabel(ra, text="範圍:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(ra, variable=p["roi"], values=ROI_OPTIONS, width=110, height=24, corner_radius=6, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))

        def _refresh_act_ui(*_):
            if p["action"].get() in ("自訂座標", "自訂特定區塊"):
                box_act_xy.pack(side="left", padx=(0, 6))
            else:
                box_act_xy.pack_forget()
        p["action"].trace_add("write", _refresh_act_ui)
        _refresh_act_ui()

        ctk.CTkLabel(ra, text="延遲:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(ra, textvariable=p["delay"], width=42, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left")
        ctk.CTkLabel(ra, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(2, 0))

        # 排除字詞列
        re = ctk.CTkFrame(detail, fg_color="transparent")
        re.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(re, text="排除字詞:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#F87171").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(re, textvariable=p["exclude_keywords"], height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=10)).pack(side="left", fill="x", expand=True)

        # 展開/收合切換邏輯
        def refresh(*_):
            if p["expanded"].get():
                btn_toggle.configure(text="▾")
                lbl_sum.pack_forget()
                detail.pack(fill="x", padx=10, pady=(0, 8))
            else:
                btn_toggle.configure(text="▸")
                detail.pack_forget()
                lbl_sum.configure(text=f"  ↳ {p['action'].get()} | 延遲 {p['delay'].get()}s | 範圍: {p['roi'].get()}")
                lbl_sum.pack(fill="x", padx=12, pady=(0, 4))

        p["expanded"].trace_add("write", refresh)
        refresh()
        self._renumber_priority_steps()

    # --------------------------------------------------------------------------
    # 一般步驟卡片建立 (Normal Steps)
    # --------------------------------------------------------------------------
    def on_add_empty_step(self):
        n = len(self.steps_list) + 1
        self._create_step_widget(name=f"步驟 {n}", keywords="", expanded=True)

    def on_delete_step(self, step):
        if step in self.steps_list:
            self.steps_list.remove(step)
            step["frame"].destroy()
            self._renumber_steps()
            self.auto_save_current_config()

    def _clear_all_steps(self):
        for s in self.steps_list:
            s["frame"].destroy()
        self.steps_list.clear()
        self.lbl_n_count.configure(text="(0)")

    def _renumber_steps(self):
        for i, s in enumerate(self.steps_list, start=1):
            if "lbl_num" in s:
                s["lbl_num"].configure(text=str(i))
        self.lbl_n_count.configure(text=f"({len(self.steps_list)})")

    def _create_step_widget(
        self,
        name: str = "",
        keywords: str = "",
        target_type: str = "📝 僅文字",
        exclude_keywords: str = "",
        action: str = "點擊詞條",
        custom_x: int = 960,
        custom_y: int = 540,
        delay: float = 2.5,
        roi_name: str = "右下角區域",
        repeat_enabled: bool = False,
        repeat_mode: str = "持續連點",
        repeat_count: int = 5,
        repeat_speed: float = 0.25,
        repeat_area: str = "右下角區域",
        repeat_custom_x: int = 960,
        repeat_custom_y: int = 540,
        timeout_enabled: bool = False,
        timeout_seconds: int = 20,
        tg_enabled: bool = False,
        tg_message: str = "",
        task_target_mode: str = "📋 完整任務清單",
        task_target_item: str = "",
        task_cooldown: float = 60.0,
        enabled: bool = True,
        expanded: bool = False
    ):
        color = STEP_COLORS[len(self.steps_list) % len(STEP_COLORS)]
        card = ctk.CTkFrame(self.frame_normal_cards, fg_color=COLOR_CARD_ITEM, corner_radius=8, border_width=1, border_color=color)
        card.pack(fill="x", pady=4, padx=2)

        if action not in ACTION_OPTIONS:
            action = "點擊詞條"
        if target_type not in TARGET_TYPES:
            target_type = "📝 僅文字"

        s = {
            "type": "normal",
            "enabled": tk.BooleanVar(value=enabled),
            "name": tk.StringVar(value=name),
            "target_type": tk.StringVar(value=target_type),
            "keywords": tk.StringVar(value=keywords),
            "exclude_keywords": tk.StringVar(value=exclude_keywords),
            "action": tk.StringVar(value=action),
            "custom_x": tk.IntVar(value=custom_x),
            "custom_y": tk.IntVar(value=custom_y),
            "delay": tk.DoubleVar(value=delay),
            "roi": tk.StringVar(value=roi_name),
            "repeat_enabled": tk.BooleanVar(value=repeat_enabled),
            "repeat_mode": tk.StringVar(value=repeat_mode),
            "repeat_count": tk.IntVar(value=repeat_count),
            "repeat_speed": tk.DoubleVar(value=repeat_speed),
            "repeat_area": tk.StringVar(value=repeat_area),
            "repeat_custom_x": tk.IntVar(value=repeat_custom_x),
            "repeat_custom_y": tk.IntVar(value=repeat_custom_y),
            "timeout_enabled": tk.BooleanVar(value=timeout_enabled),
            "timeout_seconds": tk.IntVar(value=timeout_seconds),
            "tg_enabled": tk.BooleanVar(value=tg_enabled),
            "tg_message": tk.StringVar(value=tg_message),
            "task_target_mode": tk.StringVar(value=task_target_mode),
            "task_target_item": tk.StringVar(value=task_target_item),
            "task_cooldown": tk.DoubleVar(value=task_cooldown),
            "expanded": tk.BooleanVar(value=expanded),
            "frame": card,
            "border_color": color,
        }
        self.steps_list.append(s)

        # 標題列
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=6)

        handle = ctk.CTkLabel(head, text="☰", font=ctk.CTkFont(family="Arial", size=13, weight="bold"), text_color=color, width=16)
        handle.pack(side="left", padx=(0, 4))
        self._bind_drag_events(handle, s)

        ctk.CTkCheckBox(head, text="", variable=s["enabled"], width=18, height=18, corner_radius=4).pack(side="left", padx=(0, 4))
        lbl_num = ctk.CTkLabel(head, text=str(len(self.steps_list)), font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color=color, width=24)
        lbl_num.pack(side="left")
        s["lbl_num"] = lbl_num

        ctk.CTkEntry(head, textvariable=s["name"], width=80, height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))

        ctk.CTkOptionMenu(head, variable=s["target_type"], values=TARGET_TYPES, width=110, height=26, corner_radius=6, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))

        btn_toggle = ctk.CTkButton(head, text="▸", width=26, height=26, corner_radius=4, command=lambda: s["expanded"].set(not s["expanded"].get()), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER)
        btn_toggle.pack(side="right", padx=2)

        ctk.CTkButton(head, text="✕", width=26, height=26, corner_radius=4, command=lambda: self.on_delete_step(s), fg_color=COLOR_STOPPED, hover_color="#DC2626").pack(side="right", padx=2)

        def _add_s_sym(tag):
            k = s["keywords"].get().strip()
            s["keywords"].set(f"{k}, {tag}" if k else tag)
        ctk.CTkButton(head, text="✓", width=26, height=26, corner_radius=4, command=lambda: _add_s_sym("[打勾]"), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER).pack(side="right", padx=1)
        ctk.CTkButton(head, text="✕", width=26, height=26, corner_radius=4, command=lambda: _add_s_sym("[叉叉]"), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER).pack(side="right", padx=1)

        ctk.CTkEntry(head, textvariable=s["keywords"], height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", fill="x", expand=True)

        # 展開設定內容
        lbl_sum = ctk.CTkLabel(card, text="", font=ctk.CTkFont(family="Arial", size=11), text_color=COLOR_TEXT_MUTED, anchor="w")
        detail = ctk.CTkFrame(card, fg_color="transparent")

        # 動作列
        ra = ctk.CTkFrame(detail, fg_color="transparent")
        ra.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(ra, text="動作:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(ra, variable=s["action"], values=ACTION_OPTIONS, width=120, height=24, corner_radius=6, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))

        box_act_xy = ctk.CTkFrame(ra, fg_color="transparent")
        ctk.CTkLabel(box_act_xy, text="X:", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkEntry(box_act_xy, textvariable=s["custom_x"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
        ctk.CTkLabel(box_act_xy, text="Y:", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkEntry(box_act_xy, textvariable=s["custom_y"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 6))

        ctk.CTkLabel(ra, text="範圍:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(ra, variable=s["roi"], values=ROI_OPTIONS, width=110, height=24, corner_radius=6, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))

        def _refresh_s_act_ui(*_):
            if s["action"].get() in ("自訂座標", "自訂特定區塊"):
                box_act_xy.pack(side="left", padx=(0, 6))
            else:
                box_act_xy.pack_forget()
        s["action"].trace_add("write", _refresh_s_act_ui)
        _refresh_s_act_ui()

        ctk.CTkLabel(ra, text="延遲:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(ra, textvariable=s["delay"], width=42, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left")
        ctk.CTkLabel(ra, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(2, 0))

        # 排除字詞列
        re = ctk.CTkFrame(detail, fg_color="transparent")
        re.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(re, text="排除字詞:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#F87171").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(re, textvariable=s["exclude_keywords"], height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=10)).pack(side="left", fill="x", expand=True)

        # 展開/收合切換邏輯
        def refresh(*_):
            if s["expanded"].get():
                btn_toggle.configure(text="▾")
                lbl_sum.pack_forget()
                detail.pack(fill="x", padx=10, pady=(0, 8))
            else:
                btn_toggle.configure(text="▸")
                detail.pack_forget()
                lbl_sum.configure(text=f"  ↳ {s['action'].get()} | 延遲 {s['delay'].get()}s | 範圍: {s['roi'].get()}")
                lbl_sum.pack(fill="x", padx=12, pady=(0, 4))

        s["expanded"].trace_add("write", refresh)
        refresh()
        self._renumber_steps()

    # --------------------------------------------------------------------------
    # 拖曳排序實作 (Drag & Drop Reordering)
    # --------------------------------------------------------------------------
    def _bind_drag_priority_events(self, handle, step):
        def on_start(e):
            step["_drag_start_y"] = e.y_root
            step["_orig_idx"] = self.priority_steps_list.index(step)
        def on_motion(e):
            dy = e.y_root - step.get("_drag_start_y", e.y_root)
            step_height = 40
            steps_moved = int(dy // step_height)
            orig = step.get("_orig_idx", 0)
            new_idx = max(0, min(len(self.priority_steps_list) - 1, orig + steps_moved))
            cur = self.priority_steps_list.index(step)
            if new_idx != cur:
                self.priority_steps_list.remove(step)
                self.priority_steps_list.insert(new_idx, step)
                self._repack_all_priority_steps()
        def on_end(e):
            self.auto_save_current_config()
        handle.bind("<Button-1>", on_start)
        handle.bind("<B1-Motion>", on_motion)
        handle.bind("<ButtonRelease-1>", on_end)

    def _repack_all_priority_steps(self):
        for p in self.priority_steps_list:
            p["frame"].pack_forget()
        for p in self.priority_steps_list:
            p["frame"].pack(fill="x", pady=4, padx=2)
        self._renumber_priority_steps()

    def _bind_drag_events(self, handle, step):
        def on_start(e):
            step["_drag_start_y"] = e.y_root
            step["_orig_idx"] = self.steps_list.index(step)
        def on_motion(e):
            dy = e.y_root - step.get("_drag_start_y", e.y_root)
            step_height = 40
            steps_moved = int(dy // step_height)
            orig = step.get("_orig_idx", 0)
            new_idx = max(0, min(len(self.steps_list) - 1, orig + steps_moved))
            cur = self.steps_list.index(step)
            if new_idx != cur:
                self.steps_list.remove(step)
                self.steps_list.insert(new_idx, step)
                self._repack_all_steps()
        def on_end(e):
            self.auto_save_current_config()
        handle.bind("<Button-1>", on_start)
        handle.bind("<B1-Motion>", on_motion)
        handle.bind("<ButtonRelease-1>", on_end)

    def _repack_all_steps(self):
        for s in self.steps_list:
            s["frame"].pack_forget()
        for s in self.steps_list:
            s["frame"].pack(fill="x", pady=4, padx=2)
        self._renumber_steps()

    # ==========================================================================
    # ⚙️ 設定檔序列化、自動儲存與載入 (100% 相容 JSON)
    # ==========================================================================
    def serialize_current_config(self) -> dict:
        return {
            "device": self.var_device.get(),
            "interval": self.var_interval.get(),
            "confidence": self.var_confidence.get(),
            "idle_strategy": self.var_idle_strategy.get(),
            "auto_refresh": self.var_auto_refresh.get(),
            "lang_tc": self.var_lang_tc.get(),
            "lang_sc": self.var_lang_sc.get(),
            "lang_en": self.var_lang_en.get(),
            "watchdog_enabled": self.var_watchdog_enabled.get(),
            "watchdog_seconds": self.var_watchdog_seconds.get(),
            "tg_token": self.var_tg_token.get(),
            "tg_chat_id": self.var_tg_chat_id.get(),
            "priority_steps": [
                {
                    "name": p["name"].get(),
                    "keywords": p["keywords"].get(),
                    "target_type": p["target_type"].get(),
                    "exclude_keywords": p["exclude_keywords"].get(),
                    "action": p["action"].get(),
                    "custom_x": p["custom_x"].get(),
                    "custom_y": p["custom_y"].get(),
                    "delay": p["delay"].get(),
                    "roi": p["roi"].get(),
                    "enabled": p["enabled"].get(),
                    "tg_enabled": p["tg_enabled"].get(),
                    "tg_message": p["tg_message"].get(),
                    "task_target_mode": p["task_target_mode"].get(),
                    "task_target_item": p["task_target_item"].get(),
                    "task_cooldown": p["task_cooldown"].get(),
                } for p in self.priority_steps_list
            ],
            "steps": [
                {
                    "name": s["name"].get(),
                    "keywords": s["keywords"].get(),
                    "target_type": s["target_type"].get(),
                    "exclude_keywords": s["exclude_keywords"].get(),
                    "action": s["action"].get(),
                    "custom_x": s["custom_x"].get(),
                    "custom_y": s["custom_y"].get(),
                    "delay": s["delay"].get(),
                    "roi": s["roi"].get(),
                    "enabled": s["enabled"].get(),
                    "repeat_enabled": s["repeat_enabled"].get(),
                    "repeat_mode": s["repeat_mode"].get(),
                    "repeat_count": s["repeat_count"].get(),
                    "repeat_speed": s["repeat_speed"].get(),
                    "repeat_area": s["repeat_area"].get(),
                    "repeat_custom_x": s["repeat_custom_x"].get(),
                    "repeat_custom_y": s["repeat_custom_y"].get(),
                    "timeout_enabled": s["timeout_enabled"].get(),
                    "timeout_seconds": s["timeout_seconds"].get(),
                } for s in self.steps_list
            ]
        }

    def apply_config_dict(self, cfg: dict):
        if not isinstance(cfg, dict):
            return
        if "interval" in cfg: self.var_interval.set(cfg["interval"])
        if "confidence" in cfg: self.var_confidence.set(cfg["confidence"])
        if "auto_refresh" in cfg: self.var_auto_refresh.set(cfg["auto_refresh"])
        if "lang_tc" in cfg: self.var_lang_tc.set(cfg["lang_tc"])
        if "lang_sc" in cfg: self.var_lang_sc.set(cfg["lang_sc"])
        if "lang_en" in cfg: self.var_lang_en.set(cfg["lang_en"])
        if "watchdog_enabled" in cfg: self.var_watchdog_enabled.set(cfg["watchdog_enabled"])
        if "watchdog_seconds" in cfg: self.var_watchdog_seconds.set(cfg["watchdog_seconds"])
        if "tg_token" in cfg: self.var_tg_token.set(cfg["tg_token"])
        if "tg_chat_id" in cfg: self.var_tg_chat_id.set(cfg["tg_chat_id"])

        if "priority_steps" in cfg:
            self._clear_all_priority_steps()
            for p_data in cfg["priority_steps"]:
                self._create_priority_step_widget(
                    name=p_data.get("name", ""),
                    keywords=p_data.get("keywords", ""),
                    target_type=p_data.get("target_type", "📝 僅文字"),
                    exclude_keywords=p_data.get("exclude_keywords", ""),
                    action=p_data.get("action", "點擊詞條"),
                    custom_x=p_data.get("custom_x", 960),
                    custom_y=p_data.get("custom_y", 540),
                    delay=p_data.get("delay", 2.0),
                    roi_name=p_data.get("roi", "全畫面比對"),
                    enabled=p_data.get("enabled", True),
                    tg_enabled=p_data.get("tg_enabled", False),
                    tg_message=p_data.get("tg_message", ""),
                    task_target_mode=p_data.get("task_target_mode", "📋 完整任務清單"),
                    task_target_item=p_data.get("task_target_item", ""),
                    task_cooldown=p_data.get("task_cooldown", 60.0),
                    expanded=False
                )

        if "steps" in cfg:
            self._clear_all_steps()
            for s_data in cfg["steps"]:
                self._create_step_widget(
                    name=s_data.get("name", ""),
                    keywords=s_data.get("keywords", ""),
                    target_type=s_data.get("target_type", "📝 僅文字"),
                    exclude_keywords=s_data.get("exclude_keywords", ""),
                    action=s_data.get("action", "點擊詞條"),
                    custom_x=s_data.get("custom_x", 960),
                    custom_y=s_data.get("custom_y", 540),
                    delay=s_data.get("delay", 2.5),
                    roi_name=s_data.get("roi", "右下角區域"),
                    enabled=s_data.get("enabled", True),
                    repeat_enabled=s_data.get("repeat_enabled", False),
                    repeat_mode=s_data.get("repeat_mode", "持續連點"),
                    repeat_count=s_data.get("repeat_count", 5),
                    repeat_speed=s_data.get("repeat_speed", 0.25),
                    repeat_area=s_data.get("repeat_area", "右下角區域"),
                    repeat_custom_x=s_data.get("repeat_custom_x", 960),
                    repeat_custom_y=s_data.get("repeat_custom_y", 540),
                    timeout_enabled=s_data.get("timeout_enabled", False),
                    timeout_seconds=s_data.get("timeout_seconds", 20),
                    expanded=False
                )

    def auto_save_current_config(self):
        try:
            cfg = self.serialize_current_config()
            with open(self.auto_save_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def auto_load_last_config(self) -> bool:
        if os.path.exists(self.auto_save_file):
            try:
                with open(self.auto_save_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.apply_config_dict(cfg)
                self.log_message(f"自動載入歷史設定: {os.path.basename(self.auto_save_file)}")
                return True
            except Exception:
                pass
        return False

    def on_save_config_manual(self):
        path = filedialog.asksaveasfilename(
            title="儲存設定檔",
            defaultextension=".json",
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
        )
        if path:
            try:
                cfg = self.serialize_current_config()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                self.log_message(f"設定已儲存至: {os.path.basename(path)}")
                messagebox.showinfo("成功", f"設定已成功儲存至:\n{path}")
            except Exception as e:
                messagebox.showerror("錯誤", f"儲存失敗: {e}")

    def on_load_config_manual(self):
        path = filedialog.askopenfilename(
            title="載入設定檔",
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.apply_config_dict(cfg)
                self.log_message(f"已成功載入設定: {os.path.basename(path)}")
                messagebox.showinfo("成功", f"已成功載入設定:\n{path}")
            except Exception as e:
                messagebox.showerror("錯誤", f"載入失敗: {e}")

    def _init_default_steps(self):
        if self.auto_load_last_config():
            return
        self.on_reset_baseball_template()

    def on_reset_baseball_template(self):
        """載入經典棒球聯賽範本"""
        self._clear_all_priority_steps()
        self._clear_all_steps()
        # 預設優先動作：異常連線彈窗處理
        self._create_priority_step_widget(
            name="異常連線中斷",
            keywords="連線中斷, 重新連線, 網路異常, 伺服器維護, 請重新登入",
            action="點擊詞條",
            delay=3.0,
            roi_name="中央區域",
            expanded=False
        )
        # 預設循序步驟
        default_steps = [
            ("結算確認", "確認, 確定, 領取, 結算, 結束", 3.0, "右下角區域"),
            ("繼續下一場", "繼續, 下一步, 再來一場, 返回", 2.5, "右下角區域"),
            ("準備比賽", "準備, 挑戰, 出戰, 進入", 2.5, "右半側螢幕"),
            ("開始比賽", "開始, 確定開始, 比賽開始, 開打", 4.0, "右下角區域"),
        ]
        for name, kw, d, r in default_steps:
            self._create_step_widget(name=name, keywords=kw, delay=d, roi_name=r, expanded=False)
        self.log_message("已重設為經典棒球聯賽自動刷關範本。")

    # ==========================================================================
    # 🔌 裝置連線與 ADB 控制
    # ==========================================================================
    def on_refresh_devices(self):
        self.log_message("正在搜尋 ADB 裝置與模擬器...")
        devices = self.bot.get_devices_list()
        self.combo_devices.configure(values=devices if devices else ["未偵測到裝置"])
        if devices:
            self.combo_devices.set(devices[0])
            self.log_message(f"發現裝置: {', '.join(devices)}")
        else:
            self.combo_devices.set("未偵測到裝置")
            self.log_message("未找到已連線的 ADB 裝置。請確認模擬器已啟動。")

    def on_connect_device(self):
        target = self.var_device.get()
        if not target or target == "未偵測到裝置":
            target = None
        self.log_message(f"連線至裝置: {target or '預設第一台'}")
        if self.bot.connect(target_serial=target):
            self._set_status("已連線 (CONNECTED)", COLOR_RUNNING)
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.log_message("ADB 裝置連線成功！可以啟動自動刷關。")
            self.on_preview_and_detect()
        else:
            self._set_status("連線失敗 (FAILED)", COLOR_STOPPED)
            messagebox.showerror("錯誤", "無法連線至指定的 ADB 裝置。請檢查連接埠或重啟模擬器。")

    def _set_status(self, text: str, color: str):
        self.var_status_text.set(text)
        self.lbl_status.configure(text_color=color)
        self.indicator_light.configure(text_color=color)

    # ==========================================================================
    # 🧵 執行緒運作與背景巡檢 (Worker Loop)
    # ==========================================================================
    def on_start_bot(self):
        if self.is_running:
            return
        if not self.bot.device:
            messagebox.showwarning("警告", "尚未連線至 ADB 裝置，請先點擊「連線」。")
            return

        self.is_running = True
        self.bot.is_running = True
        self.start_time = time.time()

        self._set_status("運作中 (RUNNING)", COLOR_RUNNING)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.log_message("🚀 自動刷關執行緒已啟動！")

        interval = float(self.var_interval.get())
        steps = self._get_active_steps_config()
        p_steps = self._get_active_priority_steps_config()

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(interval, steps, p_steps),
            daemon=True
        )
        self.worker_thread.start()

    def on_stop_bot(self):
        if not self.is_running:
            return
        self.log_message("🛑 正在停止自動刷關...")
        self.bot.is_running = False
        self.is_running = False
        self._set_status("已停止 (STOPPED)", COLOR_STOPPED)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _run_worker(self, interval: float, steps: list, priority_steps: list):
        """背景執行緒迴圈：完全獨立運行，保證介面零卡頓"""
        while self.is_running and self.bot.is_running:
            self.loop_count += 1
            screen = self.bot.capture_screen()
            if screen is not None:
                self.current_screen_bgr = screen
                detected = self.bot.scan_text(screen)

                # 1. 優先動作比對
                matched_p = None
                for p_cfg in priority_steps:
                    if not p_cfg.get("enabled", True):
                        continue
                    kws = [k.strip() for k in p_cfg.get("keywords", "").split(",") if k.strip()]
                    for d in detected:
                        txt = d.get("text", "")
                        if any(kw in txt for kw in kws):
                            matched_p = (p_cfg, d)
                            break
                    if matched_p:
                        break

                if matched_p:
                    p_cfg, d_item = matched_p
                    self.hit_count += 1
                    self.log_message(f"⚡ [優先命中] {p_cfg.get('name')}: {d_item.get('text')}")
                    # 執行點擊
                    cx, cy = d_item.get("center", (960, 540))
                    self.bot.tap(cx, cy)
                    time.sleep(float(p_cfg.get("delay", 2.0)))
                    continue

                # 2. 一般步驟比對
                for s_cfg in steps:
                    if not s_cfg.get("enabled", True):
                        continue
                    kws = [k.strip() for k in s_cfg.get("keywords", "").split(",") if k.strip()]
                    matched_s = None
                    for d in detected:
                        txt = d.get("text", "")
                        if any(kw in txt for kw in kws):
                            matched_s = d
                            break
                    if matched_s:
                        self.hit_count += 1
                        self.log_message(f"🎯 [命中步驟] {s_cfg.get('name')}: {matched_s.get('text')}")
                        cx, cy = matched_s.get("center", (960, 540))
                        self.bot.tap(cx, cy)
                        time.sleep(float(s_cfg.get("delay", 2.5)))
                        break

            # 睡眠等待下一輪
            time.sleep(interval)

        self.root.after(0, self._on_worker_stopped)

    def _on_worker_stopped(self):
        self._set_status("已停止 (STOPPED)", COLOR_STOPPED)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.log_message("⏹ 背景工作執行緒已安全終止。")

    def _get_active_steps_config(self) -> list:
        return [
            {
                "name": s["name"].get(),
                "keywords": s["keywords"].get(),
                "delay": s["delay"].get(),
                "roi": s["roi"].get(),
                "enabled": s["enabled"].get()
            } for s in self.steps_list if s["enabled"].get()
        ]

    def _get_active_priority_steps_config(self) -> list:
        return [
            {
                "name": p["name"].get(),
                "keywords": p["keywords"].get(),
                "delay": p["delay"].get(),
                "roi": p["roi"].get(),
                "enabled": p["enabled"].get()
            } for p in self.priority_steps_list if p["enabled"].get()
        ]

    def _execute_task_flow_for_event(self, step_cfg: dict) -> bool:
        self.log_message(f"觸發任務清單跳轉: {step_cfg}")
        return True

    # ==========================================================================
    # 📸 即時截圖與畫面預覽 (Canvas Preview & Mouse Picking)
    # ==========================================================================
    def on_preview_and_detect(self):
        if self._capturing:
            return
        self._capturing = True
        self.btn_capture.configure(state="disabled")

        def work():
            screen = self.bot.capture_screen()
            def done():
                self._capturing = False
                self.btn_capture.configure(state="normal")
                if screen is not None:
                    self.current_screen_bgr = screen
                    self._render_preview(screen)
                    self.log_message("📸 畫面截圖成功！")
            self.root.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def on_bot_frame_update(self, screen_bgr: np.ndarray, detected_items: list, matched=None):
        """當背景 bot 截取到新畫面時，由回呼推播至預覽"""
        if screen_bgr is not None:
            self.current_screen_bgr = screen_bgr
            self._render_preview(screen_bgr)

    def _render_preview(self, screen_bgr: np.ndarray):
        if screen_bgr is None:
            return
        try:
            h, w = screen_bgr.shape[:2]
            self.raw_screen_w, self.raw_screen_h = w, h
            avail_w = max(100, getattr(self, "canvas_w", 480) - 8)
            avail_h = max(100, getattr(self, "canvas_h", 270) - 8)

            scale = min(avail_w / w, avail_h / h)
            self.preview_scale = scale
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            self.preview_img_w, self.preview_img_h = new_w, new_h

            resized = cv2.resize(screen_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            self.preview_image_tk = ImageTk.PhotoImage(pil_img)
            self.lbl_canvas.configure(image=self.preview_image_tk, text="")
        except Exception:
            pass

    def _on_preview_resize(self, e=None):
        if e:
            self.canvas_w = e.width
            self.canvas_h = e.height
        if self.current_screen_bgr is not None:
            self._render_preview(self.current_screen_bgr)

    def _on_preview_mouse_move(self, e):
        rx, ry = self._preview_to_real(e.x, e.y)
        if rx is not None:
            self.var_preview_coords.set(f"X: {rx}, Y: {ry}")

    def _on_preview_click(self, e):
        rx, ry = self._preview_to_real(e.x, e.y)
        if rx is not None:
            self.log_message(f"🎯 選取座標: ({rx}, {ry})")
            if self.steps_list:
                # 填入最新展開的一般步驟
                last_s = self.steps_list[-1]
                last_s["custom_x"].set(rx)
                last_s["custom_y"].set(ry)
                last_s["action"].set("自訂座標")
                self.log_message(f"已填入步驟 [{last_s['name'].get()}] 自訂座標: ({rx}, {ry})")

    def _preview_to_real(self, ex: int, ey: int) -> Tuple[Optional[int], Optional[int]]:
        if not self.raw_screen_w or not self.preview_scale:
            return None, None
        w_offset = max(0, (self.canvas_w - self.preview_img_w) // 2)
        h_offset = max(0, (self.canvas_h - self.preview_img_h) // 2)
        img_x = ex - w_offset
        img_y = ey - h_offset
        if 0 <= img_x <= self.preview_img_w and 0 <= img_y <= self.preview_img_h:
            rx = int(img_x / self.preview_scale)
            ry = int(img_y / self.preview_scale)
            return min(self.raw_screen_w, max(0, rx)), min(self.raw_screen_h, max(0, ry))
        return None, None

    def on_toggle_auto_refresh(self):
        if self.var_auto_refresh.get():
            self._schedule_next_refresh(1500)
        else:
            if self.auto_refresh_job:
                self.root.after_cancel(self.auto_refresh_job)
                self.auto_refresh_job = None

    def _schedule_next_refresh(self, delay_ms: int = 1500):
        if self.auto_refresh_job:
            self.root.after_cancel(self.auto_refresh_job)
        self.auto_refresh_job = self.root.after(delay_ms, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        self.auto_refresh_job = None
        if self.var_auto_refresh.get() and self.bot.device:
            self.on_preview_and_detect()
            self._schedule_next_refresh(2000)

    # ==========================================================================
    # 📜 日誌終端輸出與跨執行緒佇列渲染
    # ==========================================================================
    def log_message(self, text: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{now}] {text}\n"
        self.log_queue.put(entry)

    def _process_log_queue(self):
        batch = []
        while not self.log_queue.empty():
            try:
                batch.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if batch and hasattr(self, "txt_log"):
            self.txt_log.configure(state="normal")
            for item in batch:
                self.txt_log.insert("end", item)
            if self.auto_scroll_logs:
                self.txt_log.see("end")
            self.txt_log.configure(state="disabled")
        self.root.after(50, self._process_log_queue)

    def on_clear_log(self):
        if hasattr(self, "txt_log"):
            self.txt_log.configure(state="normal")
            self.txt_log.delete("1.0", "end")
            self.txt_log.configure(state="disabled")

    def _toggle_auto_scroll(self):
        self.auto_scroll_logs = bool(self.sw_log_scroll.get())

    def _export_logs(self):
        content = self.txt_log.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("提示", "目前沒有任何日誌可匯出。")
            return
        path = filedialog.asksaveasfilename(
            title="儲存執行日誌",
            defaultextension=".log",
            filetypes=[("Log 檔案", "*.log"), ("文字檔案", "*.txt"), ("所有檔案", "*.*")]
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.log_message(f"💾 日誌成功儲存至: {os.path.basename(path)}")
                messagebox.showinfo("成功", f"日誌已成功儲存至:\n{path}")
            except Exception as e:
                messagebox.showerror("錯誤", f"無法儲存日誌檔案: {e}")

    # ==========================================================================
    # ⏱ 計時器與輔助功能
    # ==========================================================================
    def _update_uptime_timer(self):
        if self.is_running and self.start_time:
            self.total_uptime_seconds += 1
            hrs = self.total_uptime_seconds // 3600
            mins = (self.total_uptime_seconds % 3600) // 60
            secs = self.total_uptime_seconds % 60
            uptime_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
            if hasattr(self, "lbl_metrics_inline"):
                self.lbl_metrics_inline.configure(
                    text=f"⏱ 運行: {uptime_str}   |   🔄 輪次: {self.loop_count} 次   |   🎯 命中: {self.hit_count} 次"
                )
        self.root.after(1000, self._update_uptime_timer)

    def on_test_telegram_message(self):
        token = self.var_tg_token.get().strip()
        chat_id = self.var_tg_chat_id.get().strip()
        if not token or not chat_id:
            messagebox.showwarning("警告", "請先輸入 Telegram Token 與 Chat ID。")
            return
        self.log_message("正在發送 Telegram 測試通知...")
        threading.Thread(target=self._send_tg_worker, args=(token, chat_id), daemon=True).start()

    def _send_tg_worker(self, token, chat_id):
        import requests
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            resp = requests.post(url, json={"chat_id": chat_id, "text": "⚾ Auto9Innings 測試通知已成功送達！"}, timeout=10)
            if resp.status_code == 200:
                self.log_message("✅ Telegram 測試訊息發送成功！")
            else:
                self.log_message(f"❌ Telegram 發送失敗: {resp.text}")
        except Exception as e:
            self.log_message(f"❌ 發送 Telegram 異常: {e}")

    def on_run_diagnostics(self):
        self.log_message("正在執行診斷程式...")
        try:
            from diagnostics import run_diagnostics
            threading.Thread(target=run_diagnostics, args=(self.log_message,), daemon=True).start()
        except Exception as e:
            self.log_message(f"無法執行診斷: {e}")

    def on_open_new_window(self):
        new_win = ctk.CTkToplevel(self.root)
        BaseballBotGUI(new_win, instance_id=self.instance_id + 1)

    def on_close_window(self):
        self.auto_save_current_config()
        if self.is_running:
            self.on_stop_bot()
        self.root.destroy()


# ==============================================================================
# 🚀 程式入口函式 (Main Entry Point)
# ==============================================================================
def main():
    root = ctk.CTk()
    app = BaseballBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
