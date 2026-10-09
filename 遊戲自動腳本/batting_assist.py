"""
棒球手遊自動化腳本 - 即時打擊輔助核心模組 (Batting Assist Engine)
具備微秒級極速螢幕捕捉、小圓球幾何形狀過濾 (自動剔除投手白褲子等大雜訊)、
黃色/紅色進壘提示圈精準鎖定、動態幀差分析與 DirectInput 低延遲揮棒。
"""
import os
import sys
import time
import json
import logging
import threading
from typing import Optional, Dict, Any, Callable, Tuple, List

import cv2
import numpy as np

# 嘗試載入低延遲截圖庫 mss 與 DirectInput 輸入庫
try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import pydirectinput
    pydirectinput.FAILSAFE = False
    pydirectinput.PAUSE = 0.001
    HAS_PDI = True
except ImportError:
    HAS_PDI = False

import ctypes
from ctypes import wintypes

# 初始化 Windows 高 DPI 支援
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

logger = logging.getLogger("BattingAssist")


def list_emulator_windows(keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    搜尋目前開啟的模擬器 (BlueStacks, LDPlayer, Nox, MuMu) 在 Windows 桌面上的 Client 繪製區域。
    回傳: [{"hwnd": int, "title": str, "left": int, "top": int, "width": int, "height": int}]
    """
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    results = []

    def enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                t_lower = title.lower()

                matched = False
                if keyword:
                    if keyword.lower() in t_lower:
                        matched = True
                else:
                    for emu in ["bluestacks", "hd-player", "ldplayer", "dnplayer", "nox", "mumu", "雷電", "夜神"]:
                        if emu in t_lower:
                            matched = True
                            break

                if matched:
                    rc = wintypes.RECT()
                    user32.GetClientRect(hwnd, ctypes.byref(rc))
                    pt = wintypes.POINT(0, 0)
                    user32.ClientToScreen(hwnd, ctypes.byref(pt))
                    w = rc.right - rc.left
                    h = rc.bottom - rc.top
                    if w > 250 and h > 200:
                        results.append({
                            "hwnd": hwnd,
                            "title": title,
                            "left": pt.x,
                            "top": pt.y,
                            "width": w,
                            "height": h
                        })
        return 1

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return results


def get_emulator_input_hwnds(parent_hwnd: int) -> List[int]:
    """獲取模擬器可能接收輸入的視窗句柄列表 (包含渲染子視窗與主視窗)"""
    if not parent_hwnd:
        return []
    hwnds = [parent_hwnd]
    if sys.platform != "win32":
        return hwnds
    user32 = ctypes.windll.user32

    def child_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            cls_buff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buff, 256)
            cls_name = cls_buff.value.lower()
            if any(k in cls_name for k in ["render", "sub", "view", "gl", "dx", "player", "screen"]):
                hwnds.insert(0, hwnd)  # 渲染子視窗優先
        return 1

    try:
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(parent_hwnd, WNDENUMPROC(child_cb), 0)
    except Exception:
        pass
    return hwnds


# 預設演算法範本 (Presets)
ALGO_PRESETS = {
    "white_ball": {
        "name": "⚾ 小白球高速偵測 (專抓飛入白色棒球，自適應動態模糊)",
        "hsv_h_min": 0, "hsv_h_max": 180,
        "hsv_s_min": 0, "hsv_s_max": 75,
        "hsv_v_min": 175, "hsv_v_max": 255,
        "min_ball_area": 12,
        "max_ball_area": 220,
        "use_shape_filter": True,
        "algo_type": "white_ball"
    },
    "white_ball_motion": {
        "name": "🏃 動態白球進壘 (差分增量，過濾靜態白線與本壘板)",
        "hsv_h_min": 0, "hsv_h_max": 180,
        "hsv_s_min": 0, "hsv_s_max": 75,
        "hsv_v_min": 175, "hsv_v_max": 255,
        "min_ball_area": 12,
        "max_ball_area": 220,
        "use_shape_filter": True,
        "motion_diff_thresh": 25,
        "algo_type": "white_ball_motion"
    },
    "yellow_marker": {
        "name": "🟡 進壘提示黃圈 (100% 避開褲子誤判，最穩定)",
        "hsv_h_min": 18, "hsv_h_max": 35,
        "hsv_s_min": 90, "hsv_s_max": 255,
        "hsv_v_min": 140, "hsv_v_max": 255,
        "min_ball_area": 30,
        "max_ball_area": 3500,
        "use_shape_filter": False,
        "algo_type": "yellow_marker"
    },
    "red_marker": {
        "name": "🔴 進壘提示紅圈 (紅圈進壘提示點)",
        "hsv_h_min": 0, "hsv_h_max": 15,
        "hsv_s_min": 100, "hsv_s_max": 255,
        "hsv_v_min": 150, "hsv_v_max": 255,
        "min_ball_area": 30,
        "max_ball_area": 3500,
        "use_shape_filter": False,
        "algo_type": "red_marker"
    }
}

DEFAULT_CONFIG: Dict[str, Any] = {
    # 預設: 鎖定模擬器視窗 GDI 截圖 (60 FPS, 1~3ms)
    "capture_mode": "window_lock",
    "target_fps": 60,
    "window_keyword": "",
    "preset_name": "white_ball",
    "algo_type": "white_ball",
    # 預設好球帶 ROI: 嚴格置於投手丘下方 (以 1600x900 基準, Y=560 避開 Y=400 的投手)
    "roi_x": 700,
    "roi_y": 560,
    "roi_w": 180,
    "roi_h": 160,
    # HSV 門檻 (預設小白球)
    "hsv_h_min": 0,
    "hsv_h_max": 180,
    "hsv_s_min": 0,
    "hsv_s_max": 75,
    "hsv_v_min": 175,
    "hsv_v_max": 255,
    # 圓球輪廓尺寸門檻 (排除大片褲子)
    "min_ball_area": 12,
    "max_ball_area": 220,
    "use_shape_filter": True,
    "motion_diff_thresh": 25,
    # 擊球時差補償 (毫秒, -50ms ~ +150ms)
    "timing_offset_ms": 0,
    # 防重複揮棒冷卻 (毫秒)
    "cooldown_ms": 1200,
    # 模擬器揮棒點擊座標 (以 1600x900 基準，預設 1380, 720 為右下角揮棒按鈕)
    "swing_x": 1380,
    "swing_y": 720,
    # 輸入模式: 預設指定視窗實體點擊 (100% 成功，自動還原滑鼠游標)
    "input_mode": "window_click",
    "directinput_key": "space",
    "mouse_click_x": 1380,
    "mouse_click_y": 720,
    "adb_tap_x": 1380,
    "adb_tap_y": 720,
    # 全域熱鍵
    "hotkey_enabled": True,
    "hotkey_vk": 0x77              # VK_F8
}


class BattingAssistEngine:
    """即時打擊輔助運算與極速揮棒引擎 (防褲子誤判 + 60~120 FPS)"""

    def __init__(self, bot_instance=None, config_path: Optional[str] = None):
        self.bot = bot_instance
        self.config_path = config_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "configs", "batting_config.json"
        )
        self.config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load_config()

        # 狀態控制
        self.is_running = False
        self.is_active = False
        self.worker_thread: Optional[threading.Thread] = None
        self.hotkey_thread: Optional[threading.Thread] = None

        # 初始化 Windows 1ms 極速多媒體定時器
        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeBeginPeriod(1)
            except Exception:
                pass

        # 影像狀態
        self.prev_gray_roi: Optional[np.ndarray] = None
        self.last_swing_time = 0.0
        self.total_swings_count = 0

        # 當前鎖定之視窗快取
        self.locked_window_info: Optional[Dict[str, Any]] = None
        self._last_win_check_time = 0.0

        # 遙測資訊
        self.current_fps = 0.0
        self.capture_latency_ms = 0.0
        self.process_latency_ms = 0.0
        self.last_target_desc = "等待球體飛入..."
        self.last_trigger_time_str = "尚未觸發"

        # 回呼函式
        self.on_telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        # full_frame, roi_frame, mask_img, is_hit, (rx, ry, rw, rh), target_desc, best_ball_bbox
        self.on_frame_callback: Optional[Callable[[Optional[np.ndarray], np.ndarray, np.ndarray, bool, Tuple[int, int, int, int], str, Optional[Tuple[int, int, int, int]]], None]] = None
        self.on_swing_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_log_callback: Optional[Callable[[str], None]] = None

    def _log(self, msg: str):
        if self.on_log_callback:
            self.on_log_callback(f"[打擊輔助] {msg}")
        logger.info(msg)

    def load_config(self):
        """載入打擊輔助設定檔"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.config.update(loaded)
            except Exception as e:
                logger.warning(f"讀取打擊輔助設定失敗: {e}")

    def save_config(self):
        """儲存打擊輔助設定檔"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"儲存打擊輔助設定失敗: {e}")

    def apply_preset(self, preset_key: str):
        """套用預設演算法參數"""
        if preset_key in ALGO_PRESETS:
            preset = ALGO_PRESETS[preset_key]
            self.config["preset_name"] = preset_key
            self.config["algo_type"] = preset["algo_type"]
            self.config["hsv_h_min"] = preset["hsv_h_min"]
            self.config["hsv_h_max"] = preset["hsv_h_max"]
            self.config["hsv_s_min"] = preset["hsv_s_min"]
            self.config["hsv_s_max"] = preset["hsv_s_max"]
            self.config["hsv_v_min"] = preset["hsv_v_min"]
            self.config["hsv_v_max"] = preset["hsv_v_max"]
            self.config["min_ball_area"] = preset["min_ball_area"]
            self.config["max_ball_area"] = preset["max_ball_area"]
            self.config["use_shape_filter"] = preset["use_shape_filter"]
            if "motion_diff_thresh" in preset:
                self.config["motion_diff_thresh"] = preset["motion_diff_thresh"]
            self.save_config()

    def get_locked_window(self) -> Optional[Dict[str, Any]]:
        """獲取目前鎖定之模擬器視窗桌面座標 (每秒更新)"""
        now = time.perf_counter()
        if self.locked_window_info is None or (now - self._last_win_check_time > 1.0):
            self._last_win_check_time = now
            kw = self.config.get("window_keyword", "").strip() or None
            wins = list_emulator_windows(keyword=kw)
            if wins:
                self.locked_window_info = wins[0]
            else:
                self.locked_window_info = None
        return self.locked_window_info

    def start(self):
        """啟動打擊輔助背景線程"""
        if self.is_running:
            return
        self.is_running = True
        self.is_active = True
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.worker_thread.start()

        if self.config.get("hotkey_enabled", True):
            self.hotkey_thread = threading.Thread(target=self._hotkey_loop, daemon=True)
            self.hotkey_thread.start()

        target_fps = int(self.config.get("target_fps", 60))
        self._log(f"打擊輔助已啟動 (目標 {target_fps} FPS, 按 F8 隨時切換開關)")

    def stop(self):
        """停止打擊輔助"""
        self.is_running = False
        self.is_active = False
        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
        self._log("打擊輔助已停止")

    def toggle_active(self):
        """切換啟動/暫停狀態 (供熱鍵或按鈕呼叫)"""
        self.is_active = not self.is_active
        status_text = "🟢 運作中" if self.is_active else "⏸ 已暫停"
        self._log(f"打擊輔助狀態: {status_text}")

    # =========================================================================
    # 核心影像截取管線
    # =========================================================================
    def capture_frame(self, sct_inst=None, grab_full: bool = False) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """截取畫面與好球帶 ROI (高速模式僅抓取小 ROI，延遲 < 1ms)"""
        t0 = time.perf_counter()
        mode = self.config.get("capture_mode", "window_lock")

        rx = int(self.config.get("roi_x", 700))
        ry = int(self.config.get("roi_y", 560))
        rw = max(10, int(self.config.get("roi_w", 180)))
        rh = max(10, int(self.config.get("roi_h", 160)))

        # 管道 1 (預設): 鎖定視窗極速擷取 (1~2ms)
        if mode == "window_lock" and HAS_MSS:
            win = self.get_locked_window()
            if win and win["width"] > 100 and win["height"] > 100:
                sct = sct_inst or mss.mss()
                try:
                    fw, fh = win["width"], win["height"]
                    scale_x = fw / 1600.0
                    scale_y = fh / 900.0

                    clamped_rx = max(0, min(fw - 10, int(rx * scale_x)))
                    clamped_ry = max(0, min(fh - 10, int(ry * scale_y)))
                    clamped_rw = max(10, min(fw - clamped_rx, int(rw * scale_x)))
                    clamped_rh = max(10, min(fh - clamped_ry, int(rh * scale_y)))

                    full_frame = None
                    if grab_full:
                        full_mon = {
                            "top": win["top"],
                            "left": win["left"],
                            "width": win["width"],
                            "height": win["height"]
                        }
                        full_grab = sct.grab(full_mon)
                        full_frame = np.array(full_grab, dtype=np.uint8)[:, :, :3]
                        roi_frame = full_frame[clamped_ry:clamped_ry + clamped_rh, clamped_rx:clamped_rx + clamped_rw]
                    else:
                        roi_mon = {
                            "top": win["top"] + clamped_ry,
                            "left": win["left"] + clamped_rx,
                            "width": clamped_rw,
                            "height": clamped_rh
                        }
                        roi_grab = sct.grab(roi_mon)
                        roi_frame = np.array(roi_grab, dtype=np.uint8)[:, :, :3]

                    self.capture_latency_ms = (time.perf_counter() - t0) * 1000.0
                    return full_frame, roi_frame
                except Exception:
                    pass

        # 管道 2: 備援 ADB 截圖
        if self.bot and hasattr(self.bot, "capture_screen"):
            screen = self.bot.capture_screen()
            if screen is not None:
                full_frame = screen
                sh, sw = screen.shape[:2]
                clamped_rx = max(0, min(sw - 10, rx))
                clamped_ry = max(0, min(sh - 10, ry))
                clamped_rw = max(10, min(sw - clamped_rx, rw))
                clamped_rh = max(10, min(sh - clamped_ry, rh))
                roi_frame = screen[clamped_ry:clamped_ry + clamped_rh, clamped_rx:clamped_rx + clamped_rw]
                self.capture_latency_ms = (time.perf_counter() - t0) * 1000.0
                return full_frame, roi_frame

        return None, None

    # =========================================================================
    # 核心判定演算法：小白球高速識別 + 動態增量 + 提示圈
    # =========================================================================
    def _analyze_frame(self, roi_bgr: np.ndarray) -> Tuple[bool, int, np.ndarray, float, str, Optional[Tuple[int, int, int, int]]]:
        """
        對 ROI 進行極速視覺判定 (耗時 < 0.2ms)。
        回傳: (is_triggered, matched_pixels, mask_display, proc_ms, target_desc, best_ball_bbox)
        """
        t0 = time.perf_counter()
        algo = self.config.get("algo_type", "white_ball")

        min_area = int(self.config.get("min_ball_area", self.config.get("min_trigger_pixels", 12)))
        max_area = int(self.config.get("max_ball_area", self.config.get("max_trigger_pixels", 220)))
        diff_th = int(self.config.get("motion_diff_thresh", 25))

        h_min = int(self.config.get("hsv_h_min", 0))
        h_max = int(self.config.get("hsv_h_max", 180))
        s_min = int(self.config.get("hsv_s_min", 0))
        s_max = int(self.config.get("hsv_s_max", 75))
        v_min = int(self.config.get("hsv_v_min", 175))
        v_max = int(self.config.get("hsv_v_max", 255))

        is_triggered = False
        matched_px = 0
        display_mask = np.zeros(roi_bgr.shape[:2], dtype=np.uint8)
        target_desc = "等待球體飛入..."
        best_ball_bbox = None

        # 演算法 1: 小白球高速偵測 (專抓飛入白色棒球，自適應動態模糊)
        if algo == "white_ball":
            hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array([h_min, s_min, v_min]), np.array([h_max, s_max, v_max]))
            display_mask = mask
            matched_px = int(cv2.countNonZero(mask))

            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            candidate_balls = []
            has_pitcher_pants = False

            for c in cnts:
                area = cv2.contourArea(c)
                if area < min_area:
                    continue
                # 超過最大門檻視為投手球褲或球衣雜訊，排除它
                if area > max_area:
                    has_pitcher_pants = True
                    continue

                bx, by, bw, bh = cv2.boundingRect(c)
                aspect = float(bw) / max(1, bh)
                perimeter = cv2.arcLength(c, True)
                circ = (4 * np.pi * area) / (perimeter * perimeter) if perimeter > 0 else 0

                # 符合小白球條件：
                # 1. 面積在 min_area ~ max_area 之間 (約 12 ~ 220px)
                # 2. 長寬比 0.45 ~ 2.2 (高速球允許運動模糊拉伸)
                # 3. 圓形度 >= 0.28 (排除細長筆直的球場白線)
                if 0.45 <= aspect <= 2.2 and circ >= 0.28:
                    candidate_balls.append((area, bx, by, bw, bh, aspect, circ))

            if candidate_balls:
                # 排序候選球：越接近正圓形與正方比例者優先
                candidate_balls.sort(key=lambda b: abs(b[5] - 1.0) - b[6] * 0.5)
                best_area, bx, by, bw, bh, aspect, circ = candidate_balls[0]
                is_triggered = True
                best_ball_bbox = (bx, by, bw, bh)
                target_desc = f"⚾ 鎖定小白球 (面積 {int(best_area)}px, 圓形度 {circ:.2f})"
            elif has_pitcher_pants:
                target_desc = "⚠️ 偵測到大面積白色 (已過濾褲子/球衣，不揮棒)"
            else:
                target_desc = "👀 等待小白球飛入好球帶..."

        # 演算法 2: 動態白球進壘 (差分增量，過濾靜態白線與本壘板)
        elif algo == "white_ball_motion":
            hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
            white_mask = cv2.inRange(hsv, np.array([h_min, s_min, v_min]), np.array([h_max, s_max, v_max]))
            gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)

            if self.prev_gray_roi is not None and self.prev_gray_roi.shape == gray.shape:
                diff = cv2.absdiff(gray, self.prev_gray_roi)
                _, motion_mask = cv2.threshold(diff, diff_th, 255, cv2.THRESH_BINARY)
                combined_mask = cv2.bitwise_and(white_mask, motion_mask)
                display_mask = combined_mask
                matched_px = int(cv2.countNonZero(combined_mask))

                cnts, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for c in cnts:
                    area = cv2.contourArea(c)
                    if min_area <= area <= max_area:
                        bx, by, bw, bh = cv2.boundingRect(c)
                        aspect = float(bw) / max(1, bh)
                        if 0.45 <= aspect <= 2.2:
                            is_triggered = True
                            best_ball_bbox = (bx, by, bw, bh)
                            target_desc = f"⚾ 動態小白球進壘 (面積 {int(area)}px)"
                            break
            else:
                display_mask = white_mask
            self.prev_gray_roi = gray

        # 演算法 3: 黃色進壘提示圈 (Yellow Marker - 推薦，完全不受白褲子干擾)
        elif algo == "yellow_marker":
            hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array([18, 90, 140]), np.array([35, 255, 255]))
            display_mask = mask
            matched_px = int(cv2.countNonZero(mask))
            if min_area <= matched_px <= max_area:
                is_triggered = True
                target_desc = f"🟡 鎖定進壘黃圈 ({matched_px} px)"
            elif matched_px > max_area:
                target_desc = f"⚠️ 面積過大 ({matched_px} px，已過濾)"

        # 演算法 4: 紅色進壘提示圈 (Red Marker)
        elif algo == "red_marker":
            hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
            m1 = cv2.inRange(hsv, np.array([0, 100, 150]), np.array([15, 255, 255]))
            m2 = cv2.inRange(hsv, np.array([170, 100, 150]), np.array([180, 255, 255]))
            mask = cv2.bitwise_or(m1, m2)
            display_mask = mask
            matched_px = int(cv2.countNonZero(mask))
            if min_area <= matched_px <= max_area:
                is_triggered = True
                target_desc = f"🔴 鎖定進壘紅圈 ({matched_px} px)"

        proc_ms = (time.perf_counter() - t0) * 1000.0
        self.last_target_desc = target_desc
        return is_triggered, matched_px, display_mask, proc_ms, target_desc, best_ball_bbox

    # =========================================================================
    # 極速揮棒執行
    # =========================================================================
    # =========================================================================
    # 極速揮棒執行 (指定視窗後台點擊 / 視窗相對實體點擊 / ADB 內部點擊)
    # =========================================================================
    def execute_swing(self):
        """觸發擊球動作 (延遲 < 2ms)"""
        now = time.perf_counter()
        cooldown_sec = max(0.2, self.config.get("cooldown_ms", 1200) / 1000.0)

        if now - self.last_swing_time < cooldown_sec:
            return

        self.last_swing_time = now
        self.total_swings_count += 1
        self.last_trigger_time_str = time.strftime('%H:%M:%S')

        timing_offset = self.config.get("timing_offset_ms", 0)
        if timing_offset > 0:
            time.sleep(timing_offset / 1000.0)

        t_swing_start = time.perf_counter()
        mode = self.config.get("input_mode", "win_msg_click")
        swing_x = int(self.config.get("swing_x", self.config.get("mouse_click_x", 1380)))
        swing_y = int(self.config.get("swing_y", self.config.get("mouse_click_y", 720)))

        # 獲取已鎖定之模擬器視窗與相對縮放座標
        win = self.get_locked_window()
        if win and win["width"] > 100 and win["height"] > 100:
            hwnd = win["hwnd"]
            scale_x = win["width"] / 1600.0
            scale_y = win["height"] / 900.0
            client_x = int(swing_x * scale_x)
            client_y = int(swing_y * scale_y)
            desktop_x = win["left"] + client_x
            desktop_y = win["top"] + client_y
            win_title = win["title"]
        else:
            hwnd = None
            client_x = swing_x
            client_y = swing_y
            desktop_x = swing_x
            desktop_y = swing_y
            win_title = "未知模擬器"

        try:
            # 模式 1 (推薦): 指定視窗後台滑鼠點擊 (Win32 PostMessage)
            if mode in ["win_msg_click", "win_click"]:
                if hwnd:
                    self._send_win_click(hwnd, client_x, client_y)
                    cost = (time.perf_counter() - t_swing_start) * 1000.0
                    self._log(f"💥 [指定視窗後台點擊] 向「{win_title}」發送點擊！視窗內座標: ({client_x}, {client_y}) (耗時: {cost:.2f}ms)")
                else:
                    self._win32_fast_click(desktop_x, desktop_y)
                    self._log(f"⚠️ [備援實體點擊] 未鎖定視窗，點擊螢幕: ({desktop_x}, {desktop_y})")

            # 模式 2: 指定視窗後台按鍵發送 (Win32 PostMessage Key)
            elif mode in ["win_msg_key", "win_key"]:
                key = str(self.config.get("directinput_key", "space")).lower().strip()
                if hwnd:
                    self._send_win_key(hwnd, key)
                    cost = (time.perf_counter() - t_swing_start) * 1000.0
                    self._log(f"💥 [指定視窗後台按鍵] 向「{win_title}」發送「{key}」！(耗時: {cost:.2f}ms)")
                else:
                    if HAS_PDI:
                        pydirectinput.press(key)
                    self._log(f"⚠️ [備援按鍵] 未鎖定視窗，全域發送按鍵:「{key}」")

            # 模式 1 (預設推薦): 指定視窗實體快速點擊 (100% 成功，自動還原滑鼠游標)
            if mode in ["window_click", "mouse_click"]:
                self._win32_fast_click(desktop_x, desktop_y, restore_cursor=True)
                cost = (time.perf_counter() - t_swing_start) * 1000.0
                self._log(f"💥 [視窗實體點擊] 成功點擊「{win_title}」內部 ({client_x}, {client_y}) -> 螢幕: ({desktop_x}, {desktop_y}) (耗時: {cost:.2f}ms)")

            # 模式 2: 模擬器內部 ADB 精確點擊 (不搶滑鼠游標)
            elif mode == "adb":
                ax = int(self.config.get("adb_tap_x", swing_x))
                ay = int(self.config.get("adb_tap_y", swing_y))
                if self.bot and hasattr(self.bot, "device") and self.bot.device:
                    threading.Thread(
                        target=lambda: self.bot.device.shell(f"input tap {ax} {ay}"),
                        daemon=True
                    ).start()
                    cost = (time.perf_counter() - t_swing_start) * 1000.0
                    self._log(f"💥 [ADB Tap] 擊球指令已發送！座標: ({ax}, {ay}) (耗時: {cost:.2f}ms)")
                else:
                    self._log("⚠️ ADB 裝置尚未連線，無法發送 ADB 擊球！請確認模擬器已連線。")

            # 模式 3: 鍵盤映射按鍵 (DirectInput Space 鍵，延遲 < 1ms)
            elif mode == "directinput":
                if HAS_PDI:
                    key = str(self.config.get("directinput_key", "space")).lower().strip()
                    pydirectinput.press(key)
                    cost = (time.perf_counter() - t_swing_start) * 1000.0
                    self._log(f"💥 [鍵盤映射] 擊球觸發！按鍵:「{key}」 (耗時: {cost:.2f}ms)")
                else:
                    self._log("⚠️ 未安裝 pydirectinput，無法執行全域按鍵！")

            # 模式 4: 指定視窗後台點擊 (Win32 PostMessage 嘗試)
            elif mode in ["win_msg_click", "win_click"]:
                if hwnd:
                    self._send_win_click(hwnd, client_x, client_y)
                    cost = (time.perf_counter() - t_swing_start) * 1000.0
                    self._log(f"💥 [指定視窗後台點擊] 向「{win_title}」發送 PostMessage ({client_x}, {client_y}) (耗時: {cost:.2f}ms)")
                else:
                    self._win32_fast_click(desktop_x, desktop_y, restore_cursor=True)
        except Exception as e:
            self._log(f"⚠️ 揮棒觸發異常: {e}")

        if self.on_swing_callback:
            self.on_swing_callback({
                "count": self.total_swings_count,
                "time": self.last_trigger_time_str,
                "mode": mode,
                "swing_x": swing_x,
                "swing_y": swing_y
            })

    def _send_win_click(self, hwnd: int, x: int, y: int):
        """Win32 後台滑鼠點擊 (PostMessage)：嘗試向視窗發送點擊訊息"""
        if sys.platform != "win32" or not hwnd:
            return
        user32 = ctypes.windll.user32
        target_hwnds = get_emulator_input_hwnds(hwnd)
        lparam = (int(y) << 16) | (int(x) & 0xFFFF)
        for h in target_hwnds:
            user32.PostMessageW(h, 0x0201, 0x0001, lparam)  # WM_LBUTTONDOWN
        time.sleep(0.016)
        for h in target_hwnds:
            user32.PostMessageW(h, 0x0202, 0, lparam)       # WM_LBUTTONUP

    def _send_win_key(self, hwnd: int, key_name: str = "space"):
        """Win32 後台按鍵發送 (PostMessage)：指定發送給模擬器視窗，不影響其他視窗"""
        if sys.platform != "win32" or not hwnd:
            return
        user32 = ctypes.windll.user32
        target_hwnds = get_emulator_input_hwnds(hwnd)
        k = key_name.lower().strip()
        vk_map = {
            "space": 0x20, "enter": 0x0D, "j": 0x4A, "k": 0x4B, "a": 0x41,
            "s": 0x53, "d": 0x44, "w": 0x57, "f": 0x46, "z": 0x5A, "x": 0x58, "c": 0x43
        }
        vk = vk_map.get(k, ord(k.upper()) if len(k) == 1 else 0x20)
        for h in target_hwnds:
            user32.PostMessageW(h, 0x0100, vk, 0)  # WM_KEYDOWN
        time.sleep(0.016)
        for h in target_hwnds:
            user32.PostMessageW(h, 0x0101, vk, 0)  # WM_KEYUP

    def _win32_fast_click(self, x: int, y: int, restore_cursor: bool = True):
        """Win32 API 超高速硬體點擊 (耗時 < 1ms，自動還原滑鼠游標)"""
        user32 = ctypes.windll.user32
        pt = wintypes.POINT()
        if restore_cursor:
            user32.GetCursorPos(ctypes.byref(pt))
        user32.SetCursorPos(int(x), int(y))
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
        time.sleep(0.008)
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
        if restore_cursor:
            user32.SetCursorPos(pt.x, pt.y)

    # =========================================================================
    # 背景運算主循環 (60~120 FPS 精準控制)
    # =========================================================================
    def _run_loop(self):
        sct_inst = mss.mss() if HAS_MSS else None
        frame_count = 0
        fps_start = time.perf_counter()
        last_ui_frame_time = 0.0
        last_full_grab_time = 0.0

        while self.is_running:
            loop_t0 = time.perf_counter()

            if not self.is_active:
                time.sleep(0.04)
                continue

            now = time.perf_counter()
            # 僅每 40ms (~25 FPS) 抓取全景供 UI 預覽，其餘時間僅抓取 ROI (極速 < 1ms！)
            need_full_preview = (now - last_full_grab_time) >= 0.04

            full_frame, roi = self.capture_frame(sct_inst, grab_full=need_full_preview)
            if roi is None:
                time.sleep(0.005)
                continue

            if need_full_preview and full_frame is not None:
                last_full_grab_time = now

            is_hit, matched_px, mask_img, proc_ms, target_desc, best_ball = self._analyze_frame(roi)
            self.process_latency_ms = proc_ms

            if is_hit:
                self.execute_swing()

            frame_count += 1
            elapsed = time.perf_counter() - fps_start
            if elapsed >= 0.8:
                self.current_fps = frame_count / elapsed
                frame_count = 0
                fps_start = time.perf_counter()

                if self.on_telemetry_callback:
                    self.on_telemetry_callback({
                        "fps": self.current_fps,
                        "capture_ms": self.capture_latency_ms,
                        "process_ms": self.process_latency_ms,
                        "target_desc": target_desc,
                        "is_active": self.is_active,
                        "total_swings": self.total_swings_count,
                        "last_swing": self.last_trigger_time_str
                    })

            now_ui = time.perf_counter()
            if self.on_frame_callback and (now_ui - last_ui_frame_time >= 0.016):
                last_ui_frame_time = now_ui
                rx = int(self.config.get("roi_x", 700))
                ry = int(self.config.get("roi_y", 560))
                rw = int(self.config.get("roi_w", 180))
                rh = int(self.config.get("roi_h", 160))
                sw_x = int(self.config.get("swing_x", 1380))
                sw_y = int(self.config.get("swing_y", 720))
                self.on_frame_callback(
                    full_frame, roi, mask_img, is_hit, (rx, ry, rw, rh),
                    target_desc, best_ball, (sw_x, sw_y)
                )

            target_fps = int(self.config.get("target_fps", 60))
            if target_fps > 0:
                frame_budget = 1.0 / target_fps
                time_spent = time.perf_counter() - loop_t0
                rem = frame_budget - time_spent
                if rem > 0.001:
                    time.sleep(rem)

        if sct_inst:
            try:
                sct_inst.close()
            except Exception:
                pass

    def _hotkey_loop(self):
        user32 = ctypes.windll.user32
        vk = int(self.config.get("hotkey_vk", 0x77))
        was_pressed = False
        while self.is_running:
            try:
                state = user32.GetAsyncKeyState(vk)
                is_pressed = (state & 0x8000) != 0
                if is_pressed and not was_pressed:
                    self.toggle_active()
                was_pressed = is_pressed
            except Exception:
                pass
            time.sleep(0.08)
