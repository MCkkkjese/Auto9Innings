"""
循序腳本頁面。

StepScriptPage 是「優先動作 + 循序步驟」腳本的完整頁面：步驟編輯、進階參數、
即時預覽與框選截圖、日誌、存檔／載入，以及背景執行。畫面來源與點擊方式由
子類別決定：

- EmulatorScriptPage：透過 ADB 操作 Android 模擬器
- MirrorScriptPage  ：鎖定 macOS 視窗（預設為 iPhone 鏡像輸出）並以滑鼠操作

兩個頁面共用同一份介面與邏輯，只在連線方式與少數設定上不同。
"""
import datetime
import gc
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk
import numpy as np

from core import notify, storage
from core import options as O
from core.bot import GameBot
from core.imaging import imwrite_unicode, newest_image_in
from core.textutil import num, safe_filename
from ui import theme as T
from ui import widgets as W
from ui.dialogs import TemplateSnipperDialog, ask_save_config
from ui.step_cards import NORMAL, PRIORITY, StepListEditor
import version

# 沒有任何存檔時載入的通用範例步驟（以文字辨識處理常見的確認／繼續流程）
DEFAULT_PRIORITY_STEPS = [
    {"name": "異常連線中斷", "keywords": "連線中斷, 重新連線, 網路異常, 伺服器維護, 請重新登入",
     "delay": 3.0, "roi": "中央區域", "while_condition": False},
]
DEFAULT_STEPS = [
    {"name": "結算確認", "keywords": "確認, 確定, 領取, 結算, 結束", "delay": 3.0, "roi": "右下角區域"},
    {"name": "繼續下一場", "keywords": "繼續, 下一步, 再來一場, 返回", "delay": 2.5, "roi": "右下角區域"},
    {"name": "準備開始", "keywords": "準備, 挑戰, 出戰, 進入", "delay": 2.5, "roi": "右半側螢幕"},
    {"name": "開始", "keywords": "開始, 確定開始, 開打", "delay": 4.0, "roi": "右下角區域"},
]


class StepScriptPage:
    """循序腳本頁面的共用實作。"""

    KIND = "emulator"
    TITLE = "步驟與優先動作"
    START_TEXT = "啟動"
    DEVICE_NOUN = "裝置"
    PLACEHOLDER = "連線後會自動顯示即時畫面"
    DEFAULT_INTERVAL = 2.5
    DEFAULT_CONFIDENCE = 0.65
    DEFAULT_IDLE_TAP_XY = (983, 1023)
    LOAD_REPOINTS_AUTOSAVE = False   # 手動載入設定檔後，自動存檔是否改寫入該檔
    STEPS_MIN_HEIGHT = 210           # 步驟卡片的最小高度（工具列 + 至少一列步驟）

    def __init__(self, app, container):
        self.app = app
        self.root = app.root
        self.parent = container
        self.instance_id = app.instance_id
        self.task_page = None            # 由主視窗在任務流程頁建立後設定
        self.config_dir = storage.PROJECT_DIR

        self.worker_thread: Optional[threading.Thread] = None
        self.is_running = False
        self._is_loading_config = False
        self._auto_save_timer = None
        self._watchdog_restart_job = None
        self.auto_refresh_job = None
        self._capturing = False
        self._preview_update_pending = False
        self._pending_logs: List[str] = []
        self.log_panel: Optional[W.LogPanel] = None
        self.preview: Optional[W.PreviewPanel] = None
        self.current_screen_bgr: Optional[np.ndarray] = None
        self.last_snipped_template = ""

        # 統計
        self.start_time: Optional[float] = None
        self.total_uptime_seconds = 0
        self.loop_count = 0
        self.hit_count = 0

        self.auto_save_file = ""
        self._init_vars()
        self.steps = StepListEditor(self)
        self._build_ui()
        self.bot = self._create_bot()
        self.bot.set_allowed_languages(self.var_lang_tc.get(), self.var_lang_sc.get(), self.var_lang_en.get())
        self.on_storage_changed(refresh=False)
        self.last_snipped_template = newest_image_in(self.storage_dir)
        self._init_default_steps()
        self.root.after(1000, self._tick_uptime)

    # ======================================================================
    # 由子類別實作
    # ======================================================================
    def _create_bot(self) -> GameBot:
        raise NotImplementedError

    def is_connected(self) -> bool:
        raise NotImplementedError

    def build_connection_bar(self, parent):
        raise NotImplementedError

    def _ensure_connected_for_start(self) -> bool:
        raise NotImplementedError

    def _format_coords(self, rx: int, ry: int) -> str:
        return f"X: {rx}, Y: {ry}"

    def _extra_serialize(self) -> dict:
        return {}

    def _extra_apply(self, cfg: dict):
        pass

    def _before_start(self):
        pass

    def _can_start(self) -> bool:
        return True

    def _on_stop_requested(self):
        pass

    def _extra_toolbar_buttons(self, flow: W.FlowFrame):
        pass

    def _fallback_configs(self) -> List[str]:
        """沒有自己的自動存檔時，依序嘗試載入的其他設定檔。"""
        return []

    # ======================================================================
    # 存檔位置（由主視窗統一管理）
    # ======================================================================
    @property
    def storage_dir(self) -> str:
        return self.app.storage_dir

    @property
    def templates_dir(self) -> str:
        return self.app.storage_dir

    def on_storage_changed(self, refresh: bool = True):
        """存檔資料夾變更時，更新自動存檔路徑與模板搜尋位置。"""
        self.auto_save_file = storage.autosave_path(self.storage_dir, self.KIND, self.instance_id)
        self.bot.set_templates_dir(self.storage_dir)
        if refresh:
            self.steps.refresh_thumbs()

    def resolve_image_path(self, name: str) -> Optional[str]:
        dirs = [self.storage_dir]
        if self.auto_save_file:
            dirs.append(os.path.dirname(self.auto_save_file))
        return storage.resolve_image_path(name, dirs)

    # ======================================================================
    # 變數
    # ======================================================================
    def _init_vars(self):
        self.var_status_text = tk.StringVar(value="未連線")
        self.var_recognition_mode = tk.StringVar(value=O.MODE_IMAGE)
        self.var_interval = tk.DoubleVar(value=self.DEFAULT_INTERVAL)
        self.var_confidence = tk.DoubleVar(value=self.DEFAULT_CONFIDENCE)
        self.var_idle_strategy = tk.StringVar(value=O.IDLE_STRATEGIES[0])
        self.var_auto_refresh = tk.BooleanVar(value=True)
        self.var_preview_interval = tk.StringVar(value="1.5秒")
        self.var_preview_coords = tk.StringVar(value="")

        # OCR 語言過濾（預設繁中 + 英文，關閉簡中以減少誤判）
        self.var_lang_tc = tk.BooleanVar(value=True)
        self.var_lang_sc = tk.BooleanVar(value=False)
        self.var_lang_en = tk.BooleanVar(value=True)

        # 看門狗
        self.var_watchdog_enabled = tk.BooleanVar(value=False)
        self.var_watchdog_seconds = tk.IntVar(value=60)

        # 等待時連點
        self.var_idle_tap_enabled = tk.BooleanVar(value=False)
        self.var_idle_tap_area = tk.StringVar(value="右下角區域")
        self.var_idle_tap_times = tk.IntVar(value=3)
        self.var_idle_tap_interval = tk.DoubleVar(value=0.4)
        self.var_idle_tap_custom_x = tk.IntVar(value=self.DEFAULT_IDLE_TAP_XY[0])
        self.var_idle_tap_custom_y = tk.IntVar(value=self.DEFAULT_IDLE_TAP_XY[1])

        # Telegram
        self.var_tg_token = tk.StringVar(value=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
        self.var_tg_chat_id = tk.StringVar(value=os.environ.get("TELEGRAM_CHAT_ID", ""))

        def on_lang_changed(*_):
            bot = getattr(self, "bot", None)
            if bot:
                bot.set_allowed_languages(self.var_lang_tc.get(), self.var_lang_sc.get(), self.var_lang_en.get())
            self.auto_save_current_config()

        for v in (self.var_lang_tc, self.var_lang_sc, self.var_lang_en):
            v.trace_add("write", on_lang_changed)

        for v in (self.var_interval, self.var_confidence, self.var_idle_strategy,
                  self.var_watchdog_enabled, self.var_watchdog_seconds,
                  self.var_idle_tap_enabled, self.var_idle_tap_area, self.var_idle_tap_times,
                  self.var_idle_tap_interval, self.var_idle_tap_custom_x, self.var_idle_tap_custom_y,
                  self.var_tg_token, self.var_tg_chat_id):
            v.trace_add("write", lambda *_: self.auto_save_current_config())

    # ======================================================================
    # 版面
    # ======================================================================
    def _build_ui(self):
        container = W.row(self.parent)
        container.pack(fill="both", expand=True, padx=4, pady=4)
        # 左：步驟編輯；右：預覽與日誌。兩欄都會隨視窗縮放，並各自保有最小寬度。
        container.grid_columnconfigure(0, weight=5, minsize=500, uniform="cols")
        container.grid_columnconfigure(1, weight=5, minsize=420, uniform="cols")
        container.grid_rowconfigure(0, weight=1)

        # 左欄由上而下：連線列（視窗鏡像頁才有）、步驟卡片、進階參數。
        # 步驟卡片保有最小高度，進階參數展開後若空間不足會在面板內捲動，不會擠壓其他區塊。
        left = W.row(container)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1, minsize=self.STEPS_MIN_HEIGHT)
        self._left = left
        self._header_box = W.row(left, height=1)
        self._build_page_header(self._header_box)
        if self._header_box.winfo_children():
            self._header_box.grid(row=0, column=0, sticky="ew")
        self._build_steps_panel(left)
        self._build_advanced_panel(left)
        left.bind("<Configure>", lambda e: self._fit_advanced_height(), add="+")

        right = W.row(container)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=2, minsize=130)
        self._right = right
        self._build_preview_panel(right)
        self._build_log_panel(right)

    def _build_page_header(self, parent):
        """頁面上方的額外區塊（子類別可放連線列）。"""

    def _build_steps_panel(self, parent):
        box = W.card(parent)
        box.grid(row=1, column=0, sticky="nsew", pady=(0, 4))

        tools = W.row(box)
        tools.pack(fill="x", padx=12, pady=(10, 6))

        r1 = W.row(tools)
        r1.pack(fill="x", pady=(0, 6))
        W.label(r1, self.TITLE, size=13, bold=True).pack(side="left")
        self.btn_stop = W.button(r1, "停止", self.on_stop_bot, kind="danger", width=64, state="disabled")
        self.btn_stop.pack(side="right")
        self.btn_start = W.button(r1, self.START_TEXT, self.on_start_bot, kind="success", width=84, state="disabled")
        self.btn_start.pack(side="right", padx=(0, 4))

        self.seg_mode = ctk.CTkSegmentedButton(
            tools, values=O.RECOGNITION_MODES, variable=self.var_recognition_mode,
            command=self._on_recognition_mode_changed, font=T.font(11, True), height=28,
            selected_color=T.COLOR_BTN_PRIMARY, selected_hover_color=T.COLOR_BTN_PRIMARY_HOVER,
            unselected_color=T.COLOR_BTN_DARK, unselected_hover_color=T.COLOR_BTN_DARK_HOVER,
            fg_color=T.COLOR_BTN_DARK,
        )
        self.seg_mode.pack(fill="x", pady=(0, 6))

        r3 = W.FlowFrame(tools)
        r3.pack(fill="x")
        r3.add(W.button(r3, "＋ 優先動作", lambda: self.steps.add_interactive(PRIORITY), kind="warning", width=88))
        r3.add(W.button(r3, "＋ 任務跳轉", lambda: self.steps.add_interactive(PRIORITY, task_trigger=True),
                        kind="violet", width=88))
        r3.add(W.button(r3, "＋ 一般步驟", lambda: self.steps.add_interactive(NORMAL), kind="primary", width=88))
        self._extra_toolbar_buttons(r3)
        r3.add(W.button(r3, "範本", self.on_load_preset, width=52), right=True)
        r3.add(W.button(r3, "載入", self.on_load_config_manual, width=52), right=True)
        r3.add(W.button(r3, "存檔", self.on_open_save_dialog, kind="success", width=52), right=True)

        self.steps.build(box).pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_advanced_panel(self, parent):
        self.adv_card = W.card(parent)
        self.adv_card.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self._adv_open = False

        bar = W.row(self.adv_card)
        bar.pack(fill="x", padx=12, pady=8)
        self.btn_adv = W.button(bar, "進階參數設定 ▸", self._toggle_advanced, width=120, size=12)
        self.btn_adv.pack(side="left")
        self._adv_bar = bar

        # 內容放在可捲動容器中：高度依可用空間自動調整，空間足夠時完整展開
        self.adv_content = ctk.CTkScrollableFrame(self.adv_card, fg_color="transparent", height=120,
                                                  scrollbar_button_color=T.COLOR_INPUT_BORDER)
        # 捲軸預設最小高度為 200，會撐高整個面板；高度改由 _fit_advanced_height 同步
        self.adv_content._scrollbar.configure(height=60)
        grid = W.row(self.adv_content)
        grid.pack(fill="x", padx=(4, 6), pady=(0, 6))
        self._adv_grid = grid
        grid.bind("<Configure>", lambda e: self._fit_advanced_height(), add="+")
        grid.grid_columnconfigure(0, weight=0, minsize=92)
        grid.grid_columnconfigure(1, weight=1)

        def add_row(r: int, title: str, color: str = T.COLOR_TEXT_PRIMARY):
            W.label(grid, title, bold=True, color=color).grid(row=r, column=0, sticky="nw", pady=4)
            flow = W.FlowFrame(grid)
            flow.grid(row=r, column=1, sticky="ew", padx=(6, 0), pady=4)
            return flow

        muted = T.COLOR_TEXT_MUTED

        # 掃描間隔
        W.label(grid, "掃描間隔", bold=True).grid(row=0, column=0, sticky="w", pady=4)
        r_sp = W.row(grid)
        r_sp.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=4)
        self.lbl_sp_val = ctk.CTkLabel(r_sp, text=f"{self.var_interval.get():.1f}s", width=40, font=T.mono(11))
        ctk.CTkSlider(r_sp, from_=0.5, to=8.0, number_of_steps=75, variable=self.var_interval, height=16,
                      command=lambda v: self.lbl_sp_val.configure(text=f"{float(v):.1f}s")
                      ).pack(side="left", fill="x", expand=True)
        self.lbl_sp_val.pack(side="left", padx=(4, 0))

        # 文字辨識信心門檻（只影響 OCR，不影響圖片比對）
        W.label(grid, "文字門檻", bold=True).grid(row=1, column=0, sticky="w", pady=4)
        r_cf = W.row(grid)
        r_cf.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=4)
        self.lbl_cf_val = ctk.CTkLabel(r_cf, text=f"{self.var_confidence.get():.2f}", width=40, font=T.mono(11))

        def on_conf(v):
            self.lbl_cf_val.configure(text=f"{float(v):.2f}")
            self.bot.confidence_threshold = float(v)

        ctk.CTkSlider(r_cf, from_=0.4, to=0.95, number_of_steps=55, variable=self.var_confidence, height=16,
                      command=on_conf).pack(side="left", fill="x", expand=True)
        self.lbl_cf_val.pack(side="left", padx=(4, 0))

        f = add_row(2, "語言過濾")
        f.add(W.checkbox(f, "繁中", self.var_lang_tc, height=22))
        f.add(W.checkbox(f, "英文", self.var_lang_en, height=22))
        f.add(W.checkbox(f, "簡中", self.var_lang_sc, height=22))

        f = add_row(3, "看門狗守護")
        f.add(W.checkbox(f, "無進展超時自動重啟", self.var_watchdog_enabled, height=24))
        box = W.row(f)
        W.entry(box, self.var_watchdog_seconds, width=44).pack(side="left")
        W.label(box, "秒", color=muted).pack(side="left", padx=(3, 0))
        f.add(box)

        f = add_row(4, "找不到目標")
        f.add(W.option_menu(f, self.var_idle_strategy, O.IDLE_STRATEGIES, width=120))

        f = add_row(5, "等待時連點")
        f.add(W.checkbox(f, "啟用", self.var_idle_tap_enabled, height=24))
        f.add(W.option_menu(f, self.var_idle_tap_area, O.IDLE_TAP_AREAS + ["自訂座標"], width=118))
        box = W.row(f)
        W.entry(box, self.var_idle_tap_times, width=34).pack(side="left")
        W.label(box, "次，間隔", color=muted).pack(side="left", padx=(3, 4))
        W.entry(box, self.var_idle_tap_interval, width=40).pack(side="left")
        W.label(box, "秒", color=muted).pack(side="left", padx=(3, 0))
        f.add(box)
        xy = W.row(f)
        W.label(xy, "X", size=10, color=muted).pack(side="left")
        W.entry(xy, self.var_idle_tap_custom_x).pack(side="left", padx=(3, 6))
        W.label(xy, "Y", size=10, color=muted).pack(side="left")
        W.entry(xy, self.var_idle_tap_custom_y).pack(side="left", padx=(3, 0))
        f.add(xy)
        idle_flow = f

        def refresh_idle_xy(*_):
            idle_flow.set_visible(xy, "自訂" in self.var_idle_tap_area.get())

        self.var_idle_tap_area.trace_add("write", refresh_idle_xy)
        refresh_idle_xy()

        f = add_row(6, "Telegram", color="#38BDF8")
        box = W.row(f)
        W.label(box, "Token", size=10, color=muted).pack(side="left", padx=(0, 4))
        W.entry(box, self.var_tg_token, width=150).pack(side="left")
        f.add(box)
        box = W.row(f)
        W.label(box, "Chat ID", size=10, color=muted).pack(side="left", padx=(0, 4))
        W.entry(box, self.var_tg_chat_id, width=90).pack(side="left")
        f.add(box)
        f.add(W.button(f, "測試發送", self.on_test_telegram_message, width=64, height=24, size=10, bold=False))

    def _toggle_advanced(self):
        self._adv_open = not self._adv_open
        if self._adv_open:
            self.adv_content.pack(fill="x", padx=6, pady=(0, 8))
            self.btn_adv.configure(text="進階參數設定 ▾")
            self._fit_advanced_height()
        else:
            self.adv_content.pack_forget()
            self.btn_adv.configure(text="進階參數設定 ▸")

    def _fit_advanced_height(self):
        """依左欄可用高度調整進階參數面板：放得下就完整展開，否則限制高度並在面板內捲動。"""
        if not getattr(self, "_adv_open", False):
            return
        try:
            scale = self.adv_content._get_widget_scaling()
            need = self._adv_grid.winfo_reqheight() + 8
            header_h = (self._header_box.winfo_reqheight() + 6) if self._header_box.winfo_manager() else 0
            # 面板除了內容以外的固定高度（標題列、邊框與間距）
            overhead = self.adv_card.winfo_reqheight() - self.adv_content._parent_canvas.winfo_reqheight()
            avail = self._left.winfo_height() - header_h - self.STEPS_MIN_HEIGHT - overhead - 16
            height = max(70, min(need, avail))
            if abs(height - getattr(self, "_adv_height", -1)) > 1:
                self._adv_height = height
                self.adv_content.configure(height=height / scale)
                self.adv_content._scrollbar.configure(height=height / scale)
        except Exception:
            pass

    def _build_preview_panel(self, parent):
        self.preview = W.PreviewPanel(
            parent,
            placeholder=self.PLACEHOLDER + "\n在畫面上按住滑鼠左鍵拖曳可框選按鈕，再按「裁切截圖」存成模板\n單擊畫面可把座標填入展開中的步驟",
            on_capture=self.on_preview_and_detect,
            on_click=self._on_preview_click,
            on_crop=self.on_crop_preview_selection,
            coords_var=self.var_preview_coords,
            interval_var=self.var_preview_interval,
            interval_values=O.PREVIEW_INTERVALS,
            on_interval_change=self._on_preview_interval_change,
            coord_formatter=self._format_coords,
            on_fold=self._on_preview_fold,
        )
        self.preview.grid(row=0, column=0, sticky="nsew", pady=(0, 4))

    def _on_preview_fold(self, is_open: bool):
        # 收合預覽時把空間讓給日誌
        self._right.grid_rowconfigure(0, weight=3 if is_open else 0)

    def _build_log_panel(self, parent):
        self.log_panel = W.LogPanel(parent, title="執行日誌", extra_buttons=[("診斷", self.on_run_diagnostics)])
        self.log_panel.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        for text in self._pending_logs:
            self.log_panel.log(text)
        self._pending_logs.clear()

    # ======================================================================
    # 日誌與狀態
    # ======================================================================
    def log_message(self, text: str):
        if self.log_panel is not None:
            self.log_panel.log(text)
        else:
            self._pending_logs.append(text)

    def _set_status(self, text: str, color: str):
        self.var_status_text.set(text)
        for w in (getattr(self, "lbl_status", None), getattr(self, "indicator_light", None)):
            if w is not None:
                w.configure(text_color=color)

    def _build_status_block(self, parent) -> ctk.CTkFrame:
        """狀態指示燈 + 狀態文字 + 運行統計（連線列共用）。"""
        box = W.row(parent)
        self.indicator_light = ctk.CTkLabel(box, text="●", font=T.font(18, True), text_color=T.COLOR_STOPPED, width=20)
        self.indicator_light.pack(side="left", padx=(0, 6))
        self.lbl_status = ctk.CTkLabel(box, textvariable=self.var_status_text, font=T.font(14, True),
                                       text_color=T.COLOR_STOPPED)
        self.lbl_status.pack(side="left")
        self.lbl_metrics = ctk.CTkLabel(box, text=self._metrics_text(), font=T.mono(10), text_color=T.COLOR_TEXT_MUTED)
        self.lbl_metrics.pack(side="left", padx=(12, 0))
        return box

    def _metrics_text(self) -> str:
        s = self.total_uptime_seconds
        return f"運行 {s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d} | 循環 {self.loop_count} 次 | 命中 {self.hit_count} 次"

    def _tick_uptime(self):
        if self.is_running and self.start_time:
            self.total_uptime_seconds += 1
            if getattr(self, "lbl_metrics", None) is not None:
                self.lbl_metrics.configure(text=self._metrics_text())
        self.root.after(1000, self._tick_uptime)

    # ======================================================================
    # 步驟編輯器回呼 (StepListEditor host 介面)
    # ======================================================================
    def is_loading_config(self) -> bool:
        return self._is_loading_config

    def notify_steps_changed(self):
        self.auto_save_current_config()

    def _on_recognition_mode_changed(self, _mode=None):
        self.steps.refresh_mode()
        is_img = O.is_image_mode(self.var_recognition_mode.get())
        self.log_message(f"辨識模式已切換為：{'圖片特徵比對模式（不使用 OCR）' if is_img else '文字辨識模式 (RapidOCR)'}")
        self.auto_save_current_config()

    def _template_ref(self, path: str) -> str:
        return storage.relative_ref(path, self.storage_dir)

    def _remember_snippet(self, path: str):
        self.last_snipped_template = path
        self.app.on_template_snipped(path)

    def on_browse_template(self, step: dict):
        path = filedialog.askopenfilename(
            parent=self.root, title="選擇圖片模板", initialdir=self.storage_dir,
            filetypes=[("圖片檔案", "*.png *.jpg *.jpeg *.bmp"), ("所有檔案", "*.*")],
        )
        if path:
            step["template_image"].set(self._template_ref(path))
            self.auto_save_current_config()
            self.steps.refresh_thumbs()
            self.log_message(f"已指定圖片模板: {path}")

    def on_open_templates_folder(self):
        try:
            storage.open_in_file_manager(self.storage_dir)
        except Exception as ex:
            messagebox.showerror("錯誤", f"無法打開資料夾: {ex}", parent=self.root)

    def _screen_for_snip(self) -> Optional[np.ndarray]:
        screen = self.current_screen_bgr
        if screen is None and self.is_connected():
            self.log_message("正在截取最新畫面以供框選...")
            screen = self.bot.capture_screen()
            if screen is not None:
                self.current_screen_bgr = screen
                self.preview.render(screen)
        return screen

    def on_snip_template(self, step: dict):
        """開啟框選視窗，從目前畫面裁切出模板並套用到指定步驟。"""
        screen = self._screen_for_snip()
        if screen is None:
            messagebox.showwarning(
                "提示", f"目前尚無畫面可用於框選！\n請先確認{self.DEVICE_NOUN}已連線，並按右側「立即截取」取得畫面。",
                parent=self.root)
            return

        def on_saved(saved_path: str):
            self._remember_snippet(saved_path)
            step["template_image"].set(self._template_ref(saved_path))
            self.auto_save_current_config()
            self.steps.refresh_thumbs()
            self.log_message(f"已框選並儲存模板圖片: {saved_path}")

        TemplateSnipperDialog(self.root, screen, step["name"].get().strip() or "btn_template",
                              self.storage_dir, on_saved)

    def on_apply_last_snippet(self, step: dict):
        """把最近一次裁切的模板圖片帶入指定步驟。"""
        if not self.last_snipped_template:
            messagebox.showinfo(
                "提示",
                "尚未在預覽畫面上裁切過任何圖片模板！\n\n使用方式：\n"
                "1. 在右側預覽畫面按住滑鼠左鍵拖曳框選目標按鈕\n"
                "2. 按「裁切截圖」儲存模板\n"
                "3. 再按步驟上的「帶入」即可直接套用",
                parent=self.root)
            return
        step["template_image"].set(self.last_snipped_template)
        self.auto_save_current_config()
        self.log_message(f"已將最新截圖「{self.last_snipped_template}」帶入步驟「{step['name'].get()}」")

    def on_crop_preview_selection(self):
        """把預覽畫面上框選的區域存成模板圖片，並套用到展開中的步驟（沒有展開的就套用第一個步驟）。"""
        crop = self.preview.get_crop()
        if crop is None:
            messagebox.showwarning("提示", "尚未在預覽畫面上框選任何區域！\n請先在畫面上按住滑鼠並拖曳出框選範圍。",
                                   parent=self.root)
            return
        ch, cw = crop.shape[:2]
        if cw < 4 or ch < 4:
            messagebox.showwarning("提示", "框選範圍過小，請重新框選！", parent=self.root)
            return

        target = self.steps.expanded_step()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if target:
            clean = safe_filename(target["name"].get().strip())
            init_name = f"{clean}.png" if clean else f"snip_{ts}.png"
        else:
            init_name = f"template_{ts}.png"
        save_path = filedialog.asksaveasfilename(
            parent=self.root, title="儲存圖片模板（請選擇儲存位置與檔名）", initialdir=self.storage_dir,
            initialfile=init_name, defaultextension=".png",
            filetypes=[("PNG 圖片", "*.png"), ("所有檔案", "*.*")],
        )
        if not save_path:
            return
        try:
            if not imwrite_unicode(save_path, crop):
                messagebox.showerror("錯誤", f"無法寫入圖檔至:\n{save_path}\n請檢查是否有寫入權限或磁碟空間。",
                                     parent=self.root)
                return
            self._remember_snippet(save_path)
            if not target and self.steps.normal:
                target = self.steps.normal[0]
            applied = ""
            if target:
                target["template_image"].set(self._template_ref(save_path))
                target["target_type"].set(O.TARGET_IMAGE)
                applied = f"\n\n已自動套用至步驟：「{target['name'].get()}」"
            self.auto_save_current_config()
            self.steps.refresh_thumbs()
            self.log_message(f"截圖儲存成功: {save_path} ({cw}×{ch}){applied.replace(chr(10), ' ')}")
            self.preview.clear_selection()
            self.var_preview_coords.set(f"已截圖: {os.path.basename(save_path)} ({cw}×{ch})")
            messagebox.showinfo("截圖成功", f"圖片模板已成功儲存至：\n{save_path}{applied}", parent=self.root)
        except Exception as ex:
            self.log_message(f"截圖儲存失敗: {ex}")
            messagebox.showerror("截圖失敗", f"無法儲存截圖: {ex}", parent=self.root)

    def _on_preview_click(self, rx: int, ry: int):
        """單擊預覽畫面：複製座標，並填入展開中的步驟（連點自訂座標優先）。"""
        self.log_message(f"選取座標: ({rx}, {ry})")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(f"{rx}, {ry}")
        except Exception:
            pass
        target = self.steps.expanded_step()
        if target is None:
            # 沒有展開的卡片時，填入最後一個一般步驟（沒有一般步驟則填最後一個優先動作）
            if self.steps.normal:
                target = self.steps.normal[-1]
            elif self.steps.priority:
                target = self.steps.priority[-1]
            else:
                return
            use_repeat = False
        else:
            use_repeat = bool(target["repeat_enabled"].get()) and "自訂" in target["repeat_area"].get()
        label = "優先動作" if target["type"] == PRIORITY else "步驟"
        if use_repeat:
            target["repeat_custom_x"].set(rx)
            target["repeat_custom_y"].set(ry)
            self.log_message(f"已填入{label} [{target['name'].get()}] 連點自訂座標: ({rx}, {ry})")
        else:
            target["custom_x"].set(rx)
            target["custom_y"].set(ry)
            target["action"].set(O.ACTION_CUSTOM_COORD)
            self.log_message(f"已填入{label} [{target['name'].get()}] 點擊指定座標: ({rx}, {ry})")

    # ======================================================================
    # 設定檔
    # ======================================================================
    def serialize_current_config(self) -> dict:
        langs = {"tc": self.var_lang_tc.get(), "sc": self.var_lang_sc.get(), "en": self.var_lang_en.get()}
        cfg = {
            "version": "1.0",
            "app_version": version.VERSION,
            "type": self.KIND,
            "recognition_mode": self.var_recognition_mode.get(),
            "interval": num(self.var_interval, self.DEFAULT_INTERVAL),
            "confidence": num(self.var_confidence, self.DEFAULT_CONFIDENCE),
            "idle_strategy": self.var_idle_strategy.get(),
            "auto_refresh": self.var_auto_refresh.get(),
            "preview_interval": self.var_preview_interval.get(),
            "lang_tc": langs["tc"], "lang_sc": langs["sc"], "lang_en": langs["en"],
            "ocr_languages": langs,
            "watchdog": {
                "enabled": self.var_watchdog_enabled.get(),
                "seconds": num(self.var_watchdog_seconds, 60, int),
            },
            "idle_tap": {
                "enabled": self.var_idle_tap_enabled.get(),
                "area": self.var_idle_tap_area.get(),
                "times": num(self.var_idle_tap_times, 3, int),
                "interval": num(self.var_idle_tap_interval, 0.4),
                "custom_x": num(self.var_idle_tap_custom_x, self.DEFAULT_IDLE_TAP_XY[0], int),
                "custom_y": num(self.var_idle_tap_custom_y, self.DEFAULT_IDLE_TAP_XY[1], int),
            },
            "telegram_global": {"token": self.var_tg_token.get(), "chat_id": self.var_tg_chat_id.get()},
            "priority_steps": self.steps.serialize(PRIORITY),
            "steps": self.steps.serialize(NORMAL),
        }
        cfg.update(self._extra_serialize())
        return cfg

    def apply_config_dict(self, cfg: dict):
        """把設定檔內容套用到頁面。相容舊版的各種欄位寫法。"""
        if not isinstance(cfg, dict):
            return
        self._is_loading_config = True
        try:
            all_steps = (cfg.get("steps") or []) + (cfg.get("priority_steps") or [])
            if "recognition_mode" in cfg:
                mode = O.normalize_recognition_mode(cfg["recognition_mode"])
            else:
                has_img = any(isinstance(s, dict) and (s.get("template_image") or "圖片" in str(s.get("target_type", "")))
                              for s in all_steps)
                mode = O.MODE_IMAGE if has_img else O.MODE_TEXT
            self.var_recognition_mode.set(mode)

            self._set_number(self.var_interval, cfg.get("interval"), float)
            self._set_number(self.var_confidence, cfg.get("confidence"), float)
            if cfg.get("idle_strategy") in O.IDLE_STRATEGIES:
                self.var_idle_strategy.set(cfg["idle_strategy"])
            if "auto_refresh" in cfg:
                self.var_auto_refresh.set(bool(cfg["auto_refresh"]))
            if cfg.get("preview_interval") in O.PREVIEW_INTERVALS:
                self.var_preview_interval.set(cfg["preview_interval"])

            langs = cfg.get("ocr_languages")
            if not isinstance(langs, dict):
                langs = cfg.get("allowed_languages")
            if isinstance(langs, dict):
                self.var_lang_tc.set(bool(langs.get("tc", True)))
                self.var_lang_sc.set(bool(langs.get("sc", False)))
                self.var_lang_en.set(bool(langs.get("en", True)))
            else:
                for key, var in (("lang_tc", self.var_lang_tc), ("lang_sc", self.var_lang_sc), ("lang_en", self.var_lang_en)):
                    if key in cfg:
                        var.set(bool(cfg[key]))
            self.bot.confidence_threshold = num(self.var_confidence, self.DEFAULT_CONFIDENCE)
            self.lbl_sp_val.configure(text=f"{num(self.var_interval, self.DEFAULT_INTERVAL):.1f}s")
            self.lbl_cf_val.configure(text=f"{num(self.var_confidence, self.DEFAULT_CONFIDENCE):.2f}")

            wd = cfg.get("watchdog")
            if isinstance(wd, dict):
                self.var_watchdog_enabled.set(bool(wd.get("enabled", False)))
                self._set_number(self.var_watchdog_seconds, wd.get("seconds", 60), int)
            else:
                if "watchdog_enabled" in cfg:
                    self.var_watchdog_enabled.set(bool(cfg["watchdog_enabled"]))
                self._set_number(self.var_watchdog_seconds, cfg.get("watchdog_seconds"), int)

            it = cfg.get("idle_tap")
            if isinstance(it, dict):
                self.var_idle_tap_enabled.set(bool(it.get("enabled", False)))
                self.var_idle_tap_area.set(str(it.get("area", "右下角區域")))
                self._set_number(self.var_idle_tap_times, it.get("times", 3), int)
                interval = num(it.get("interval", 0.4), 0.4)
                # 舊版視窗鏡像存檔的預設值是 30（未曾在介面開放），視為無效並改回 0.4 秒
                self.var_idle_tap_interval.set(interval if 0 < interval <= 10 else 0.4)
                self._set_number(self.var_idle_tap_custom_x, it.get("custom_x"), int)
                self._set_number(self.var_idle_tap_custom_y, it.get("custom_y"), int)

            tg = cfg.get("telegram_global")
            if isinstance(tg, dict):
                self.var_tg_token.set(str(tg.get("token", "")))
                self.var_tg_chat_id.set(str(tg.get("chat_id", "")))
            else:
                if "tg_token" in cfg:
                    self.var_tg_token.set(str(cfg["tg_token"]))
                if "tg_chat_id" in cfg:
                    self.var_tg_chat_id.set(str(cfg["tg_chat_id"]))

            p_list = cfg.get("priority_steps")
            if p_list is None and isinstance(cfg.get("priority"), dict):
                old = cfg["priority"]   # 更早期的單一優先動作格式
                if old.get("keywords") or old.get("enabled") or old.get("template_image"):
                    p_list = [old]
            if isinstance(p_list, list):
                self.steps.load(PRIORITY, p_list)
            if isinstance(cfg.get("steps"), list):
                self.steps.load(NORMAL, cfg["steps"])

            self._extra_apply(cfg)
        finally:
            self._is_loading_config = False
        self.steps.refresh_mode()

    @staticmethod
    def _set_number(var, value, cast):
        if value is None:
            return
        try:
            var.set(cast(float(value)))
        except Exception:
            pass

    def auto_save_current_config(self):
        """防抖的自動存檔：連續編輯時只在停下 300ms 後寫入一次。"""
        if self._is_loading_config or not self.auto_save_file:
            return
        if self._auto_save_timer:
            try:
                self.root.after_cancel(self._auto_save_timer)
            except Exception:
                pass
        self._auto_save_timer = self.root.after(300, self._do_auto_save_write)

    def _do_auto_save_write(self):
        self._auto_save_timer = None
        if self._is_loading_config or not self.auto_save_file:
            return
        try:
            storage.save_config(self.auto_save_file, self.serialize_current_config())
        except Exception:
            pass

    def flush_auto_save(self):
        if self._auto_save_timer:
            try:
                self.root.after_cancel(self._auto_save_timer)
            except Exception:
                pass
        self._do_auto_save_write()

    def _load_file_into_page(self, path: str) -> bool:
        try:
            self.apply_config_dict(storage.load_config(path))
            return True
        except Exception:
            return False

    def _init_default_steps(self):
        """啟動時依序嘗試：自己的自動存檔、舊版檔名的存檔、子類別指定的備援設定，最後才是通用範例。"""
        candidates = [
            self.auto_save_file,
            storage.legacy_autosave_path(self.storage_dir, self.KIND, self.instance_id),
        ] + self._fallback_configs()
        for path in candidates:
            if path and os.path.exists(path) and self._load_file_into_page(path):
                self.log_message(f"已載入上次的設定: {os.path.basename(path)}")
                return
        if self._inherit_initial_config():
            return
        self.reset_default_steps()

    def _inherit_initial_config(self) -> bool:
        return False

    def reset_default_steps(self):
        """重設為通用範例步驟。"""
        self._is_loading_config = True
        try:
            self.var_recognition_mode.set(O.MODE_TEXT)
            self.steps.load(PRIORITY, DEFAULT_PRIORITY_STEPS)
            self.steps.load(NORMAL, DEFAULT_STEPS)
        finally:
            self._is_loading_config = False
        self.steps.refresh_mode()
        self.log_message("已載入通用範例步驟，可依遊戲畫面自行調整。")

    def on_open_save_dialog(self):
        def do_save(target: str):
            storage.save_config(target, self.serialize_current_config())
            self.auto_save_file = target
            self._after_manual_save(target)
            self.log_message(f"設定已儲存至: {target}")

        ask_save_config(self.root, "儲存設定", self.auto_save_file, self.storage_dir,
                        f"script_{self.KIND}.json", "設定檔", do_save)

    def _after_manual_save(self, target: str):
        pass

    def on_load_config_manual(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="載入設定檔",
            initialdir=self.storage_dir if os.path.isdir(self.storage_dir) else None,
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")],
        )
        if path:
            self._load_with_feedback(path, repoint=self.LOAD_REPOINTS_AUTOSAVE)

    def on_load_preset(self):
        """從內建範本資料夾挑選設定檔載入（不會改變自動存檔位置）。"""
        path = filedialog.askopenfilename(
            parent=self.root, title="載入內建範本", initialdir=storage.STEP_PRESETS_DIR,
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")],
        )
        if path:
            self._load_with_feedback(path, repoint=False)

    def _load_with_feedback(self, path: str, repoint: bool):
        try:
            self.apply_config_dict(storage.load_config(path))
        except Exception as e:
            self.log_message(f"載入失敗: {e}")
            messagebox.showerror("錯誤", f"載入失敗: {e}", parent=self.root)
            return
        if repoint:
            self.auto_save_file = path
        self.auto_save_current_config()
        self.log_message(f"已載入設定: {os.path.basename(path)}")
        messagebox.showinfo("成功", f"已成功載入設定:\n{path}", parent=self.root)

    # ======================================================================
    # 執行
    # ======================================================================
    def on_start_bot(self):
        if self.is_running:
            return
        if not self._ensure_connected_for_start() or not self._can_start():
            return
        token, chat_id = self.var_tg_token.get().strip(), self.var_tg_chat_id.get().strip()
        steps = self.steps.active_config(NORMAL, token, chat_id)
        priority_steps = self.steps.active_config(PRIORITY, token, chat_id)
        if not any(s["enabled"] for s in steps) and not any(p["enabled"] for p in priority_steps):
            messagebox.showwarning("提示", "請至少啟用一個步驟或優先動作（並確認已填入關鍵字或模板圖片）", parent=self.root)
            return

        self.auto_save_current_config()
        self.bot.confidence_threshold = num(self.var_confidence, self.DEFAULT_CONFIDENCE)
        self.bot.roi = None
        self.bot.set_allowed_languages(self.var_lang_tc.get(), self.var_lang_sc.get(), self.var_lang_en.get())
        self._before_start()
        self.current_screen_bgr = None
        self._preview_update_pending = False
        gc.collect()

        tap_x = num(self.var_idle_tap_custom_x, self.DEFAULT_IDLE_TAP_XY[0], int)
        tap_y = num(self.var_idle_tap_custom_y, self.DEFAULT_IDLE_TAP_XY[1], int)
        idle_tap_cfg = {
            "enabled": self.var_idle_tap_enabled.get(),
            "area": self.var_idle_tap_area.get(),
            "times": num(self.var_idle_tap_times, 3, int),
            "interval": num(self.var_idle_tap_interval, 0.4),
            "custom_x": tap_x, "custom_y": tap_y, "custom_coord": (tap_x, tap_y),
        }
        watchdog_cfg = {
            "enabled": self.var_watchdog_enabled.get(),
            "seconds": num(self.var_watchdog_seconds, 60, int),
        }

        self.is_running = True
        self.bot.is_running = True
        self.start_time = time.time()
        self._set_status("運作中", T.COLOR_RUNNING)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.log_message("腳本已啟動。")
        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(num(self.var_interval, self.DEFAULT_INTERVAL), steps,
                  O.idle_strategy_code(self.var_idle_strategy.get()), idle_tap_cfg, priority_steps, watchdog_cfg),
            daemon=True,
        )
        self.worker_thread.start()

    def on_stop_bot(self):
        if self._watchdog_restart_job:
            self.root.after_cancel(self._watchdog_restart_job)
            self._watchdog_restart_job = None
        self.log_message("正在停止腳本...")
        self.bot.stop()
        self._on_stop_requested()
        self.is_running = False
        self._set_status("已停止", T.COLOR_STOPPED)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _run_worker(self, interval, steps, idle, idle_tap_cfg, priority_steps, watchdog_cfg):
        try:
            self.bot.run_loop(
                poll_interval=interval, custom_steps=steps, idle_strategy=idle,
                idle_tap_config=idle_tap_cfg, priority_steps=priority_steps, watchdog_config=watchdog_cfg,
            )
        except Exception as e:
            self.log_message(f"執行中斷: {e}")
        finally:
            self.root.after(0, self._on_worker_stopped)

    def _on_worker_stopped(self):
        self.current_screen_bgr = None
        gc.collect()
        was_watchdog = getattr(self.bot, "_watchdog_triggered", False)
        self.bot._watchdog_triggered = False
        if was_watchdog:
            self.log_message("[防卡死守護] 腳本已由守護程式停止，將於 1.5 秒後自動重新啟動...")
            self._set_status("防卡死重新啟動中", T.COLOR_PAUSED)
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self._watchdog_restart_job = self.root.after(1500, self._restart_worker_after_watchdog)
            return
        self.is_running = False
        self.bot.is_running = False
        self._set_status("已停止", T.COLOR_STOPPED)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.log_message("背景工作執行緒已終止。")
        if self.var_auto_refresh.get() and not self.auto_refresh_job:
            self._schedule_next_refresh(500)

    def _restart_worker_after_watchdog(self):
        self._watchdog_restart_job = None
        self.is_running = False
        self.bot.is_running = False
        if not self.is_connected():
            self.log_message(f"{self.DEVICE_NOUN}連線已中斷，無法自動重啟")
            self._on_worker_stopped()
            return
        self.log_message("[防卡死守護] 自動重新啟動腳本！")
        self.on_start_bot()

    # ======================================================================
    # 預覽
    # ======================================================================
    def _busy(self) -> bool:
        return self.is_running or self.bot.is_running

    def on_preview_and_detect(self):
        """在背景截取一張畫面並顯示到預覽。"""
        if self._capturing:
            return
        self._capturing = True
        self.preview.set_capture_enabled(False)

        def work():
            screen = None
            try:
                screen = self.bot.capture_screen()
            except Exception as e:
                self.log_message(f"畫面抓取異常: {e}")

            def done():
                self._capturing = False
                self.preview.set_capture_enabled(True)
                if screen is not None:
                    self.current_screen_bgr = screen
                    self.preview.render(screen)
                if self.var_auto_refresh.get() and self.is_connected() and not self._busy() and not self.auto_refresh_job:
                    self._schedule_next_refresh()

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def on_bot_frame_update(self, screen_bgr, detected_items=None, matched=None, *_):
        """執行中由背景執行緒呼叫：更新統計並把畫面送到預覽（上一張還沒畫完就丟棄）。"""
        self.loop_count += 1
        if matched is not None:
            self.hit_count += 1
        if screen_bgr is None:
            return
        self.current_screen_bgr = screen_bgr
        if self._preview_update_pending:
            return
        self._preview_update_pending = True

        def draw():
            self._preview_update_pending = False
            self.preview.render(screen_bgr, matched=matched)

        try:
            self.root.after(0, draw)
        except Exception:
            self._preview_update_pending = False

    def _get_preview_interval_ms(self) -> int:
        try:
            raw = self.var_preview_interval.get().replace("秒", "").replace("s", "").strip()
            return max(300, int(float(raw) * 1000))
        except Exception:
            return 1500

    def _on_preview_interval_change(self, _val=None):
        self.log_message(f"預覽畫面自動刷新間隔已設定為: {self.var_preview_interval.get()}")
        if self.var_auto_refresh.get() and self.is_connected() and not self._busy():
            self._schedule_next_refresh()
        self.auto_save_current_config()

    def _cancel_refresh(self):
        if self.auto_refresh_job:
            try:
                self.root.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
            self.auto_refresh_job = None

    def _schedule_next_refresh(self, delay_ms: Optional[int] = None):
        self._cancel_refresh()
        self.auto_refresh_job = self.root.after(delay_ms or self._get_preview_interval_ms(), self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        self.auto_refresh_job = None
        if self._busy() or not self.var_auto_refresh.get():
            return
        if self.preview.is_dragging:
            self._schedule_next_refresh(600)
            return
        if not self.is_connected():
            self._schedule_next_refresh(2000)
            return
        if self.app.is_page_visible(self):
            self.on_preview_and_detect()
        self._schedule_next_refresh()

    def on_page_shown(self):
        """切換到本頁時恢復預覽刷新。"""
        if self.var_auto_refresh.get() and self.is_connected() and not self._busy():
            self._schedule_next_refresh(200)

    # ======================================================================
    # 其他
    # ======================================================================
    def on_test_telegram_message(self):
        token, chat_id = self.var_tg_token.get().strip(), self.var_tg_chat_id.get().strip()
        if not token or not chat_id:
            messagebox.showwarning("警告", "請先輸入 Telegram Token 與 Chat ID。", parent=self.root)
            return
        self.log_message("正在發送 Telegram 測試通知...")

        def done(ok: bool):
            self.log_message("Telegram 測試通知發送成功！" if ok else "Telegram 測試通知發送失敗，請檢查 Token 與 Chat ID。")

        notify.send_telegram_async(token, chat_id, f"{version.APP_NAME} 測試通知已成功送達！",
                                   self.current_screen_bgr, log=self.log_message, on_done=done)

    def on_run_diagnostics(self):
        self.log_message("正在執行環境診斷...")

        def work():
            try:
                from core.diagnostics import SystemDiagnostics
                diag = SystemDiagnostics.run_full_diagnosis(self.bot)
                for line in SystemDiagnostics.format_report_for_clipboard(diag).splitlines():
                    if line.strip() and not line.startswith("```"):
                        self.log_message(line)
            except Exception as e:
                self.log_message(f"無法執行診斷: {e}")

        threading.Thread(target=work, daemon=True).start()

    def shutdown(self):
        """關閉視窗前：寫入自動存檔並停止執行中的腳本。"""
        self.flush_auto_save()
        self._cancel_refresh()
        if self._busy():
            self.on_stop_bot()


# ==========================================================================
# 模擬器 (ADB)
# ==========================================================================
class EmulatorScriptPage(StepScriptPage):
    """透過 ADB 連線 Android 模擬器的循序腳本頁面。"""

    KIND = "emulator"
    START_TEXT = "啟動腳本"
    DEVICE_NOUN = "模擬器"
    PLACEHOLDER = "模擬器連線後會自動顯示即時畫面"
    NO_DEVICE = "未偵測到裝置"

    def __init__(self, app, container):
        self.var_device = tk.StringVar()
        super().__init__(app, container)
        self.bot.set_task_flow_handler(self._execute_task_flow_for_event)

    def _create_bot(self) -> GameBot:
        return GameBot(log_callback=self.log_message, on_frame_callback=self.on_bot_frame_update)

    def is_connected(self) -> bool:
        return bool(self.bot.device)

    # 任務流程頁沿用這些路徑（與舊版相同：任務存檔與範本都放在存檔資料夾）
    @property
    def task_presets_dir(self) -> str:
        return self.storage_dir

    @property
    def task_save_file(self) -> str:
        return storage.autosave_path(self.storage_dir, "task", self.instance_id)

    def build_connection_bar(self, parent):
        """放在主視窗標題區的裝置列：狀態 + 裝置選單 + 搜尋 + 連線。"""
        bar = W.FlowFrame(parent, hgap=6)
        bar.add(self._build_status_block(bar))
        bar.add(W.label(bar, "模擬器裝置", color=T.COLOR_TEXT_MUTED, height=28), right=True)
        self.combo_devices = ctk.CTkComboBox(
            bar, variable=self.var_device, width=170, height=28, corner_radius=6, state="readonly",
            fg_color=T.COLOR_INPUT_BG, border_color=T.COLOR_INPUT_BORDER, button_color=T.COLOR_INPUT_BORDER,
            font=T.font(11), dropdown_font=T.font(11), values=[self.NO_DEVICE],
        )
        bar.add(self.combo_devices, right=True)
        self.btn_refresh = bar.add(W.button(bar, "搜尋", self.on_refresh_devices, width=60), right=True)
        self.btn_connect = bar.add(W.button(bar, "連線", self.on_connect_device, kind="primary", width=60), right=True)
        return bar

    def on_refresh_devices(self):
        self.log_message("正在搜尋 ADB 裝置與模擬器...")
        devices = self.bot.get_devices_list()
        self.combo_devices.configure(values=devices or [self.NO_DEVICE])
        if devices:
            self.combo_devices.set(devices[0])
            self.log_message(f"發現裝置: {', '.join(devices)}")
        else:
            self.combo_devices.set(self.NO_DEVICE)
            self.log_message("未找到已連線的 ADB 裝置，請確認模擬器已啟動。")

    def on_connect_device(self):
        target = self.var_device.get()
        if not target or target == self.NO_DEVICE:
            target = None
        self.log_message(f"連線至裝置: {target or '預設第一台'}")
        self._capturing = False   # 清除前次連線可能殘留的截圖鎖定
        self._cancel_refresh()
        if self.bot.connect(target_serial=target):
            self.var_device.set(self.bot.device.serial)
            self._set_status("已連線", T.COLOR_RUNNING)
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.log_message("ADB 裝置連線成功，已開始自動刷新即時畫面。")
            self.on_preview_and_detect()
            if self.var_auto_refresh.get():
                self._schedule_next_refresh()
            if self.task_page:
                try:
                    self.task_page.on_device_connected()
                except Exception as e:
                    self.log_message(f"通知任務流程頁連線時發生異常: {e}")
        else:
            self._set_status("連線失敗", T.COLOR_STOPPED)
            messagebox.showerror("錯誤", "無法連線至指定的 ADB 裝置。請檢查連接埠或重啟模擬器。", parent=self.root)

    def _ensure_connected_for_start(self) -> bool:
        if not self.bot.device:
            messagebox.showwarning("警告", "尚未連線至 ADB 裝置，請先按上方的「連線」。", parent=self.root)
            return False
        return True

    def _can_start(self) -> bool:
        if self.task_page and self.task_page.engine.is_running:
            messagebox.showwarning("提示", "「任務流程」正在執行中，請先停止任務流程再啟動腳本。", parent=self.root)
            return False
        return True

    def _on_stop_requested(self):
        if self.task_page:
            self.task_page.engine.stop()

    def _extra_serialize(self) -> dict:
        extra = {"device": self.var_device.get()}
        if self.task_page:
            try:
                extra["task_flow"] = self.task_page._serialize_all_blocks()
                extra["task_loop_count"] = self.task_page.var_loop_count.get()
            except Exception:
                pass
        return extra

    def _extra_apply(self, cfg: dict):
        if cfg.get("device"):
            self.var_device.set(cfg["device"])
        if not self.task_page:
            return
        # 設定檔若帶有任務流程積木，一併載入任務流程頁
        blocks = cfg.get("task_flow") or (cfg.get("blocks") if "priority_steps" not in cfg else None)
        if not isinstance(blocks, list):
            return
        try:
            loops = cfg.get("task_loop_count", cfg.get("loop_count"))
            if loops is not None:
                self.task_page.var_loop_count.set(int(loops))
            self.task_page.replace_blocks(blocks)
        except Exception:
            pass

    def _after_manual_save(self, target: str):
        # 與舊版相同：另存設定後，存檔資料夾跟著移到該檔案所在位置
        self.app.adopt_storage_dir(os.path.dirname(target))

    def _execute_task_flow_for_event(self, step_cfg: dict) -> bool:
        """
        循序腳本偵測到指定事件時，暫停循環並跳轉執行任務流程，完成後再回到循序腳本。
        由工作執行緒直接呼叫，會同步執行到任務完成或被停止。
        """
        tp = self.task_page
        if not tp:
            self.log_message("尚未初始化任務流程頁，跳過執行。")
            return False
        mode = step_cfg.get("task_target_mode", O.TASK_MODE_FULL)
        target_item = step_cfg.get("task_target_item", "")
        step_name = step_cfg.get("name", "事件步驟")

        blocks: list = []
        if ("任務檔" in mode or "範本" in mode) and target_item:
            preset = tp.get_preset_data(target_item.split(":")[0].strip())
            if preset:
                blocks = [dict(b) for b in preset.get("blocks", [])]
                self.log_message(f"[任務跳轉] 載入任務設定「{preset.get('title', target_item)}」(共 {len(blocks)} 個步驟)")
            else:
                self.log_message(f"[任務跳轉] 找不到任務設定「{target_item}」，改為執行完整任務清單")
                blocks = tp._serialize_all_blocks()
        elif mode == O.TASK_MODE_BLOCK and target_item:
            single = tp.get_block_data_by_choice(target_item)
            if single:
                blocks = [single]
                self.log_message(f"[任務跳轉] 執行指定積木「{single.get('name', target_item)}」")
            else:
                self.log_message(f"[任務跳轉] 找不到指定積木「{target_item}」，改為執行完整任務清單")
                blocks = tp._serialize_all_blocks()
        else:
            blocks = tp._serialize_all_blocks()
            self.log_message(f"[任務跳轉] 執行完整任務清單 (共 {len(blocks)} 個步驟)")

        if not blocks:
            self.log_message("[任務跳轉] 任務清單中沒有可執行的步驟，結束跳轉並回到循序腳本。")
            return False

        self.root.after(0, lambda: self._set_status(f"執行任務: {step_name}", T.COLOR_TASK))

        def on_step_change(idx, _cycle, _total):
            self.root.after(0, lambda: tp.highlight_active_step(idx if idx >= 0 else -1))

        def on_priority_hit(hit_idx):
            self.root.after(0, lambda: tp.highlight_active_step(hit_idx if hit_idx >= 0 else -1, is_priority=True))

        ok = tp.engine.run_sync(
            blocks_data=blocks,
            priority_blocks_data=tp._serialize_all_priority_blocks(),
            loop_count=1,
            on_step_change=on_step_change,
            global_settings=tp.get_global_settings(),
            on_priority_hit=on_priority_hit,
        )
        self.root.after(0, lambda: tp.highlight_active_step(-1))
        if self.bot.is_running:
            self.root.after(0, lambda: self._set_status("運作中", T.COLOR_RUNNING))
        return ok


# ==========================================================================
# 視窗鏡像 (macOS)
# ==========================================================================
class MirrorScriptPage(StepScriptPage):
    """鎖定 macOS 視窗（預設為 iPhone 鏡像輸出）並以滑鼠點擊操作的循序腳本頁面。"""

    KIND = "mirror"
    START_TEXT = "啟動腳本"
    DEVICE_NOUN = "鏡像視窗"
    PLACEHOLDER = "按上方「鎖定視窗」連接 iPhone 鏡像輸出（或其他視窗）後會自動顯示即時畫面"
    DEFAULT_INTERVAL = 2.0
    DEFAULT_CONFIDENCE = 0.75
    DEFAULT_IDLE_TAP_XY = (600, 300)
    LOAD_REPOINTS_AUTOSAVE = True
    DEFAULT_WINDOW = "iPhone Mirroring"

    def __init__(self, app, container, emulator_page: Optional[StepScriptPage] = None):
        self.emulator_page = emulator_page
        self.var_window_name = tk.StringVar(value=self.DEFAULT_WINDOW)
        self.var_auto_activate = tk.BooleanVar(value=True)
        self.var_restore_cursor = tk.BooleanVar(value=True)
        super().__init__(app, container)

    def _init_vars(self):
        super()._init_vars()
        if self.emulator_page is not None:   # Telegram 設定預設沿用模擬器頁
            self.var_tg_token.set(self.emulator_page.var_tg_token.get())
            self.var_tg_chat_id.set(self.emulator_page.var_tg_chat_id.get())
        for v in (self.var_window_name, self.var_auto_activate, self.var_restore_cursor):
            v.trace_add("write", lambda *_: self.auto_save_current_config())

    def _create_bot(self) -> GameBot:
        from core.mirror_bot import IPhoneMirrorBot
        return IPhoneMirrorBot(templates_dir=self.storage_dir, logger_func=self.log_message,
                               on_frame_callback=self.on_bot_frame_update)

    def is_connected(self) -> bool:
        return bool(self.bot.window_ctrl.locked_app_name)

    def _build_page_header(self, parent):
        self.build_connection_bar(parent).pack(fill="x", pady=(0, 6))

    def build_connection_bar(self, parent):
        box = W.card(parent)
        inner = W.row(box)
        inner.pack(fill="x", padx=12, pady=8)

        r1 = W.FlowFrame(inner, hgap=6)
        r1.pack(fill="x")
        r1.add(self._build_status_block(r1))
        win = W.row(r1)
        W.label(win, "視窗", bold=True).pack(side="left", padx=(0, 6))
        self.combo_windows = ctk.CTkComboBox(
            win, variable=self.var_window_name, width=170, height=28, corner_radius=6,
            values=[self.DEFAULT_WINDOW, "iPhone鏡像輸出", "QuickTime Player"],
            fg_color=T.COLOR_INPUT_BG, border_color=T.COLOR_INPUT_BORDER, button_color=T.COLOR_INPUT_BORDER,
            font=T.font(11), dropdown_font=T.font(11),
        )
        self.combo_windows.pack(side="left")
        r1.add(win, right=True)
        r1.add(W.button(r1, "鎖定視窗", self.on_lock_window, kind="primary", width=76), right=True)
        r1.add(W.button(r1, "重新整理", self.on_refresh_windows, width=72, bold=False), right=True)

        r2 = W.FlowFrame(inner, hgap=10)
        r2.pack(fill="x", pady=(6, 0))
        self.lbl_win_info = r2.add(ctk.CTkLabel(r2, text="尚未鎖定視窗", font=T.mono(10),
                                                text_color=T.COLOR_TEXT_INFO, height=22))
        r2.add(W.checkbox(r2, "點擊時移到最前景", self.var_auto_activate, height=22), right=True)
        r2.add(W.checkbox(r2, "點擊後游標歸位", self.var_restore_cursor, height=22), right=True)
        return box

    def _extra_toolbar_buttons(self, flow: W.FlowFrame):
        if self.emulator_page is not None:
            flow.add(W.button(flow, "套用模擬器設定", self.on_apply_emulator_config, width=104, bold=False), right=True)

    def on_refresh_windows(self):
        self.log_message("正在搜尋 macOS 前台視窗...")
        names = sorted({w["owner"] for w in self.bot.window_ctrl.get_running_windows() if w.get("owner")})
        if self.DEFAULT_WINDOW not in names:
            names.insert(0, self.DEFAULT_WINDOW)
        self.combo_windows.configure(values=names)
        self.log_message(f"發現 {len(names)} 個前台應用程式視窗。")

    def on_lock_window(self):
        target = self.var_window_name.get().strip() or None
        self.log_message(f"正在鎖定視窗: {target or self.DEFAULT_WINDOW}...")
        if self.bot.connect(target_serial=target):
            self._set_status("已鎖定", T.COLOR_RUNNING)
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            c = self.bot.window_ctrl
            info = f"已鎖定: {c.locked_app_name} (位置 {int(c.win_x)}, {int(c.win_y)} | 尺寸 {int(c.win_w)}×{int(c.win_h)})"
            self.lbl_win_info.configure(text=info)
            self.log_message(info)
            self.on_preview_and_detect()
            if self.var_auto_refresh.get():
                self._schedule_next_refresh()
        else:
            self._set_status("鎖定失敗", T.COLOR_STOPPED)
            self.lbl_win_info.configure(text="找不到指定視窗，請先在 Mac 上開啟「iPhone 鏡像輸出」")
            messagebox.showwarning(
                "未找到視窗",
                "未在 Mac 上找到指定的視窗！\n\n請確認：\n"
                "1. iPhone 已成功與 Mac 建立「iPhone 鏡像輸出」連線。\n"
                "2. 該 App 的視窗沒有被最小化或關閉。",
                parent=self.root)

    def _ensure_connected_for_start(self) -> bool:
        if self.is_connected() or self.bot.connect(target_serial=self.var_window_name.get()):
            return True
        messagebox.showwarning("提示", "請先確認 iPhone 鏡像輸出 App 已開啟並成功鎖定視窗！", parent=self.root)
        return False

    def _before_start(self):
        self.bot.restore_cursor = self.var_restore_cursor.get()
        self.bot.auto_activate = self.var_auto_activate.get()

    def _format_coords(self, rx: int, ry: int) -> str:
        c = self.bot.window_ctrl
        try:
            sx, sy = int(c.win_x + rx / c.scale_x), int(c.win_y + ry / c.scale_y)
            return f"畫面: ({rx}, {ry}) | 螢幕: ({sx}, {sy})"
        except Exception:
            return f"X: {rx}, Y: {ry}"

    def _extra_serialize(self) -> dict:
        return {
            "window_name": self.var_window_name.get(),
            "auto_activate": self.var_auto_activate.get(),
            "restore_cursor": self.var_restore_cursor.get(),
        }

    def _extra_apply(self, cfg: dict):
        if cfg.get("window_name"):
            self.var_window_name.set(str(cfg["window_name"]))
        if "auto_activate" in cfg:
            self.var_auto_activate.set(bool(cfg["auto_activate"]))
        if "restore_cursor" in cfg:
            self.var_restore_cursor.set(bool(cfg["restore_cursor"]))

    def _fallback_configs(self) -> List[str]:
        # 沒有自己的存檔時，沿用模擬器頁的存檔
        paths = []
        if self.emulator_page is not None:
            paths.append(self.emulator_page.auto_save_file)
        paths.append(storage.legacy_autosave_path(self.storage_dir, "emulator", self.instance_id))
        return paths

    def _inherit_initial_config(self) -> bool:
        ep = self.emulator_page
        if ep is None or not (ep.steps.normal or ep.steps.priority):
            return False
        try:
            self.apply_config_dict(self._emulator_config())
            self.log_message("已帶入目前模擬器腳本的步驟設定。")
            return True
        except Exception:
            return False

    def _emulator_config(self) -> dict:
        cfg = dict(self.emulator_page.serialize_current_config())
        for key in ("task_flow", "task_loop_count", "device", "type"):
            cfg.pop(key, None)
        return cfg

    def on_apply_emulator_config(self):
        """把模擬器腳本頁目前的步驟與設定整份帶入本頁。"""
        try:
            self.apply_config_dict(self._emulator_config())
            self.auto_save_current_config()
            self.log_message("已套用模擬器腳本的所有步驟設定。")
            messagebox.showinfo("同步成功", "已將模擬器腳本的步驟、優先動作與辨識模式套用到視窗鏡像腳本。", parent=self.root)
        except Exception as ex:
            self.log_message(f"套用模擬器設定失敗: {ex}")
            messagebox.showerror("錯誤", f"套用模擬器設定失敗: {ex}", parent=self.root)
