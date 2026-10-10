"""
棒球手遊自動化腳本 - 即時打擊輔助 GUI 頁面 (Batting Assist Tab)
專為手遊打擊設計：小白球高速幾何偵測、動態增量識別、黃圈進壘鎖定。
支援指定模擬器實體點擊 (自動還原游標)、ADB 內部點擊與鍵盤映射，排版清晰無重疊。
"""
import os
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any, Callable, Tuple

import cv2
import numpy as np
from PIL import Image, ImageTk

from batting_assist import BattingAssistEngine, ALGO_PRESETS, DEFAULT_CONFIG, list_emulator_windows, HAS_MSS
from theme import DARK_BG, DARK_FG, DARK_FG_MUTED, DARK_BORDER, get_theme_palette

PRESET_DESCRIPTIONS = {
    "white_ball": "⚾【小白球高速偵測】專門鎖定高速飛入好球帶的白色棒球，自適應運動模糊與橢圓拉伸，自動過濾投手褲子大雜訊！",
    "white_ball_motion": "🏃【動態白球進壘】比對前後影格的白色動態增量，本壘板與球場白線等靜態物體不會觸發，精準鎖定飛行中的棒球！",
    "yellow_marker": "🟡【進壘提示黃圈】球進壘時好球帶會浮現黃色落點圓圈（如 4SFB 等），黃色與白色球褲/球衣完全不同，100% 避開褲子誤判！",
    "red_marker": "🔴【進壘提示紅圈】針對特定的進壘紅圈或紅色提示標記進行遮罩鎖定。"
}

INPUT_MODES = [
    ("window_click", "🖱️ 指定視窗實體點擊 (Win32 極速硬體點擊，100% 成功，推薦！)"),
    ("adb", "📱 模擬器 ADB 內部點擊 (原生精確座標，不搶滑鼠)"),
    ("directinput", "⌨️ 鍵盤映射按鍵 (DirectInput Space 鍵，延遲 < 1ms)"),
    ("win_msg_click", "🎯 指定視窗後台點擊 (Win32 PostMessage 嘗試)")
]

INPUT_MODE_TIPS = {
    "window_click": "💡 自動抓取模擬器在螢幕上的位置進行實體硬體點擊，點擊後 0.008 秒內自動還原你的滑鼠游標，100% 支援所有模擬器！",
    "adb": "💡 透過 ADB 伺服器在模擬器 Android 系統內部發送 input tap 指令，完全不移動 Windows 滑鼠。",
    "directinput": "💡 向目前處於最前景的視窗發送鍵盤按鍵 (如 Space/J 鍵)，請在模擬器鍵盤映射中將該鍵設定於揮棒按鈕上。",
    "win_msg_click": "💡 嘗試透過 Win32 PostMessage 發送滑鼠點擊訊息 (部分模擬器若關閉硬體加速可能支援)。"
}


class BattingAssistTab:
    """即時打擊輔助頁籤控制介面"""

    def __init__(
        self,
        parent: ttk.Frame,
        bot_instance=None,
        gui_parent=None,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.parent = parent
        self.bot = bot_instance
        self.gui = gui_parent
        self.log_callback = log_callback

        # 核心引擎 (預設 window_lock 模式, 60 FPS, window_click)
        self.engine = BattingAssistEngine(bot_instance=self.bot)
        self.engine.on_telemetry_callback = self._on_telemetry_update
        self.engine.on_frame_callback = self._on_frame_update
        self.engine.on_swing_callback = self._on_swing_event
        self.engine.on_log_callback = self._log

        # 演算法名稱初始化
        curr_p = self.engine.config.get("preset_name", "white_ball")
        if curr_p in ALGO_PRESETS:
            initial_p_str = f"{curr_p}: {ALGO_PRESETS[curr_p]['name']}"
        else:
            initial_p_str = f"white_ball: {ALGO_PRESETS['white_ball']['name']}"

        # 輸入模式初始化
        curr_in = self.engine.config.get("input_mode", "window_click")
        initial_in_str = next((name for code, name in INPUT_MODES if code == curr_in), INPUT_MODES[0][1])

        # 介面變數
        self.var_preview_mode = tk.StringVar(value="full")  # "full", "roi", "mask"
        self.var_canvas_target_mode = tk.StringVar(value="roi")  # "roi" (設定好球帶), "swing" (設定揮棒點)
        self.var_preset = tk.StringVar(value=initial_p_str)
        self.var_preset_desc = tk.StringVar(value=PRESET_DESCRIPTIONS.get(curr_p, ""))
        self.var_capture_mode = tk.StringVar(value=self.engine.config.get("capture_mode", "window_lock"))
        self.var_target_fps = tk.IntVar(value=self.engine.config.get("target_fps", 60))
        self.var_locked_window_text = tk.StringVar(value="🔍 正在搜尋模擬器視窗...")
        self.var_input_mode_display = tk.StringVar(value=initial_in_str)
        self.var_input_tip = tk.StringVar(value=INPUT_MODE_TIPS.get(curr_in, ""))
        self.var_directinput_key = tk.StringVar(value=self.engine.config.get("directinput_key", "space"))

        # 好球帶 ROI 變數 (基準為 1600x900 解析度，Y=560 避開上方 Y=300~420 的投手球褲)
        self.var_roi_x = tk.IntVar(value=self.engine.config.get("roi_x", 700))
        self.var_roi_y = tk.IntVar(value=self.engine.config.get("roi_y", 560))
        self.var_roi_w = tk.IntVar(value=self.engine.config.get("roi_w", 180))
        self.var_roi_h = tk.IntVar(value=self.engine.config.get("roi_h", 160))

        # 模擬器揮棒點擊座標 (基準 1600x900，預設 1380, 720 為右下角揮棒按鈕)
        self.var_swing_x = tk.IntVar(value=self.engine.config.get("swing_x", 1380))
        self.var_swing_y = tk.IntVar(value=self.engine.config.get("swing_y", 720))

        # 門檻變數
        self.var_h_min = tk.IntVar(value=self.engine.config.get("hsv_h_min", 0))
        self.var_h_max = tk.IntVar(value=self.engine.config.get("hsv_h_max", 180))
        self.var_s_min = tk.IntVar(value=self.engine.config.get("hsv_s_min", 0))
        self.var_s_max = tk.IntVar(value=self.engine.config.get("hsv_s_max", 75))
        self.var_v_min = tk.IntVar(value=self.engine.config.get("hsv_v_min", 175))
        self.var_v_max = tk.IntVar(value=self.engine.config.get("hsv_v_max", 255))
        self.var_min_px = tk.IntVar(value=self.engine.config.get("min_ball_area", self.engine.config.get("min_trigger_pixels", 12)))
        self.var_max_px = tk.IntVar(value=self.engine.config.get("max_ball_area", self.engine.config.get("max_trigger_pixels", 220)))
        self.var_diff_th = tk.IntVar(value=self.engine.config.get("motion_diff_thresh", 25))

        # 時差與冷卻
        self.var_timing_offset = tk.IntVar(value=self.engine.config.get("timing_offset_ms", 0))
        self.var_cooldown = tk.IntVar(value=self.engine.config.get("cooldown_ms", 1200))

        # 狀態遙測變數
        self.var_status_badge = tk.StringVar(value="⏸ 打擊輔助未啟動 (按 F8 或點擊啟動)")
        self.var_fps_text = tk.StringVar(value="FPS: --")
        self.var_latency_text = tk.StringVar(value="延遲: 截圖 -- ms | 辨識 -- ms")
        self.var_pixels_text = tk.StringVar(value="命中像素: 0 px")
        self.var_swings_text = tk.StringVar(value="擊球次數: 0 次 (最近: 無)")
        self.var_target_desc = tk.StringVar(value="👀 等待小白球飛入好球帶...")

        # 預覽緩衝與尺寸
        self.current_full_bgr: Optional[np.ndarray] = None
        self.current_roi_bgr: Optional[np.ndarray] = None
        self.current_mask_img: Optional[np.ndarray] = None
        self.preview_photo: Optional[ImageTk.PhotoImage] = None
        self._swing_flash_timer = 0.0

        # Canvas 尺寸與縮放映射
        self.canvas_w = 480
        self.canvas_h = 270
        self.render_scale = 1.0
        self.pad_x = 0
        self.pad_y = 0
        self.raw_w = 1600
        self.raw_h = 900

        # 滑鼠拖曳互動狀態
        self._drag_start = None

        # 建構 UI
        self._build_ui()

        # 初始搜尋並鎖定模擬器視窗
        self.on_scan_emulator_windows()

        # 嘗試從主介面載入既有的模擬器畫面
        self._check_initial_emulator_frame()

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    def _get_current_input_mode_code(self) -> str:
        disp = self.var_input_mode_display.get()
        for code, name in INPUT_MODES:
            if name == disp:
                return code
        return "window_click"

    def on_scan_emulator_windows(self):
        """掃描 Windows 桌面尋找模擬器視窗"""
        wins = list_emulator_windows()
        if wins:
            w = wins[0]
            self.var_locked_window_text.set(f"🎯 鎖定視窗: {w['title']} ({w['width']}x{w['height']})")
            self._log(f"成功鎖定模擬器視窗: {w['title']} 尺寸 ({w['width']}x{w['height']})")
        else:
            self.var_locked_window_text.set("⚠️ 尚未偵測到模擬器視窗 (請確認模擬器未最小化)")

    def _check_initial_emulator_frame(self):
        """啟動時若主介面已連線並有畫面，立即呈現"""
        if self.gui and getattr(self.gui, "current_screen_bgr", None) is not None:
            self.update_emulator_preview(self.gui.current_screen_bgr)
        elif self.bot and getattr(self.bot, "device", None) is not None:
            def _grab():
                try:
                    frame = self.bot.capture_screen()
                    if frame is not None:
                        self.parent.after(0, self.update_emulator_preview, frame)
                except Exception:
                    pass
            import threading
            threading.Thread(target=_grab, daemon=True).start()

    def _build_ui(self):
        """建構頁面排版"""
        # 1. 頂部操作列
        top_box = ttk.Frame(self.parent, padding=(8, 6, 8, 4))
        top_box.pack(fill=tk.X)

        self.btn_toggle = tk.Button(
            top_box, text="▶ 啟動打擊輔助 (F8)", font=("Arial", 11, "bold"),
            bg="#16a34a", fg="#ffffff", padx=12, pady=4, relief=tk.RAISED,
            command=self.on_toggle_engine
        )
        self.btn_toggle.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_grab_frame = ttk.Button(
            top_box, text="📸 抓取模擬器畫面", command=self.on_refresh_emulator_frame
        )
        self.btn_grab_frame.pack(side=tk.LEFT, padx=(0, 6))

        p_pal = get_theme_palette()
        self.lbl_status_badge = tk.Label(
            top_box, textvariable=self.var_status_badge, font=("Arial", 10, "bold"),
            fg="#ef4444", bg=p_pal["bg"]
        )
        self.lbl_status_badge.pack(side=tk.RIGHT, padx=6)

        # 2. 視窗鎖定與目標幀率狀態列
        status_bar = ttk.Frame(self.parent, padding=(8, 0, 8, 4))
        status_bar.pack(fill=tk.X)

        lbl_win = tk.Label(
            status_bar, textvariable=self.var_locked_window_text, font=("Arial", 9, "bold"),
            fg="#38bdf8", bg="#0c4a6e", padx=6, pady=2, relief=tk.SOLID, borderwidth=1
        )
        lbl_win.pack(side=tk.LEFT)

        btn_rescan = ttk.Button(status_bar, text="🔍 重新搜尋視窗", command=self.on_scan_emulator_windows)
        btn_rescan.pack(side=tk.LEFT, padx=(6, 12))

        ttk.Label(status_bar, text="目標幀率:").pack(side=tk.LEFT, padx=(0, 4))
        combo_fps = ttk.Combobox(
            status_bar, textvariable=self.var_target_fps,
            values=[30, 60, 90, 120, 0], state="readonly", width=6
        )
        combo_fps.pack(side=tk.LEFT)
        combo_fps.bind("<<ComboboxSelected>>", lambda e: self.on_apply_config())
        ttk.Label(status_bar, text="FPS (0 = 無上限極速)", foreground="#6b7280").pack(side=tk.LEFT, padx=(4, 0))

        # 3. 主體分割區 (左: 模擬器畫面與好球帶 | 右: 揮棒動作與判定門檻)
        main_pane = ttk.PanedWindow(self.parent, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        left_frame = ttk.Frame(main_pane, padding=4)
        right_frame = ttk.Frame(main_pane, padding=4)
        main_pane.add(left_frame, weight=1)
        main_pane.add(right_frame, weight=1)

        self._build_vision_panel(left_frame)
        self._build_settings_panel(right_frame)

    # =========================================================================
    # 左側：模擬器遊戲畫面與好球帶 (Strike Zone) 標定
    # =========================================================================
    def _build_vision_panel(self, parent):
        box_preview = ttk.LabelFrame(parent, text="📱 模擬器即時畫面 (支援點擊畫布設定好球帶或揮棒點)", padding=6)
        box_preview.pack(fill=tk.BOTH, expand=True)

        # 畫面操作工具列 (清晰兩列，絕不重疊)
        tool_row1 = ttk.Frame(box_preview)
        tool_row1.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(tool_row1, text="預覽模式:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(tool_row1, text="📺 全景", value="full", variable=self.var_preview_mode, command=self._redraw_current_frame).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Radiobutton(tool_row1, text="🔍 特寫", value="roi", variable=self.var_preview_mode, command=self._redraw_current_frame).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Radiobutton(tool_row1, text="🎯 遮罩", value="mask", variable=self.var_preview_mode, command=self._redraw_current_frame).pack(side=tk.LEFT)

        tool_row2 = ttk.Frame(box_preview)
        tool_row2.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(tool_row2, text="畫布點選作用:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(tool_row2, text="🎯 設定好球帶 (藍框)", value="roi", variable=self.var_canvas_target_mode).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(tool_row2, text="💥 設定揮棒點 (紅靶心)", value="swing", variable=self.var_canvas_target_mode).pack(side=tk.LEFT)

        # 畫布 (支援滑鼠點擊/拖曳)
        pal = get_theme_palette()
        self.canvas = tk.Canvas(box_preview, width=self.canvas_w, height=self.canvas_h, bg=pal["preview_bg"])
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=2)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)

        # 遙測數據顯示條
        tele_box = ttk.Frame(box_preview, padding=2)
        tele_box.pack(fill=tk.X)

        tele_row1 = ttk.Frame(tele_box)
        tele_row1.pack(fill=tk.X)
        ttk.Label(tele_row1, textvariable=self.var_fps_text, font=("Consolas", 10, "bold"), foreground="#16a34a").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(tele_row1, textvariable=self.var_latency_text, font=("Consolas", 9)).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(tele_row1, textvariable=self.var_pixels_text, font=("Consolas", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(tele_row1, textvariable=self.var_swings_text, font=("Arial", 9, "bold"), foreground="#2563eb").pack(side=tk.RIGHT)

        tele_row2 = ttk.Frame(tele_box)
        tele_row2.pack(fill=tk.X, pady=(3, 0))
        ttk.Label(tele_row2, text="目標監控:").pack(side=tk.LEFT, padx=(0, 4))
        self.lbl_target_desc = tk.Label(
            tele_row2, textvariable=self.var_target_desc, font=("Microsoft JhengHei", 9, "bold"),
            fg="#38bdf8", bg="#0c4a6e", padx=6, pady=2, relief=tk.SOLID, borderwidth=1, anchor="w"
        )
        self.lbl_target_desc.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 好球帶 ROI 座標控制區 (寬敞排版，不擁擠)
        box_roi = ttk.LabelFrame(parent, text="📐 模擬器好球帶座標 (Strike Zone ROI)", padding=6)
        box_roi.pack(fill=tk.X, pady=(6, 0))

        preset_pos_row = ttk.Frame(box_roi)
        preset_pos_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(preset_pos_row, text="快速定位:").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(preset_pos_row, text="🎯 對齊好球帶 (避開投手, 推薦)", command=self.on_align_strike_zone).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(preset_pos_row, text="🖐️ 對齊投手出手點", command=self.on_align_release_point).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(preset_pos_row, text="🔄 重設好球帶", command=self.on_align_strike_zone).pack(side=tk.LEFT)

        roi_inputs = ttk.Frame(box_roi)
        roi_inputs.pack(fill=tk.X, pady=2)
        ttk.Label(roi_inputs, text="X:").grid(row=0, column=0, padx=2)
        tk.Spinbox(roi_inputs, from_=0, to=3840, textvariable=self.var_roi_x, width=6, command=self.on_roi_spin_changed).grid(row=0, column=1, padx=2)
        ttk.Label(roi_inputs, text="Y:").grid(row=0, column=2, padx=2)
        tk.Spinbox(roi_inputs, from_=0, to=2160, textvariable=self.var_roi_y, width=6, command=self.on_roi_spin_changed).grid(row=0, column=3, padx=2)
        ttk.Label(roi_inputs, text="寬 (W):").grid(row=0, column=4, padx=2)
        tk.Spinbox(roi_inputs, from_=10, to=1000, textvariable=self.var_roi_w, width=6, command=self.on_roi_spin_changed).grid(row=0, column=5, padx=2)
        ttk.Label(roi_inputs, text="高 (H):").grid(row=0, column=6, padx=2)
        tk.Spinbox(roi_inputs, from_=10, to=1000, textvariable=self.var_roi_h, width=6, command=self.on_roi_spin_changed).grid(row=0, column=7, padx=2)

        lbl_roi_tip = ttk.Label(
            box_roi,
            text="💡 提示：請將藍框維持在好球帶（Y 約 560），避免覆蓋到上方投手的白色球褲（Y 300~420）。",
            foreground="#6b7280", wraplength=480
        )
        lbl_roi_tip.pack(fill=tk.X, pady=(2, 0))

    # =========================================================================
    # 右側：模擬器揮棒動作與判定設定 (揮棒設定置頂，絕不重疊)
    # =========================================================================
    def _build_settings_panel(self, parent):
        # 1. 模擬器揮棒設定與點擊座標 (卡片 1 - 最重要，直接放最上面)
        box_swing = ttk.LabelFrame(parent, text="⚡ 模擬器揮棒動作與點擊座標 (Swing Action & Target)", padding=6)
        box_swing.pack(fill=tk.X, pady=(0, 6))

        in_row = ttk.Frame(box_swing)
        in_row.pack(fill=tk.X, pady=2)
        ttk.Label(in_row, text="輸入方式:").pack(side=tk.LEFT, padx=(0, 4))
        self.combo_in_mode = ttk.Combobox(
            in_row, textvariable=self.var_input_mode_display,
            values=[name for _, name in INPUT_MODES],
            state="readonly", width=42
        )
        self.combo_in_mode.pack(side=tk.LEFT)
        self.combo_in_mode.bind("<<ComboboxSelected>>", self.on_input_mode_changed)

        # 模擬器點擊座標設定行 + 立即測試點擊按鈕
        sw_coords_row = ttk.Frame(box_swing)
        sw_coords_row.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(sw_coords_row, text="點擊座標 X:").grid(row=0, column=0, padx=2)
        tk.Spinbox(sw_coords_row, from_=0, to=3840, textvariable=self.var_swing_x, width=6, command=self.on_roi_spin_changed).grid(row=0, column=1, padx=2)
        ttk.Label(sw_coords_row, text="Y:").grid(row=0, column=2, padx=2)
        tk.Spinbox(sw_coords_row, from_=0, to=2160, textvariable=self.var_swing_y, width=6, command=self.on_roi_spin_changed).grid(row=0, column=3, padx=2)

        self.btn_test_click = tk.Button(
            sw_coords_row, text="💥 立即測試點擊此處", font=("Arial", 9, "bold"),
            bg="#f97316", fg="#ffffff", padx=8, pady=2, relief=tk.RAISED,
            command=self.on_test_swing_click
        )
        self.btn_test_click.grid(row=0, column=4, padx=(8, 0))

        # 快速座標定位按鈕
        sw_preset_row = ttk.Frame(box_swing)
        sw_preset_row.pack(fill=tk.X, pady=(4, 2))
        ttk.Label(sw_preset_row, text="快速座標:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(sw_preset_row, text="📍 右下角按鈕 (1380, 720)", command=self.on_preset_swing_bottom_right).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(sw_preset_row, text="📍 畫面中央 (800, 600)", command=self.on_preset_swing_center).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(sw_preset_row, text="📍 跟隨好球帶中心", command=self.on_align_swing_to_strike_zone).pack(side=tk.LEFT)

        key_row = ttk.Frame(box_swing)
        key_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(key_row, text="映射按鍵 (若選用鍵盤模式):").pack(side=tk.LEFT, padx=(0, 4))
        self.ent_key = ttk.Entry(key_row, textvariable=self.var_directinput_key, width=8)
        self.ent_key.pack(side=tk.LEFT)
        self.ent_key.bind("<KeyRelease>", lambda e: self.on_apply_config())

        self.lbl_mode_tip = ttk.Label(
            box_swing, textvariable=self.var_input_tip,
            foreground="#0369a1", wraplength=480
        )
        self.lbl_mode_tip.pack(fill=tk.X, pady=(4, 0))

        # 2. 判定門檻 (卡片 2)
        box_thresh = ttk.LabelFrame(parent, text="⚙️ 視覺判定演算法與門檻 (Algorithm & Thresholds)", padding=6)
        box_thresh.pack(fill=tk.BOTH, expand=True)

        preset_row = ttk.Frame(box_thresh)
        preset_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(preset_row, text="演算法範本:").pack(side=tk.LEFT, padx=(0, 4))
        preset_options = list(ALGO_PRESETS.keys())
        self.combo_presets = ttk.Combobox(
            preset_row, textvariable=self.var_preset,
            values=[f"{k}: {ALGO_PRESETS[k]['name']}" for k in preset_options],
            state="readonly", width=36
        )
        self.combo_presets.pack(side=tk.LEFT)
        self.combo_presets.bind("<<ComboboxSelected>>", self.on_preset_changed)

        self.lbl_preset_detail = tk.Label(
            box_thresh, textvariable=self.var_preset_desc, font=("Microsoft JhengHei", 9),
            fg="#38bdf8", bg="#0c4a6e", padx=6, pady=3, relief=tk.SOLID, borderwidth=1,
            justify=tk.LEFT, wraplength=460
        )
        self.lbl_preset_detail.pack(fill=tk.X, pady=(0, 4))

        grid = ttk.Frame(box_thresh)
        grid.pack(fill=tk.X, pady=2)

        # H 色相
        ttk.Label(grid, text="色相 H (Min~Max):").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Scale(grid, from_=0, to=180, variable=self.var_h_min, command=lambda v: self.on_apply_config()).grid(row=0, column=1, sticky=tk.EW, padx=4)
        ttk.Scale(grid, from_=0, to=180, variable=self.var_h_max, command=lambda v: self.on_apply_config()).grid(row=0, column=2, sticky=tk.EW, padx=4)
        ttk.Label(grid, textvariable=self.var_h_min, width=4).grid(row=0, column=3)
        ttk.Label(grid, textvariable=self.var_h_max, width=4).grid(row=0, column=4)

        # S 飽和度
        ttk.Label(grid, text="飽和度 S (Min~Max):").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Scale(grid, from_=0, to=255, variable=self.var_s_min, command=lambda v: self.on_apply_config()).grid(row=1, column=1, sticky=tk.EW, padx=4)
        ttk.Scale(grid, from_=0, to=255, variable=self.var_s_max, command=lambda v: self.on_apply_config()).grid(row=1, column=2, sticky=tk.EW, padx=4)
        ttk.Label(grid, textvariable=self.var_s_min, width=4).grid(row=1, column=3)
        ttk.Label(grid, textvariable=self.var_s_max, width=4).grid(row=1, column=4)

        # V 明度
        ttk.Label(grid, text="明度 V (Min~Max):").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Scale(grid, from_=0, to=255, variable=self.var_v_min, command=lambda v: self.on_apply_config()).grid(row=2, column=1, sticky=tk.EW, padx=4)
        ttk.Scale(grid, from_=0, to=255, variable=self.var_v_max, command=lambda v: self.on_apply_config()).grid(row=2, column=2, sticky=tk.EW, padx=4)
        ttk.Label(grid, textvariable=self.var_v_min, width=4).grid(row=2, column=3)
        ttk.Label(grid, textvariable=self.var_v_max, width=4).grid(row=2, column=4)

        # 觸發像素面積 (小白球 12~220px)
        ttk.Label(grid, text="球體面積範圍 (Min~Max px):").grid(row=3, column=0, sticky=tk.W, pady=3)
        tk.Spinbox(grid, from_=1, to=5000, textvariable=self.var_min_px, width=7, command=self.on_apply_config).grid(row=3, column=1, padx=4)
        tk.Spinbox(grid, from_=10, to=20000, textvariable=self.var_max_px, width=7, command=self.on_apply_config).grid(row=3, column=2, padx=4)

        # 幀差靈敏度
        ttk.Label(grid, text="幀差靈敏度 (Motion Thresh):").grid(row=4, column=0, sticky=tk.W, pady=3)
        tk.Spinbox(grid, from_=5, to=150, textvariable=self.var_diff_th, width=7, command=self.on_apply_config).grid(row=4, column=1, padx=4)

        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(2, weight=1)

        # 3. 揮棒時差與冷卻 (卡片 3)
        box_timing = ttk.LabelFrame(parent, text="⏱️ 擊球時差校準與防抖 (Timing Calibration)", padding=6)
        box_timing.pack(fill=tk.X, pady=(4, 0))

        timing_grid = ttk.Frame(box_timing)
        timing_grid.pack(fill=tk.X, pady=2)

        ttk.Label(timing_grid, text="時差補償 (毫秒):").grid(row=0, column=0, sticky=tk.W)
        tk.Spinbox(timing_grid, from_=-50, to=200, textvariable=self.var_timing_offset, width=6, command=self.on_apply_config).grid(row=0, column=1, padx=4)
        ttk.Label(timing_grid, text="(0 = 立即揮棒, +20ms = 稍等進壘)", foreground="#6b7280").grid(row=0, column=2, sticky=tk.W)

        ttk.Label(timing_grid, text="防連點冷卻 (毫秒):").grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        tk.Spinbox(timing_grid, from_=300, to=3000, textvariable=self.var_cooldown, width=6, command=self.on_apply_config).grid(row=1, column=1, padx=4, pady=(4, 0))
        ttk.Label(timing_grid, text="(預設 1200ms 防止同一球重複揮棒)", foreground="#6b7280").grid(row=1, column=2, sticky=tk.W, pady=(4, 0))

        # 底部動作按鈕
        btn_bar = ttk.Frame(parent)
        btn_bar.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_bar, text="💾 儲存打擊設定", command=self.on_save_config_file).pack(side=tk.LEFT)
        ttk.Button(btn_bar, text="🔄 重設為原廠建議", command=self.on_reset_defaults).pack(side=tk.LEFT, padx=6)

    # =========================================================================
    # 畫布滑鼠互動：直接在遊戲畫面上設定好球帶或揮棒點
    # =========================================================================
    def _canvas_to_emulator(self, cx: int, cy: int) -> Tuple[int, int]:
        """將畫布上的點選座標換算為模擬器真實解析度座標"""
        if self.render_scale <= 0:
            return (self.var_roi_x.get(), self.var_roi_y.get())
        rx = cx - self.pad_x
        ry = cy - self.pad_y
        emu_x = max(0, min(self.raw_w - 1, int(rx / self.render_scale)))
        emu_y = max(0, min(self.raw_h - 1, int(ry / self.render_scale)))
        return emu_x, emu_y

    def on_canvas_click(self, event):
        """點擊畫布直接定位好球帶或揮棒點"""
        if self.var_preview_mode.get() != "full":
            return
        emu_x, emu_y = self._canvas_to_emulator(event.x, event.y)
        target_mode = self.var_canvas_target_mode.get()

        if target_mode == "swing":
            self.var_swing_x.set(emu_x)
            self.var_swing_y.set(emu_y)
            self.on_apply_config()
            self._redraw_current_frame()
            self._log(f"已將揮棒點擊座標設定為: ({emu_x}, {emu_y})")
        else:
            rw = self.var_roi_w.get()
            rh = self.var_roi_h.get()
            new_x = max(0, min(self.raw_w - rw, emu_x - rw // 2))
            new_y = max(0, min(self.raw_h - rh, emu_y - rh // 2))
            self.var_roi_x.set(new_x)
            self.var_roi_y.set(new_y)
            self._drag_start = (emu_x, emu_y)
            self.on_apply_config()
            self._redraw_current_frame()

    def on_canvas_drag(self, event):
        """拖曳畫布動態調整好球帶尺寸或移動揮棒點"""
        if self.var_preview_mode.get() != "full":
            return
        emu_x, emu_y = self._canvas_to_emulator(event.x, event.y)
        target_mode = self.var_canvas_target_mode.get()

        if target_mode == "swing":
            self.var_swing_x.set(emu_x)
            self.var_swing_y.set(emu_y)
            self.on_apply_config()
            self._redraw_current_frame()
        else:
            if not self._drag_start:
                return
            sx, sy = self._drag_start
            min_x, max_x = min(sx, emu_x), max(sx, emu_x)
            min_y, max_y = min(sy, emu_y), max(sy, emu_y)
            w, h = max_x - min_x, max_y - min_y
            if w >= 20 and h >= 20:
                self.var_roi_x.set(min_x)
                self.var_roi_y.set(min_y)
                self.var_roi_w.set(w)
                self.var_roi_h.set(h)
                self.on_apply_config()
                self._redraw_current_frame()

    def on_align_strike_zone(self):
        """將好球帶對齊至打擊進壘區 (Y=560，避開投手)"""
        self.var_roi_x.set(700)
        self.var_roi_y.set(560)
        self.var_roi_w.set(180)
        self.var_roi_h.set(160)
        self.on_apply_config()
        self._redraw_current_frame()
        self._log("已切換為【好球帶進壘區】(Y=560，避開投手)")

    def on_align_release_point(self):
        """將好球帶對齊至投手出手點 (Y=400)"""
        self.var_roi_x.set(730)
        self.var_roi_y.set(400)
        self.var_roi_w.set(140)
        self.var_roi_h.set(120)
        self.on_apply_config()
        self._redraw_current_frame()
        self._log("已切換為【投手出手點】(Y=400)")

    def on_preset_swing_bottom_right(self):
        """設定揮棒點為右下角按鈕 (1380, 720)"""
        self.var_swing_x.set(1380)
        self.var_swing_y.set(720)
        self.on_apply_config()
        self._redraw_current_frame()
        self._log("已將揮棒點設為【右下角按鈕】(1380, 720)")

    def on_preset_swing_center(self):
        """設定揮棒點為畫面中心 (800, 600)"""
        self.var_swing_x.set(800)
        self.var_swing_y.set(600)
        self.on_apply_config()
        self._redraw_current_frame()
        self._log("已將揮棒點設為【畫面中心】(800, 600)")

    def on_align_swing_to_strike_zone(self):
        """將揮棒點設定為好球帶中心"""
        cx = self.var_roi_x.get() + self.var_roi_w.get() // 2
        cy = self.var_roi_y.get() + self.var_roi_h.get() // 2
        self.var_swing_x.set(cx)
        self.var_swing_y.set(cy)
        self.on_apply_config()
        self._redraw_current_frame()
        self._log(f"已將揮棒點設為好球帶中心: ({cx}, {cy})")

    def on_test_swing_click(self):
        """測試點擊指定揮棒座標"""
        self.on_apply_config()
        self.engine.execute_swing()
        self._log("已發送測試揮棒點擊！請觀察模擬器是否有動作。")

    def on_roi_spin_changed(self):
        self.on_apply_config()
        self._redraw_current_frame()

    def on_input_mode_changed(self, event=None):
        code = self._get_current_input_mode_code()
        self.var_input_tip.set(INPUT_MODE_TIPS.get(code, ""))
        self.on_apply_config()
        self._log(f"已切換揮棒輸入方式為: {code}")

    # =========================================================================
    # 外部畫面推播 (主介面捕獲模擬器畫面時自動同步)
    # =========================================================================
    def update_emulator_preview(self, screen_bgr: np.ndarray):
        """由外部 (主介面連線截圖或自動刷關) 推送模擬器最新畫面"""
        if screen_bgr is None:
            return
        self.current_full_bgr = screen_bgr
        self.raw_h, self.raw_w = screen_bgr.shape[:2]

        rx = self.var_roi_x.get()
        ry = self.var_roi_y.get()
        rw = self.var_roi_w.get()
        rh = self.var_roi_h.get()

        # 裁切 ROI
        clamped_rx = max(0, min(self.raw_w - 10, rx))
        clamped_ry = max(0, min(self.raw_h - 10, ry))
        clamped_rw = max(10, min(self.raw_w - clamped_rx, rw))
        clamped_rh = max(10, min(self.raw_h - clamped_ry, rh))
        roi = screen_bgr[clamped_ry:clamped_ry + clamped_rh, clamped_rx:clamped_rx + clamped_rw]
        self.current_roi_bgr = roi

        # 若打擊引擎未在運行中，直接手動繪製一幀預覽
        if not self.engine.is_running or not self.engine.is_active:
            self._render_frame(screen_bgr, roi, None, False, (clamped_rx, clamped_ry, clamped_rw, clamped_rh))

    def on_refresh_emulator_frame(self):
        """手動立即截取一幀模擬器畫面更新畫布"""
        win = self.engine.get_locked_window()
        if win and HAS_MSS:
            try:
                import mss
                with mss.mss() as sct:
                    mon = {"top": win["top"], "left": win["left"], "width": win["width"], "height": win["height"]}
                    frame = np.array(sct.grab(mon), dtype=np.uint8)[:, :, :3]
                    self.update_emulator_preview(frame)
                    self._log(f"已從視窗「{win['title']}」獲取最新畫面！")
                    return
            except Exception:
                pass

        if self.bot and getattr(self.bot, "device", None):
            try:
                frame = self.bot.capture_screen()
                if frame is not None:
                    self.update_emulator_preview(frame)
                    self._log("已從模擬器 ADB 獲取最新畫面！")
                    return
            except Exception as e:
                self._log(f"ADB 截圖異常: {e}")

        messagebox.showwarning("提示", "未找到開啟的模擬器視窗或連線裝置，請確認模擬器未最小化！")

    # =========================================================================
    # 畫面渲染管線
    # =========================================================================
    def _redraw_current_frame(self):
        if self.current_full_bgr is not None:
            rx = self.var_roi_x.get()
            ry = self.var_roi_y.get()
            rw = self.var_roi_w.get()
            rh = self.var_roi_h.get()
            self._render_frame(
                self.current_full_bgr, self.current_roi_bgr, self.current_mask_img,
                False, (rx, ry, rw, rh)
            )

    def _on_frame_update(
        self,
        full_bgr: Optional[np.ndarray],
        roi_bgr: np.ndarray,
        mask_img: np.ndarray,
        is_hit: bool,
        roi_rect: Tuple[int, int, int, int],
        target_desc: str = "",
        best_ball: Optional[Tuple[int, int, int, int]] = None,
        swing_point: Optional[Tuple[int, int]] = None
    ):
        """引擎背景線程推播的最新即時影格"""
        self.parent.after(
            0, self._render_frame,
            full_bgr, roi_bgr, mask_img, is_hit, roi_rect, target_desc, best_ball, swing_point
        )

    def _render_frame(
        self,
        full_bgr: Optional[np.ndarray],
        roi_bgr: Optional[np.ndarray],
        mask_img: Optional[np.ndarray],
        is_hit: bool,
        roi_rect: Tuple[int, int, int, int],
        target_desc: str = "",
        best_ball: Optional[Tuple[int, int, int, int]] = None,
        swing_point: Optional[Tuple[int, int]] = None
    ):
        try:
            if full_bgr is not None:
                self.current_full_bgr = full_bgr
                self.raw_h, self.raw_w = full_bgr.shape[:2]
            if roi_bgr is not None:
                self.current_roi_bgr = roi_bgr
            if mask_img is not None:
                self.current_mask_img = mask_img

            mode = self.var_preview_mode.get()
            rx, ry, rw, rh = roi_rect

            # 更新動態遙測文字與樣式
            if target_desc:
                self.var_target_desc.set(target_desc)
                if "白褲子" in target_desc or "過大" in target_desc:
                    self.lbl_target_desc.config(fg="#fb923c", bg="#7c2d12")
                elif "鎖定" in target_desc or "⚾" in target_desc or "🟡" in target_desc:
                    self.lbl_target_desc.config(fg="#4ade80", bg="#14532d")
                else:
                    self.lbl_target_desc.config(fg="#38bdf8", bg="#0c4a6e")

            now = time.perf_counter()
            is_recent_swing = (now - self._swing_flash_timer) < 0.28
            sw_x = self.var_swing_x.get()
            sw_y = self.var_swing_y.get()

            # 根據顯示模式產生影像
            if mode == "full" and self.current_full_bgr is not None:
                disp_bgr = self.current_full_bgr.copy()

                # 1. 繪製好球帶偵測框
                if is_hit or is_recent_swing:
                    box_color = (0, 255, 0)
                elif best_ball is not None:
                    box_color = (0, 230, 255)
                elif "白褲子" in target_desc or "過大" in target_desc:
                    box_color = (0, 140, 255)
                else:
                    box_color = (255, 200, 0)

                cv2.rectangle(disp_bgr, (rx, ry), (rx + rw, ry + rh), box_color, 2)
                cx, cy = rx + rw // 2, ry + rh // 2
                cv2.line(disp_bgr, (cx - 12, cy), (cx + 12, cy), box_color, 1)
                cv2.line(disp_bgr, (cx, cy - 12), (cx, cy + 12), box_color, 1)

                # 2. 繪製鎖定之小白球
                if best_ball is not None:
                    bx, by, bw, bh = best_ball
                    ball_abs_x = rx + bx
                    ball_abs_y = ry + by
                    cv2.rectangle(disp_bgr, (ball_abs_x, ball_abs_y), (ball_abs_x + bw, ball_abs_y + bh), (0, 255, 0), 2)
                    cv2.circle(disp_bgr, (ball_abs_x + bw // 2, ball_abs_y + bh // 2), max(bw, bh) // 2 + 3, (0, 255, 0), 2)
                    cv2.putText(disp_bgr, "BALL", (ball_abs_x, max(20, ball_abs_y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # 3. 繪製好球帶標籤
                if is_hit or is_recent_swing:
                    cv2.putText(disp_bgr, "💥 SWING! (HIT)", (rx, max(40, ry - 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 3)
                elif "白褲子" in target_desc or "過大" in target_desc:
                    cv2.putText(disp_bgr, "FILTERED PANTS", (rx, max(25, ry - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2)
                else:
                    cv2.putText(disp_bgr, f"ZONE ({rx},{ry})", (rx, max(25, ry - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2)

                # 4. 繪製揮棒點擊目標標記 (靶心圖示)
                swing_color = (0, 215, 255) if is_recent_swing else (0, 0, 240)
                cv2.circle(disp_bgr, (sw_x, sw_y), 18, swing_color, 2)
                cv2.circle(disp_bgr, (sw_x, sw_y), 5, swing_color, -1)
                cv2.line(disp_bgr, (sw_x - 24, sw_y), (sw_x + 24, sw_y), swing_color, 2)
                cv2.line(disp_bgr, (sw_x, sw_y - 24), (sw_x, sw_y + 24), swing_color, 2)
                sw_tag = "💥 CLICK!" if is_recent_swing else f"揮棒點 ({sw_x},{sw_y})"
                cv2.putText(disp_bgr, sw_tag, (sw_x + 20, max(25, sw_y + 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, swing_color, 2)

            elif mode == "roi" and self.current_roi_bgr is not None:
                disp_bgr = self.current_roi_bgr.copy()
                if is_hit or is_recent_swing:
                    cv2.rectangle(disp_bgr, (0, 0), (disp_bgr.shape[1] - 1, disp_bgr.shape[0] - 1), (0, 255, 0), 4)
                    cv2.putText(disp_bgr, "SWING!", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                elif best_ball is not None:
                    bx, by, bw, bh = best_ball
                    cv2.rectangle(disp_bgr, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
                    cv2.circle(disp_bgr, (bx + bw // 2, by + bh // 2), max(bw, bh) // 2 + 2, (0, 255, 0), 2)
                    cv2.putText(disp_bgr, "BALL", (bx, max(15, by - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            elif mode == "mask" and self.current_mask_img is not None:
                disp_bgr = cv2.cvtColor(self.current_mask_img, cv2.COLOR_GRAY2BGR)
                if best_ball is not None:
                    bx, by, bw, bh = best_ball
                    cv2.rectangle(disp_bgr, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
            else:
                if self.current_full_bgr is not None:
                    disp_bgr = self.current_full_bgr.copy()
                else:
                    return

            # 等比縮放適應 Canvas
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw < 50 or ch < 50:
                cw, ch = self.canvas_w, self.canvas_h

            h, w = disp_bgr.shape[:2]
            scale = min(cw / max(1, w), ch / max(1, h))
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))

            self.render_scale = scale
            self.pad_x = (cw - new_w) // 2
            self.pad_y = (ch - new_h) // 2

            resized = cv2.resize(disp_bgr, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            self.preview_photo = ImageTk.PhotoImage(image=pil_img)

            self.canvas.delete("all")
            self.canvas.create_image(cw // 2, ch // 2, image=self.preview_photo, anchor=tk.CENTER)
        except Exception:
            pass

    # =========================================================================
    # 事件處理
    # =========================================================================
    def on_toggle_engine(self):
        """切換啟動/停止打擊輔助"""
        if not self.engine.is_running:
            self.on_apply_config()
            self.engine.start()
            self.btn_toggle.config(text="⏹ 停止打擊輔助 (F8)", bg="#dc2626")
            self.lbl_status_badge.config(text="🟢 打擊輔助運作中 (按 F8 暫停)", fg="#22c55e")
        else:
            self.engine.stop()
            self.btn_toggle.config(text="▶ 啟動打擊輔助 (F8)", bg="#16a34a")
            self.lbl_status_badge.config(text="⏸ 打擊輔助已停止", fg="#ef4444")

    def on_preset_changed(self, event=None):
        """使用者選擇預設演算法"""
        sel = self.var_preset.get().split(":")[0].strip()
        if sel in ALGO_PRESETS:
            self.engine.apply_preset(sel)
            preset = ALGO_PRESETS[sel]
            self.var_h_min.set(preset["hsv_h_min"])
            self.var_h_max.set(preset["hsv_h_max"])
            self.var_s_min.set(preset["hsv_s_min"])
            self.var_s_max.set(preset["hsv_s_max"])
            self.var_v_min.set(preset["hsv_v_min"])
            self.var_v_max.set(preset["hsv_v_max"])
            min_area = preset.get("min_ball_area", preset.get("min_trigger_pixels", 12))
            max_area = preset.get("max_ball_area", preset.get("max_trigger_pixels", 220))
            self.var_min_px.set(min_area)
            self.var_max_px.set(max_area)
            if "motion_diff_thresh" in preset:
                self.var_diff_th.set(preset["motion_diff_thresh"])
            desc = PRESET_DESCRIPTIONS.get(sel, "")
            self.var_preset_desc.set(desc)
            self._log(f"已套用打擊範本: {preset['name']}")
            self._redraw_current_frame()

    def on_apply_config(self):
        """將 UI 上的值即時同步至引擎"""
        c = self.engine.config
        c["capture_mode"] = self.var_capture_mode.get()
        c["target_fps"] = self.var_target_fps.get()
        c["roi_x"] = self.var_roi_x.get()
        c["roi_y"] = self.var_roi_y.get()
        c["roi_w"] = self.var_roi_w.get()
        c["roi_h"] = self.var_roi_h.get()

        # 揮棒點擊座標
        sw_x = self.var_swing_x.get()
        sw_y = self.var_swing_y.get()
        c["swing_x"] = sw_x
        c["swing_y"] = sw_y
        c["mouse_click_x"] = sw_x
        c["mouse_click_y"] = sw_y
        c["adb_tap_x"] = sw_x
        c["adb_tap_y"] = sw_y

        c["hsv_h_min"] = self.var_h_min.get()
        c["hsv_h_max"] = self.var_h_max.get()
        c["hsv_s_min"] = self.var_s_min.get()
        c["hsv_s_max"] = self.var_s_max.get()
        c["hsv_v_min"] = self.var_v_min.get()
        c["hsv_v_max"] = self.var_v_max.get()

        min_px = self.var_min_px.get()
        max_px = self.var_max_px.get()
        c["min_ball_area"] = min_px
        c["max_ball_area"] = max_px
        c["min_trigger_pixels"] = min_px
        c["max_trigger_pixels"] = max_px

        c["motion_diff_thresh"] = self.var_diff_th.get()

        c["timing_offset_ms"] = self.var_timing_offset.get()
        c["cooldown_ms"] = self.var_cooldown.get()

        c["input_mode"] = self._get_current_input_mode_code()
        c["directinput_key"] = self.var_directinput_key.get()

    def on_save_config_file(self):
        """儲存打擊設定到檔案"""
        self.on_apply_config()
        self.engine.save_config()
        messagebox.showinfo("成功", "打擊輔助設定已成功儲存！")

    def on_reset_defaults(self):
        """重設為預設值"""
        if messagebox.askyesno("確認", "確定要將打擊輔助恢復為原廠設定嗎？"):
            self.engine.config = dict(DEFAULT_CONFIG)
            self.engine.save_config()
            self._reload_vars_from_config()
            self._redraw_current_frame()

    def _reload_vars_from_config(self):
        """從引擎重新整理變數到 UI"""
        c = self.engine.config
        curr_p = c.get("preset_name", "white_ball")
        if curr_p in ALGO_PRESETS:
            self.var_preset.set(f"{curr_p}: {ALGO_PRESETS[curr_p]['name']}")
        else:
            self.var_preset.set(curr_p)
        self.var_preset_desc.set(PRESET_DESCRIPTIONS.get(curr_p, ""))

        curr_in = c.get("input_mode", "window_click")
        in_name = next((name for code, name in INPUT_MODES if code == curr_in), INPUT_MODES[0][1])
        self.var_input_mode_display.set(in_name)
        self.var_input_tip.set(INPUT_MODE_TIPS.get(curr_in, ""))

        self.var_capture_mode.set(c.get("capture_mode", "window_lock"))
        self.var_target_fps.set(c.get("target_fps", 60))
        self.var_roi_x.set(c.get("roi_x", 700))
        self.var_roi_y.set(c.get("roi_y", 560))
        self.var_roi_w.set(c.get("roi_w", 180))
        self.var_roi_h.set(c.get("roi_h", 160))

        self.var_swing_x.set(c.get("swing_x", 1380))
        self.var_swing_y.set(c.get("swing_y", 720))

        self.var_h_min.set(c.get("hsv_h_min", 0))
        self.var_h_max.set(c.get("hsv_h_max", 180))
        self.var_s_min.set(c.get("hsv_s_min", 0))
        self.var_s_max.set(c.get("hsv_s_max", 75))
        self.var_v_min.set(c.get("hsv_v_min", 175))
        self.var_v_max.set(c.get("hsv_v_max", 255))
        self.var_min_px.set(c.get("min_ball_area", c.get("min_trigger_pixels", 12)))
        self.var_max_px.set(c.get("max_ball_area", c.get("max_trigger_pixels", 220)))
        self.var_diff_th.set(c.get("motion_diff_thresh", 25))
        self.var_timing_offset.set(c.get("timing_offset_ms", 0))
        self.var_cooldown.set(c.get("cooldown_ms", 1200))
        self.var_directinput_key.set(c.get("directinput_key", "space"))

    def _on_telemetry_update(self, tele: Dict[str, Any]):
        """背景線程推送的效能與狀態更新"""
        self.parent.after(0, self._render_telemetry, tele)

    def _render_telemetry(self, tele: Dict[str, Any]):
        self.var_fps_text.set(f"FPS: {tele.get('fps', 0.0):.1f}")
        self.var_latency_text.set(
            f"延遲: 截圖 {tele.get('capture_ms', 0.0):.1f}ms | 運算 {tele.get('process_ms', 0.0):.2f}ms"
        )
        self.var_pixels_text.set(f"命中像素: {tele.get('matched_pixels', 0)} px")
        self.var_swings_text.set(
            f"擊球: {tele.get('total_swings', 0)} 次 ({tele.get('last_swing', '--')})"
        )

        desc = tele.get("target_desc", "")
        if desc:
            self.var_target_desc.set(desc)
            if "白褲子" in desc or "過大" in desc:
                self.lbl_target_desc.config(fg="#fb923c", bg="#7c2d12")
            elif "鎖定" in desc or "⚾" in desc or "🟡" in desc:
                self.lbl_target_desc.config(fg="#4ade80", bg="#14532d")
            else:
                self.lbl_target_desc.config(fg="#38bdf8", bg="#0c4a6e")

        if not self.engine.is_running:
            self.lbl_status_badge.config(text="⏸ 打擊輔助未啟動", fg="#ef4444")
        elif not tele.get("is_active", True):
            self.lbl_status_badge.config(text="⏸ 已暫停 (按 F8 恢復)", fg="#f59e0b")
        else:
            self.lbl_status_badge.config(text="🟢 打擊輔助運作中 (按 F8 暫停)", fg="#22c55e")

    def _on_swing_event(self, event_data: Dict[str, Any]):
        """觸發擊球瞬間閃爍動畫"""
        self._swing_flash_timer = time.perf_counter()

    def on_theme_changed(self, mode: str):
        """全域主題切換時動態更新預覽畫布與狀態標籤"""
        p = get_theme_palette(mode)
        try:
            if hasattr(self, "canvas"):
                self.canvas.configure(bg=p["preview_bg"])
            if hasattr(self, "lbl_status_badge"):
                self.lbl_status_badge.configure(bg=p["bg"])
        except Exception:
            pass

    def on_close(self):
        """視窗關閉時釋放資源"""
        if self.engine:
            self.engine.stop()
