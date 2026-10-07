"""
棒球手遊自動化腳本 - 圖形介面
"""
import os
import sys
import time
import threading
import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

import cv2
import numpy as np
from PIL import Image, ImageTk
from bot_core import BaseballBot


# ==========================================
# 常數
# ==========================================
ROI_OPTIONS = ["右下角區域", "右半側螢幕", "下半部區域", "中央區域", "全畫面比對"]
REPEAT_MODES = ["持續連點", "指定次數"]
REPEAT_AREAS = ["右下角區域", "中央區域", "右上角 (Skip)", "右半側中央", "跟隨命中目標", "自訂座標"]
ACTION_OPTIONS = ["點擊詞條", "自訂座標", "右下角區域", "中央區域", "右上角 (Skip)", "右半側中央"]
IDLE_STRATEGIES = ["常規等待", "快速跳過", "自動停止"]

# 每個步驟卡片專屬邊框色 (拖曳時顏色跟著卡片走)
STEP_COLORS = ["#2563eb", "#16a34a", "#d97706", "#dc2626", "#9333ea", "#0891b2"]

DEFAULT_STEPS = [
    dict(name="結算確認", keywords="確認, 確定, 領取, 結算, 結束", delay=3.0, roi_name="右下角區域"),
    dict(name="繼續下一場", keywords="繼續, 下一步, 再來一場, 返回", delay=2.5, roi_name="右下角區域"),
    dict(name="準備比賽", keywords="準備, 挑戰, 出戰, 進入", delay=2.5, roi_name="右半側螢幕"),
    dict(name="開始比賽", keywords="開始, 確定開始, 比賽開始, 開打", delay=4.0, roi_name="右下角區域", repeat_enabled=True),
]

COLOR_OK = "#16a34a"
COLOR_BAD = "#dc2626"
COLOR_IDLE = "#6b7280"
COLOR_WARN = "#d97706"

# 預設 Telegram Bot 設定 (可透過環境變數傳入，或於 GUI 介面中自行輸入)
DEFAULT_TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DEFAULT_TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _num(var, default, cast=float):
    """安全讀取數值變數 (輸入框暫時為空或非數字時回傳預設值)"""
    try:
        return cast(var.get())
    except (tk.TclError, ValueError, TypeError):
        return default


class BaseballBotGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("⚾ 棒球自動刷關")
        self.root.geometry("1200x780")
        self.root.minsize(1000, 640)

        self.config_dir = os.path.dirname(os.path.abspath(__file__))
        self.auto_save_file = os.path.join(self.config_dir, "autosave_last_config.json")

        self.bot = BaseballBot(log_callback=self.log_message, on_frame_callback=self.on_bot_frame_update)
        self.worker_thread = None

        # 預覽狀態
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

        # 變數
        self.var_device = tk.StringVar()
        self.var_status_text = tk.StringVar(value="● 未連線")
        self.var_interval = tk.DoubleVar(value=2.5)
        self.var_confidence = tk.DoubleVar(value=0.65)
        self.var_idle_strategy = tk.StringVar(value=IDLE_STRATEGIES[0])
        self.var_auto_refresh = tk.BooleanVar(value=True)
        self.var_preview_coords = tk.StringVar(value="")
        self.auto_refresh_job = None

        # 看門狗防卡死守護參數 (可於進階面板設定)
        self.var_watchdog_enabled = tk.BooleanVar(value=False)
        self.var_watchdog_seconds = tk.IntVar(value=60)
        self._watchdog_restart_job = None

        # 等待時連點參數 (可於進階面板設定)
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

        self._init_theme()
        self._build_ui()
        self._init_default_steps()
        self.on_refresh_devices()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

    # ==========================================
    # 介面建構
    # ==========================================
    def _init_theme(self):
        style = ttk.Style()
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

    def _build_ui(self):
        self._build_topbar()

        body = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(body)
        right = ttk.PanedWindow(body, orient=tk.VERTICAL)
        body.add(left, weight=1)
        body.add(right, weight=1)

        self._build_steps_panel(left)
        self._build_advanced_panel(left)
        self._build_preview_panel(right)
        self._build_log_panel(right)

    def _build_topbar(self):
        bar = ttk.Frame(self.root, padding=(10, 8, 10, 8))
        bar.pack(fill=tk.X)

        ttk.Label(bar, text="裝置").pack(side=tk.LEFT)
        self.combo_devices = ttk.Combobox(bar, textvariable=self.var_device, width=18, state="readonly")
        self.combo_devices.pack(side=tk.LEFT, padx=(6, 4))
        self.btn_refresh = ttk.Button(bar, text="搜尋", width=5, command=self.on_refresh_devices)
        self.btn_refresh.pack(side=tk.LEFT, padx=(0, 2))
        self.btn_connect = ttk.Button(bar, text="連線", width=5, command=self.on_connect_device)
        self.btn_connect.pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)

        self.btn_start = ttk.Button(bar, text="▶ 開始", width=8, command=self.on_start_bot, state=tk.DISABLED)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 4))
        self.btn_stop = ttk.Button(bar, text="■ 停止", width=8, command=self.on_stop_bot, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT)

        self.lbl_status = tk.Label(bar, textvariable=self.var_status_text, font=("Arial", 12, "bold"), fg=COLOR_BAD)
        self.lbl_status.pack(side=tk.RIGHT)

    def _build_steps_panel(self, parent):
        box = ttk.LabelFrame(parent, text="步驟與優先動作", padding=6)
        box.pack(fill=tk.BOTH, expand=True)

        tools = ttk.Frame(box)
        tools.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(tools, text="⭐ ＋優先", command=self.on_add_priority_step).pack(side=tk.LEFT)
        ttk.Button(tools, text="＋ 步驟", command=self.on_add_empty_step).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(tools, text="範本", width=5, command=self.on_reset_baseball_template).pack(side=tk.RIGHT)
        ttk.Button(tools, text="載入", width=5, command=self.on_load_config_manual).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tools, text="存檔", width=5, command=self.on_save_config_manual).pack(side=tk.RIGHT)

        area = ttk.Frame(box)
        area.pack(fill=tk.BOTH, expand=True)

        self.step_canvas = tk.Canvas(area, borderwidth=0, highlightthickness=0)
        self.step_scrollbar = ttk.Scrollbar(area, orient="vertical", command=self.step_canvas.yview)
        self.step_inner_frame = ttk.Frame(self.step_canvas)
        self.step_canvas_window = self.step_canvas.create_window((0, 0), window=self.step_inner_frame, anchor="nw")
        self.step_canvas.configure(yscrollcommand=self.step_scrollbar.set)

        self.step_inner_frame.bind(
            "<Configure>", lambda e: self.step_canvas.configure(scrollregion=self.step_canvas.bbox("all"))
        )
        self.step_canvas.bind(
            "<Configure>", lambda e: self.step_canvas.itemconfig(self.step_canvas_window, width=e.width)
        )

        self.step_canvas.bind("<Enter>", lambda e: self._set_wheel(True))
        self.step_canvas.bind("<Leave>", self._on_canvas_leave)

        self.step_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.step_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 1. 優先動作區塊
        self.frame_priority_section = ttk.Frame(self.step_inner_frame)
        self.frame_priority_section.pack(fill=tk.X, padx=2, pady=(0, 6))

        hdr_p = tk.Frame(self.frame_priority_section)
        hdr_p.pack(fill=tk.X, pady=(2, 2))
        tk.Label(hdr_p, text="⭐ 優先動作 (依序判定，符合立即中斷)", font=("Arial", 11, "bold"), fg="#b45309").pack(side=tk.LEFT)
        self.lbl_p_count = tk.Label(hdr_p, text="(0)", font=("Arial", 10), fg="#9ca3af")
        self.lbl_p_count.pack(side=tk.LEFT, padx=4)

        self.frame_priority_cards = ttk.Frame(self.frame_priority_section)
        self.frame_priority_cards.pack(fill=tk.X)

        self.lbl_no_priority = tk.Label(
            self.frame_priority_section,
            text="（尚無優先動作，點擊上方「⭐ ＋優先」新增）",
            font=("Arial", 10),
            fg="#9ca3af"
        )
        self.lbl_no_priority.pack(pady=4)

        # 2. 一般步驟區塊
        self.frame_normal_section = ttk.Frame(self.step_inner_frame)
        self.frame_normal_section.pack(fill=tk.X, padx=2, pady=(4, 0))

        hdr_n = tk.Frame(self.frame_normal_section)
        hdr_n.pack(fill=tk.X, pady=(2, 2))
        tk.Label(hdr_n, text="📋 一般步驟 (依序循環執行)", font=("Arial", 11, "bold"), fg="#2563eb").pack(side=tk.LEFT)
        self.lbl_n_count = tk.Label(hdr_n, text="(0)", font=("Arial", 10), fg="#9ca3af")
        self.lbl_n_count.pack(side=tk.LEFT, padx=4)

        self.frame_normal_cards = ttk.Frame(self.frame_normal_section)
        self.frame_normal_cards.pack(fill=tk.X)

    # ==========================================
    # 優先動作卡片元件
    # ==========================================
    def on_add_priority_step(self):
        n = len(self.priority_steps_list) + 1
        self._create_priority_step_widget(name=f"優先 {n}", keywords="", expanded=True)
        self.root.after(50, lambda: self.step_canvas.yview_moveto(0.0))

    def on_delete_priority_step(self, p_step):
        if p_step in self.priority_steps_list:
            p_step["frame"].destroy()
            self.priority_steps_list.remove(p_step)
            self._renumber_priority_steps()
            self.auto_save_current_config()

    def _clear_all_priority_steps(self):
        for p in self.priority_steps_list:
            p["frame"].destroy()
        self.priority_steps_list.clear()
        self._renumber_priority_steps()

    def _renumber_priority_steps(self):
        for i, p in enumerate(self.priority_steps_list, start=1):
            p["lbl_num"].config(text=f"⭐{i}")
        cnt = len(self.priority_steps_list)
        if hasattr(self, "lbl_p_count"):
            self.lbl_p_count.config(text=f"({cnt})")
        if hasattr(self, "lbl_no_priority"):
            if cnt == 0:
                self.lbl_no_priority.pack(pady=4)
            else:
                self.lbl_no_priority.pack_forget()
        self.root.update_idletasks()

    def _create_priority_step_widget(
        self,
        name: str = "優先動作",
        keywords: str = "NEXT SCHEDULE, 確定",
        exclude_keywords: str = "",
        action: str = "點擊字元",
        custom_x: int = 0,
        custom_y: int = 0,
        delay: float = 1.0,
        roi_name: str = "全畫面比對",
        while_condition: bool = True,
        repeat_enabled: bool = False,
        repeat_mode: str = "持續連點",
        repeat_count: int = 15,
        repeat_speed: float = 0.3,
        repeat_area: str = "右下角區域",
        repeat_custom_x: int = 0,
        repeat_custom_y: int = 0,
        tg_enabled: bool = False,
        tg_message: str = "",
        enabled: bool = True,
        expanded: bool = False
    ):
        color = "#f59e0b"
        card = tk.Frame(
            self.frame_priority_cards,
            bg="#fffbeb",
            highlightbackground=color,
            highlightcolor=color,
            highlightthickness=2,
            padx=8,
            pady=6
        )
        card.pack(fill=tk.X, pady=4, padx=4)

        # 舊版設定檔相容
        if action in ("點擊字元", "click_text"):
            action = "點擊詞條"
        elif action in ("custom_coord", "自訂特定區塊"):
            action = "自訂座標"
        elif action not in ACTION_OPTIONS:
            action = "點擊詞條"
        repeat_mode = "指定次數" if ("次數" in str(repeat_mode) or repeat_mode == "count") else "持續連點"
        repeat_area = "自訂座標" if "自訂" in str(repeat_area) else repeat_area
        if repeat_area not in REPEAT_AREAS:
            repeat_area = "右下角區域"
        if roi_name not in ROI_OPTIONS:
            roi_name = "全畫面比對"

        p = {
            "type": "priority",
            "enabled": tk.BooleanVar(value=enabled),
            "name": tk.StringVar(value=name),
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
            "expanded": tk.BooleanVar(value=expanded),
            "frame": card,
        }
        self.priority_steps_list.append(p)

        # 標題列
        head = tk.Frame(card, bg="#fffbeb")
        head.pack(fill=tk.X)

        handle = tk.Label(head, text="⭐", fg=color, bg="#fffbeb", cursor="fleur", font=("Arial", 13, "bold"))
        handle.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Checkbutton(head, variable=p["enabled"]).pack(side=tk.LEFT)
        lbl_num = tk.Label(head, text=f"⭐{len(self.priority_steps_list)}", fg=color, bg="#fffbeb", font=("Arial", 12, "bold"), width=3)
        lbl_num.pack(side=tk.LEFT)
        ttk.Entry(head, textvariable=p["name"], width=10).pack(side=tk.LEFT, padx=(2, 6))

        ttk.Button(head, text="✕", width=2, command=lambda: self.on_delete_priority_step(p)).pack(side=tk.RIGHT)
        btn_toggle = ttk.Button(head, text="▸", width=2, command=lambda: p["expanded"].set(not p["expanded"].get()))
        btn_toggle.pack(side=tk.RIGHT, padx=(4, 2))
        ttk.Entry(head, textvariable=p["keywords"]).pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_sum = tk.Label(card, fg="#92400e", bg="#fffbeb", font=("Arial", 10), anchor="w")

        detail = tk.Frame(card, bg="#fffbeb")

        ra = tk.Frame(detail, bg="#fffbeb")
        ra.pack(fill=tk.X, pady=(6, 0))
        tk.Label(ra, text="動作", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT)
        combo_act = ttk.Combobox(ra, textvariable=p["action"], values=ACTION_OPTIONS, state="readonly", width=10)
        combo_act.pack(side=tk.LEFT, padx=(4, 8))

        box_xy = tk.Frame(ra, bg="#fffbeb")
        tk.Label(box_xy, text="X", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT)
        ttk.Entry(box_xy, textvariable=p["custom_x"], width=5).pack(side=tk.LEFT, padx=(2, 6))
        tk.Label(box_xy, text="Y", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT)
        ttk.Entry(box_xy, textvariable=p["custom_y"], width=5).pack(side=tk.LEFT, padx=(2, 8))

        lbl_roi = tk.Label(ra, text="範圍", bg="#fffbeb", fg="#78350f")
        lbl_roi.pack(side=tk.LEFT)
        combo_roi = ttk.Combobox(ra, textvariable=p["roi"], values=ROI_OPTIONS, state="readonly", width=9)
        combo_roi.pack(side=tk.LEFT, padx=(4, 8))

        def _refresh_priority_act_ui(*_):
            act_val = p["action"].get()
            if act_val in ("自訂座標", "自訂特定區塊"):
                box_xy.pack(side=tk.LEFT, padx=(0, 8), before=lbl_roi)
            else:
                box_xy.pack_forget()

        p["action"].trace_add("write", _refresh_priority_act_ui)
        _refresh_priority_act_ui()

        tk.Label(ra, text="延遲", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT)
        ttk.Spinbox(ra, from_=0.2, to=10.0, increment=0.2, textvariable=p["delay"], width=4).pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(ra, text="秒", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT, padx=(2, 8))

        rc = tk.Frame(detail, bg="#fffbeb")
        rc.pack(fill=tk.X, pady=(4, 0))
        tk.Label(rc, text="🚫 排除", bg="#fffbeb", fg="#dc2626", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        ttk.Entry(rc, textvariable=p["exclude_keywords"]).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        rb = tk.Frame(detail, bg="#fffbeb")
        rb.pack(fill=tk.X, pady=(4, 0))
        ttk.Checkbutton(rb, text="條件持續時重複執行 (while 條件直至字元消失)", variable=p["while_condition"]).pack(side=tk.LEFT)

        rd = tk.Frame(detail, bg="#fffbeb")
        rd.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(rd, text="命中後連點", variable=p["repeat_enabled"]).pack(side=tk.LEFT)

        re = tk.Frame(detail, bg="#fffbeb")
        combo_mode = ttk.Combobox(re, textvariable=p["repeat_mode"], values=REPEAT_MODES, state="readonly", width=7)
        combo_mode.pack(side=tk.LEFT, padx=(22, 8))
        box_count = tk.Frame(re, bg="#fffbeb")
        ttk.Spinbox(box_count, from_=1, to=200, increment=1, textvariable=p["repeat_count"], width=4).pack(side=tk.LEFT)
        tk.Label(box_count, text="次", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(re, text="間隔", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT)
        ttk.Spinbox(re, from_=0.1, to=2.0, increment=0.05, textvariable=p["repeat_speed"], width=4).pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(re, text="秒", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT, padx=(2, 0))

        rf = tk.Frame(detail, bg="#fffbeb")
        tk.Label(rf, text="位置", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT, padx=(22, 4))
        combo_area = ttk.Combobox(rf, textvariable=p["repeat_area"], values=REPEAT_AREAS, state="readonly", width=11)
        combo_area.pack(side=tk.LEFT)
        box_rep_xy = tk.Frame(rf, bg="#fffbeb")
        tk.Label(box_rep_xy, text="X", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT)
        ttk.Entry(box_rep_xy, textvariable=p["repeat_custom_x"], width=5).pack(side=tk.LEFT, padx=(2, 6))
        tk.Label(box_rep_xy, text="Y", bg="#fffbeb", fg="#78350f").pack(side=tk.LEFT)
        ttk.Entry(box_rep_xy, textvariable=p["repeat_custom_y"], width=5).pack(side=tk.LEFT, padx=(2, 0))

        # Telegram 通知列 (動作成功時觸發)
        rg = tk.Frame(detail, bg="#fffbeb")
        rg.pack(fill=tk.X, pady=(4, 0))
        ttk.Checkbutton(rg, text="📱 成功後發送 Telegram 通知", variable=p["tg_enabled"]).pack(side=tk.LEFT)

        rh = tk.Frame(detail, bg="#fffbeb")
        tk.Label(rh, text="訊息內容", bg="#fffbeb", fg="#0284c7", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(22, 4))
        ttk.Entry(rh, textvariable=p["tg_message"]).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def summary() -> str:
            act = p["action"].get()
            if act in ("自訂座標", "自訂特定區塊"):
                act += f" ({p['custom_x'].get()}, {p['custom_y'].get()})"
            parts = [act, p["roi"].get(), f"延遲 {_num(p['delay'], 1.0):g}s"]
            if p["while_condition"].get():
                parts.append("while 重複")
            ex = p["exclude_keywords"].get().strip()
            if ex:
                parts.append(f"排除: {ex}")
            if p["repeat_enabled"].get():
                rep = "連點"
                if p["repeat_mode"].get() == "指定次數":
                    rep += f" ×{_num(p['repeat_count'], 0, int)}"
                area = p["repeat_area"].get()
            if p["tg_enabled"].get():
                parts.append("📱TG通知")
            text = "  ·  ".join(parts)
            return text if p["enabled"].get() else "已停用  ·  " + text

        def refresh(*_):
            exp = p["expanded"].get()
            btn_toggle.config(text="▾" if exp else "▸")
            if exp:
                lbl_sum.pack_forget()
                detail.pack(fill=tk.X)
            else:
                detail.pack_forget()
                lbl_sum.config(text=summary())
                lbl_sum.pack(fill=tk.X, pady=(2, 0))

            if p["action"].get() == "自訂座標":
                box_xy.pack(side=tk.LEFT, after=combo_act, padx=(0, 8))
            else:
                box_xy.pack_forget()

            if p["repeat_enabled"].get():
                re.pack(fill=tk.X, pady=(4, 0), after=rd)
                rf.pack(fill=tk.X, pady=(4, 0), after=re)
            else:
                re.pack_forget()
                rf.pack_forget()

            if p["repeat_mode"].get() == "指定次數":
                box_count.pack(side=tk.LEFT, after=combo_mode, padx=(0, 14))
            else:
                box_count.pack_forget()

            if "自訂" in p["repeat_area"].get():
                box_rep_xy.pack(side=tk.LEFT, after=combo_area, padx=(10, 0))
            else:
                box_rep_xy.pack_forget()

            if p["tg_enabled"].get():
                rh.pack(fill=tk.X, pady=(2, 0), after=rg)
            else:
                rh.pack_forget()

        for key in ("enabled", "expanded", "action", "custom_x", "custom_y", "roi", "delay",
                    "while_condition", "exclude_keywords", "repeat_enabled", "repeat_mode",
                    "repeat_count", "repeat_speed", "repeat_area", "repeat_custom_x", "repeat_custom_y",
                    "tg_enabled", "tg_message"):
            p[key].trace_add("write", refresh)

        p["lbl_num"] = lbl_num
        p["refresh"] = refresh
        self._bind_drag_priority_events(handle, p)
        refresh()
        self._renumber_priority_steps()

    def _bind_drag_priority_events(self, handle, step):
        def on_start(e):
            self._drag_p_data = {"step": step, "y": e.y_root}

        def on_motion(e):
            d = getattr(self, "_drag_p_data", None)
            if not d or d["step"] not in self.priority_steps_list:
                return
            idx = self.priority_steps_list.index(d["step"])
            dy = e.y_root - d["y"]
            h = d["step"]["frame"].winfo_height() or 50
            if dy > h * 0.6 and idx < len(self.priority_steps_list) - 1:
                self.priority_steps_list[idx], self.priority_steps_list[idx + 1] = self.priority_steps_list[idx + 1], self.priority_steps_list[idx]
                self._repack_all_priority_steps()
                d["y"] = e.y_root
            elif dy < -h * 0.6 and idx > 0:
                self.priority_steps_list[idx], self.priority_steps_list[idx - 1] = self.priority_steps_list[idx - 1], self.priority_steps_list[idx]
                self._repack_all_priority_steps()
                d["y"] = e.y_root

        def on_end(e):
            if getattr(self, "_drag_p_data", None):
                self._drag_p_data = None
                self.auto_save_current_config()

        handle.bind("<Button-1>", on_start)
        handle.bind("<B1-Motion>", on_motion)
        handle.bind("<ButtonRelease-1>", on_end)

    def _repack_all_priority_steps(self):
        for p in self.priority_steps_list:
            p["frame"].pack_forget()
        for i, p in enumerate(self.priority_steps_list, start=1):
            p["frame"].pack(fill=tk.X, pady=4, padx=4)
            p["lbl_num"].config(text=f"⭐{i}")
        cnt = len(self.priority_steps_list)
        if hasattr(self, "lbl_p_count"):
            self.lbl_p_count.config(text=f"({cnt})")
        if hasattr(self, "lbl_no_priority"):
            if cnt == 0:
                self.lbl_no_priority.pack(pady=4)
            else:
                self.lbl_no_priority.pack_forget()
        self.root.update_idletasks()

    def _get_active_priority_steps_config(self):
        cfg = []
        for p in self.priority_steps_list:
            kws = [k.strip() for k in p["keywords"].get().replace("，", ",").split(",") if k.strip()]
            ex_kws = [k.strip() for k in p["exclude_keywords"].get().replace("，", ",").split(",") if k.strip()]
            rep_on = p["repeat_enabled"].get()
            cfg.append({
                "type": "priority",
                "name": p["name"].get().strip() or "優先動作",
                "keywords": kws,
                "exclude_keywords": ex_kws,
                "action": "custom_coord" if p["action"].get() in ("自訂座標", "自訂特定區塊") else p["action"].get(),
                "custom_x": _num(p["custom_x"], 0, int),
                "custom_y": _num(p["custom_y"], 0, int),
                "delay": _num(p["delay"], 1.0),
                "roi": self._map_roi_name_to_tuple(p["roi"].get()),
                "roi_name": p["roi"].get(),
                "while_condition": p["while_condition"].get(),
                "repeat_enabled": rep_on,
                "repeat_mode": "count" if p["repeat_mode"].get() == "指定次數" else "until_next",
                "repeat_count": _num(p["repeat_count"], 15, int) if rep_on else 1,
                "repeat_speed": _num(p["repeat_speed"], 0.3),
                "repeat_area": p["repeat_area"].get(),
                "repeat_custom_coord": (_num(p["repeat_custom_x"], 0, int), _num(p["repeat_custom_y"], 0, int)),
                "telegram": {
                    "enabled": p["tg_enabled"].get(),
                    "message": p["tg_message"].get().strip(),
                    "token": self.var_tg_token.get().strip(),
                    "chat_id": self.var_tg_chat_id.get().strip(),
                },
                "enabled": p["enabled"].get() and bool(kws),
                "max_continuous": 25,
            })
        return cfg

    def _build_advanced_panel(self, parent):
        hdr = ttk.Frame(parent)
        hdr.pack(fill=tk.X, pady=(6, 0))
        self.btn_adv = ttk.Button(hdr, text="⚙ 進階 ▸", command=self._toggle_advanced)
        self.btn_adv.pack(side=tk.LEFT)
        self._adv_hdr = hdr

        f = ttk.Frame(parent, padding=(6, 6, 6, 0))
        self.adv_frame = f

        ttk.Label(f, text="掃描間隔(秒)").grid(row=0, column=0, sticky="w", pady=2)
        row_speed = ttk.Frame(f)
        row_speed.grid(row=0, column=1, sticky="w", padx=8)

        def _on_speed_slider_changed(v):
            val = round(float(v), 2)
            self.var_interval.set(val)

        scale_speed = ttk.Scale(
            row_speed, from_=0.0, to=5.0, variable=self.var_interval, orient=tk.HORIZONTAL,
            length=140, command=_on_speed_slider_changed
        )
        scale_speed.pack(side=tk.LEFT, padx=(0, 6))

        ent_speed = ttk.Entry(row_speed, textvariable=self.var_interval, width=5)
        ent_speed.pack(side=tk.LEFT)
        ttk.Label(row_speed, text="秒 (0為極限無延遲)", font=("Arial", 9), foreground="#6b7280").pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(f, text="辨識門檻").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Scale(
            f, from_=0.40, to=0.95, variable=self.var_confidence, orient=tk.HORIZONTAL,
            command=lambda v: self.lbl_conf_val.config(text=f"{float(v):.2f}")
        ).grid(row=1, column=1, sticky="ew", padx=8)
        self.lbl_conf_val = ttk.Label(f, text="0.65", width=5)
        self.lbl_conf_val.grid(row=1, column=2, sticky="w")

        ttk.Label(f, text="找不到時").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Combobox(
            f, textvariable=self.var_idle_strategy, values=IDLE_STRATEGIES, state="readonly", width=10
        ).grid(row=2, column=1, sticky="w", padx=8)

        # 等待中連點跳過設定
        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 4))
        
        row_it = ttk.Frame(f)
        row_it.grid(row=4, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Checkbutton(row_it, text="⏳ 等待時背景連點 (比賽進行中連點跳過)", variable=self.var_idle_tap_enabled).pack(side=tk.LEFT)

        row_it_detail = ttk.Frame(f)
        row_it_detail.grid(row=5, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Label(row_it_detail, text="位置:").pack(side=tk.LEFT)
        combo_it_area = ttk.Combobox(row_it_detail, textvariable=self.var_idle_tap_area, values=REPEAT_AREAS, state="readonly", width=10)
        combo_it_area.pack(side=tk.LEFT, padx=4)

        box_it_xy = ttk.Frame(row_it_detail)
        ttk.Label(box_it_xy, text="X:").pack(side=tk.LEFT)
        ttk.Entry(box_it_xy, textvariable=self.var_idle_tap_custom_x, width=5).pack(side=tk.LEFT, padx=(2, 4))
        ttk.Label(box_it_xy, text="Y:").pack(side=tk.LEFT)
        ttk.Entry(box_it_xy, textvariable=self.var_idle_tap_custom_y, width=5).pack(side=tk.LEFT, padx=(2, 0))

        def _refresh_it_ui(*_):
            if "自訂" in self.var_idle_tap_area.get():
                box_it_xy.pack(side=tk.LEFT, padx=(4, 0))
            else:
                box_it_xy.pack_forget()

        # 看門狗防卡死守護設定 (超時自動停止並重新開啟)
        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=6, column=0, columnspan=3, sticky="ew", pady=(6, 4))

        row_wd = ttk.Frame(f)
        row_wd.grid(row=7, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Checkbutton(row_wd, text="🔄 無動作自動重啟 (防卡死守護)", variable=self.var_watchdog_enabled).pack(side=tk.LEFT)

        row_wd_detail = ttk.Frame(f)
        row_wd_detail.grid(row=8, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Label(row_wd_detail, text="超過").pack(side=tk.LEFT)
        ttk.Spinbox(row_wd_detail, from_=10, to=1800, increment=10, textvariable=self.var_watchdog_seconds, width=5).pack(side=tk.LEFT, padx=4)
        ttk.Label(row_wd_detail, text="秒無動作時，自動停止並重新開啟腳本").pack(side=tk.LEFT)

        # Telegram 通知全域設定
        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=9, column=0, columnspan=3, sticky="ew", pady=(6, 4))

        row_tg_hdr = ttk.Frame(f)
        row_tg_hdr.grid(row=10, column=0, columnspan=3, sticky="w", pady=2)
        tk.Label(row_tg_hdr, text="📱 Telegram 推播通知設定", font=("Arial", 10, "bold"), fg="#0284c7").pack(side=tk.LEFT)
        ttk.Button(row_tg_hdr, text="發送測試訊息", width=12, command=self.on_test_telegram_message).pack(side=tk.RIGHT, padx=4)

        row_tg_1 = ttk.Frame(f)
        row_tg_1.grid(row=11, column=0, columnspan=3, sticky="ew", pady=1)
        ttk.Label(row_tg_1, text="Bot Token:").pack(side=tk.LEFT)
        ttk.Entry(row_tg_1, textvariable=self.var_tg_token, width=28).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        row_tg_2 = ttk.Frame(f)
        row_tg_2.grid(row=12, column=0, columnspan=3, sticky="ew", pady=1)
        ttk.Label(row_tg_2, text="Chat ID:   ").pack(side=tk.LEFT)
        ttk.Entry(row_tg_2, textvariable=self.var_tg_chat_id, width=16).pack(side=tk.LEFT, padx=(4, 0))

        f.columnconfigure(1, weight=1)

    def on_test_telegram_message(self):
        tok = self.var_tg_token.get().strip()
        cid = self.var_tg_chat_id.get().strip()
        if not tok or not cid:
            messagebox.showwarning("提示", "請先輸入 Telegram Bot Token 與 Chat ID")
            return
        self.log_message("📱 正在發送 Telegram 測試通知...")
        success = self.bot.send_telegram_notify(
            token=tok,
            chat_id=cid,
            custom_text="9局職棒狀態通知測試成功！",
            step_name="手動測試"
        )
        if success:
            self.log_message("✅ 測試請求已送出，請檢查 Telegram 聊天室！")

    def _toggle_advanced(self):
        self._adv_open = not self._adv_open
        if self._adv_open:
            self.adv_frame.pack(fill=tk.X, after=self._adv_hdr)
            self.btn_adv.config(text="⚙ 進階 ▾")
        else:
            self.adv_frame.pack_forget()
            self.btn_adv.config(text="⚙ 進階 ▸")

    def _build_preview_panel(self, parent):
        box = ttk.LabelFrame(parent, text="預覽", padding=6)
        parent.add(box, weight=3)

        tools = ttk.Frame(box)
        tools.pack(fill=tk.X)
        self.btn_capture = ttk.Button(tools, text="擷取", width=5, command=self.on_preview_and_detect)
        self.btn_capture.pack(side=tk.LEFT)
        ttk.Checkbutton(
            tools, text="自動刷新", variable=self.var_auto_refresh, command=self.on_toggle_auto_refresh
        ).pack(side=tk.LEFT, padx=8)
        tk.Label(tools, textvariable=self.var_preview_coords, fg="#2563eb", font=("Menlo", 12, "bold")).pack(side=tk.RIGHT)

        # 固定大小容器，避免圖片尺寸變動造成版面跳動
        holder = tk.Frame(box, width=480, height=300)
        holder.pack_propagate(False)
        holder.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        holder.bind("<Configure>", self._on_preview_resize)

        self.lbl_canvas = tk.Label(holder, text="連線後按「擷取」", fg="#9ca3af", cursor="crosshair", anchor=tk.CENTER)
        self.lbl_canvas.pack(fill=tk.BOTH, expand=True)
        self.lbl_canvas.bind("<Motion>", self._on_preview_mouse_move)
        self.lbl_canvas.bind("<Leave>", lambda e: self.var_preview_coords.set(""))
        self.lbl_canvas.bind("<Button-1>", self._on_preview_click)

    def _build_log_panel(self, parent):
        box = ttk.LabelFrame(parent, text="紀錄", padding=6)
        parent.add(box, weight=2)

        tools = ttk.Frame(box)
        tools.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(tools, text="清除", width=5, command=self.on_clear_log).pack(side=tk.RIGHT)
        ttk.Button(tools, text="自檢", width=5, command=self.on_run_diagnostics).pack(side=tk.RIGHT, padx=2)

        self.txt_log = scrolledtext.ScrolledText(box, wrap=tk.WORD, height=8, font=("Menlo", 11), relief=tk.FLAT)
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        self.txt_log.tag_config("err", foreground=COLOR_BAD)
        self.txt_log.tag_config("warn", foreground=COLOR_WARN)
        self.txt_log.tag_config("hit", foreground=COLOR_OK)

    # ==========================================
    # 步驟卡片
    # ==========================================
    def _create_step_widget(
        self,
        name: str,
        keywords: str,
        exclude_keywords: str = "",
        action: str = "點擊詞條",
        custom_x: int = 0,
        custom_y: int = 0,
        delay: float = 2.5,
        enabled: bool = True,
        roi_name: str = "右下角區域",
        repeat_enabled: bool = False,
        repeat_mode: str = "持續連點",
        repeat_count: int = 15,
        repeat_speed: float = 0.3,
        repeat_area: str = "右下角區域",
        repeat_custom_x: int = 0,
        repeat_custom_y: int = 0,
        timeout_enabled: bool = False,
        timeout_seconds: int = 15,
        tg_enabled: bool = False,
        tg_message: str = "",
        expanded: bool = False
    ):
        """建立步驟卡片：平時只顯示名稱與關鍵字，展開後才顯示細部設定"""
        color = STEP_COLORS[len(self.steps_list) % len(STEP_COLORS)]

        # 舊版設定檔相容
        if action in ("點擊字元", "click_text"):
            action = "點擊詞條"
        elif action in ("custom_coord", "自訂特定區塊"):
            action = "自訂座標"
        elif action not in ACTION_OPTIONS:
            action = "點擊詞條"
        repeat_mode = "指定次數" if ("次數" in str(repeat_mode) or repeat_mode == "count") else "持續連點"
        repeat_area = "自訂座標" if "自訂" in str(repeat_area) else repeat_area
        if repeat_area not in REPEAT_AREAS:
            repeat_area = "右下角區域"
        if roi_name not in ROI_OPTIONS:
            roi_name = "右下角區域"

        card = tk.Frame(
            self.frame_normal_cards, highlightbackground=color, highlightcolor=color,
            highlightthickness=3, padx=8, pady=6
        )
        card.pack(fill=tk.X, pady=4, padx=4)

        s = {
            "enabled": tk.BooleanVar(value=enabled),
            "name": tk.StringVar(value=name),
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
            "expanded": tk.BooleanVar(value=expanded),
            "frame": card,
            "border_color": color,
        }
        self.steps_list.append(s)

        # ---- 標題列 (永遠顯示) ----
        head = tk.Frame(card)
        head.pack(fill=tk.X)

        handle = tk.Label(head, text="☰", fg=color, cursor="fleur", font=("Arial", 14, "bold"))
        handle.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Checkbutton(head, variable=s["enabled"]).pack(side=tk.LEFT)
        lbl_num = tk.Label(head, text=str(len(self.steps_list)), fg=color, font=("Arial", 13, "bold"), width=2)
        lbl_num.pack(side=tk.LEFT)
        ttk.Entry(head, textvariable=s["name"], width=11).pack(side=tk.LEFT, padx=(2, 6))

        ttk.Button(head, text="✕", width=2, command=lambda: self.on_delete_step(s)).pack(side=tk.RIGHT)
        btn_toggle = ttk.Button(head, text="▸", width=2, command=lambda: s["expanded"].set(not s["expanded"].get()))
        btn_toggle.pack(side=tk.RIGHT, padx=(4, 2))
        ttk.Entry(head, textvariable=s["keywords"]).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ---- 收合時的摘要 ----
        lbl_sum = tk.Label(card, fg="#9ca3af", font=("Arial", 11), anchor="w")

        # ---- 展開後的細部設定 ----
        detail = tk.Frame(card)

        ra = tk.Frame(detail)
        ra.pack(fill=tk.X, pady=(8, 0))

        ttk.Label(ra, text="動作").pack(side=tk.LEFT)
        combo_act = ttk.Combobox(ra, textvariable=s["action"], values=ACTION_OPTIONS, state="readonly", width=10)
        combo_act.pack(side=tk.LEFT, padx=(4, 8))

        box_act_xy = tk.Frame(ra)
        ttk.Label(box_act_xy, text="X").pack(side=tk.LEFT)
        ttk.Entry(box_act_xy, textvariable=s["custom_x"], width=5).pack(side=tk.LEFT, padx=(2, 6))
        ttk.Label(box_act_xy, text="Y").pack(side=tk.LEFT)
        ttk.Entry(box_act_xy, textvariable=s["custom_y"], width=5).pack(side=tk.LEFT, padx=(2, 8))

        lbl_step_roi = ttk.Label(ra, text="範圍")
        lbl_step_roi.pack(side=tk.LEFT)
        combo_roi = ttk.Combobox(ra, textvariable=s["roi"], values=ROI_OPTIONS, state="readonly", width=9)
        combo_roi.pack(side=tk.LEFT, padx=(4, 14))
        combo_roi.bind("<<ComboboxSelected>>", lambda e: self.on_step_roi_changed())

        def _refresh_step_act_ui(*_):
            act_val = s["action"].get()
            if act_val in ("自訂座標", "自訂特定區塊"):
                box_act_xy.pack(side=tk.LEFT, padx=(0, 8), before=lbl_step_roi)
            else:
                box_act_xy.pack_forget()

        s["action"].trace_add("write", _refresh_step_act_ui)
        _refresh_step_act_ui()

        ttk.Label(ra, text="延遲").pack(side=tk.LEFT)
        ttk.Spinbox(ra, from_=0.5, to=15.0, increment=0.5, textvariable=s["delay"], width=4).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(ra, text="秒").pack(side=tk.LEFT, padx=(2, 14))
        chk_timeout = ttk.Checkbutton(ra, text="逾時跳過", variable=s["timeout_enabled"])
        chk_timeout.pack(side=tk.LEFT)
        box_timeout = tk.Frame(ra)
        ttk.Spinbox(box_timeout, from_=3, to=300, increment=1, textvariable=s["timeout_seconds"], width=4).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(box_timeout, text="秒").pack(side=tk.LEFT, padx=(2, 0))

        re = tk.Frame(detail)
        re.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(re, text="🚫 排除").pack(side=tk.LEFT)
        ttk.Entry(re, textvariable=s["exclude_keywords"]).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        rb = tk.Frame(detail)
        rb.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(rb, text="命中後連點", variable=s["repeat_enabled"]).pack(side=tk.LEFT)

        rc = tk.Frame(detail)
        combo_mode = ttk.Combobox(rc, textvariable=s["repeat_mode"], values=REPEAT_MODES, state="readonly", width=7)
        combo_mode.pack(side=tk.LEFT, padx=(22, 8))
        box_count = tk.Frame(rc)
        ttk.Spinbox(box_count, from_=1, to=200, increment=1, textvariable=s["repeat_count"], width=4).pack(side=tk.LEFT)
        ttk.Label(box_count, text="次").pack(side=tk.LEFT, padx=(2, 0))
        ttk.Label(rc, text="間隔").pack(side=tk.LEFT)
        ttk.Spinbox(rc, from_=0.1, to=2.0, increment=0.05, textvariable=s["repeat_speed"], width=4).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(rc, text="秒").pack(side=tk.LEFT, padx=(2, 0))

        rd = tk.Frame(detail)
        ttk.Label(rd, text="位置").pack(side=tk.LEFT, padx=(22, 4))
        combo_area = ttk.Combobox(rd, textvariable=s["repeat_area"], values=REPEAT_AREAS, state="readonly", width=11)
        combo_area.pack(side=tk.LEFT)
        box_xy = tk.Frame(rd)
        ttk.Label(box_xy, text="X").pack(side=tk.LEFT)
        ttk.Entry(box_xy, textvariable=s["repeat_custom_x"], width=5).pack(side=tk.LEFT, padx=(2, 6))
        ttk.Label(box_xy, text="Y").pack(side=tk.LEFT)
        ttk.Entry(box_xy, textvariable=s["repeat_custom_y"], width=5).pack(side=tk.LEFT, padx=(2, 0))

        # Telegram 通知列 (動作成功時觸發)
        rtg = tk.Frame(detail)
        rtg.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(rtg, text="📱 成功後發送 Telegram 通知", variable=s["tg_enabled"]).pack(side=tk.LEFT)

        rtg_msg = tk.Frame(detail)
        tk.Label(rtg_msg, text="訊息內容", fg="#0284c7", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(22, 4))
        ttk.Entry(rtg_msg, textvariable=s["tg_message"]).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def summary() -> str:
            act = s["action"].get()
            if act in ("自訂座標", "自訂特定區塊"):
                act += f" ({s['custom_x'].get()}, {s['custom_y'].get()})"
            parts = [act, s["roi"].get(), f"延遲 {_num(s['delay'], 0):g}s"]
            ex = s["exclude_keywords"].get().strip()
            if ex:
                parts.append(f"排除: {ex}")
            if s["repeat_enabled"].get():
                rep = "連點"
                if s["repeat_mode"].get() == "指定次數":
                    rep += f" ×{_num(s['repeat_count'], 0, int)}"
                area = s["repeat_area"].get()
                if area == "自訂座標":
                    area = f"({_num(s['repeat_custom_x'], 0, int)}, {_num(s['repeat_custom_y'], 0, int)})"
                parts.append(f"{rep} @ {area}")
            if s["timeout_enabled"].get():
                parts.append(f"{_num(s['timeout_seconds'], 0, int)}s 未命中跳過")
            if s["tg_enabled"].get():
                parts.append("📱TG通知")
            text = "  ·  ".join(parts)
            return text if s["enabled"].get() else "已停用  ·  " + text

        def refresh(*_):
            exp = s["expanded"].get()
            btn_toggle.config(text="▾" if exp else "▸")
            if exp:
                lbl_sum.pack_forget()
                detail.pack(fill=tk.X)
            else:
                detail.pack_forget()
                lbl_sum.config(text=summary())
                lbl_sum.pack(fill=tk.X, pady=(4, 0))

            if s["timeout_enabled"].get():
                box_timeout.pack(side=tk.LEFT, after=chk_timeout)
            else:
                box_timeout.pack_forget()

            if s["repeat_enabled"].get():
                rc.pack(fill=tk.X, pady=(4, 0), after=rb)
                rd.pack(fill=tk.X, pady=(4, 0), after=rc)
            else:
                rc.pack_forget()
                rd.pack_forget()

            if s["repeat_mode"].get() == "指定次數":
                box_count.pack(side=tk.LEFT, after=combo_mode, padx=(0, 14))
            else:
                box_count.pack_forget()

            if "自訂" in s["repeat_area"].get():
                box_xy.pack(side=tk.LEFT, after=combo_area, padx=(10, 0))
            else:
                box_xy.pack_forget()

            if s["tg_enabled"].get():
                rtg_msg.pack(fill=tk.X, pady=(2, 0), after=rtg)
            else:
                rtg_msg.pack_forget()

        for key in ("enabled", "expanded", "action", "custom_x", "custom_y", "roi", "delay", "timeout_enabled", "timeout_seconds",
                    "repeat_enabled", "repeat_mode", "repeat_count", "repeat_area",
                    "repeat_custom_x", "repeat_custom_y", "exclude_keywords",
                    "tg_enabled", "tg_message"):
            s[key].trace_add("write", refresh)

        s["lbl_num"] = lbl_num
        s["lbl_drag"] = handle
        s["refresh"] = refresh
        self._bind_drag_events(handle, s)
        refresh()

    def _bind_drag_events(self, handle, step):
        def on_start(e):
            self._drag_data = {"step": step, "y": e.y_root}

        def on_motion(e):
            d = getattr(self, "_drag_data", None)
            if not d or d["step"] not in self.steps_list:
                return
            idx = self.steps_list.index(d["step"])
            dy = e.y_root - d["y"]
            h = d["step"]["frame"].winfo_height() or 60
            if dy > h * 0.6 and idx < len(self.steps_list) - 1:
                self.steps_list[idx], self.steps_list[idx + 1] = self.steps_list[idx + 1], self.steps_list[idx]
                self._repack_all_steps()
                d["y"] = e.y_root
            elif dy < -h * 0.6 and idx > 0:
                self.steps_list[idx], self.steps_list[idx - 1] = self.steps_list[idx - 1], self.steps_list[idx]
                self._repack_all_steps()
                d["y"] = e.y_root

        def on_end(e):
            if getattr(self, "_drag_data", None):
                self._drag_data = None
                self.auto_save_current_config()

        handle.bind("<Button-1>", on_start)
        handle.bind("<B1-Motion>", on_motion)
        handle.bind("<ButtonRelease-1>", on_end)

    def _repack_all_steps(self):
        """依目前順序重新排列卡片，顏色跟著卡片，只更新編號"""
        for s in self.steps_list:
            s["frame"].pack_forget()
        for i, s in enumerate(self.steps_list, start=1):
            s["frame"].pack(fill=tk.X, pady=4, padx=4)
            s["lbl_num"].config(text=str(i))
        if hasattr(self, "lbl_n_count"):
            self.lbl_n_count.config(text=f"({len(self.steps_list)})")
        self.root.update_idletasks()

    def _renumber_steps(self):
        self._repack_all_steps()

    def _set_wheel(self, on: bool):
        if on:
            self.root.bind_all("<MouseWheel>", self._on_mousewheel)
            self.root.bind_all("<Button-4>", self._on_mousewheel)
            self.root.bind_all("<Button-5>", self._on_mousewheel)
        else:
            self.root.unbind_all("<MouseWheel>")
            self.root.unbind_all("<Button-4>")
            self.root.unbind_all("<Button-5>")

    def _on_canvas_leave(self, _e):
        # 滑進卡片子元件也會觸發 Leave，確認游標真的離開步驟區才解除
        x, y = self.root.winfo_pointerxy()
        w = self.root.winfo_containing(x, y)
        if w is None or not str(w).startswith(str(self.step_canvas)):
            self._set_wheel(False)

    def _on_mousewheel(self, e):
        c = self.step_canvas
        bbox = c.bbox("all")
        if not bbox or bbox[3] <= c.winfo_height():
            return
        if getattr(e, "num", None) == 4:
            d = -1
        elif getattr(e, "num", None) == 5:
            d = 1
        elif sys.platform == "darwin":
            d = -e.delta if abs(e.delta) < 120 else -e.delta // 120
        else:
            d = -e.delta // 120
        c.yview_scroll(int(d), "units")

    def on_add_empty_step(self):
        n = len(self.steps_list) + 1
        self._create_step_widget(name=f"步驟 {n}", keywords="", expanded=True)
        self.root.after(50, lambda: self.step_canvas.yview_moveto(1.0))

    def on_delete_step(self, step):
        if len(self.steps_list) <= 1 and not self.priority_steps_list:
            messagebox.showwarning("提示", "至少保留一個步驟或優先動作")
            return
        if step in self.steps_list:
            step["frame"].destroy()
            self.steps_list.remove(step)
            self._renumber_steps()
            self.auto_save_current_config()

    def _clear_all_steps(self):
        for s in self.steps_list:
            s["frame"].destroy()
        self.steps_list.clear()
        self._renumber_steps()

    def _load_default_steps(self):
        for d in DEFAULT_STEPS:
            self._create_step_widget(**d)

    def _map_roi_name_to_tuple(self, roi_name: str):
        """範圍名稱 -> (ymin, xmin, ymax, xmax) 比例"""
        return {
            "右下角區域": (0.45, 0.45, 1.0, 1.0),
            "右半側螢幕": (0.0, 0.45, 1.0, 1.0),
            "下半部區域": (0.50, 0.0, 1.0, 1.0),
            "中央區域": (0.25, 0.25, 0.75, 0.75),
        }.get(roi_name, (0.0, 0.0, 1.0, 1.0))

    def _get_active_steps_config(self):
        """把介面上的步驟轉成 bot_core 用的設定"""
        cfg = []
        for s in self.steps_list:
            kws = [k.strip() for k in s["keywords"].get().replace("，", ",").split(",") if k.strip()]
            ex_kws = [k.strip() for k in s["exclude_keywords"].get().replace("，", ",").split(",") if k.strip()]
            delay = _num(s["delay"], 2.5)
            rep_on = s["repeat_enabled"].get()
            cfg.append({
                "name": s["name"].get().strip() or "步驟",
                "keywords": kws,
                "exclude_keywords": ex_kws,
                "action": "custom_coord" if s["action"].get() in ("自訂座標", "自訂特定區塊") else s["action"].get(),
                "custom_x": _num(s["custom_x"], 0, int),
                "custom_y": _num(s["custom_y"], 0, int),
                "delay": delay,
                "delay_min": max(0.05, delay - 0.15),
                "delay_max": delay + 0.15,
                "enabled": s["enabled"].get() and bool(kws),
                "roi": self._map_roi_name_to_tuple(s["roi"].get()),
                "roi_name": s["roi"].get(),
                "repeat_enabled": rep_on,
                "repeat_mode": "count" if s["repeat_mode"].get() == "指定次數" else "until_next",
                "repeat_count": _num(s["repeat_count"], 15, int) if rep_on else 1,
                "repeat_speed": _num(s["repeat_speed"], 0.3),
                "repeat_area": s["repeat_area"].get(),
                "repeat_custom_coord": (_num(s["repeat_custom_x"], 0, int), _num(s["repeat_custom_y"], 0, int)),
                "timeout_enabled": s["timeout_enabled"].get(),
                "timeout_seconds": _num(s["timeout_seconds"], 15, int),
                "telegram": {
                    "enabled": s["tg_enabled"].get(),
                    "message": s["tg_message"].get().strip(),
                    "token": self.var_tg_token.get().strip(),
                    "chat_id": self.var_tg_chat_id.get().strip(),
                },
            })
        return cfg

    # ==========================================
    # 設定檔
    # ==========================================
    def serialize_current_config(self) -> dict:
        priority_steps = []
        for p in self.priority_steps_list:
            priority_steps.append({
                "name": p["name"].get(),
                "keywords": p["keywords"].get(),
                "exclude_keywords": p["exclude_keywords"].get(),
                "action": p["action"].get(),
                "custom_x": _num(p["custom_x"], 0, int),
                "custom_y": _num(p["custom_y"], 0, int),
                "delay": _num(p["delay"], 1.0),
                "roi": p["roi"].get(),
                "while_condition": p["while_condition"].get(),
                "repeat_enabled": p["repeat_enabled"].get(),
                "repeat_mode": p["repeat_mode"].get(),
                "repeat_count": _num(p["repeat_count"], 15, int),
                "repeat_speed": _num(p["repeat_speed"], 0.3),
                "repeat_area": p["repeat_area"].get(),
                "repeat_custom_x": _num(p["repeat_custom_x"], 0, int),
                "repeat_custom_y": _num(p["repeat_custom_y"], 0, int),
                "tg_enabled": p["tg_enabled"].get(),
                "tg_message": p["tg_message"].get().strip(),
                "enabled": p["enabled"].get(),
            })

        steps = []
        for s in self.steps_list:
            steps.append({
                "name": s["name"].get(),
                "keywords": s["keywords"].get(),
                "exclude_keywords": s["exclude_keywords"].get(),
                "action": s["action"].get(),
                "custom_x": _num(s["custom_x"], 0, int),
                "custom_y": _num(s["custom_y"], 0, int),
                "delay": _num(s["delay"], 2.5),
                "enabled": s["enabled"].get(),
                "roi": s["roi"].get(),
                "repeat_enabled": s["repeat_enabled"].get(),
                "repeat_mode": s["repeat_mode"].get(),
                "repeat_count": _num(s["repeat_count"], 15, int),
                "repeat_speed": _num(s["repeat_speed"], 0.3),
                "repeat_area": s["repeat_area"].get(),
                "repeat_custom_x": _num(s["repeat_custom_x"], 0, int),
                "repeat_custom_y": _num(s["repeat_custom_y"], 0, int),
                "timeout_enabled": s["timeout_enabled"].get(),
                "timeout_seconds": _num(s["timeout_seconds"], 15, int),
                "tg_enabled": s["tg_enabled"].get(),
                "tg_message": s["tg_message"].get().strip(),
            })
        return {
            "version": "1.0",
            "interval": _num(self.var_interval, 2.5),
            "confidence": _num(self.var_confidence, 0.65),
            "idle_strategy": self.var_idle_strategy.get(),
            "auto_refresh": bool(self.var_auto_refresh.get()),
            "watchdog": {
                "enabled": bool(self.var_watchdog_enabled.get()),
                "seconds": _num(self.var_watchdog_seconds, 60, int),
            },
            "telegram_global": {
                "token": self.var_tg_token.get().strip(),
                "chat_id": self.var_tg_chat_id.get().strip(),
            },
            "idle_tap": {
                "enabled": self.var_idle_tap_enabled.get(),
                "area": self.var_idle_tap_area.get(),
                "times": _num(self.var_idle_tap_times, 3, int),
                "interval": _num(self.var_idle_tap_interval, 0.4),
                "custom_x": _num(self.var_idle_tap_custom_x, 983, int),
                "custom_y": _num(self.var_idle_tap_custom_y, 1023, int),
            },
            "priority_steps": priority_steps,
            "steps": steps,
        }

    def apply_config_dict(self, cfg: dict):
        if "interval" in cfg:
            self.var_interval.set(float(cfg["interval"]))
        if "confidence" in cfg:
            self.var_confidence.set(cfg["confidence"])
            self.lbl_conf_val.config(text=f"{float(cfg['confidence']):.2f}")
        if "idle_strategy" in cfg:
            v = str(cfg["idle_strategy"])
            self.var_idle_strategy.set("快速跳過" if "跳過" in v else "自動停止" if "停止" in v else "常規等待")
        if "auto_refresh" in cfg:
            self.var_auto_refresh.set(bool(cfg["auto_refresh"]))
        if "watchdog" in cfg and isinstance(cfg["watchdog"], dict):
            wd = cfg["watchdog"]
            self.var_watchdog_enabled.set(bool(wd.get("enabled", False)))
            self.var_watchdog_seconds.set(int(wd.get("seconds", 60)))
        if "idle_tap" in cfg and isinstance(cfg["idle_tap"], dict):
            it = cfg["idle_tap"]
            self.var_idle_tap_enabled.set(it.get("enabled", False))
            self.var_idle_tap_area.set(it.get("area", "自訂座標" if "custom_x" in it else "右下角區域"))
            self.var_idle_tap_times.set(it.get("times", 3))
            self.var_idle_tap_interval.set(it.get("interval", 0.4))
            self.var_idle_tap_custom_x.set(it.get("custom_x", 983))
            self.var_idle_tap_custom_y.set(it.get("custom_y", 1023))

        if "telegram_global" in cfg and isinstance(cfg["telegram_global"], dict):
            tg_g = cfg["telegram_global"]
            self.var_tg_token.set(tg_g.get("token", DEFAULT_TG_TOKEN))
            self.var_tg_chat_id.set(tg_g.get("chat_id", DEFAULT_TG_CHAT_ID))

        # 載入優先動作清單 (支援向下相容單一 priority 物件)
        self._clear_all_priority_steps()
        p_list = cfg.get("priority_steps")
        if p_list is None and "priority" in cfg and isinstance(cfg["priority"], dict):
            p_old = cfg["priority"]
            if p_old.get("keywords") or p_old.get("enabled"):
                p_list = [{
                    "name": "優先 1",
                    "keywords": p_old.get("keywords", ""),
                    "exclude_keywords": p_old.get("exclude_keywords", ""),
                    "action": p_old.get("action", "點擊字元"),
                    "custom_x": p_old.get("custom_x", 0),
                    "custom_y": p_old.get("custom_y", 0),
                    "delay": p_old.get("delay", 1.0),
                    "roi": "全畫面比對",
                    "while_condition": True,
                    "repeat_enabled": False,
                    "repeat_mode": "持續連點",
                    "repeat_count": 15,
                    "repeat_speed": 0.3,
                    "repeat_area": "右下角區域",
                    "repeat_custom_x": 0,
                    "repeat_custom_y": 0,
                    "tg_enabled": False,
                    "tg_message": "",
                    "enabled": p_old.get("enabled", True),
                }]

        if isinstance(p_list, list):
            for p in p_list:
                self._create_priority_step_widget(
                    name=p.get("name", "優先動作"),
                    keywords=p.get("keywords", ""),
                    exclude_keywords=p.get("exclude_keywords", ""),
                    action=p.get("action", "點擊字元"),
                    custom_x=p.get("custom_x", 0),
                    custom_y=p.get("custom_y", 0),
                    delay=p.get("delay", 1.0),
                    roi_name=p.get("roi", "全畫面比對"),
                    while_condition=p.get("while_condition", True),
                    repeat_enabled=p.get("repeat_enabled", False),
                    repeat_mode=p.get("repeat_mode", "持續連點"),
                    repeat_count=p.get("repeat_count", 15),
                    repeat_speed=p.get("repeat_speed", 0.3),
                    repeat_area=p.get("repeat_area", "右下角區域"),
                    repeat_custom_x=p.get("repeat_custom_x", 0),
                    repeat_custom_y=p.get("repeat_custom_y", 0),
                    tg_enabled=p.get("tg_enabled", p.get("telegram", {}).get("enabled", False) if isinstance(p.get("telegram"), dict) else False),
                    tg_message=p.get("tg_message", p.get("telegram", {}).get("message", "") if isinstance(p.get("telegram"), dict) else ""),
                    enabled=p.get("enabled", True),
                    expanded=False,
                )

        if isinstance(cfg.get("steps"), list) and cfg["steps"]:
            self._clear_all_steps()
            for s in cfg["steps"]:
                self._create_step_widget(
                    name=s.get("name", "步驟"),
                    keywords=s.get("keywords", ""),
                    exclude_keywords=s.get("exclude_keywords", ""),
                    action=s.get("action", "點擊詞條"),
                    custom_x=s.get("custom_x", 0),
                    custom_y=s.get("custom_y", 0),
                    delay=s.get("delay", 2.5),
                    enabled=s.get("enabled", True),
                    roi_name=s.get("roi", "右下角區域"),
                    repeat_enabled=s.get("repeat_enabled", False),
                    repeat_mode=s.get("repeat_mode", "持續連點"),
                    repeat_count=s.get("repeat_count", 15),
                    repeat_speed=s.get("repeat_speed", 0.3),
                    repeat_area=s.get("repeat_area", "右下角區域"),
                    repeat_custom_x=s.get("repeat_custom_x", 0),
                    repeat_custom_y=s.get("repeat_custom_y", 0),
                    timeout_enabled=s.get("timeout_enabled", False),
                    timeout_seconds=s.get("timeout_seconds", 15),
                    tg_enabled=s.get("tg_enabled", s.get("telegram", {}).get("enabled", False) if isinstance(s.get("telegram"), dict) else False),
                    tg_message=s.get("tg_message", s.get("telegram", {}).get("message", "") if isinstance(s.get("telegram"), dict) else ""),
                )
            self._renumber_steps()

    def auto_save_current_config(self):
        try:
            with open(self.auto_save_file, "w", encoding="utf-8") as f:
                json.dump(self.serialize_current_config(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_message(f"⚠️ 自動存檔失敗: {e}")

    def auto_load_last_config(self) -> bool:
        if not os.path.exists(self.auto_save_file):
            return False
        try:
            with open(self.auto_save_file, "r", encoding="utf-8") as f:
                self.apply_config_dict(json.load(f))
            return bool(self.steps_list or self.priority_steps_list)
        except Exception as e:
            self.log_message(f"⚠️ 讀取上次設定失敗: {e}")
            return False

    def on_save_config_manual(self):
        configs_dir = os.path.join(self.config_dir, "configs")
        os.makedirs(configs_dir, exist_ok=True)
        path = filedialog.asksaveasfilename(
            initialdir=configs_dir, title="存檔", defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("所有檔案", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.serialize_current_config(), f, ensure_ascii=False, indent=2)
            self.auto_save_current_config()
            self.log_message(f"已存檔: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("存檔失敗", str(e))

    def on_load_config_manual(self):
        configs_dir = os.path.join(self.config_dir, "configs")
        os.makedirs(configs_dir, exist_ok=True)
        path = filedialog.askopenfilename(
            initialdir=configs_dir, title="載入", filetypes=[("JSON", "*.json"), ("所有檔案", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.apply_config_dict(json.load(f))
            self.auto_save_current_config()
            self.log_message(f"已載入: {os.path.basename(path)}")
            self.on_step_roi_changed()
        except Exception as e:
            messagebox.showerror("載入失敗", str(e))

    def _init_default_steps(self):
        # 1. 優先載入上次自動存檔
        if self.auto_load_last_config():
            return

        # 2. 初次使用時自動載入 configs/league_default.json
        preset_file = os.path.join(self.config_dir, "configs", "league_default.json")
        if os.path.exists(preset_file):
            try:
                with open(preset_file, "r", encoding="utf-8") as f:
                    self.apply_config_dict(json.load(f))
                self.auto_save_current_config()
                self.log_message("已預先載入預設聯賽自動刷關設定 (league_default.json)")
                return
            except Exception as e:
                self.log_message(f"載入預設範本失敗: {e}")

        # 3. 備援預設設定
        self._create_priority_step_widget(
            name="快速結算",
            keywords="NEXT SCHEDULE, SCHEDULE",
            action="點擊字元",
            delay=1.0,
            while_condition=True,
            enabled=True
        )
        self._load_default_steps()

    def on_reset_baseball_template(self):
        if messagebox.askyesno("範本", "清除目前設定並套用預設「自動聯賽」範本？"):
            self._clear_all_priority_steps()
            self._clear_all_steps()
            preset_file = os.path.join(self.config_dir, "configs", "league_default.json")
            if os.path.exists(preset_file):
                try:
                    with open(preset_file, "r", encoding="utf-8") as f:
                        self.apply_config_dict(json.load(f))
                    self.auto_save_current_config()
                    self.log_message("已套用預設聯賽範本 (league_default.json)")
                    return
                except Exception as e:
                    self.log_message(f"套用範本失敗: {e}")

            self._create_priority_step_widget(
                name="快速結算",
                keywords="NEXT SCHEDULE, SCHEDULE",
                action="點擊字元",
                delay=1.0,
                while_condition=True,
                enabled=True
            )
            self._load_default_steps()
            self._renumber_steps()
            self.auto_save_current_config()

    # ==========================================
    # 日誌與狀態
    # ==========================================
    def log_message(self, text: str):
        def _append():
            msg = text if text[:2].isdigit() else time.strftime("%H:%M:%S ") + text
            msg = msg.replace(" [INFO] ", " ")
            if "[ERROR]" in msg or "❌" in msg:
                tags = ("err",)
            elif "[WARNING]" in msg or "⚠️" in msg or "⏩" in msg or "🚨" in msg:
                tags = ("warn",)
            elif "🎯" in msg:
                tags = ("hit",)
            else:
                tags = ()
            self.txt_log.insert(tk.END, msg + "\n", tags)
            # 只保留最近約 800 行
            lines = int(self.txt_log.index("end-1c").split(".")[0])
            if lines > 800:
                self.txt_log.delete("1.0", f"{lines - 600}.0")
            self.txt_log.see(tk.END)
        self.root.after(0, _append)

    def on_clear_log(self):
        self.txt_log.delete("1.0", tk.END)

    def _set_status(self, text: str, color: str):
        self.var_status_text.set(text)
        self.lbl_status.config(fg=color)

    # ==========================================
    # 連線
    # ==========================================
    def on_refresh_devices(self):
        devices = self.bot.get_devices_list()
        self.combo_devices["values"] = devices
        if devices:
            self.combo_devices.current(0)
            self.log_message(f"找到裝置: {', '.join(devices)}")
            if not self.bot.device:
                self._set_status("● 未連線", COLOR_WARN)
        else:
            self.combo_devices.set("")
            self.log_message("⚠️ 找不到模擬器，請先開啟模擬器再按「搜尋」")
            self._set_status("● 找不到裝置", COLOR_BAD)

    def on_connect_device(self):
        target = self.var_device.get().strip() or None
        if self.bot.connect(target_serial=target):
            self._set_status(f"● 已連線  {self.bot.device.serial}", COLOR_OK)
            self.btn_start.configure(state=tk.NORMAL)
            self._capture_async(announce=True)
            if self.var_auto_refresh.get() and not self.auto_refresh_job:
                self._schedule_next_refresh(delay_ms=600)
        else:
            self._set_status("● 連線失敗", COLOR_BAD)
            messagebox.showerror("連線失敗", "無法連線模擬器，請確認模擬器已完全開機。")

    def _sync_bot_roi(self):
        self.bot.confidence_threshold = _num(self.var_confidence, 0.65)
        # 整張截圖都做 OCR，由各步驟自己的範圍過濾
        self.bot.roi = None

    # ==========================================
    # 預覽
    # ==========================================
    def on_preview_and_detect(self):
        if not self.bot.device:
            messagebox.showwarning("提示", "請先連線模擬器")
            return
        if self.bot.is_running:
            return
        self._capture_async(announce=True)

    def _capture_async(self, announce: bool = False, on_done=None):
        """背景擷取 + OCR，完成後回主執行緒繪製 (不卡介面)"""
        if self._capturing:
            if on_done:
                self.root.after(500, on_done)
            return
        self._capturing = True
        self._sync_bot_roi()
        steps = self._get_active_steps_config()

        def work():
            screen, detected, matched, err = None, None, None, None
            try:
                screen = self.bot.capture_screen()
                if screen is not None:
                    h, w = screen.shape[:2]
                    detected = self.bot.scan_text(screen)
                    p_steps = self._get_active_priority_steps_config()
                    matched = None
                    p_best = self.bot.match_all_priority_steps(detected, p_steps, screen_shape=(h, w))
                    if p_best:
                        p_step_obj, (p_text, px, py, p_score, _) = p_best
                        matched = (p_step_obj, p_text, px, py, p_score)
                    if not matched:
                        matched = self.bot.match_custom_steps(detected, steps, screen_shape=(h, w))
            except Exception as e:
                err = e

            def done():
                self._capturing = False
                if screen is None:
                    if announce:
                        self.log_message(f"❌ 擷取失敗{': ' + str(err) if err else ''}")
                else:
                    self.current_screen_bgr = screen
                    self._last_detected = detected
                    self._render_preview(screen, detected, matched)
                    if announce:
                        self._announce_match(detected, matched)
                if on_done:
                    on_done()
            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _announce_match(self, detected, matched):
        if matched:
            step, text, x, y, _ = matched
            step_name = step.get("name", "步驟")
            if step.get("type") == "priority":
                self.log_message(f"⭐ [優先 - {step_name}] 命中「{text}」→ 優先點擊 ({x}, {y})")
            else:
                self.log_message(f"🎯 [{step_name}] 命中「{text}」→ 點擊 ({x}, {y})")
        else:
            self.log_message("⏳ 未命中任何步驟（畫面目前無符合目標）")

    def on_bot_frame_update(self, screen_bgr: np.ndarray, detected_items: list, matched=None):
        """
        執行中由背景執行緒呼叫，即時更新預覽 (極輕量化、超低畫質極速縮放、降頻更新、零卡頓)：
        1. 降頻節流：無命中時以一半速率更新 (每 2 幀一次，且間隔 >= 0.25s)，有命中或連點時第一時間更新點擊點。
        2. 取消無效的全量文字框繪製：免去幾十個文字框的多邊形渲染迴圈，僅在命中時繪製醒目標記。
        3. 極速縮圖：使用 INTER_NEAREST 進行微型縮放 (~480x270)，縮放耗時僅 ~0.1ms。
        4. 安全傳遞：以參數方式傳遞影像給 UI 執行緒，徹底避免閉包變數存取錯誤。
        """
        now = time.time()
        # 幀數降頻控制：無命中時降為一半刷新頻率 (每 2 幀一次，第 1 幀必定顯示)
        if matched is None:
            self._preview_frame_count += 1
            if self._preview_frame_count > 1 and (self._preview_frame_count % 2 != 0):
                return
            if (self._preview_frame_count > 1) and (now - self._last_preview_time < 0.25):
                return
            if self._preview_update_pending:
                return
        else:
            self._preview_frame_count = 0
            # 命中動作或連點具最高優先權，若連續多幀命中則保留至少 0.05s 防撕裂
            if now - self._last_preview_time < 0.05:
                return

        self._preview_update_pending = True
        self._last_preview_time = now

        try:
            cw = max(100, getattr(self, "canvas_w", 480) - 4)
            ch = max(100, getattr(self, "canvas_h", 270) - 4)

            h, w = screen_bgr.shape[:2]
            scale = min(cw / w, ch / h)
            pw = max(1, int(w * scale))
            ph = max(1, int(h * scale))

            # 超快極低負擔縮圖 (INTER_NEAREST 耗時僅 ~0.1ms)
            small = cv2.resize(screen_bgr, (pw, ph), interpolation=cv2.INTER_NEAREST)

            # 僅在有命中或連點時繪製點擊標記，不進行實時全文字框多邊形繪製 (省下 CPU 負擔)
            if matched:
                t = max(1, pw // 320)
                step, m_text, tx, ty, _conf = matched
                is_priority = (step.get("type") == "priority")
                is_tapping = (step.get("status") == "continuous_tap")
                roi = step.get("roi")
                if roi:
                    ymin, xmin, ymax, xmax = roi
                    cv2.rectangle(
                        small,
                        (int(xmin * pw), int(ymin * ph)),
                        (int(xmax * pw), int(ymax * ph)),
                        (0, 140, 255),
                        t + 1
                    )

                stx, sty = int(tx * scale), int(ty * scale)
                if is_tapping:
                    cv2.circle(small, (stx, sty), 10 * t, (0, 230, 255), t + 1)
                    cv2.circle(small, (stx, sty), 5 * t, (0, 140, 255), -1)
                    cv2.line(small, (stx - 8 * t, sty), (stx + 8 * t, sty), (0, 255, 255), t)
                    cv2.line(small, (stx, sty - 8 * t), (stx, sty + 8 * t), (0, 255, 255), t)
                    cv2.putText(
                        small,
                        f"TAP: {m_text}",
                        (max(6, stx - 40 * t), max(18, sty - 12 * t)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 240, 255),
                        1
                    )
                else:
                    dot_color = (0, 215, 255) if is_priority else (0, 255, 0)
                    cv2.circle(small, (stx, sty), 5 * t, dot_color, -1)
                    cv2.circle(small, (stx, sty), 9 * t, dot_color, t)
                    if is_priority:
                        cv2.putText(
                            small,
                            f"{step.get('name')}",
                            (stx + 10 * t, sty + 4 * t),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            (0, 215, 255),
                            1
                        )
                    if step.get("repeat_enabled"):
                        rx, ry = self._repeat_point(step, w, h, tx, ty)
                        srx, sry = int(rx * scale), int(ry * scale)
                        cv2.circle(small, (srx, sry), 9 * t, (0, 210, 255), t + 1)
                        cv2.line(small, (srx - 5 * t, sry), (srx + 5 * t, sry), (0, 210, 255), t)
                        cv2.line(small, (srx, sry - 5 * t), (srx, sry + 5 * t), (0, 210, 255), t)

            # 轉換為 RGB PIL 圖片並立即釋放 small 矩陣
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            del small
            pil_img = Image.fromarray(rgb)
            del rgb

            # 更新座標轉換參數
            self.preview_scale = scale
            self.preview_img_w = pw
            self.preview_img_h = ph
            self.raw_screen_w = w
            self.raw_screen_h = h

            def _update_ui(img=pil_img):
                try:
                    self.preview_image_tk = ImageTk.PhotoImage(img)
                    self.lbl_canvas.configure(image=self.preview_image_tk, text="")
                except Exception:
                    pass
                finally:
                    self._preview_update_pending = False

            self.root.after(0, _update_ui)
        except Exception:
            self._preview_update_pending = False

    def on_step_roi_changed(self):
        """改範圍時用快取的辨識結果重新比對，不必重新截圖"""
        if self.current_screen_bgr is None or self._last_detected is None or self.bot.is_running:
            return
        h, w = self.current_screen_bgr.shape[:2]
        self._sync_bot_roi()
        p_steps = self._get_active_priority_steps_config()
        matched = None
        p_best = self.bot.match_all_priority_steps(self._last_detected, p_steps, screen_shape=(h, w))
        if p_best:
            p_step_obj, (p_text, px, py, p_score, _) = p_best
            matched = (p_step_obj, p_text, px, py, p_score)
        if not matched:
            matched = self.bot.match_custom_steps(self._last_detected, self._get_active_steps_config(), screen_shape=(h, w))
        self._render_preview(self.current_screen_bgr, self._last_detected, matched)

    @staticmethod
    def _repeat_point(step: dict, w: int, h: int, tx: int, ty: int):
        area = step.get("repeat_area", "")
        if area == "右下角區域":
            return int(w * 0.86), int(h * 0.86)
        if area == "中央區域":
            return int(w * 0.50), int(h * 0.50)
        if area == "右上角 (Skip)":
            return int(w * 0.90), int(h * 0.12)
        if area == "右半側中央":
            return int(w * 0.82), int(h * 0.50)
        if "自訂" in area:
            if step.get("repeat_custom_coord"):
                cx, cy = step["repeat_custom_coord"]
                return int(cx), int(cy)
            cx = step.get("repeat_custom_x", step.get("custom_x", tx))
            cy = step.get("repeat_custom_y", step.get("custom_y", ty))
            return int(cx), int(cy)
        return tx, ty

    def _render_preview(self, screen_bgr: np.ndarray, detected, matched):
        """手動截圖與改範圍專用預覽渲染 (立即縮放並即刻釋放中間影像)"""
        if screen_bgr is None:
            return
        h, w = screen_bgr.shape[:2]
        self.raw_screen_w, self.raw_screen_h = w, h

        avail_w = max(100, self.lbl_canvas.winfo_width() - 4)
        avail_h = max(100, self.lbl_canvas.winfo_height() - 4)
        scale = min(avail_w / w, avail_h / h)
        pw, ph = max(1, int(w * scale)), max(1, int(h * scale))
        self.preview_scale = scale
        self.preview_img_w, self.preview_img_h = pw, ph

        small = cv2.resize(screen_bgr, (pw, ph), interpolation=cv2.INTER_LINEAR)
        t = max(1, pw // 320)

        for r in detected or []:
            sb = np.int32(r["box"] * scale)
            cv2.polylines(small, [sb], isClosed=True, color=(90, 200, 90), thickness=t)
            del sb

        if matched:
            step, m_text, tx, ty, _conf = matched
            is_priority = (step.get("type") == "priority")
            roi = step.get("roi")
            if roi:
                ymin, xmin, ymax, xmax = roi
                cv2.rectangle(small, (int(xmin * pw), int(ymin * ph)), (int(xmax * pw), int(ymax * ph)), (0, 140, 255), t + 1)
            stx, sty = int(tx * scale), int(ty * scale)
            dot_color = (0, 215, 255) if is_priority else (0, 255, 0)
            cv2.circle(small, (stx, sty), 5 * t, dot_color, -1)
            cv2.circle(small, (stx, sty), 9 * t, dot_color, t)
            if is_priority:
                cv2.putText(small, f"PRIORITY: {step.get('name')}", (stx + 10 * t, sty + 4 * t), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 215, 255), 1)

        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        del small
        pil_img = Image.fromarray(rgb)
        del rgb
        self.preview_image_tk = ImageTk.PhotoImage(pil_img)
        self.lbl_canvas.configure(image=self.preview_image_tk, text="")

    def _show_image(self):
        self._resize_job = None
        if self.current_screen_bgr is not None and not self.bot.is_running:
            self._render_preview(self.current_screen_bgr, self._last_detected, None)

    def _on_preview_resize(self, e=None):
        if e and getattr(e, "width", 0) > 50 and getattr(e, "height", 0) > 50:
            self.canvas_w = e.width
            self.canvas_h = e.height
        if self.bot.is_running:
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(120, self._show_image)

    def _preview_to_real(self, ex: int, ey: int):
        if self.preview_scale <= 0 or self.raw_screen_w <= 0 or self.raw_screen_h <= 0:
            return None
        pad_x = max(0, (self.lbl_canvas.winfo_width() - self.preview_img_w) // 2)
        pad_y = max(0, (self.lbl_canvas.winfo_height() - self.preview_img_h) // 2)
        rx, ry = ex - pad_x, ey - pad_y
        if not (0 <= rx <= self.preview_img_w and 0 <= ry <= self.preview_img_h):
            return None
        x = min(max(0, int(rx / self.preview_scale)), self.raw_screen_w - 1)
        y = min(max(0, int(ry / self.preview_scale)), self.raw_screen_h - 1)
        return x, y

    def _on_preview_mouse_move(self, e):
        xy = self._preview_to_real(e.x, e.y)
        self.var_preview_coords.set(f"{xy[0]}, {xy[1]}" if xy else "")

    def _on_preview_click(self, e):
        xy = self._preview_to_real(e.x, e.y)
        if not xy:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(f"{xy[0]}, {xy[1]}")
        self.log_message(f"已複製座標 {xy[0]}, {xy[1]}")

    def on_toggle_auto_refresh(self):
        if self.var_auto_refresh.get():
            if not self.bot.device:
                messagebox.showwarning("提示", "請先連線模擬器")
                self.var_auto_refresh.set(False)
                return
            self._schedule_next_refresh(delay_ms=200)
        elif self.auto_refresh_job:
            self.root.after_cancel(self.auto_refresh_job)
            self.auto_refresh_job = None

    def _schedule_next_refresh(self, delay_ms: int = None):
        if not self.var_auto_refresh.get():
            return
        if delay_ms is None:
            delay_ms = int(max(0.2, _num(self.var_interval, 2.5)) * 1000)
        self.auto_refresh_job = self.root.after(delay_ms, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        self.auto_refresh_job = None
        if not self.var_auto_refresh.get():
            return
        # 執行中由腳本本身回傳畫面，不重複擷取
        if self.bot.is_running or not self.bot.device:
            self._schedule_next_refresh()
            return
        self._capture_async(on_done=self._schedule_next_refresh)

    # ==========================================
    # 執行控制
    # ==========================================
    def on_start_bot(self):
        if self.bot.is_running:
            return
        steps = self._get_active_steps_config()
        priority_steps = self._get_active_priority_steps_config()
        if not any(s["enabled"] for s in steps) and not any(p["enabled"] for p in priority_steps):
            messagebox.showwarning("提示", "請至少啟用一個步驟或優先動作")
            return

        self.auto_save_current_config()
        self._sync_bot_roi()
        # 【用完即刪】：開始執行前徹底清理舊有截圖快取與歷史陣列
        self.current_screen_bgr = None
        self._last_detected = None
        self._preview_frame_count = 0
        self._last_preview_time = 0.0
        self._preview_update_pending = False
        import gc
        gc.collect()

        interval = _num(self.var_interval, 2.5)
        strat = self.var_idle_strategy.get()
        idle = "skip" if "跳過" in strat else "stop" if "停止" in strat else "wait"
        idle_tap_cfg = {
            "enabled": self.var_idle_tap_enabled.get(),
            "area": self.var_idle_tap_area.get(),
            "times": _num(self.var_idle_tap_times, 3, int),
            "interval": _num(self.var_idle_tap_interval, 0.4),
            "custom_x": _num(self.var_idle_tap_custom_x, 983, int),
            "custom_y": _num(self.var_idle_tap_custom_y, 1023, int),
            "custom_coord": (_num(self.var_idle_tap_custom_x, 983, int), _num(self.var_idle_tap_custom_y, 1023, int)),
        }
        watchdog_cfg = {
            "enabled": self.var_watchdog_enabled.get(),
            "seconds": _num(self.var_watchdog_seconds, 60, int),
        }

        for b in (self.btn_start, self.btn_connect, self.btn_refresh, self.btn_capture):
            b.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self._set_status("● 執行中", COLOR_OK)

        self.worker_thread = threading.Thread(
            target=self._run_worker, args=(interval, steps, idle, idle_tap_cfg, priority_steps, watchdog_cfg), daemon=True
        )
        self.worker_thread.start()

    def _run_worker(self, interval: float, steps, idle: str, idle_tap_cfg: dict, priority_steps: list, watchdog_cfg: dict = None):
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
            self.log_message(f"❌ 執行中斷: {e}")
        finally:
            self.root.after(0, self._on_worker_stopped)

    def _on_worker_stopped(self):
        # 【用完即刪】：停止後清除殘留的大圖快取
        self.current_screen_bgr = None
        self._last_detected = None
        import gc
        gc.collect()

        was_watchdog = getattr(self.bot, "_watchdog_triggered", False)
        self.bot._watchdog_triggered = False

        if was_watchdog:
            self.log_message("🔄 [防卡死守護] 腳本已由守護程式停止，將於 1.5 秒後自動重新開啟...")
            self._set_status("● 防卡死重新啟動中...", COLOR_WARN)
            for b in (self.btn_start, self.btn_connect, self.btn_refresh, self.btn_capture):
                b.configure(state=tk.DISABLED)
            self.btn_stop.configure(state=tk.NORMAL)
            self._watchdog_restart_job = self.root.after(1500, self._restart_worker_after_watchdog)
            return

        for b in (self.btn_start, self.btn_connect, self.btn_refresh, self.btn_capture):
            b.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        if self.bot.device:
            self._set_status(f"● 已停止  {self.bot.device.serial}", COLOR_IDLE)
        else:
            self._set_status("● 已停止", COLOR_IDLE)

        if self.var_auto_refresh.get() and not self.auto_refresh_job:
            self._schedule_next_refresh(delay_ms=500)

    def _restart_worker_after_watchdog(self):
        self._watchdog_restart_job = None
        if not self.bot.device:
            self.log_message("⚠️ 模擬器連線已中斷，無法自動重啟")
            self._on_worker_stopped()
            return
        self.log_message("🚀 [防卡死守護] 自動重新開啟腳本！")
        self.on_start_bot()

    def on_stop_bot(self):
        if getattr(self, "_watchdog_restart_job", None):
            self.root.after_cancel(self._watchdog_restart_job)
            self._watchdog_restart_job = None
        self.bot.stop()

    def on_run_diagnostics(self):
        try:
            from diagnostics import SystemDiagnostics
        except ImportError:
            self.log_message("❌ 找不到 diagnostics 模組")
            return
        lines = self.txt_log.get("1.0", tk.END).strip().split("\n")
        recent = "\n".join(lines[-25:]) if lines else ""
        data = SystemDiagnostics.run_full_diagnosis(bot_instance=self.bot)
        report = SystemDiagnostics.format_report_for_clipboard(data, recent_logs=recent)
        self.root.clipboard_clear()
        self.root.clipboard_append(report)
        self.root.update()
        self.log_message("自檢報告已複製到剪貼簿")

    def on_close_window(self):
        self.var_auto_refresh.set(False)
        for job in (self.auto_refresh_job, self._resize_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        self.auto_save_current_config()
        if self.bot.is_running:
            self.bot.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    BaseballBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
