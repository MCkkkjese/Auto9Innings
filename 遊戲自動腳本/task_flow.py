"""
棒球手遊自動化腳本 - 任務清單 (Scratch 積木式日常任務編程 / 循環工作流)
支援跨平台 (macOS 與 Windows)：
1. 👆 無條件點擊指定座標
2. 🔍 偵測文字或特殊符號 (打勾/叉叉) 並點擊
3. 🔀 判斷當前畫面文字點擊不同座標 (If-Else 條件分支)
4. ⏱ 固定秒數等待
5. ↔ 螢幕滑動手勢
6. 📱 模擬返回鍵 (Back)
7. 🔁 任務清單多輪循環執行
8. 🎯 點擊截圖直接吸取座標快捷填入
"""
import os
import sys
import time
import json
import random
import threading
import requests
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Dict, Any, List, Callable, Tuple

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk

from theme import DARK_BG, DARK_FG, DARK_FG_MUTED, DARK_BORDER, DARK_SURFACE, apply_dark_theme, get_theme_palette

# 現代化配色常數 (Catppuccin 低飽和深色)
COLOR_BG = "#1E1E2E"
COLOR_CARD = "#252538"
COLOR_CARD_BORDER = "#313244"
COLOR_CARD_ITEM = "#20222e"
COLOR_INPUT_BG = "#181825"
COLOR_INPUT_BORDER = "#45475a"
COLOR_TEXT_PRIMARY = "#CDD6F4"
COLOR_TEXT_MUTED = "#A6ADC8"
COLOR_TEXT_DIM = "#6C7086"

COLOR_BTN_PRIMARY = "#3B82F6"
COLOR_BTN_PRIMARY_HOVER = "#2563EB"
COLOR_BTN_START = "#10B981"
COLOR_BTN_START_HOVER = "#059669"
COLOR_BTN_STOP = "#EF4444"
COLOR_BTN_STOP_HOVER = "#DC2626"
COLOR_BTN_DARK = "#313244"
COLOR_BTN_DARK_HOVER = "#45475A" 


# ==========================================
# 積木外觀與色彩常數 (Scratch 色彩系統)
# ==========================================
COLOR_BLOCK_ACTION = "#2563eb"     # 動作 (寶藍)
COLOR_BLOCK_MULTI_TAP = "#ea580c"  # 連續點擊 (活力橙紅)
COLOR_BLOCK_DETECT = "#059669"     # 偵測 (翡翠綠)
COLOR_BLOCK_BRANCH = "#d97706"     # 條件分支 (琥珀橙)
COLOR_BLOCK_LOOP = "#6366f1"       # 迴圈容器 (靛青紫)
COLOR_BLOCK_WAIT = "#7c3aed"       # 等待 (紫羅蘭)
COLOR_BLOCK_TELEGRAM = "#0284c7"   # Telegram (晴空藍)
COLOR_BLOCK_SWIPE = "#0891b2"      # 滑動 (青藍)
COLOR_BLOCK_BACK = "#475569"       # 返回鍵 (深灰藍)
COLOR_BLOCK_COMMENT = "#ca8a04"    # 備註 (便條金黃)
COLOR_BLOCK_ACTIVE = "#eab308"     # 執行中光環 (金黃色)
COLOR_BLOCK_BG = "#1e232d"         # 積木卡片底色 (深石板色)
COLOR_BLOCK_BODY = "#161922"       # 積木內容區底色 (深黑藍)
COLOR_BLOCK_FG = "#ffffff"         # 積木白色文字
COLOR_BLOCK_MUTED = "#94a3b8"      # 積木次要文字

BLOCK_TYPES = {
    "tap_coord": {
        "title": "點擊座標",
        "badge": "動作",
        "color": COLOR_BLOCK_ACTION,
        "default_name": "點擊座標",
        "default_params": {"x": 960, "y": 540, "delay": 1.5, "repeat": 1}
    },
    "multi_tap": {
        "title": "連續點擊（可設停止條件）",
        "badge": "連點",
        "color": COLOR_BLOCK_MULTI_TAP,
        "default_name": "連續點擊",
        "default_params": {
            "x": 960,
            "y": 540,
            "count": 10,
            "interval": 0.3,
            "stop_mode": "無 (僅點滿次數)",
            "stop_keywords": "確認, 確定, 完成, 上限",
            "template_image": "",
            "image_threshold": 0.80,
            "image_multiscale": False,
            "check_every": 1,
            "delay_after": 0.5
        }
    },
    "detect_click": {
        "title": "偵測文字或圖片並點擊",
        "badge": "偵測",
        "color": COLOR_BLOCK_DETECT,
        "default_name": "等待並點擊",
        "default_params": {
            "target_type": "📝 僅文字",
            "keywords": "確認, 確定",
            "template_image": "",
            "image_threshold": 0.80,
            "image_multiscale": False,
            "timeout": 10,
            "click_mode": "🎯 點擊目標中心",
            "custom_x": 960,
            "custom_y": 540,
            "block_x1": 800,
            "block_y1": 450,
            "block_x2": 1120,
            "block_y2": 630,
            "delay": 1.5,
            "on_timeout": "continue",
            "repeat_enabled": False,
            "repeat_mode": "指定次數",
            "repeat_count": 10,
            "repeat_interval": 0.25,
            "repeat_area": "跟隨命中目標",
            "repeat_custom_x": 960,
            "repeat_custom_y": 540
        }
    },
    "branch_if": {
        "title": "條件分支（If / Else）",
        "badge": "條件",
        "color": COLOR_BLOCK_BRANCH,
        "default_name": "條件分支",
        "default_params": {
            "timeout": 8,
            "delay": 1.5,
            "else_action": "skip",
            "else_x": 960,
            "else_y": 950,
            "branches": [
                {"name": "If", "keywords": "勝利, 挑戰成功", "template_image": "", "threshold": 0.80, "multiscale": False, "x": 1650, "y": 950},
                {"name": "Else If", "keywords": "失敗, 挑戰失敗", "template_image": "", "threshold": 0.80, "multiscale": False, "x": 960, "y": 950}
            ]
        }
    },
    "loop": {
        "title": "迴圈（指定次數或條件）",
        "badge": "迴圈",
        "color": COLOR_BLOCK_LOOP,
        "default_name": "迴圈容器",
        "default_params": {
            "stop_mode": "依指定次數",
            "count": 3,
            "keywords": "",
            "template_image": "",
            "image_threshold": 0.80,
            "image_multiscale": False,
            "check_timing": "每輪開始與結束",
            "delay_after": 0.5,
            "inner_blocks": []
        }
    },
    "wait_condition": {
        "title": "等待條件（等待直到）",
        "badge": "等待",
        "color": "#8b5cf6",
        "default_name": "等待條件達成",
        "default_params": {
            "cond_mode": "出現 (Wait Appear)",
            "target_type": "📝 僅文字",
            "keywords": "確認, 確定",
            "template_image": "",
            "image_threshold": 0.80,
            "image_multiscale": False,
            "interval": 1.0,
            "timeout": 30,
            "click_mode": "🎯 點擊目標中心",
            "custom_x": 960,
            "custom_y": 540,
            "block_x1": 800,
            "block_y1": 450,
            "block_x2": 1120,
            "block_y2": 630,
            "delay": 0.5,
            "delay_after": 0.5,
            "on_timeout": "continue",
            "repeat_enabled": False,
            "repeat_mode": "指定次數",
            "repeat_count": 10,
            "repeat_interval": 0.25,
            "repeat_area": "跟隨命中目標",
            "repeat_custom_x": 960,
            "repeat_custom_y": 540
        }
    },
    "wait_sec": {
        "title": "等待秒數",
        "badge": "流程",
        "color": COLOR_BLOCK_WAIT,
        "default_name": "等待延遲",
        "default_params": {"seconds": 3.0}
    },
    "swipe": {
        "title": "滑動",
        "badge": "手勢",
        "color": COLOR_BLOCK_SWIPE,
        "default_name": "滑動螢幕",
        "default_params": {"x1": 1500, "y1": 540, "x2": 400, "y2": 540, "duration_ms": 400, "delay": 1.0}
    },
    "back_key": {
        "title": "返回鍵",
        "badge": "系統",
        "color": COLOR_BLOCK_BACK,
        "default_name": "返回上一頁",
        "default_params": {"delay": 1.2}
    },
    "comment": {
        "title": "備註",
        "badge": "備註",
        "color": COLOR_BLOCK_COMMENT,
        "default_name": "備註說明",
        "default_params": {"note": "此處為備註說明文字，執行時不執行任何操作"}
    },
    "send_telegram": {
        "title": "傳送 Telegram 通知",
        "badge": "推播",
        "color": COLOR_BLOCK_TELEGRAM,
        "default_name": "發送 Telegram",
        "default_params": {
            "message": "任務步驟執行完成！",
            "attach_screenshot": True,
            "use_custom": False,
            "custom_token": "",
            "custom_chat_id": "",
            "delay_after": 0.5
        }
    }
}

# 常用任務範本字典 (動態從 task_presets/ 資料夾載入，支援使用者自訂新增與修改)
DAILY_PRESETS: Dict[str, Dict[str, Any]] = {}


def imread_unicode(path: str, flags: int = cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
    """跨平台安全讀取包含中文檔名的圖片 (使用原生 Python IO)"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        nparr = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(nparr, flags)
    except Exception:
        return None


def imwrite_unicode(path: str, img: np.ndarray) -> bool:
    """跨平台安全寫入包含中文檔名與路徑的圖片 (使用原生 Python IO)"""
    try:
        p = os.path.abspath(path)
        ext = os.path.splitext(p)[1]
        if not ext:
            ext = ".png"
            p = p + ext
        parent_dir = os.path.dirname(p)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        success, encoded = cv2.imencode(ext, img)
        if success:
            with open(p, "wb") as f:
                f.write(encoded.tobytes())
            return os.path.exists(p) and os.path.getsize(p) > 0
        return False
    except Exception:
        return False


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


# ==========================================
# 任務執行核心引擎 (TaskEngine)
# ==========================================
class TaskEngine:
    """獨立背景任務清單執行器"""

    def __init__(
        self,
        bot_instance,
        log_callback: Optional[Callable[[str], None]] = None,
        global_settings: Optional[Dict[str, Any]] = None
    ):
        self.bot = bot_instance
        self.log_callback = log_callback
        self.global_settings = dict(global_settings or {})
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.current_block_idx = -1
        self.current_cycle = 0
        self.total_cycles = 1

    def _get_scan_interval(self) -> float:
        """取得掃描/刷新間隔 (秒)，吃到聯賽自動刷的快速刷設定 (0=極速無延遲)"""
        interval = _safe_float(self.global_settings.get("interval", 0.4), 0.4)
        if interval <= 0:
            return 0.02
        return max(0.02, min(5.0, interval))

    def _get_confidence(self) -> float:
        """取得 OCR 辨識門檻"""
        return max(0.40, min(0.95, _safe_float(self.global_settings.get("confidence", 0.65), 0.65)))

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(f"[任務清單] {msg}")

    def start(
        self,
        blocks_data: List[Dict[str, Any]],
        loop_count: int = 1,
        on_step_change: Optional[Callable[[int, int, int], None]] = None,
        on_finish: Optional[Callable[[bool, str], None]] = None,
        global_settings: Optional[Dict[str, Any]] = None
    ):
        if self.is_running:
            return

        if global_settings:
            self.global_settings.update(global_settings)

        # 套用語言過濾設定至 bot
        if self.bot and hasattr(self.bot, "set_allowed_languages"):
            self.bot.set_allowed_languages(
                allow_tc=bool(self.global_settings.get("lang_tc", True)),
                allow_sc=bool(self.global_settings.get("lang_sc", False)),
                allow_en=bool(self.global_settings.get("lang_en", True))
            )

        if not self.bot or not self.bot.device:
            if not self.bot.connect():
                self._log("❌ 無法執行：尚未連線到模擬器裝置！")
                if on_finish:
                    on_finish(False, "未連線裝置")
                return

        self.is_running = True
        self._stop_event.clear()
        self.total_cycles = loop_count

        def _worker():
            success = True
            msg = "任務清單執行完成！"
            cycle = 1
            try:
                while self.is_running and not self._stop_event.is_set():
                    self.current_cycle = cycle
                    self._log(f"🚀 開始執行第 {cycle}/{self.total_cycles if self.total_cycles > 0 else '∞'} 輪任務...")

                    for idx, block in enumerate(blocks_data):
                        if self._stop_event.is_set():
                            break
                        if not block.get("enabled", True):
                            continue

                        self.current_block_idx = idx
                        if on_step_change:
                            on_step_change(idx, cycle, self.total_cycles)

                        b_name = block.get("name", "未命名步驟")
                        b_type = block.get("type", "tap_coord")
                        params = block.get("params", {})

                        self._log(f"👉 步驟 #{idx + 1} [{b_name}] ({BLOCK_TYPES.get(b_type, {}).get('title', b_type)})")
                        step_ok = self.execute_block(b_type, params)

                        if not step_ok and params.get("on_timeout") == "stop":
                            self._log(f"⚠️ 步驟 #{idx + 1} 觸發超時終止設定，任務停止。")
                            success = False
                            msg = f"步驟 #{idx + 1} 超時終止"
                            self._stop_event.set()
                            break

                    if self._stop_event.is_set():
                        break

                    if self.total_cycles > 0 and cycle >= self.total_cycles:
                        break

                    cycle += 1
                    time.sleep(1.0)

            except Exception as e:
                self._log(f"❌ 執行異常: {e}")
                success = False
                msg = str(e)
            finally:
                self.is_running = False
                self.current_block_idx = -1
                if on_step_change:
                    on_step_change(-1, self.current_cycle, self.total_cycles)
                self._log("🏁 任務清單已停止。")
                if on_finish:
                    on_finish(success, msg)

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def stop(self):
        if self.is_running:
            self._stop_event.set()
            self.is_running = False
            self._log("已發送停止信號，等待當前動作結束...")

    def run_sync(
        self,
        blocks_data: List[Dict[str, Any]],
        loop_count: int = 1,
        on_step_change: Optional[Callable[[int, int, int], None]] = None,
        global_settings: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        同步執行任務清單 (專供聯賽事件跳轉或單步呼叫使用，執行完成後回傳)
        """
        if global_settings:
            self.global_settings.update(global_settings)

        if self.bot and hasattr(self.bot, "set_allowed_languages"):
            self.bot.set_allowed_languages(
                allow_tc=bool(self.global_settings.get("lang_tc", True)),
                allow_sc=bool(self.global_settings.get("lang_sc", False)),
                allow_en=bool(self.global_settings.get("lang_en", True))
            )

        if not self.bot or not self.bot.device:
            if not self.bot or not self.bot.connect():
                self._log("❌ 無法執行任務清單：尚未連線至模擬器裝置！")
                return False

        self._stop_event.clear()
        self.is_running = True
        success = True
        total = loop_count

        try:
            for cycle in range(1, total + 1):
                if self._stop_event.is_set():
                    break
                self._log(f"📋 [任務跳轉] 開始執行第 {cycle}/{total} 輪 (共 {len(blocks_data)} 個步驟)...")

                for idx, block in enumerate(blocks_data):
                    if self._stop_event.is_set():
                        break
                    if not block.get("enabled", True):
                        continue

                    self.current_block_idx = idx
                    if on_step_change:
                        on_step_change(idx, cycle, total)

                    b_name = block.get("name", "未命名步驟")
                    b_type = block.get("type", "tap_coord")
                    params = block.get("params", {})

                    self._log(f"👉 步驟 #{idx + 1} [{b_name}] ({BLOCK_TYPES.get(b_type, {}).get('title', b_type)})")
                    step_ok = self.execute_block(b_type, params)

                    if not step_ok and params.get("on_timeout") == "stop":
                        self._log(f"⚠️ 步驟 #{idx + 1} 觸發超時終止設定，任務停止。")
                        success = False
                        self._stop_event.set()
                        break

                if self._stop_event.is_set():
                    break
                if cycle < total:
                    time.sleep(0.5)

        except Exception as e:
            self._log(f"❌ 任務跳轉執行異常: {e}")
            success = False
        finally:
            self.is_running = False
            self.current_block_idx = -1
            if on_step_change:
                on_step_change(-1, 0, 0)

        return success

    def execute_block(self, b_type: str, params: Dict[str, Any]) -> bool:
        """執行單個積木動作"""
        if b_type == "tap_coord":
            return self._exec_tap_coord(params)
        elif b_type == "multi_tap":
            return self._exec_multi_tap(params)
        elif b_type == "detect_click":
            return self._exec_detect_click(params)
        elif b_type == "branch_if":
            return self._exec_branch_if(params)
        elif b_type == "loop":
            return self._exec_loop(params)
        elif b_type == "wait_condition":
            return self._exec_wait_condition(params)
        elif b_type == "wait_sec":
            return self._exec_wait_sec(params)
        elif b_type == "swipe":
            return self._exec_swipe(params)
        elif b_type == "back_key":
            return self._exec_back_key(params)
        elif b_type == "comment":
            return self._exec_comment(params)
        elif b_type == "send_telegram":
            return self._exec_send_telegram(params)
        return True

    def _sleep_interruptible(self, seconds: float) -> bool:
        """可被停止中斷的睡眠"""
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self._stop_event.is_set():
                return False
            time.sleep(0.08)
        return True

    def _exec_tap_coord(self, p: Dict[str, Any]) -> bool:
        x = _safe_int(p.get("x", 960))
        y = _safe_int(p.get("y", 540))
        delay = _safe_float(p.get("delay", 1.5))
        repeat = max(1, _safe_int(p.get("repeat", 1)))

        for r in range(repeat):
            if self._stop_event.is_set():
                return False
            self.bot.tap(x, y)
            if r < repeat - 1:
                time.sleep(0.3)
        self._sleep_interruptible(delay)
        return True

    def _check_condition_met(
        self,
        stop_mode: str,
        raw_keywords: str,
        template_image: str = "",
        threshold: float = 0.80,
        multiscale: bool = False
    ) -> Tuple[bool, str]:
        """檢測當前畫面是否滿足終止條件 (文字出現/消失、圖片出現/消失、打勾/叉叉符號)"""
        if not self.bot:
            return False, ""

        if stop_mode in ("依指定次數", "無 (僅點滿次數)"):
            return False, ""

        is_disappear = ("消失" in stop_mode or "disappear" in stop_mode.lower())
        is_check = ("打勾" in stop_mode or "check" in stop_mode.lower())
        is_cross = ("叉叉" in stop_mode or "cross" in stop_mode.lower())
        is_image = ("圖片" in stop_mode or "image" in stop_mode.lower() or "模板" in stop_mode or bool(template_image))
        is_appear = (not is_disappear)

        screen = None
        try:
            screen = self.bot.capture_screen()
        except Exception:
            pass

        if screen is None:
            return False, ""

        # 圖片模板比對條件
        if is_image and template_image:
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            matched = False
            score_val = 0.0
            match_res = None
            if hasattr(self.bot, "match_template"):
                match_res = self.bot.match_template(
                    screen_gray,
                    template_image,
                    threshold=threshold,
                    multi_scale=multiscale
                )
            if match_res is not None:
                cx, cy, score_val, _ = match_res
                matched = True

            img_fname = os.path.basename(template_image)
            if is_appear and matched:
                return True, f"偵測到圖片「{img_fname}」出現 (相似度 {score_val:.2f})"
            elif is_disappear and not matched:
                return True, f"圖片「{img_fname}」已消失"
            return False, ""

        # 符號比對
        det_results = self.bot.scan_text(screen)
        present = False
        matched_desc = ""

        if is_check or is_cross:
            for item in det_results:
                sym = item.get("symbol")
                txt = item.get("text", "")
                if is_check and (sym == "check" or txt in ("[打勾]", "✓", "✔", "√") or (len(txt) == 1 and txt.upper() == "V")):
                    present = True
                    matched_desc = f"打勾圖案 [{txt}]"
                    break
                if is_cross and (sym == "cross" or txt in ("[叉叉]", "✕", "✖", "×", "X", "x")):
                    present = True
                    matched_desc = f"叉叉圖案 [{txt}]"
                    break

        # 文字比對
        kws = [k.strip() for k in raw_keywords.replace("，", ",").split(",") if k.strip()]
        conf_thresh = self._get_confidence()
        if not present and kws:
            for kw in kws:
                for item in det_results:
                    matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                    if matched and ratio >= conf_thresh:
                        present = True
                        matched_desc = f"關鍵字「{kw}」({item.get('text')})"
                        break
                if present:
                    break

        if is_appear and present:
            return True, f"偵測到 {matched_desc} 出現"
        elif is_disappear and not present:
            return True, f"目標「{raw_keywords}」已消失"

        return False, ""

    def _exec_multi_tap(self, p: Dict[str, Any]) -> bool:
        """連續點擊指定座標，支援設定間隔與停止條件"""
        x = _safe_int(p.get("x", 960))
        y = _safe_int(p.get("y", 540))
        count = max(0, _safe_int(p.get("count", 10)))  # 0 = 無限點擊直到停止條件
        interval = max(0.05, _safe_float(p.get("interval", 0.3)))
        stop_mode = p.get("stop_mode", "無 (僅點滿次數)")
        raw_kws = p.get("stop_keywords", "")
        template_img = p.get("template_image", "").strip()
        img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
        img_multiscale = bool(p.get("image_multiscale", False))
        check_every = max(1, _safe_int(p.get("check_every", 1)))
        delay_after = max(0.0, _safe_float(p.get("delay_after", 0.5)))

        has_stop_cond = (stop_mode != "無 (僅點滿次數)")
        tot_str = str(count) if count > 0 else "∞"
        self._log(f"  ⚡ 開始連續點擊 ({x}, {y}) [預計 {tot_str} 次，間隔 {interval:.2f}s，停止條件: {stop_mode}]")

        taps_done = 0
        while count == 0 or taps_done < count:
            if self._stop_event.is_set():
                return False

            self.bot.tap(x, y)
            taps_done += 1

            if has_stop_cond and (taps_done % check_every == 0):
                met, desc = self._check_condition_met(
                    stop_mode,
                    raw_kws,
                    template_image=template_img,
                    threshold=img_thresh,
                    multiscale=img_multiscale
                )
                if met:
                    self._log(f"  🛑 觸發停止條件！{desc}，停止連點 (共完成 {taps_done} 次)")
                    break

            if count == 0 or taps_done < count:
                if not self._sleep_interruptible(interval):
                    return False

        self._log(f"  ⚡ 連續點擊結束，共執行 {taps_done} 次點擊。")
        if delay_after > 0:
            self._sleep_interruptible(delay_after)
        return True

    def _handle_detect_hit(
        self,
        hit_name: str,
        hit_center: Tuple[int, int],
        p: Dict[str, Any],
        img_shape: Tuple[int, int],
        is_image: bool = False,
        template_img: str = "",
        img_thresh: float = 0.80,
        img_multiscale: bool = False,
        raw_kws: str = "",
        is_check: bool = False,
        is_cross: bool = False
    ) -> bool:
        """
        處理偵測命中後的動作執行：
        1. 依動作模式計算點擊位置 (目標中心、自訂座標、自訂特定區塊、無動作僅等待)
        2. ⚡ 命中後連點 (跟隨目標、自訂座標、右下角、中央、右上Skip、右半中央；支援指定次數或持續連點直到目標消失)
        3. 執行結束延遲
        """
        img_h, img_w = img_shape
        click_mode = str(p.get("click_mode", "🎯 點擊目標中心")).strip()
        cx = _safe_int(p.get("custom_x", 960))
        cy = _safe_int(p.get("custom_y", 540))
        bx1 = _safe_int(p.get("block_x1", 800))
        by1 = _safe_int(p.get("block_y1", 450))
        bx2 = _safe_int(p.get("block_x2", 1120))
        by2 = _safe_int(p.get("block_y2", 630))

        # 1. 計算第一階段點擊目標座標
        click_coord = None
        is_custom_xy = (
            click_mode in ("custom_coord", "自訂座標", "📍 點擊自訂座標", "📍 點擊指定座標 (自訂)")
            or "自訂座標" in click_mode
            or "指定座標" in click_mode
        )
        is_custom_block = (
            click_mode in ("custom_block", "自訂特定區塊", "🔲 自訂特定區塊")
            or "特定區塊" in click_mode
            or "自訂區塊" in click_mode
        )
        is_wait_only = (
            click_mode in ("wait_only", "無動作", "無動作(僅等待)", "⏳ 無動作(僅等待)")
            or "僅等待" in click_mode
            or "無動作" in click_mode
        )

        if is_wait_only:
            click_coord = None
        elif is_custom_xy:
            click_coord = (cx + random.randint(-4, 4), cy + random.randint(-4, 4))
        elif is_custom_block:
            min_x, max_x = min(bx1, bx2), max(bx1, bx2)
            min_y, max_y = min(by1, by2), max(by1, by2)
            click_coord = (random.randint(min_x, max_x), random.randint(min_y, max_y))
        else:
            # 🎯 點擊目標中心 (預設)
            click_coord = (hit_center[0] + random.randint(-3, 3), hit_center[1] + random.randint(-3, 3))

        # 2. 執行第一階段點擊
        if click_coord is not None:
            self._log(f"  🎯 命中【{hit_name}】→ 點擊目標 ({click_coord[0]}, {click_coord[1]})")
            self.bot.tap(click_coord[0], click_coord[1])
        else:
            self._log(f"  🎯 命中【{hit_name}】(設定為無動作/僅等待，不執行單次點擊)")

        # 3. ⚡ 命中後連點（過場跳過）
        rep_enabled = bool(p.get("repeat_enabled", False))
        if rep_enabled and not self._stop_event.is_set():
            rep_mode = str(p.get("repeat_mode", "指定次數")).strip()
            rep_area = str(p.get("repeat_area", "跟隨命中目標")).strip()
            rep_count = max(1, _safe_int(p.get("repeat_count", 10)))
            rep_interval = max(0.05, _safe_float(p.get("repeat_interval", p.get("repeat_speed", 0.25))))
            rep_cx = _safe_int(p.get("repeat_custom_x", 960))
            rep_cy = _safe_int(p.get("repeat_custom_y", 540))

            # 計算連點基準座標 (base_x, base_y)
            if rep_area == "右下角區域":
                base_x, base_y = int(img_w * 0.86), int(img_h * 0.86)
            elif rep_area == "中央區域":
                base_x, base_y = int(img_w * 0.50), int(img_h * 0.50)
            elif rep_area == "右上角 (Skip)":
                base_x, base_y = int(img_w * 0.90), int(img_h * 0.12)
            elif rep_area == "右半側中央":
                base_x, base_y = int(img_w * 0.82), int(img_h * 0.50)
            elif "自訂" in rep_area:
                base_x, base_y = rep_cx, rep_cy
            else:
                # 跟隨命中目標 (或若為無動作，跟隨 hit_center)
                base_x, base_y = click_coord if click_coord is not None else hit_center

            min_spd = max(0.05, rep_interval - 0.05)
            max_spd = rep_interval + 0.05

            if rep_mode == "指定次數":
                self._log(f"  ⚡ [命中後連點] 在「{rep_area}」({base_x}, {base_y}) 連點 {rep_count} 次 (間隔 {rep_interval:.2f}s)...")
                for c in range(rep_count):
                    if self._stop_event.is_set():
                        return False
                    rx = base_x + random.randint(-8, 8)
                    ry = base_y + random.randint(-8, 8)
                    self.bot.tap(rx, ry, delay_range=(min_spd, max_spd))
            else:
                # 持續連點直到畫面變動 / 目標消失
                self._log(f"  ⚡ [命中後連點] 正在持續連點「{rep_area}」({base_x}, {base_y}) 跳過過場 (直到目標消失)...")
                tap_cnt = 0
                max_continuous_taps = 60  # 防卡死安全上限
                while tap_cnt < max_continuous_taps:
                    if self._stop_event.is_set():
                        return False
                    rx = base_x + random.randint(-8, 8)
                    ry = base_y + random.randint(-8, 8)
                    self.bot.tap(rx, ry, delay_range=(min_spd, max_spd))
                    tap_cnt += 1

                    if tap_cnt % 3 == 0:
                        chk_screen = self.bot.capture_screen()
                        if chk_screen is not None:
                            still_there = False
                            if is_image and template_img:
                                chk_gray = cv2.cvtColor(chk_screen, cv2.COLOR_BGR2GRAY)
                                if hasattr(self.bot, "match_template"):
                                    m = self.bot.match_template(
                                        chk_gray, template_img,
                                        threshold=img_thresh,
                                        multi_scale=img_multiscale
                                    )
                                    if m:
                                        still_there = True
                            else:
                                chk_det = self.bot.scan_text(chk_screen)
                                if is_check or is_cross:
                                    for it in chk_det:
                                        s = it.get("symbol")
                                        t = it.get("text", "")
                                        if is_check and (s == "check" or t in ("[打勾]", "✓", "✔", "√") or (len(t) == 1 and t.upper() == "V")):
                                            still_there = True
                                            break
                                        if is_cross and (s == "cross" or t in ("[叉叉]", "✕", "✖", "×", "X", "x")):
                                            still_there = True
                                            break
                                if not still_there and raw_kws:
                                    conf_thresh = self._get_confidence()
                                    kws_chk = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
                                    for kw in kws_chk:
                                        for it in chk_det:
                                            matched, ratio = self.bot._is_text_matched(kw, it.get("text", ""), similarity_threshold=conf_thresh)
                                            if matched and ratio >= conf_thresh:
                                                still_there = True
                                                break
                                        if still_there:
                                            break

                            if not still_there:
                                self._log(f"  ✨ [命中後連點] 原目標已消失，過場跳過完成！(共連點 {tap_cnt} 次)")
                                break

        # 4. 執行結束延遲
        delay = max(0.0, _safe_float(p.get("delay", 1.5)))
        if delay > 0:
            self._sleep_interruptible(delay)

        return True

    def _exec_detect_click(self, p: Dict[str, Any]) -> bool:
        target_type = p.get("target_type", "📝 僅文字")
        raw_kws = p.get("keywords", "")
        template_img = p.get("template_image", "").strip()
        img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
        img_multiscale = bool(p.get("image_multiscale", False))
        timeout = max(1, _safe_int(p.get("timeout", 10)))

        is_image_mode = ("圖片" in target_type or "image" in target_type.lower() or "模板" in target_type)
        is_check = ("打勾" in target_type or "check" in target_type.lower())
        is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)

        kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
        scan_delay = self._get_scan_interval()
        deadline = time.time() + timeout

        desc_target = f"圖片「{os.path.basename(template_img)}」" if is_image_mode else (f"文字/符號「{raw_kws}」" if raw_kws else target_type)
        self._log(f"  🔍 等待目標【{desc_target}】出現 (限時 {timeout}s, 刷新速度 {scan_delay:.2f}s)...")

        while time.time() < deadline:
            if self._stop_event.is_set():
                return False

            screen = self.bot.capture_screen()
            if screen is not None:
                img_h, img_w = screen.shape[:2]
                # 1. 圖片模板模式
                if is_image_mode:
                    if not template_img:
                        self._log("  ⚠️ 未指定模板圖檔，無法進行圖片比對！")
                        return False
                    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    if hasattr(self.bot, "match_template"):
                        res = self.bot.match_template(
                            screen_gray,
                            template_img,
                            threshold=img_thresh,
                            multi_scale=img_multiscale
                        )
                        if res is not None:
                            tx, ty, score_val, bbox = res
                            img_name = os.path.basename(template_img)
                            return self._handle_detect_hit(
                                hit_name=f"圖片模板「{img_name}」(相似度 {score_val:.2f})",
                                hit_center=(tx, ty),
                                p=p,
                                img_shape=(img_h, img_w),
                                is_image=True,
                                template_img=template_img,
                                img_thresh=img_thresh,
                                img_multiscale=img_multiscale
                            )
                else:
                    # 2. 文字/符號 OCR 模式
                    det_results = self.bot.scan_text(screen)

                    # 優先比對符號
                    if is_check or is_cross:
                        for item in det_results:
                            sym = item.get("symbol")
                            txt = item.get("text", "")
                            if is_check and (sym == "check" or txt in ("[打勾]", "✓", "✔", "√") or (len(txt) == 1 and txt.upper() == "V")):
                                return self._handle_detect_hit(
                                    hit_name=f"打勾符號 [{txt}]",
                                    hit_center=item["center"],
                                    p=p,
                                    img_shape=(img_h, img_w),
                                    raw_kws=raw_kws,
                                    is_check=True
                                )
                            if is_cross and (sym == "cross" or txt in ("[叉叉]", "✕", "✖", "×", "X", "x")):
                                return self._handle_detect_hit(
                                    hit_name=f"叉叉符號 [{txt}]",
                                    hit_center=item["center"],
                                    p=p,
                                    img_shape=(img_h, img_w),
                                    raw_kws=raw_kws,
                                    is_cross=True
                                )

                    # 比對關鍵字
                    conf_thresh = self._get_confidence()
                    for kw in kws:
                        for item in det_results:
                            matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                            if matched and ratio >= conf_thresh:
                                return self._handle_detect_hit(
                                    hit_name=f"文字「{item.get('text')}」(匹配「{kw}」)",
                                    hit_center=item["center"],
                                    p=p,
                                    img_shape=(img_h, img_w),
                                    raw_kws=raw_kws
                                )

            time.sleep(scan_delay)

        self._log(f"  ⚠️ 等待超時 ({timeout}s 未偵測到目標【{desc_target}】)")
        return False

    def _exec_branch_if(self, p: Dict[str, Any]) -> bool:
        """條件分支：判斷當前畫面文字或圖片來去點擊不同的座標 (支援多個 If 與 Else If)"""
        branches = p.get("branches")
        if not branches:
            branches = []
            if p.get("cond_a_kws") or p.get("cond_a_x"):
                branches.append({
                    "name": "If",
                    "keywords": p.get("cond_a_kws", ""),
                    "template_image": "",
                    "threshold": 0.80,
                    "multiscale": False,
                    "x": _safe_int(p.get("cond_a_x", 1650)),
                    "y": _safe_int(p.get("cond_a_y", 950))
                })
            if p.get("cond_b_kws") or p.get("cond_b_x"):
                branches.append({
                    "name": "Else If",
                    "keywords": p.get("cond_b_kws", ""),
                    "template_image": "",
                    "threshold": 0.80,
                    "multiscale": False,
                    "x": _safe_int(p.get("cond_b_x", 960)),
                    "y": _safe_int(p.get("cond_b_y", 950))
                })

        else_act = p.get("else_action", p.get("cond_else_action", "skip"))
        ex = _safe_int(p.get("else_x", 960))
        ey = _safe_int(p.get("else_y", 950))

        timeout = max(1, _safe_int(p.get("timeout", 8)))
        delay = _safe_float(p.get("delay", 1.5))

        scan_delay = self._get_scan_interval()
        conf_thresh = self._get_confidence()
        deadline = time.time() + timeout
        self._log(f"  🔀 正在判斷多分支條件 (共有 {len(branches)} 個分支, 限時 {timeout}s, 刷新速度 {scan_delay:.2f}s)...")

        while time.time() < deadline:
            if self._stop_event.is_set():
                return False

            screen = self.bot.capture_screen()
            if screen is not None:
                screen_gray = None
                det_results = None

                # 依序檢查 If 以及各個 Else If 分支
                for b_idx, branch in enumerate(branches):
                    b_tag = branch.get("name", "If" if b_idx == 0 else f"Else If {b_idx}")
                    tpl_img = branch.get("template_image", "").strip()
                    raw_kws = branch.get("keywords", "")
                    kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
                    bx = _safe_int(branch.get("x", 960))
                    by = _safe_int(branch.get("y", 540))

                    # 1. 優先判斷分支圖片模板
                    if tpl_img and hasattr(self.bot, "match_template"):
                        if screen_gray is None:
                            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                        br_thresh = _safe_float(branch.get("threshold", 0.80), 0.80)
                        br_multi = bool(branch.get("multiscale", False))
                        m_res = self.bot.match_template(screen_gray, tpl_img, threshold=br_thresh, multi_scale=br_multi)
                        if m_res is not None:
                            self._log(f"  🎯 命中分支 [{b_tag}] 圖片「{os.path.basename(tpl_img)}」(相似度 {m_res[2]:.2f}) ➜ 點擊座標 ({bx}, {by})")
                            self.bot.tap(bx, by)
                            self._sleep_interruptible(delay)
                            return True

                    # 2. 判斷分支關鍵字 (OCR)
                    if kws:
                        if det_results is None:
                            det_results = self.bot.scan_text(screen)
                        for kw in kws:
                            for item in det_results:
                                matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                                if matched and ratio >= conf_thresh:
                                    self._log(f"  🎯 命中分支 [{b_tag}] 關鍵字「{kw}」➜ 點擊座標 ({bx}, {by})")
                                    self.bot.tap(bx, by)
                                    self._sleep_interruptible(delay)
                                    return True

            time.sleep(scan_delay)

        # 全部 If / Else If 皆未命中 ➜ 執行 Else
        if else_act == "click_coord":
            self._log(f"  ⏩ 所有分支皆未命中，執行 Else 點擊 ({ex}, {ey})")
            self.bot.tap(ex, ey)
            self._sleep_interruptible(delay)
        else:
            self._log("  ⏩ 所有分支皆未命中，跳過此條件區塊。")
        return True

    def _exec_loop(self, p: Dict[str, Any]) -> bool:
        """迴圈容器：重複執行內部包含的積木步驟 (支援 While 條件與指定次數)"""
        stop_mode = p.get("stop_mode", "依指定次數")
        raw_kws = p.get("keywords", p.get("stop_keywords", ""))
        template_img = p.get("template_image", "").strip()
        img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
        img_multiscale = bool(p.get("image_multiscale", False))
        count = max(0, _safe_int(p.get("count", 3)))
        check_timing = p.get("check_timing", "每輪開始與結束")
        delay_after = max(0.0, _safe_float(p.get("delay_after", 0.5)))
        inner_blocks = p.get("inner_blocks", [])

        if not inner_blocks:
            self._log("  🔁 迴圈內無任何積木步驟，跳過執行。")
            return True

        is_cond_mode = (stop_mode != "依指定次數" and "無" not in stop_mode)
        tot_str = str(count) if count > 0 else "∞"
        if is_cond_mode:
            target_desc = f"圖片「{os.path.basename(template_img)}」" if template_img else (f"「{raw_kws}」" if raw_kws else stop_mode)
            self._log(f"  🔁 進入 While 條件迴圈 [停止條件: {stop_mode} {target_desc}，上限: {tot_str} 次，內含 {len(inner_blocks)} 個步驟]...")
        else:
            self._log(f"  🔁 進入重複迴圈 [共 {tot_str} 次，內含 {len(inner_blocks)} 個步驟]...")

        rounds_done = 0
        cycle = 1
        while count == 0 or cycle <= count:
            if self._stop_event.is_set():
                return False

            # 每輪開始前檢查 (While 模式)
            if is_cond_mode and ("開始" in check_timing or "While" in check_timing):
                met, desc = self._check_condition_met(
                    stop_mode,
                    raw_kws,
                    template_image=template_img,
                    threshold=img_thresh,
                    multiscale=img_multiscale
                )
                if met:
                    self._log(f"  🛑 迴圈終止！在第 {cycle} 輪開始前觸發停止條件 ({desc})")
                    break

            self._log(f"    🔁 ── 迴圈第 {cycle}/{tot_str} 輪 ──")
            broken_by_step = False

            for s_idx, sb in enumerate(inner_blocks):
                if self._stop_event.is_set():
                    return False
                if not sb.get("enabled", True):
                    continue

                sb_type = sb.get("type", "tap_coord")
                sb_name = sb.get("name", f"子步驟 #{s_idx + 1}")
                sb_params = sb.get("params", {})
                self._log(f"      👉 [{sb_name}] ({BLOCK_TYPES.get(sb_type, {}).get('title', sb_type)})")
                ok = self.execute_block(sb_type, sb_params)
                if not ok and sb_params.get("on_timeout") == "stop":
                    self._log(f"      ⚠️ 子步驟觸發超時終止，中斷迴圈。")
                    return False

                # 每個子步驟後檢查
                if is_cond_mode and "子步驟" in check_timing:
                    met, desc = self._check_condition_met(
                        stop_mode,
                        raw_kws,
                        template_image=template_img,
                        threshold=img_thresh,
                        multiscale=img_multiscale
                    )
                    if met:
                        self._log(f"  🛑 迴圈終止！在子步驟 [{sb_name}] 執行後觸發停止條件 ({desc})")
                        broken_by_step = True
                        break

            rounds_done += 1
            if broken_by_step:
                break

            # 每輪結束後檢查 (Do-While 模式)
            if is_cond_mode and ("結束" in check_timing or "Do-While" in check_timing):
                met, desc = self._check_condition_met(
                    stop_mode,
                    raw_kws,
                    template_image=template_img,
                    threshold=img_thresh,
                    multiscale=img_multiscale
                )
                if met:
                    self._log(f"  🛑 迴圈終止！第 {cycle} 輪結束時觸發停止條件 ({desc})")
                    break

            cycle += 1
            time.sleep(0.1)

        self._log(f"  🔁 迴圈結束！共完成 {rounds_done} 輪。")
        if delay_after > 0:
            self._sleep_interruptible(delay_after)
        return True

    def _exec_wait_condition(self, p: Dict[str, Any]) -> bool:
        """等待指定條件達成 (畫面出現或消失特定文字/圖片/符號)，期間依設定的頻率 (秒) 循環檢測"""
        cond_mode = p.get("cond_mode", "出現 (Wait Appear)")
        is_wait_disappear = ("消失" in cond_mode or "disappear" in cond_mode.lower())
        is_wait_appear = not is_wait_disappear
        target_type = p.get("target_type", "📝 僅文字")
        raw_kws = p.get("keywords", "")
        template_img = p.get("template_image", "").strip()
        img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
        img_multiscale = bool(p.get("image_multiscale", False))

        is_image_mode = ("圖片" in target_type or "image" in target_type.lower() or "模板" in target_type)
        is_check = ("打勾" in target_type or "check" in target_type.lower())
        is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)

        scan_delay = self._get_scan_interval()
        default_interval = scan_delay if "interval" not in p else _safe_float(p.get("interval", scan_delay))
        interval = max(0.02, default_interval)

        timeout = max(1, _safe_int(p.get("timeout", 30)))
        delay_after = max(0.0, _safe_float(p.get("delay_after", 0.5)))
        on_timeout = p.get("on_timeout", "continue")

        mode_str = "出現" if is_wait_appear else "消失"
        if is_image_mode:
            desc = f"圖片「{os.path.basename(template_img)}」"
        else:
            kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
            desc = f"{target_type} [{raw_kws}]" if kws else target_type

        self._log(f"  ⏳ 等待「{desc}」{mode_str} (每 {interval:.2f}s 偵測一次，限時 {timeout}s)...")

        start_time = time.time()
        deadline = start_time + timeout

        while time.time() < deadline:
            if self._stop_event.is_set():
                return False

            screen = self.bot.capture_screen()
            present = False
            matched_desc = ""
            hit_coord = (_safe_int(p.get("custom_x", 960)), _safe_int(p.get("custom_y", 540)))

            if screen is not None:
                if is_image_mode:
                    if template_img and hasattr(self.bot, "match_template"):
                        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                        m_res = self.bot.match_template(
                            screen_gray,
                            template_img,
                            threshold=img_thresh,
                            multi_scale=img_multiscale
                        )
                        if m_res is not None:
                            present = True
                            hit_coord = (int(m_res[0]), int(m_res[1]))
                            matched_desc = f"圖片「{os.path.basename(template_img)}」(相似度 {m_res[2]:.2f})"
                else:
                    det_results = self.bot.scan_text(screen)

                    # 優先比對符號
                    if is_check or is_cross:
                        for item in det_results:
                            sym = item.get("symbol")
                            txt = item.get("text", "")
                            if is_check and (sym == "check" or txt in ("[打勾]", "✓", "✔", "√") or (len(txt) == 1 and txt.upper() == "V")):
                                present = True
                                hit_coord = item["center"]
                                matched_desc = f"打勾圖案 [{txt}]"
                                break
                            if is_cross and (sym == "cross" or txt in ("[叉叉]", "✕", "✖", "×", "X", "x")):
                                present = True
                                hit_coord = item["center"]
                                matched_desc = f"叉叉圖案 [{txt}]"
                                break

                    # 比對關鍵字
                    conf_thresh = self._get_confidence()
                    if not present and kws:
                        for kw in kws:
                            for item in det_results:
                                matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                                if matched and ratio >= conf_thresh:
                                    present = True
                                    hit_coord = item["center"]
                                    matched_desc = f"關鍵字「{kw}」({item.get('text')})"
                                    break
                            if present:
                                break

            elapsed = time.time() - start_time
            if is_wait_appear and present:
                self._log(f"  ✅ 條件達成！已偵測到「{matched_desc}」出現 (耗時 {elapsed:.1f}s)")
                return self._handle_detect_hit(
                    hit_name=matched_desc,
                    hit_center=hit_coord,
                    p=p,
                    img_shape=(screen.shape[0], screen.shape[1]),
                    is_image=is_image_mode,
                    template_img=template_img,
                    img_thresh=img_thresh,
                    img_multiscale=img_multiscale,
                    raw_kws=raw_kws,
                    is_check=is_check,
                    is_cross=is_cross
                )
            elif not is_wait_appear and not present:
                self._log(f"  ✅ 條件達成！目標「{desc}」已消失 (耗時 {elapsed:.1f}s)")
                click_mode = str(p.get("click_mode", "⏳ 無動作(僅等待)")).strip()
                is_wait_only = ("無動作" in click_mode or "僅等待" in click_mode or click_mode == "wait_only")
                if not is_wait_only:
                    return self._handle_detect_hit(
                        hit_name=f"目標消失「{desc}」",
                        hit_center=(p.get("custom_x", 960), p.get("custom_y", 540)),
                        p=p,
                        img_shape=(screen.shape[0], screen.shape[1]) if screen is not None else (1080, 1920),
                        is_image=False
                    )
                if delay_after > 0:
                    self._sleep_interruptible(delay_after)
                return True

            if not self._sleep_interruptible(interval):
                return False

        self._log(f"  ⚠️ 等待超時 ({timeout}s 未滿足「{desc}」{mode_str} 條件)")
        if delay_after > 0:
            self._sleep_interruptible(delay_after)
        return (on_timeout != "stop")

    def _exec_wait_sec(self, p: Dict[str, Any]) -> bool:
        sec = max(0.1, _safe_float(p.get("seconds", 3.0)))
        self._log(f"  ⏱ 等待 {sec:.1f} 秒...")
        return self._sleep_interruptible(sec)

    def _exec_swipe(self, p: Dict[str, Any]) -> bool:
        x1 = _safe_int(p.get("x1", 1500))
        y1 = _safe_int(p.get("y1", 540))
        x2 = _safe_int(p.get("x2", 400))
        y2 = _safe_int(p.get("y2", 540))
        dur = max(50, _safe_int(p.get("duration_ms", 400)))
        delay = _safe_float(p.get("delay", 1.0))

        self._log(f"  ↔ 滑動手勢: ({x1}, {y1}) ➜ ({x2}, {y2}) [{dur}ms]")
        if self.bot.device:
            try:
                self.bot.device.shell(f"input swipe {x1} {y1} {x2} {y2} {dur}")
            except Exception as e:
                self._log(f"  ⚠️ 滑動指令失敗: {e}")
        self._sleep_interruptible(delay)
        return True

    def _exec_back_key(self, p: Dict[str, Any]) -> bool:
        delay = _safe_float(p.get("delay", 1.2))
        self._log("  📱 按下模擬器返回鍵 (Back)")
        if self.bot.device:
            try:
                self.bot.device.shell("input keyevent 4")
            except Exception as e:
                self._log(f"  ⚠️ 返回鍵指令失敗: {e}")
        self._sleep_interruptible(delay)
        return True

    def _exec_comment(self, p: Dict[str, Any]) -> bool:
        """備註方塊：無程式功能，僅於日誌輸出備註提示"""
        note = p.get("note", "").strip()
        if note:
            self._log(f"  📝 [備註] {note}")
        return True

    def _exec_send_telegram(self, p: Dict[str, Any]) -> bool:
        """發送 Telegram 通知 (支援自訂文字與附帶模擬器截圖，預設讀取通用進階設定)"""
        use_custom = bool(p.get("use_custom", False))
        custom_tok = p.get("custom_token", "").strip() if use_custom else ""
        custom_cid = p.get("custom_chat_id", "").strip() if use_custom else ""

        token = custom_tok or self.global_settings.get("tg_token", "").strip()
        chat_id = custom_cid or self.global_settings.get("tg_chat_id", "").strip()

        if not token and self.bot:
            token = getattr(self.bot, "tg_token", "")
        if not chat_id and self.bot:
            chat_id = getattr(self.bot, "tg_chat_id", "")

        msg = p.get("message", "任務步驟執行完成！")
        attach_img = bool(p.get("attach_screenshot", True))
        delay_after = max(0.0, _safe_float(p.get("delay_after", 0.5)))

        if not token or not chat_id:
            self._log("⚠️ [Telegram] 尚未設定 Bot Token 或 Chat ID！請在「⚙ 通用進階」面板填寫或在積木內自訂。")
            if delay_after > 0:
                self._sleep_interruptible(delay_after)
            return True

        self._log(f"📱 正在發送 Telegram 通知:「{msg}」{' (附帶截圖)' if attach_img else ''}...")

        screen = None
        if attach_img and self.bot:
            try:
                screen = self.bot.capture_screen()
            except Exception:
                screen = None

        success = False
        if self.bot and hasattr(self.bot, "send_telegram_notify"):
            success = self.bot.send_telegram_notify(
                token=token,
                chat_id=chat_id,
                custom_text=msg,
                step_name="任務清單積木",
                screen_bgr=screen
            )
        else:
            success = self._send_telegram_direct(token, chat_id, msg, screen)

        if success:
            self._log(f"✅ [Telegram] 通知已成功發送！")
        else:
            self._log(f"⚠️ [Telegram] 通知發送請求已送出 (請確認網路連線與 Token/Chat ID 正確)")

        if delay_after > 0:
            self._sleep_interruptible(delay_after)
        return True

    def _send_telegram_direct(self, token: str, chat_id: str, text: str, screen_bgr: Optional[np.ndarray] = None) -> bool:
        now_str = time.strftime('%Y-%m-%d %H:%M:%S')
        full_msg = f"⚾ 【9局職棒任務清單通知】\n📢 訊息: {text}\n⏰ 時間: {now_str}"

        def _do_send():
            try:
                if screen_bgr is not None:
                    try:
                        ok, buf = cv2.imencode('.jpg', screen_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                        if ok:
                            url = f"https://api.telegram.org/bot{token}/sendPhoto"
                            files = {'photo': ('screenshot.jpg', buf.tobytes(), 'image/jpeg')}
                            data = {'chat_id': chat_id, 'caption': full_msg}
                            resp = requests.post(url, data=data, files=files, timeout=12)
                            if resp.status_code == 200 and resp.json().get("ok"):
                                return
                    except Exception:
                        pass

                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {"chat_id": chat_id, "text": full_msg}
                requests.post(url, json=payload, timeout=8)
            except Exception:
                pass

        threading.Thread(target=_do_send, daemon=True).start()
        return True


# ==========================================
# 任務清單 GUI 頁籤 (TaskFlowTab - CustomTkinter 現代化控制面板)
# ==========================================
class TaskFlowTab:
    """Scratch 積木式日常任務編程頁籤 (CustomTkinter 現代化控制面板)"""

    def __init__(
        self,
        parent: Any,
        bot_instance=None,
        gui_parent=None,
        log_callback: Optional[Callable[[str], None]] = None,
        instance_id: int = 1
    ):
        self.parent = parent
        self.bot = bot_instance
        self.gui = gui_parent
        self.log_callback = log_callback
        self.instance_id = instance_id

        # 連接父層 GUI 的全域通用進階變數
        if self.gui:
            self.var_interval = self.gui.var_interval
            self.var_confidence = self.gui.var_confidence
            self.var_idle_strategy = self.gui.var_idle_strategy
            self.var_lang_tc = self.gui.var_lang_tc
            self.var_lang_sc = self.gui.var_lang_sc
            self.var_lang_en = self.gui.var_lang_en
            self.var_tg_token = self.gui.var_tg_token
            self.var_tg_chat_id = self.gui.var_tg_chat_id
            self.var_watchdog_enabled = self.gui.var_watchdog_enabled
            self.var_watchdog_seconds = self.gui.var_watchdog_seconds
        else:
            self.var_interval = tk.DoubleVar(value=2.5)
            self.var_confidence = tk.DoubleVar(value=0.65)
            self.var_idle_strategy = tk.StringVar(value="快速跳過")
            self.var_lang_tc = tk.BooleanVar(value=True)
            self.var_lang_sc = tk.BooleanVar(value=False)
            self.var_lang_en = tk.BooleanVar(value=True)
            self.var_tg_token = tk.StringVar(value=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
            self.var_tg_chat_id = tk.StringVar(value=os.environ.get("TELEGRAM_CHAT_ID", ""))
            self.var_watchdog_enabled = tk.BooleanVar(value=False)
            self.var_watchdog_seconds = tk.IntVar(value=60)

        self._adv_open = False
        self.engine = TaskEngine(bot_instance=self.bot, log_callback=self._log, global_settings=self.get_global_settings())
        self.blocks_list: List[Dict[str, Any]] = []
        self.selected_block_idx: int = -1
        self.selected_block_target: Optional[Dict[str, Any]] = None

        def _on_lang_changed(*_):
            if self.bot and hasattr(self.bot, "set_allowed_languages"):
                self.bot.set_allowed_languages(
                    self.var_lang_tc.get(),
                    self.var_lang_sc.get(),
                    self.var_lang_en.get()
                )
            self.auto_save_config()

        self.var_lang_tc.trace_add("write", _on_lang_changed)
        self.var_lang_sc.trace_add("write", _on_lang_changed)
        self.var_lang_en.trace_add("write", _on_lang_changed)
        self.var_interval.trace_add("write", lambda *_: self.auto_save_config())
        self.var_confidence.trace_add("write", lambda *_: self.auto_save_config())
        self.var_tg_token.trace_add("write", lambda *_: self.auto_save_config())
        self.var_tg_chat_id.trace_add("write", lambda *_: self.auto_save_config())

        self.var_loop_count = tk.IntVar(value=1)
        self.var_status_text = tk.StringVar(value="🟢 閒置中")
        self.var_auto_preview = tk.BooleanVar(value=False)
        self.var_preview_coords = tk.StringVar(value="")
        self.var_picked_coord = tk.StringVar(value="尚未選取座標")

        self.current_screen_bgr: Optional[np.ndarray] = None
        self.preview_scale: float = 1.0
        self.preview_img_w: int = 0
        self.preview_img_h: int = 0
        self.raw_screen_w: int = 1920
        self.raw_screen_h: int = 1080
        self.canvas_w: int = 340
        self.canvas_h: int = 240
        self.preview_image_tk = None
        self._resize_job = None
        self._auto_preview_job = None
        self._capturing: bool = False
        self.selected_coord: Optional[Tuple[int, int]] = None
        self._drag_data = None

        if self.gui and hasattr(self.gui, "config_dir"):
            self.config_dir = self.gui.config_dir
        else:
            self.config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")
            if not os.path.exists(self.config_dir):
                try:
                    os.makedirs(self.config_dir, exist_ok=True)
                except Exception:
                    self.config_dir = os.getcwd()

        if self.gui and hasattr(self.gui, "task_presets_dir"):
            self.presets_dir = self.gui.task_presets_dir
            self.save_file = getattr(self.gui, "task_save_file", os.path.join(self.presets_dir, "tasks_flow.json"))
        else:
            self.presets_dir = self.config_dir
            tf_name = "tasks_flow.json" if self.instance_id == 1 else f"tasks_flow_{self.instance_id}.json"
            self.save_file = os.path.join(self.config_dir, tf_name)
        self.presets: Dict[str, Dict[str, Any]] = {}

        self.last_snipped_template = ""
        if self.gui and hasattr(self.gui, "last_snipped_template"):
            self.last_snipped_template = self.gui.last_snipped_template

        self._build_ui()
        self.reload_presets()
        self.load_config_auto()

    def resolve_image_path(self, p: str) -> Optional[str]:
        """解析圖片模板路徑，支援絕對路徑、相對路徑、截圖存檔、存檔目錄"""
        if not p:
            return None
        p = str(p).strip()
        if not p:
            return None
        if os.path.isabs(p) and os.path.isfile(p):
            return os.path.abspath(p)

        candidates = [
            p,
            os.path.join(self.presets_dir, p),
            os.path.join(self.presets_dir, os.path.basename(p)),
            os.path.join(self.presets_dir, "截圖存檔", os.path.basename(p)),
            os.path.join(self.presets_dir, "截圖存檔", p),
            os.path.join(self.presets_dir, "templates", os.path.basename(p)),
            os.path.join(self.presets_dir, "templates", p),
            os.path.join(self.config_dir, p),
            os.path.join(self.config_dir, "templates", os.path.basename(p)),
            os.path.join(os.getcwd(), p),
            os.path.join(os.getcwd(), "截圖存檔", os.path.basename(p)),
        ]
        if self.gui and hasattr(self.gui, "storage_dir") and self.gui.storage_dir:
            sd = self.gui.storage_dir
            candidates.append(os.path.join(sd, p))
            candidates.append(os.path.join(sd, os.path.basename(p)))
            candidates.append(os.path.join(sd, "截圖存檔", os.path.basename(p)))
            candidates.append(os.path.join(sd, "templates", os.path.basename(p)))

        if hasattr(self.bot, "resolve_template_path"):
            b_res = self.bot.resolve_template_path(p)
            if b_res and os.path.isfile(b_res):
                return os.path.abspath(b_res)

        for c in candidates:
            if c and os.path.isfile(c):
                return os.path.abspath(c)
        return None

    def on_snip_template_dialog(self, target_vp: Dict[str, Any], initial_name: str = "btn_template"):
        """開啟拖曳框選裁切對話框，儲存為圖片模板"""
        screen_bgr = self.current_screen_bgr
        if screen_bgr is None and self.gui and getattr(self.gui, "current_screen_bgr", None) is not None:
            screen_bgr = self.gui.current_screen_bgr
        if screen_bgr is None and self.bot and hasattr(self.bot, "capture_screen"):
            try:
                screen_bgr = self.bot.capture_screen()
                if screen_bgr is not None:
                    self.current_screen_bgr = screen_bgr
                    self._render_preview(screen_bgr)
            except Exception:
                screen_bgr = None

        if screen_bgr is None:
            messagebox.showwarning(
                "提示",
                "目前尚無畫面可用於截圖！\n請先確認模擬器已連線，並點擊右側「📸 截圖」取得畫面。",
                parent=self.parent
            )
            return

        save_dir = self.presets_dir
        if self.gui and hasattr(self.gui, "storage_dir") and self.gui.storage_dir:
            save_dir = self.gui.storage_dir

        def on_saved(saved_path: str):
            self.last_snipped_template = saved_path
            if self.gui and hasattr(self.gui, "last_snipped_template"):
                self.gui.last_snipped_template = saved_path
            if "template_image" in target_vp:
                target_vp["template_image"].set(saved_path)
            self.auto_save_config()
            self._log(f"✂️ 已框選並儲存模板圖片: {saved_path}")

        try:
            from gui import TemplateSnipperDialog
            TemplateSnipperDialog(
                parent=self.parent,
                screen_bgr=screen_bgr,
                initial_name=initial_name,
                templates_dir=save_dir,
                on_save_callback=on_saved
            )
        except Exception as e:
            messagebox.showerror("錯誤", f"開啟框選工具失敗: {e}", parent=self.parent)

    def on_browse_template_dialog(self, target_vp: Dict[str, Any]):
        """開啟檔案選擇器選擇本機圖片"""
        init_dir = self.presets_dir
        if self.gui and hasattr(self.gui, "storage_dir") and self.gui.storage_dir:
            init_dir = self.gui.storage_dir
        f = filedialog.askopenfilename(
            parent=self.parent,
            title="選擇圖片模板",
            initialdir=init_dir,
            filetypes=[("圖片檔案", "*.png *.jpg *.jpeg *.bmp"), ("所有檔案", "*.*")]
        )
        if f:
            abs_f = os.path.abspath(f)
            self.last_snipped_template = abs_f
            if self.gui and hasattr(self.gui, "last_snipped_template"):
                self.gui.last_snipped_template = abs_f
            if "template_image" in target_vp:
                target_vp["template_image"].set(abs_f)
            self.auto_save_config()
            self._log(f"📂 已選取圖片模板: {abs_f}")

    def on_apply_last_snippet(self, target_vp: Dict[str, Any]):
        """帶入最新裁切的截圖"""
        target = self.last_snipped_template
        if not target and self.gui and getattr(self.gui, "last_snipped_template", ""):
            target = self.gui.last_snipped_template

        if not target:
            search_dirs = [self.presets_dir]
            if self.gui and hasattr(self.gui, "storage_dir") and self.gui.storage_dir:
                search_dirs.append(self.gui.storage_dir)
            search_dirs.append(os.path.join(self.presets_dir, "截圖存檔"))

            all_imgs = []
            for sd in search_dirs:
                if sd and os.path.exists(sd):
                    try:
                        for fn in os.listdir(sd):
                            if fn.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                                fp = os.path.join(sd, fn)
                                if os.path.isfile(fp):
                                    all_imgs.append((os.path.getmtime(fp), fp))
                    except Exception:
                        pass
            if all_imgs:
                all_imgs.sort(key=lambda x: x[0], reverse=True)
                target = all_imgs[0][1]

        if not target:
            messagebox.showinfo("提示", "目前尚無任何截圖歷史記錄！\n請先點擊「✂️ 截圖」框選畫面。", parent=self.parent)
            return

        self.last_snipped_template = target
        if "template_image" in target_vp:
            target_vp["template_image"].set(target)
        self.auto_save_config()
        self._log(f"📥 已成功帶入最新截圖: {target}")

    def _build_image_template_row(self, parent_frame, vp: Dict[str, Any], block_dict: Optional[Dict[str, Any]] = None) -> ctk.CTkFrame:
        """建立圖片特徵比對專用控制面板 (縮圖、路徑、截圖、瀏覽、帶入、門檻、多尺度)"""
        box = ctk.CTkFrame(parent_frame, fg_color="#181825", corner_radius=6, border_width=1, border_color="#334155")

        # 行 1: 縮圖 + 門檻值滑桿 + 多尺度容錯
        row1 = ctk.CTkFrame(box, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=(4, 2))

        lbl_thumb = tk.Label(row1, bg="#11111B", fg=COLOR_TEXT_DIM, font=("Arial", 10), text="（未選圖）", width=8, height=2)
        lbl_thumb.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row1, text="門檻:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 2))
        lbl_thresh_val = ctk.CTkLabel(row1, text=f"{_safe_float(vp['image_threshold'].get(), 0.80):.2f}", width=34, font=ctk.CTkFont(family="Menlo", size=11))
        slider_thresh = ctk.CTkSlider(row1, from_=0.50, to=0.98, number_of_steps=48, variable=vp["image_threshold"], width=110, height=16)
        slider_thresh.pack(side="left", padx=(2, 2))
        lbl_thresh_val.pack(side="left", padx=(0, 6))

        def _on_slider(v):
            lbl_thresh_val.configure(text=f"{float(v):.2f}")
            self.auto_save_config()

        slider_thresh.configure(command=_on_slider)

        chk_multi = ctk.CTkCheckBox(
            row1,
            text="多尺度容錯 (0.95x~1.05x)",
            variable=vp["image_multiscale"],
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_PRIMARY,
            width=18,
            height=18,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4,
            command=self.auto_save_config
        )
        chk_multi.pack(side="left", padx=(4, 0))

        # 行 2: 圖片檔名/路徑輸入框 + 動作按鈕 (✂️ 截圖 / 📂 瀏覽 / 📥 帶入最新截圖)
        row2 = ctk.CTkFrame(box, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=(2, 5))

        ctk.CTkLabel(row2, text="圖檔:", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))
        ent_img = ctk.CTkEntry(row2, textvariable=vp["template_image"], height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, font=ctk.CTkFont(size=10))
        ent_img.pack(side="left", fill="x", expand=True, padx=(0, 6))

        init_name = block_dict["name"].get() if (block_dict and "name" in block_dict and hasattr(block_dict["name"], "get")) else "btn_task"

        btn_snip = ctk.CTkButton(
            row2,
            text="✂️ 截圖",
            width=54,
            height=24,
            corner_radius=4,
            command=lambda: self.on_snip_template_dialog(vp, initial_name=init_name),
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1"
        )
        btn_snip.pack(side="left", padx=(0, 4))

        btn_browse = ctk.CTkButton(
            row2,
            text="📂 瀏覽",
            width=54,
            height=24,
            corner_radius=4,
            command=lambda: self.on_browse_template_dialog(vp),
            font=ctk.CTkFont(size=10),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER
        )
        btn_browse.pack(side="left", padx=(0, 4))

        btn_apply = ctk.CTkButton(
            row2,
            text="📥 帶入最新截圖",
            width=96,
            height=24,
            corner_radius=4,
            command=lambda: self.on_apply_last_snippet(vp),
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#F59E0B",
            hover_color="#D97706"
        )
        btn_apply.pack(side="left")

        def _update_thumb(*_):
            img_val = vp["template_image"].get().strip() if "template_image" in vp and hasattr(vp["template_image"], "get") else ""
            if not img_val:
                lbl_thumb.configure(image="", text="（未選圖）", fg=COLOR_TEXT_DIM, width=8, height=2)
                lbl_thumb.image = None
                vp.pop("_thumb_img", None)
                return
            full_p = self.resolve_image_path(img_val)
            if full_p and os.path.exists(full_p):
                try:
                    bgr = imread_unicode(full_p)
                    if bgr is not None:
                        th_h, th_w = bgr.shape[:2]
                        max_dim = 36
                        scale = min(max_dim / max(1, th_w), max_dim / max(1, th_h))
                        tw, th = max(1, int(th_w * scale)), max(1, int(th_h * scale))
                        resized = cv2.resize(bgr, (tw, th), interpolation=cv2.INTER_AREA)
                        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                        pil_img = Image.fromarray(rgb)
                        tk_img = ImageTk.PhotoImage(pil_img)
                        lbl_thumb.configure(image=tk_img, text="", width=tw, height=th)
                        lbl_thumb.image = tk_img  # 保存在 Label 自身防止垃圾回收，絕不放進 var_params 污染存檔
                        vp.pop("_thumb_img", None)
                        return
                except Exception:
                    pass
            lbl_thumb.configure(image="", text="⚠️ 缺檔", fg="#EF4444", width=8, height=2)
            lbl_thumb.image = None
            vp.pop("_thumb_img", None)

        vp["template_image"].trace_add("write", _update_thumb)
        vp["template_image"].trace_add("write", lambda *_: self.auto_save_config())
        self.parent.after(100, _update_thumb)

        return box

    def get_global_settings(self) -> Dict[str, Any]:
        return {
            "interval": _safe_float(self.var_interval.get(), 2.5),
            "confidence": _safe_float(self.var_confidence.get(), 0.65),
            "idle_strategy": self.var_idle_strategy.get(),
            "lang_tc": bool(self.var_lang_tc.get()),
            "lang_sc": bool(self.var_lang_sc.get()),
            "lang_en": bool(self.var_lang_en.get()),
            "tg_token": self.var_tg_token.get().strip(),
            "tg_chat_id": self.var_tg_chat_id.get().strip(),
            "watchdog_enabled": bool(self.var_watchdog_enabled.get()),
            "watchdog_seconds": _safe_int(self.var_watchdog_seconds.get(), 60),
        }

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    def _build_ui(self):
        container = ctk.CTkFrame(self.parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=4, pady=4)
        container.grid_columnconfigure(0, weight=2)
        container.grid_columnconfigure(1, weight=5)
        container.grid_columnconfigure(2, weight=3)
        container.grid_rowconfigure(0, weight=1)

        frame_palette = ctk.CTkFrame(container, fg_color="transparent")
        frame_palette.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)

        frame_program = ctk.CTkFrame(container, fg_color="transparent")
        frame_program.grid(row=0, column=1, sticky="nsew", padx=(0, 6), pady=0)

        frame_picker = ctk.CTkFrame(container, fg_color="transparent")
        frame_picker.grid(row=0, column=2, sticky="nsew", padx=0, pady=0)

        self._build_palette_panel(frame_palette)
        self._build_program_panel(frame_program)
        self._build_picker_panel(frame_picker)

    def _build_palette_panel(self, parent):
        card_palette = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card_palette.pack(fill="x", pady=(0, 8))

        lbl_hdr = ctk.CTkLabel(
            card_palette,
            text="🧩 積木工具庫",
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        lbl_hdr.pack(anchor="w", padx=12, pady=(10, 2))

        lbl_tip = ctk.CTkLabel(
            card_palette,
            text="點擊積木加入程式區：",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_MUTED
        )
        lbl_tip.pack(anchor="w", padx=12, pady=(0, 6))

        box_blocks = ctk.CTkFrame(card_palette, fg_color="transparent")
        box_blocks.pack(fill="x", padx=10, pady=(0, 10))

        for b_type, info in BLOCK_TYPES.items():
            btn = ctk.CTkButton(
                box_blocks,
                text=f"[{info['badge']}] {info['title']} ＋",
                font=ctk.CTkFont(family="Arial", size=11, weight="bold"),
                fg_color=info["color"],
                hover_color=info["color"],
                height=30,
                corner_radius=6,
                anchor="w",
                command=lambda bt=b_type: self.add_block(bt)
            )
            btn.pack(fill="x", pady=2)

        card_presets = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card_presets.pack(fill="both", expand=True)

        tool_pre = ctk.CTkFrame(card_presets, fg_color="transparent")
        tool_pre.pack(fill="x", padx=12, pady=(10, 6))

        lbl_pre = ctk.CTkLabel(
            tool_pre,
            text="💾 任務存檔管理",
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        lbl_pre.pack(side="left")

        btn_new_pre = ctk.CTkButton(
            tool_pre,
            text="💾 存檔",
            width=54,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self.on_save_config_dialog
        )
        btn_new_pre.pack(side="right", padx=(4, 0))

        btn_load = ctk.CTkButton(
            tool_pre,
            text="📂 載入",
            width=54,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_load_config_dialog
        )
        btn_load.pack(side="right")

        self.frame_preset_buttons = ctk.CTkScrollableFrame(card_presets, fg_color="transparent", corner_radius=8)
        self.frame_preset_buttons.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def reload_presets(self):
        global DAILY_PRESETS
        DAILY_PRESETS.clear()
        self.presets = {}
        if not os.path.exists(self.presets_dir):
            self._render_preset_buttons()
            return

        try:
            entries = sorted(os.listdir(self.presets_dir))
        except Exception:
            entries = []

        for fname in entries:
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self.presets_dir, fname)
            key = os.path.splitext(fname)[0]
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                # 只有包含 blocks 或任務清單特徵的檔案才認列為任務設定檔
                if "blocks" not in data and "version" not in data and "loop_count" not in data:
                    continue
                title = data.get("title") or data.get("name") or key
                desc = data.get("desc", "")
                blocks = data.get("blocks", [])
                preset_obj = {
                    "key": key,
                    "title": title,
                    "desc": desc,
                    "blocks": blocks,
                    "loop_count": data.get("loop_count", 1),
                    "global_settings": data.get("global_settings", {}),
                    "file_path": fpath,
                }
                DAILY_PRESETS[key] = preset_obj
                self.presets[key] = preset_obj
            except Exception:
                pass

        self._render_preset_buttons()

    def _render_preset_buttons(self):
        if not hasattr(self, "frame_preset_buttons") or not self.frame_preset_buttons:
            return
        for w in self.frame_preset_buttons.winfo_children():
            w.destroy()

        if not self.presets:
            lbl_empty = ctk.CTkLabel(
                self.frame_preset_buttons,
                text="尚無任務存檔\n點擊「💾 存檔」或「📂 載入」\n即可管理任務設定。",
                font=ctk.CTkFont(size=11),
                text_color=COLOR_TEXT_DIM,
                justify="left"
            )
            lbl_empty.pack(anchor="w", padx=6, pady=8)
            return

        for p_key, p_val in list(self.presets.items()):
            row = ctk.CTkFrame(self.frame_preset_buttons, fg_color="transparent")
            row.pack(fill="x", pady=2)

            title_str = p_val.get("title", p_key)
            btn_load = ctk.CTkButton(
                row,
                text=title_str,
                font=ctk.CTkFont(size=11),
                fg_color=COLOR_BTN_DARK,
                hover_color=COLOR_BTN_DARK_HOVER,
                corner_radius=6,
                height=28,
                anchor="w",
                command=lambda pk=p_key: self.load_preset(pk)
            )
            btn_load.pack(side="left", fill="x", expand=True)

            btn_del = ctk.CTkButton(
                row,
                text="✕",
                width=26,
                height=28,
                corner_radius=6,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#EF4444",
                hover_color="#DC2626",
                command=lambda pk=p_key: self.delete_preset(pk)
            )
            btn_del.pack(side="right", padx=(4, 0))

    def delete_preset(self, preset_key: str):
        preset = self.presets.get(preset_key)
        title = preset.get("title", preset_key) if preset else preset_key
        if not messagebox.askyesno("確認刪除", f"確定要刪除任務存檔「{title}」嗎？"):
            return
        fpath = os.path.join(self.presets_dir, f"{preset_key}.json")
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
            self._log(f"已刪除任務存檔: {title}")
            self.reload_presets()
        except Exception as e:
            messagebox.showerror("錯誤", f"刪除存檔失敗: {e}")

    def _build_program_panel(self, parent):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="both", expand=True)

        tb = ctk.CTkFrame(card, fg_color="transparent")
        tb.pack(fill="x", padx=10, pady=(10, 6))
        self.bar_tb = tb

        self.btn_run = ctk.CTkButton(
            tb,
            text="▶ 全部執行",
            width=88,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color=COLOR_BTN_START,
            hover_color=COLOR_BTN_START_HOVER,
            command=self.on_run_tasks
        )
        self.btn_run.pack(side="left", padx=(0, 4))

        self.btn_step = ctk.CTkButton(
            tb,
            text="👣 單步",
            width=62,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self.on_step_task
        )
        self.btn_step.pack(side="left", padx=(0, 4))

        self.btn_stop = ctk.CTkButton(
            tb,
            text="⏹ 停止",
            width=62,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color=COLOR_BTN_STOP,
            hover_color=COLOR_BTN_STOP_HOVER,
            state="disabled",
            command=self.on_stop_tasks
        )
        self.btn_stop.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(tb, text="循環:", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_PRIMARY).pack(side="left")
        ent_loop = ctk.CTkEntry(tb, textvariable=self.var_loop_count, width=44, height=28, corner_radius=6, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)
        ent_loop.pack(side="left", padx=(4, 2))
        ctk.CTkLabel(tb, text="次(0=無限)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 8))

        self.btn_adv = ctk.CTkButton(
            tb,
            text="進階設定 ▸",
            width=82,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self._toggle_advanced
        )
        self.btn_adv.pack(side="left", padx=(2, 0))

        btn_clear = ctk.CTkButton(
            tb,
            text="清空",
            width=46,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color="#EF4444",
            hover_color="#DC2626",
            command=self.on_clear_blocks
        )
        btn_clear.pack(side="right")

        btn_load = ctk.CTkButton(
            tb,
            text="載入",
            width=46,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_load_config_dialog
        )
        btn_load.pack(side="right", padx=(4, 4))

        btn_save = ctk.CTkButton(
            tb,
            text="存檔",
            width=46,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_save_config_dialog
        )
        btn_save.pack(side="right")

        self._build_advanced_panel(card)

        self.bar_status = ctk.CTkFrame(card, fg_color=COLOR_CARD_ITEM, corner_radius=6, border_width=1, border_color=COLOR_CARD_BORDER)
        self.bar_status.pack(fill="x", padx=10, pady=(0, 6))

        self.indicator_light = ctk.CTkLabel(
            self.bar_status,
            text="●",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#10B981"
        )
        self.indicator_light.pack(side="left", padx=(8, 4), pady=4)

        self.lbl_st = ctk.CTkLabel(
            self.bar_status,
            textvariable=self.var_status_text,
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        self.lbl_st.pack(side="left", pady=4)

        self.scroll_blocks = ctk.CTkScrollableFrame(card, fg_color=COLOR_INPUT_BG, corner_radius=8)
        self.scroll_blocks.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.inner_blocks = self.scroll_blocks
        self.canvas_blocks = getattr(self.scroll_blocks, "_parent_canvas", self.scroll_blocks)

    def _build_advanced_panel(self, parent):
        f = ctk.CTkFrame(parent, fg_color=COLOR_CARD_ITEM, corner_radius=8, border_width=1, border_color=COLOR_CARD_BORDER)
        self.adv_frame = f

        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        lbl_title = ctk.CTkLabel(
            inner,
            text="⚙ 進階設定（與聯賽自動刷共享）",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        lbl_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ctk.CTkLabel(inner, text="掃描間隔:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).grid(row=1, column=0, sticky="w", pady=3)
        row_speed = ctk.CTkFrame(inner, fg_color="transparent")
        row_speed.grid(row=1, column=1, sticky="w", padx=6, pady=3)

        def _on_speed_slider(v):
            self.var_interval.set(round(float(v), 2))

        scale_speed = ctk.CTkSlider(
            row_speed, from_=0.0, to=5.0, variable=self.var_interval, width=120, height=16,
            command=_on_speed_slider
        )
        scale_speed.pack(side="left", padx=(0, 6))
        ent_speed = ctk.CTkEntry(row_speed, textvariable=self.var_interval, width=48, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)
        ent_speed.pack(side="left", padx=(0, 4))
        ctk.CTkLabel(row_speed, text="秒 (0=不延遲)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left")

        ctk.CTkLabel(inner, text="辨識門檻:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).grid(row=2, column=0, sticky="w", pady=3)
        row_conf = ctk.CTkFrame(inner, fg_color="transparent")
        row_conf.grid(row=2, column=1, sticky="w", padx=6, pady=3)

        self.lbl_conf_val = ctk.CTkLabel(row_conf, text=f"{self.var_confidence.get():.2f}", font=ctk.CTkFont(size=11), width=36)
        def _on_conf_slider(v):
            val = round(float(v), 2)
            self.var_confidence.set(val)
            self.lbl_conf_val.configure(text=f"{val:.2f}")

        scale_conf = ctk.CTkSlider(
            row_conf, from_=0.40, to=0.95, variable=self.var_confidence, width=120, height=16,
            command=_on_conf_slider
        )
        scale_conf.pack(side="left", padx=(0, 6))
        self.lbl_conf_val.pack(side="left")

        ctk.CTkLabel(inner, text="找不到目標時:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).grid(row=3, column=0, sticky="w", pady=3)
        cbo_idle = ctk.CTkComboBox(
            inner, variable=self.var_idle_strategy, values=["快速跳過", "等待下輪", "隨機點擊", "固定點擊", "不動作"],
            width=120, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly"
        )
        cbo_idle.grid(row=3, column=1, sticky="w", padx=6, pady=3)

        ctk.CTkLabel(inner, text="語言辨識:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).grid(row=4, column=0, sticky="w", pady=3)
        row_lang = ctk.CTkFrame(inner, fg_color="transparent")
        row_lang.grid(row=4, column=1, sticky="w", padx=6, pady=3)
        ctk.CTkCheckBox(row_lang, text="繁中", variable=self.var_lang_tc, font=ctk.CTkFont(size=11), width=56, checkbox_width=16, checkbox_height=16).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(row_lang, text="簡中", variable=self.var_lang_sc, font=ctk.CTkFont(size=11), width=56, checkbox_width=16, checkbox_height=16).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(row_lang, text="英文/數字", variable=self.var_lang_en, font=ctk.CTkFont(size=11), width=80, checkbox_width=16, checkbox_height=16).pack(side="left")

        ctk.CTkLabel(inner, text="Telegram:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).grid(row=5, column=0, sticky="w", pady=3)
        row_tg = ctk.CTkFrame(inner, fg_color="transparent")
        row_tg.grid(row=5, column=1, sticky="w", padx=6, pady=3)

        ctk.CTkLabel(row_tg, text="Token:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left")
        ctk.CTkEntry(row_tg, textvariable=self.var_tg_token, width=120, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6))
        ctk.CTkLabel(row_tg, text="Chat ID:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left")
        ctk.CTkEntry(row_tg, textvariable=self.var_tg_chat_id, width=80, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6))

        btn_test_tg = ctk.CTkButton(
            row_tg, text="測試發送", width=64, height=24, corner_radius=4, font=ctk.CTkFont(size=10),
            fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, command=self.on_test_telegram_message
        )
        btn_test_tg.pack(side="left")

    def _toggle_advanced(self):
        self._adv_open = not self._adv_open
        if self._adv_open:
            self.adv_frame.pack(fill="x", after=self.bar_tb, padx=10, pady=(0, 6))
            self.btn_adv.configure(text="進階設定 ▾")
        else:
            self.adv_frame.pack_forget()
            self.btn_adv.configure(text="進階設定 ▸")

    def on_test_telegram_message(self):
        tok = self.var_tg_token.get().strip()
        cid = self.var_tg_chat_id.get().strip()
        if not tok or not cid:
            messagebox.showwarning("提示", "請先輸入 Telegram Bot Token 與 Chat ID！")
            return
        self._log("📱 正在發送 Telegram 測試通知...")
        screen = None
        if self.bot and hasattr(self.bot, "capture_screen"):
            try:
                screen = self.bot.capture_screen()
            except Exception:
                screen = None
        elif self.current_screen_bgr is not None:
            screen = self.current_screen_bgr

        if self.bot and hasattr(self.bot, "send_telegram_notify"):
            success = self.bot.send_telegram_notify(
                token=tok,
                chat_id=cid,
                custom_text="⚾ 任務清單 Telegram 連線測試成功！",
                step_name="手動測試",
                screen_bgr=screen
            )
        else:
            success = self.engine._send_telegram_direct(tok, cid, "⚾ 任務清單 Telegram 連線測試成功！", screen)

        if success:
            self._log("✅ 測試請求已送出，請檢查 Telegram 聊天室！")

    def _build_picker_panel(self, parent):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="both", expand=True)

        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=10, pady=(10, 6))

        self.btn_capture = ctk.CTkButton(
            tools,
            text="📸 截圖",
            width=76,
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(family="Arial", size=11, weight="bold"),
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self.on_capture_screen
        )
        self.btn_capture.pack(side="left")

        sw_auto = ctk.CTkSwitch(
            tools,
            text="自動刷新",
            variable=self.var_auto_preview,
            font=ctk.CTkFont(size=11),
            command=self.on_toggle_auto_refresh,
            width=80
        )
        sw_auto.pack(side="left", padx=8)

        self.lbl_coord_rt = ctk.CTkLabel(
            tools,
            textvariable=self.var_preview_coords,
            font=ctk.CTkFont(family="Menlo", size=12, weight="bold"),
            text_color="#60A5FA"
        )
        self.lbl_coord_rt.pack(side="right")

        self.preview_holder = tk.Frame(card, width=340, height=240, bg="#181825")
        self.preview_holder.pack_propagate(False)
        self.preview_holder.pack(fill="both", expand=True, padx=10, pady=(4, 6))
        self.preview_holder.bind("<Configure>", self._on_preview_resize)

        self.lbl_canvas = tk.Label(
            self.preview_holder,
            text="連線後按「📸 截圖」，\n再點擊畫面即可選取座標",
            bg="#181825",
            fg="#A6ADC8",
            cursor="crosshair",
            anchor=tk.CENTER,
            font=("Arial", 11)
        )
        self.lbl_canvas.pack(fill="both", expand=True)
        self.lbl_canvas.bind("<Motion>", self._on_preview_mouse_move)
        self.lbl_canvas.bind("<Leave>", lambda e: self.var_preview_coords.set(""))
        self.lbl_canvas.bind("<Button-1>", self._on_preview_click)

        coord_box = ctk.CTkFrame(card, fg_color="transparent")
        coord_box.pack(fill="x", padx=10, pady=(0, 10))

        lbl_c = ctk.CTkLabel(
            coord_box,
            textvariable=self.var_picked_coord,
            font=ctk.CTkFont(family="Menlo", size=12, weight="bold"),
            text_color="#38BDF8"
        )
        lbl_c.pack(anchor="w", pady=(0, 4))

        row_fill = ctk.CTkFrame(coord_box, fg_color="transparent")
        row_fill.pack(fill="x", pady=2)

        btn_fill_sel = ctk.CTkButton(
            row_fill,
            text="填入選取的積木",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            corner_radius=6,
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self.on_fill_selected_block
        )
        btn_fill_sel.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_copy = ctk.CTkButton(
            row_fill,
            text="複製",
            width=50,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_copy_picked_coord
        )
        btn_copy.pack(side="right")

        row_cond = ctk.CTkFrame(coord_box, fg_color="transparent")
        row_cond.pack(fill="x", pady=2)

        btn_if = ctk.CTkButton(
            row_cond,
            text="填入 If",
            font=ctk.CTkFont(size=11),
            height=26,
            corner_radius=6,
            fg_color="#D97706",
            hover_color="#B45309",
            command=lambda: self.on_fill_branch_coord(0)
        )
        btn_if.pack(side="left", fill="x", expand=True, padx=(0, 2))

        btn_elif = ctk.CTkButton(
            row_cond,
            text="填入 Else If 1",
            font=ctk.CTkFont(size=11),
            height=26,
            corner_radius=6,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=lambda: self.on_fill_branch_coord(1)
        )
        btn_elif.pack(side="left", fill="x", expand=True, padx=(0, 2))

        btn_else = ctk.CTkButton(
            row_cond,
            text="填入 Else",
            width=68,
            height=26,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color="#475569",
            hover_color="#334155",
            command=lambda: self.on_fill_branch_coord("else")
        )
        btn_else.pack(side="right")

    def add_block(
        self,
        b_type: str,
        params: Optional[Dict[str, Any]] = None,
        name: str = "",
        enabled: bool = True,
        parent_loop: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        info = BLOCK_TYPES.get(b_type, BLOCK_TYPES["tap_coord"])
        if params is None:
            params = dict(info["default_params"])
        if not name:
            if parent_loop:
                name = f"{info['default_name']} #{len(parent_loop.get('inner_blocks_list', [])) + 1}"
            else:
                name = f"{info['default_name']} #{len(self.blocks_list) + 1}"

        block_item = {
            "type": b_type,
            "name": tk.StringVar(value=name),
            "enabled": tk.BooleanVar(value=enabled),
            "params": params,
            "var_params": {},
            "frame": None,
            "expanded": tk.BooleanVar(value=True),
            "parent_loop": parent_loop,
            "inner_blocks_list": [],
        }

        self._render_block_widget(block_item, parent_loop=parent_loop)

        if parent_loop:
            parent_loop.setdefault("inner_blocks_list", []).append(block_item)
        else:
            self.blocks_list.append(block_item)

        if b_type == "loop" and "inner_blocks" in params:
            for sub_data in params.get("inner_blocks", []):
                self.add_block(
                    b_type=sub_data.get("type", "tap_coord"),
                    params=sub_data.get("params"),
                    name=sub_data.get("name", ""),
                    enabled=sub_data.get("enabled", True),
                    parent_loop=block_item
                )

        self._renumber_blocks()
        self.auto_save_config()

        if parent_loop is None:
            self.parent.after(50, lambda: getattr(self.canvas_blocks, "yview_moveto", lambda *_: None)(1.0))

        return block_item

    def add_inner_block(self, loop_item: Dict[str, Any], b_type: str, params: Optional[Dict[str, Any]] = None, name: str = ""):
        return self.add_block(b_type=b_type, params=params, name=name, parent_loop=loop_item)

    def pull_prev_block_into_loop(self, loop_item: Dict[str, Any]):
        if loop_item not in self.blocks_list:
            return
        idx = self.blocks_list.index(loop_item)
        if idx <= 0:
            messagebox.showinfo("提示", "此迴圈上方沒有其他積木可裝入！")
            return
        prev_b = self.blocks_list.pop(idx - 1)
        prev_b["parent_loop"] = loop_item
        loop_item.setdefault("inner_blocks_list", []).append(prev_b)
        prev_b["frame"].destroy()
        self._render_block_widget(prev_b, parent_loop=loop_item)
        self._repack_all_blocks()
        self.auto_save_config()
        self._log(f"已將上方積木 [{prev_b['name'].get()}] 裝入迴圈！")

    def move_out_of_loop(self, child_block: Dict[str, Any]):
        parent = child_block.get("parent_loop")
        if not parent or parent not in self.blocks_list:
            return
        in_list = parent.get("inner_blocks_list", [])
        if child_block in in_list:
            in_list.remove(child_block)
            idx = self.blocks_list.index(parent)
            self.blocks_list.insert(idx + 1, child_block)
            child_block["parent_loop"] = None
            child_block["frame"].destroy()
            self._render_block_widget(child_block, parent_loop=None)
            self._repack_all_blocks()
            self.auto_save_config()
            self._log(f"已將積木 [{child_block['name'].get()}] 移出迴圈至主列表")

    def _render_block_widget(self, block_item: Dict[str, Any], parent_loop: Optional[Dict[str, Any]] = None):
        b_type = block_item["type"]
        info = BLOCK_TYPES.get(b_type, BLOCK_TYPES["tap_coord"])

        target_parent = parent_loop["inner_container"] if (parent_loop and "inner_container" in parent_loop) else self.inner_blocks
        card = ctk.CTkFrame(
            target_parent,
            fg_color=COLOR_CARD_ITEM,
            corner_radius=8,
            border_width=1,
            border_color=info["color"]
        )
        card.pack(fill="x", padx=4, pady=3)
        block_item["frame"] = card

        hdr = ctk.CTkFrame(card, fg_color=info["color"], corner_radius=6, height=32)
        hdr.pack(fill="x", padx=2, pady=2)

        lbl_drag = ctk.CTkLabel(
            hdr,
            text=" ☰ ",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            text_color="#FFFFFF",
            cursor="fleur"
        )
        lbl_drag.pack(side="left", padx=(2, 0))
        self._bind_drag(lbl_drag, block_item)

        chk_en = ctk.CTkCheckBox(
            hdr,
            text="",
            variable=block_item["enabled"],
            width=20,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=4,
            fg_color="#10B981",
            hover_color="#059669"
        )
        chk_en.pack(side="left", padx=(0, 2))

        lbl_num = ctk.CTkLabel(
            hdr,
            text="#0",
            font=ctk.CTkFont(family="Arial", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        lbl_num.pack(side="left", padx=2)
        block_item["lbl_num"] = lbl_num

        ent_name = ctk.CTkEntry(
            hdr,
            textvariable=block_item["name"],
            width=130,
            height=24,
            corner_radius=4,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11)
        )
        ent_name.pack(side="left", padx=4)

        lbl_type = ctk.CTkLabel(
            hdr,
            text=f"[{info['badge']}]",
            font=ctk.CTkFont(family="Arial", size=10),
            text_color="#FFFFFF"
        )
        lbl_type.pack(side="left", padx=2)

        btn_del = ctk.CTkButton(
            hdr,
            text="✕",
            width=24,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#EF4444",
            hover_color="#DC2626",
            command=lambda: self.delete_block(block_item)
        )
        btn_del.pack(side="right", padx=(2, 2))

        btn_dup = ctk.CTkButton(
            hdr,
            text="複製",
            width=38,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=lambda: self.duplicate_block(block_item)
        )
        btn_dup.pack(side="right", padx=1)

        btn_down = ctk.CTkButton(
            hdr,
            text="▼",
            width=24,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=lambda: self.move_block(block_item, 1)
        )
        btn_down.pack(side="right", padx=1)

        btn_up = ctk.CTkButton(
            hdr,
            text="▲",
            width=24,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=lambda: self.move_block(block_item, -1)
        )
        btn_up.pack(side="right", padx=1)

        if parent_loop:
            btn_out = ctk.CTkButton(
                hdr,
                text="移出",
                width=38,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#FB923C",
                hover_color="#EA580C",
                text_color="#000000",
                command=lambda: self.move_out_of_loop(block_item)
            )
            btn_out.pack(side="right", padx=1)

        btn_pick = ctk.CTkButton(
            hdr,
            text="選取",
            width=38,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#F59E0B",
            hover_color="#D97706",
            text_color="#000000",
            command=lambda: self.select_block(block_item)
        )
        btn_pick.pack(side="right", padx=(1, 4))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=6, pady=(2, 6))
        block_item["body_frame"] = body

        self._build_block_fields(block_item, body)

    def _build_block_fields(self, block: Dict[str, Any], body: ctk.CTkFrame):
        b_type = block["type"]
        p = block["params"]
        vp = block["var_params"]

        if b_type == "tap_coord":
            vp["x"] = tk.IntVar(value=p.get("x", 960))
            vp["y"] = tk.IntVar(value=p.get("y", 540))
            vp["delay"] = tk.DoubleVar(value=p.get("delay", 1.5))
            vp["repeat"] = tk.IntVar(value=p.get("repeat", 1))

            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="座標 X:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row, textvariable=vp["x"], width=50, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6))
            ctk.CTkLabel(row, text="Y:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row, textvariable=vp["y"], width=50, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6))
            btn_fill = ctk.CTkButton(row, text="填入", width=46, height=26, corner_radius=4, fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, font=ctk.CTkFont(size=11), command=lambda target=block: self._fill_block_coords(target))
            btn_fill.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(row, text="延遲:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row, textvariable=vp["delay"], width=46, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(row, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 10))

            ctk.CTkLabel(row, text="點擊次數:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row, textvariable=vp["repeat"], width=42, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 0))

        elif b_type == "multi_tap":
            vp["x"] = tk.IntVar(value=_safe_int(p.get("x", 960)))
            vp["y"] = tk.IntVar(value=_safe_int(p.get("y", 540)))
            vp["count"] = tk.IntVar(value=_safe_int(p.get("count", 10)))
            vp["interval"] = tk.DoubleVar(value=_safe_float(p.get("interval", 0.3)))
            vp["stop_mode"] = tk.StringVar(value=p.get("stop_mode", "無 (僅點滿次數)"))
            vp["stop_keywords"] = tk.StringVar(value=p.get("stop_keywords", "確認, 確定, 完成, 上限"))
            vp["template_image"] = tk.StringVar(value=p.get("template_image", ""))
            vp["image_threshold"] = tk.DoubleVar(value=_safe_float(p.get("image_threshold", 0.80), 0.80))
            vp["image_multiscale"] = tk.BooleanVar(value=bool(p.get("image_multiscale", False)))
            vp["check_every"] = tk.IntVar(value=_safe_int(p.get("check_every", 1)))
            vp["delay_after"] = tk.DoubleVar(value=_safe_float(p.get("delay_after", 0.5)))

            row1 = ctk.CTkFrame(body, fg_color="transparent")
            row1.pack(fill="x", pady=2)
            ctk.CTkLabel(row1, text="座標 X:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row1, textvariable=vp["x"], width=50, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6))
            ctk.CTkLabel(row1, text="Y:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row1, textvariable=vp["y"], width=50, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6))
            btn_fill = ctk.CTkButton(row1, text="填入", width=46, height=26, corner_radius=4, fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, font=ctk.CTkFont(size=11), command=lambda target=block: self._fill_block_coords(target))
            btn_fill.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(row1, text="次數:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row1, textvariable=vp["count"], width=46, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(row1, text="次(0=無限)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 8))

            ctk.CTkLabel(row1, text="間隔:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row1, textvariable=vp["interval"], width=46, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(row1, text="秒/次", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left")

            row2 = ctk.CTkFrame(body, fg_color="transparent")
            row2.pack(fill="x", pady=2)
            ctk.CTkLabel(row2, text="停止條件:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#FB923C").pack(side="left")
            combo_stop = ctk.CTkComboBox(row2, variable=vp["stop_mode"], values=[
                "無 (僅點滿次數)",
                "偵測到文字出現",
                "偵測到文字消失",
                "偵測到圖片出現",
                "偵測到圖片消失",
                "偵測到打勾圖案",
                "偵測到叉叉圖案"
            ], width=130, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly")
            combo_stop.pack(side="left", padx=(4, 6))

            box_kws = ctk.CTkFrame(row2, fg_color="transparent")
            ctk.CTkLabel(box_kws, text="關鍵字:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(box_kws, textvariable=vp["stop_keywords"], width=130, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6))

            ctk.CTkLabel(row2, text="每:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row2, textvariable=vp["check_every"], width=36, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(row2, text="次檢查", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(row2, text="結束延遲:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row2, textvariable=vp["delay_after"], width=42, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(row2, text="秒", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left")

            box_img_multi = self._build_image_template_row(body, vp, block_dict=block)

            def _toggle_stop_mode(*_):
                sm = vp["stop_mode"].get()
                if "圖片" in sm:
                    box_kws.pack_forget()
                    box_img_multi.pack(fill="x", pady=(2, 2))
                elif "文字" in sm:
                    box_img_multi.pack_forget()
                    box_kws.pack(side="left")
                else:
                    box_img_multi.pack_forget()
                    box_kws.pack_forget()
            vp["stop_mode"].trace_add("write", _toggle_stop_mode)
            _toggle_stop_mode()

        elif b_type == "detect_click":
            vp["target_type"] = tk.StringVar(value=p.get("target_type", "📝 僅文字"))
            vp["keywords"] = tk.StringVar(value=p.get("keywords", "確認, 確定"))
            vp["template_image"] = tk.StringVar(value=p.get("template_image", ""))
            vp["image_threshold"] = tk.DoubleVar(value=_safe_float(p.get("image_threshold", 0.80), 0.80))
            vp["image_multiscale"] = tk.BooleanVar(value=bool(p.get("image_multiscale", False)))
            vp["timeout"] = tk.IntVar(value=_safe_int(p.get("timeout", 10)))

            raw_mode = p.get("click_mode", "🎯 點擊目標中心")
            if raw_mode in ("click_text", "click_target", "點擊目標中心", "🎯 點擊目標圖片 (按鈕中心)", "🎯 點擊目標文字 (詞條中心)"):
                init_act = "🎯 點擊目標中心"
            elif raw_mode in ("custom_coord", "自訂座標", "📍 點擊指定座標 (自訂)"):
                init_act = "📍 點擊自訂座標"
            elif raw_mode in ("custom_block", "自訂特定區塊", "🔲 自訂特定區塊"):
                init_act = "🔲 自訂特定區塊"
            elif raw_mode in ("wait_only", "無動作", "無動作(僅等待)", "⏳ 無動作(僅等待)"):
                init_act = "⏳ 無動作(僅等待)"
            else:
                init_act = raw_mode
            vp["click_mode"] = tk.StringVar(value=init_act)

            vp["custom_x"] = tk.IntVar(value=_safe_int(p.get("custom_x", 960)))
            vp["custom_y"] = tk.IntVar(value=_safe_int(p.get("custom_y", 540)))
            vp["block_x1"] = tk.IntVar(value=_safe_int(p.get("block_x1", 800)))
            vp["block_y1"] = tk.IntVar(value=_safe_int(p.get("block_y1", 450)))
            vp["block_x2"] = tk.IntVar(value=_safe_int(p.get("block_x2", 1120)))
            vp["block_y2"] = tk.IntVar(value=_safe_int(p.get("block_y2", 630)))
            vp["delay"] = tk.DoubleVar(value=_safe_float(p.get("delay", 1.5)))
            vp["on_timeout"] = tk.StringVar(value=p.get("on_timeout", "continue"))

            # 命中後連點設定
            vp["repeat_enabled"] = tk.BooleanVar(value=bool(p.get("repeat_enabled", False)))
            vp["repeat_mode"] = tk.StringVar(value=p.get("repeat_mode", "指定次數"))
            vp["repeat_count"] = tk.IntVar(value=_safe_int(p.get("repeat_count", 10)))
            vp["repeat_interval"] = tk.DoubleVar(value=_safe_float(p.get("repeat_interval", p.get("repeat_speed", 0.25))))
            vp["repeat_area"] = tk.StringVar(value=p.get("repeat_area", "跟隨命中目標"))
            vp["repeat_custom_x"] = tk.IntVar(value=_safe_int(p.get("repeat_custom_x", 960)))
            vp["repeat_custom_y"] = tk.IntVar(value=_safe_int(p.get("repeat_custom_y", 540)))

            for k in ("target_type", "keywords", "template_image", "image_threshold", "image_multiscale",
                      "timeout", "click_mode", "custom_x", "custom_y", "block_x1", "block_y1",
                      "block_x2", "block_y2", "delay", "on_timeout", "repeat_enabled", "repeat_mode",
                      "repeat_count", "repeat_interval", "repeat_area", "repeat_custom_x", "repeat_custom_y"):
                vp[k].trace_add("write", lambda *_: self.auto_save_config())

            def _fill_from_preview(target_x_var, target_y_var, desc_label="座標"):
                c_text = self.var_picked_coord.get()
                if "座標:" not in c_text:
                    messagebox.showinfo("提示", "請先在右側截圖預覽上點擊位置以獲取座標！")
                    return
                raw = c_text.replace("座標:", "").strip().strip("()")
                try:
                    x, y = [int(v.strip()) for v in raw.split(",")]
                    target_x_var.set(x)
                    target_y_var.set(y)
                    b_name = block["name"].get() if hasattr(block.get("name"), "get") else "偵測點擊"
                    self._log(f"已將選取座標 ({x}, {y}) 填入 [{b_name}] 之 {desc_label}")
                    self.auto_save_config()
                except Exception:
                    pass

            # 行 1: 偵測類型與關鍵字
            row1 = ctk.CTkFrame(body, fg_color="transparent")
            row1.pack(fill="x", pady=2)
            ctk.CTkLabel(row1, text="類型:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkComboBox(
                row1,
                variable=vp["target_type"],
                values=["📝 僅文字", "🖼️ 圖片特徵 (模板比對)", "✓ 打勾圖案", "✕ 叉叉/關閉", "🔀 文字或圖案"],
                width=140,
                height=26,
                corner_radius=4,
                fg_color=COLOR_INPUT_BG,
                border_color=COLOR_INPUT_BORDER,
                state="readonly"
            ).pack(side="left", padx=(2, 6))

            box_kw = ctk.CTkFrame(row1, fg_color="transparent")
            ctk.CTkLabel(box_kw, text="關鍵字:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(box_kw, textvariable=vp["keywords"], width=150, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6), fill="x", expand=True)

            # 圖片模板微縮圖與參數設定列
            box_img_det = self._build_image_template_row(body, vp, block_dict=block)

            # 行 2: 動作設定、超時與延遲
            row2 = ctk.CTkFrame(body, fg_color="transparent")
            row2.pack(fill="x", pady=2)
            ctk.CTkLabel(row2, text="超時:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row2, textvariable=vp["timeout"], width=38, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(row2, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(row2, text="動作:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left")
            ACTION_MODES = ["🎯 點擊目標中心", "📍 點擊自訂座標", "🔲 自訂特定區塊", "⏳ 無動作(僅等待)"]
            combo_act = ctk.CTkComboBox(row2, variable=vp["click_mode"], values=ACTION_MODES, width=135, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly")
            combo_act.pack(side="left", padx=(2, 6))

            ctk.CTkLabel(row2, text="延遲:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row2, textvariable=vp["delay"], width=40, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(row2, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")

            # 動作細項面板：自訂座標輸入
            box_custom_xy = ctk.CTkFrame(body, fg_color="transparent")
            ctk.CTkLabel(box_custom_xy, text="點擊座標 X:", font=ctk.CTkFont(size=11), text_color="#38BDF8").pack(side="left")
            ctk.CTkEntry(box_custom_xy, textvariable=vp["custom_x"], width=48, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 4))
            ctk.CTkLabel(box_custom_xy, text="Y:", font=ctk.CTkFont(size=11), text_color="#38BDF8").pack(side="left")
            ctk.CTkEntry(box_custom_xy, textvariable=vp["custom_y"], width=48, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6))
            ctk.CTkButton(box_custom_xy, text="填入選取座標", width=76, height=24, corner_radius=4, font=ctk.CTkFont(size=10, weight="bold"), fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, command=lambda: _fill_from_preview(vp["custom_x"], vp["custom_y"], "自訂座標")).pack(side="left")

            # 動作細項面板：自訂特定區塊輸入
            box_custom_block = ctk.CTkFrame(body, fg_color="transparent")
            ctk.CTkLabel(box_custom_block, text="區塊左上(X1,Y1):", font=ctk.CTkFont(size=10), text_color="#A78BFA").pack(side="left")
            ctk.CTkEntry(box_custom_block, textvariable=vp["block_x1"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=1)
            ctk.CTkEntry(box_custom_block, textvariable=vp["block_y1"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(1, 4))
            ctk.CTkButton(box_custom_block, text="填左上", width=46, height=22, corner_radius=4, font=ctk.CTkFont(size=9), fg_color="#6D28D9", hover_color="#5B21B6", command=lambda: _fill_from_preview(vp["block_x1"], vp["block_y1"], "區塊左上")).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(box_custom_block, text="右下(X2,Y2):", font=ctk.CTkFont(size=10), text_color="#A78BFA").pack(side="left")
            ctk.CTkEntry(box_custom_block, textvariable=vp["block_x2"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=1)
            ctk.CTkEntry(box_custom_block, textvariable=vp["block_y2"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(1, 4))
            ctk.CTkButton(box_custom_block, text="填右下", width=46, height=22, corner_radius=4, font=ctk.CTkFont(size=9), fg_color="#6D28D9", hover_color="#5B21B6", command=lambda: _fill_from_preview(vp["block_x2"], vp["block_y2"], "區塊右下")).pack(side="left")

            # 行 3: ⚡ 命中後連點（過場跳過）勾選框
            row_rep = ctk.CTkFrame(body, fg_color="transparent")
            row_rep.pack(fill="x", pady=(3, 1))
            ctk.CTkCheckBox(
                row_rep,
                text="⚡ 命中後連點（過場跳過）",
                variable=vp["repeat_enabled"],
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#F59E0B",
                width=18,
                height=18,
                checkbox_width=16,
                checkbox_height=16,
                corner_radius=4
            ).pack(side="left", padx=(0, 6))

            # 連點細項面板 (暗色圓角卡片)
            box_rep_detail = ctk.CTkFrame(body, fg_color="#181825", corner_radius=6, border_width=1, border_color="#334155")

            # 連點面板第 1 列: 模式 + 次數 + 間隔
            row_ro1 = ctk.CTkFrame(box_rep_detail, fg_color="transparent")
            row_ro1.pack(fill="x", padx=6, pady=(3, 2))

            ctk.CTkLabel(row_ro1, text="連點模式:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
            ctk.CTkOptionMenu(
                row_ro1,
                variable=vp["repeat_mode"],
                values=["指定次數", "持續連點"],
                width=88,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=10)
            ).pack(side="left", padx=(0, 6))

            box_ro_cnt = ctk.CTkFrame(row_ro1, fg_color="transparent")
            ctk.CTkLabel(box_ro_cnt, text="次數:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(box_ro_cnt, textvariable=vp["repeat_count"], width=38, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(box_ro_cnt, text="次", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(row_ro1, text="間隔:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row_ro1, textvariable=vp["repeat_interval"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(row_ro1, text="秒", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left")

            # 連點面板第 2 列: 連點位置 + 自訂座標輸入
            row_ro2 = ctk.CTkFrame(box_rep_detail, fg_color="transparent")
            row_ro2.pack(fill="x", padx=6, pady=(2, 4))

            ctk.CTkLabel(row_ro2, text="連點位置:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
            REP_AREAS = ["跟隨命中目標", "右下角區域", "中央區域", "右上角 (Skip)", "右半側中央", "自訂座標"]
            ctk.CTkOptionMenu(
                row_ro2,
                variable=vp["repeat_area"],
                values=REP_AREAS,
                width=110,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=10)
            ).pack(side="left", padx=(0, 6))

            box_rep_xy = ctk.CTkFrame(row_ro2, fg_color="transparent")
            ctk.CTkLabel(box_rep_xy, text="X:", font=ctk.CTkFont(size=10), text_color="#F59E0B").pack(side="left")
            ctk.CTkEntry(box_rep_xy, textvariable=vp["repeat_custom_x"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(box_rep_xy, text="Y:", font=ctk.CTkFont(size=10), text_color="#F59E0B").pack(side="left")
            ctk.CTkEntry(box_rep_xy, textvariable=vp["repeat_custom_y"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
            ctk.CTkButton(box_rep_xy, text="填入", width=38, height=22, corner_radius=4, font=ctk.CTkFont(size=9), fg_color="#D97706", hover_color="#B45309", command=lambda: _fill_from_preview(vp["repeat_custom_x"], vp["repeat_custom_y"], "連點自訂座標")).pack(side="left")

            def _refresh_click_mode_ui(*_):
                cm = vp["click_mode"].get()
                if "自訂座標" in cm or cm == "custom_coord":
                    box_custom_block.pack_forget()
                    box_custom_xy.pack(fill="x", pady=(2, 2), before=row_rep)
                elif "區塊" in cm or cm == "custom_block":
                    box_custom_xy.pack_forget()
                    box_custom_block.pack(fill="x", pady=(2, 2), before=row_rep)
                else:
                    box_custom_xy.pack_forget()
                    box_custom_block.pack_forget()

            vp["click_mode"].trace_add("write", _refresh_click_mode_ui)

            def _toggle_det_type(*_):
                tt = vp["target_type"].get()
                if "圖片" in tt or "模板" in tt:
                    box_kw.pack_forget()
                    box_img_det.pack(fill="x", pady=(2, 2), before=row2)
                else:
                    box_img_det.pack_forget()
                    box_kw.pack(side="left", fill="x", expand=True)

            vp["target_type"].trace_add("write", _toggle_det_type)

            def _refresh_repeat_ui(*_):
                if vp["repeat_enabled"].get():
                    box_rep_detail.pack(fill="x", pady=(2, 2))
                    if vp["repeat_mode"].get() == "指定次數":
                        box_ro_cnt.pack(side="left", padx=(0, 6), before=row_ro1.winfo_children()[-3])
                    else:
                        box_ro_cnt.pack_forget()

                    if "自訂" in vp["repeat_area"].get():
                        box_rep_xy.pack(side="left", padx=(4, 0))
                    else:
                        box_rep_xy.pack_forget()
                else:
                    box_rep_detail.pack_forget()

            vp["repeat_enabled"].trace_add("write", _refresh_repeat_ui)
            vp["repeat_mode"].trace_add("write", _refresh_repeat_ui)
            vp["repeat_area"].trace_add("write", _refresh_repeat_ui)

            _toggle_det_type()
            _refresh_click_mode_ui()
            _refresh_repeat_ui()

        elif b_type == "branch_if":
            branches_data = p.get("branches")
            if not branches_data:
                branches_data = []
                if p.get("cond_a_kws") or p.get("cond_a_x"):
                    branches_data.append({
                        "name": "If",
                        "keywords": p.get("cond_a_kws", "勝利, 挑戰成功"),
                        "template_image": "",
                        "threshold": 0.80,
                        "multiscale": False,
                        "x": _safe_int(p.get("cond_a_x", 1650)),
                        "y": _safe_int(p.get("cond_a_y", 950))
                    })
                if p.get("cond_b_kws") or p.get("cond_b_x"):
                    branches_data.append({
                        "name": "Else If",
                        "keywords": p.get("cond_b_kws", "失敗, 挑戰失敗"),
                        "template_image": "",
                        "threshold": 0.80,
                        "multiscale": False,
                        "x": _safe_int(p.get("cond_b_x", 960)),
                        "y": _safe_int(p.get("cond_b_y", 950))
                    })
                if not branches_data:
                    branches_data = [
                        {"name": "If", "keywords": "勝利, 挑戰成功", "template_image": "", "threshold": 0.80, "multiscale": False, "x": 1650, "y": 950},
                        {"name": "Else If", "keywords": "失敗, 挑戰失敗", "template_image": "", "threshold": 0.80, "multiscale": False, "x": 960, "y": 950}
                    ]

            vp["timeout"] = tk.IntVar(value=p.get("timeout", 8))
            vp["delay"] = tk.DoubleVar(value=p.get("delay", 1.5))
            vp["else_action"] = tk.StringVar(value=p.get("else_action", p.get("cond_else_action", "skip")))
            vp["else_x"] = tk.IntVar(value=p.get("else_x", 960))
            vp["else_y"] = tk.IntVar(value=p.get("else_y", 950))
            vp["branches"] = []

            for idx, bd in enumerate(branches_data):
                b_name = "If" if idx == 0 else f"Else If {idx}"
                vp["branches"].append({
                    "name": b_name,
                    "keywords": tk.StringVar(value=bd.get("keywords", "")),
                    "template_image": tk.StringVar(value=bd.get("template_image", "")),
                    "threshold": tk.DoubleVar(value=_safe_float(bd.get("threshold", 0.80), 0.80)),
                    "multiscale": tk.BooleanVar(value=bool(bd.get("multiscale", False))),
                    "x": tk.IntVar(value=_safe_int(bd.get("x", 960))),
                    "y": tk.IntVar(value=_safe_int(bd.get("y", 540)))
                })

            row_ctrl = ctk.CTkFrame(body, fg_color="transparent")
            row_ctrl.pack(fill="x", pady=(0, 4))
            ctk.CTkLabel(row_ctrl, text="條件分支 (支援文字/圖片):", font=ctk.CTkFont(size=11, weight="bold"), text_color="#F59E0B").pack(side="left")

            btn_add_br = ctk.CTkButton(
                row_ctrl, text="＋ 新增 Else If", width=100, height=24, corner_radius=4,
                font=ctk.CTkFont(size=10, weight="bold"), fg_color="#D97706", hover_color="#B45309",
                command=lambda: _add_branch()
            )
            btn_add_br.pack(side="left", padx=(6, 12))

            ctk.CTkLabel(row_ctrl, text="限時:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row_ctrl, textvariable=vp["timeout"], width=38, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=2)
            ctk.CTkLabel(row_ctrl, text="s 延遲:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(4, 0))
            ctk.CTkEntry(row_ctrl, textvariable=vp["delay"], width=42, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=2)
            ctk.CTkLabel(row_ctrl, text="s", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")

            branches_box = ctk.CTkFrame(body, fg_color="transparent")
            branches_box.pack(fill="x")

            def _render_branch_rows():
                for widget in branches_box.winfo_children():
                    widget.destroy()

                for idx, br in enumerate(vp["branches"]):
                    is_first = (idx == 0)
                    br["name"] = "If" if is_first else f"Else If {idx}"

                    row = ctk.CTkFrame(branches_box, fg_color=COLOR_CARD_ITEM, corner_radius=6, border_width=1, border_color="#313244")
                    row.pack(fill="x", pady=2, ipady=1)

                    badge_bg = "#D97706" if is_first else "#0284C7"
                    lbl_badge = ctk.CTkLabel(row, text=f" {br['name']} ", fg_color=badge_bg, corner_radius=4, text_color="#FFFFFF", font=ctk.CTkFont(size=10, weight="bold"), width=64)
                    lbl_badge.pack(side="left", padx=(4, 6), pady=2)

                    ctk.CTkLabel(row, text="文字:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
                    ctk.CTkEntry(row, textvariable=br["keywords"], width=90, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 4))

                    ctk.CTkLabel(row, text="或圖片:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
                    ent_br_img = ctk.CTkEntry(row, textvariable=br["template_image"], width=90, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)
                    ent_br_img.pack(side="left", padx=(2, 2))

                    btn_br_snip = ctk.CTkButton(
                        row, text="✂️", width=24, height=22, corner_radius=4, font=ctk.CTkFont(size=10),
                        fg_color="#0284C7", hover_color="#0369A1",
                        command=lambda b_ref=br: self.on_snip_template_dialog(b_ref, initial_name=f"branch_{b_ref['name']}")
                    )
                    btn_br_snip.pack(side="left", padx=1)

                    btn_br_apply = ctk.CTkButton(
                        row, text="📥", width=24, height=22, corner_radius=4, font=ctk.CTkFont(size=10),
                        fg_color="#F59E0B", hover_color="#D97706",
                        command=lambda b_ref=br: self.on_apply_last_snippet(b_ref)
                    )
                    btn_br_apply.pack(side="left", padx=(1, 4))

                    ctk.CTkLabel(row, text="點擊 X:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
                    ctk.CTkEntry(row, textvariable=br["x"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=1)
                    ctk.CTkLabel(row, text="Y:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
                    ctk.CTkEntry(row, textvariable=br["y"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(1, 4))

                    btn_fill = ctk.CTkButton(row, text="填入", width=38, height=24, corner_radius=4, font=ctk.CTkFont(size=10), fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, command=lambda target=br: self._fill_branch_from_picker(target))
                    btn_fill.pack(side="left", padx=1)

                    if not is_first:
                        btn_del = ctk.CTkButton(row, text="✕", width=22, height=22, corner_radius=4, font=ctk.CTkFont(size=10, weight="bold"), fg_color="#EF4444", hover_color="#DC2626", command=lambda target_idx=idx: _remove_branch(target_idx))
                        btn_del.pack(side="right", padx=4)

            def _add_branch():
                new_idx = len(vp["branches"])
                vp["branches"].append({
                    "name": f"Else If {new_idx}",
                    "keywords": tk.StringVar(value=""),
                    "template_image": tk.StringVar(value=""),
                    "threshold": tk.DoubleVar(value=0.80),
                    "multiscale": tk.BooleanVar(value=False),
                    "x": tk.IntVar(value=960),
                    "y": tk.IntVar(value=540)
                })
                _render_branch_rows()
                self.auto_save_config()

            def _remove_branch(target_idx):
                if 0 < target_idx < len(vp["branches"]):
                    vp["branches"].pop(target_idx)
                    _render_branch_rows()
                    self.auto_save_config()

            _render_branch_rows()

            row_else = ctk.CTkFrame(body, fg_color=COLOR_CARD_ITEM, corner_radius=6, border_width=1, border_color="#313244")
            row_else.pack(fill="x", pady=(3, 0), ipady=1)

            lbl_else_badge = ctk.CTkLabel(row_else, text=" Else ", fg_color="#475569", corner_radius=4, text_color="#FFFFFF", font=ctk.CTkFont(size=10, weight="bold"), width=64)
            lbl_else_badge.pack(side="left", padx=(4, 6), pady=2)

            ctk.CTkLabel(row_else, text="若皆不符合:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            combo_else = ctk.CTkComboBox(row_else, variable=vp["else_action"], values=["skip", "click_coord"], width=105, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly")
            combo_else.pack(side="left", padx=(2, 6))

            box_else_xy = ctk.CTkFrame(row_else, fg_color="transparent")
            ctk.CTkLabel(box_else_xy, text="X:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(box_else_xy, textvariable=vp["else_x"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=1)
            ctk.CTkLabel(box_else_xy, text="Y:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(box_else_xy, textvariable=vp["else_y"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(1, 4))
            btn_fill_else = ctk.CTkButton(box_else_xy, text="填入", width=42, height=24, corner_radius=4, font=ctk.CTkFont(size=10), fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, command=lambda: self.on_fill_branch_coord("else"))
            btn_fill_else.pack(side="left", padx=2)

            def _toggle_else(*_):
                if vp["else_action"].get() == "click_coord":
                    box_else_xy.pack(side="left")
                else:
                    box_else_xy.pack_forget()
            vp["else_action"].trace_add("write", _toggle_else)
            _toggle_else()

        elif b_type == "loop":
            vp["stop_mode"] = tk.StringVar(value=p.get("stop_mode", "依指定次數"))
            vp["count"] = tk.IntVar(value=_safe_int(p.get("count", 3)))
            vp["keywords"] = tk.StringVar(value=p.get("keywords", p.get("stop_keywords", "")))
            vp["template_image"] = tk.StringVar(value=p.get("template_image", ""))
            vp["image_threshold"] = tk.DoubleVar(value=_safe_float(p.get("image_threshold", 0.80), 0.80))
            vp["image_multiscale"] = tk.BooleanVar(value=bool(p.get("image_multiscale", False)))
            vp["check_timing"] = tk.StringVar(value=p.get("check_timing", "每輪開始與結束"))
            vp["delay_after"] = tk.DoubleVar(value=_safe_float(p.get("delay_after", 0.5)))

            box_loop_header = ctk.CTkFrame(body, fg_color="transparent")
            box_loop_header.pack(fill="x", pady=(0, 4))

            row_loop_ctrl = ctk.CTkFrame(box_loop_header, fg_color="transparent")
            row_loop_ctrl.pack(fill="x", pady=(0, 2))

            ctk.CTkLabel(row_loop_ctrl, text="停止條件:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#818CF8").pack(side="left")
            LOOP_MODES = [
                "依指定次數",
                "偵測到文字出現",
                "偵測到文字消失",
                "偵測到圖片出現",
                "偵測到圖片消失",
                "偵測到打勾圖案",
                "偵測到叉叉圖案"
            ]
            cbo_mode = ctk.CTkComboBox(row_loop_ctrl, variable=vp["stop_mode"], values=LOOP_MODES, width=130, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly")
            cbo_mode.pack(side="left", padx=4)

            lbl_cnt_title = ctk.CTkLabel(row_loop_ctrl, text="次數:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
            lbl_cnt_title.pack(side="left", padx=(4, 2))
            spn_cnt = ctk.CTkEntry(row_loop_ctrl, textvariable=vp["count"], width=42, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)
            spn_cnt.pack(side="left")
            lbl_cnt_hint = ctk.CTkLabel(row_loop_ctrl, text="次(0=無限)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM)
            lbl_cnt_hint.pack(side="left", padx=(2, 6))

            ctk.CTkLabel(row_loop_ctrl, text="延遲:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(2, 1))
            ctk.CTkEntry(row_loop_ctrl, textvariable=vp["delay_after"], width=42, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left")
            ctk.CTkLabel(row_loop_ctrl, text="s", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left")

            row_cond_detail = ctk.CTkFrame(box_loop_header, fg_color="transparent")

            lbl_kw_title = ctk.CTkLabel(row_cond_detail, text="停止關鍵字:", font=ctk.CTkFont(size=10, weight="bold"), text_color="#C4B5FD")
            lbl_kw_title.pack(side="left")
            ent_kw = ctk.CTkEntry(row_cond_detail, textvariable=vp["keywords"], width=140, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)
            ent_kw.pack(side="left", padx=(2, 6))

            ctk.CTkLabel(row_cond_detail, text="檢查時機:", font=ctk.CTkFont(size=10), text_color="#C4B5FD").pack(side="left")
            TIMINGS = [
                "每輪開始與結束",
                "每輪開始前 (While)",
                "每輪結束後 (Do-While)",
                "每個子步驟後"
            ]
            cbo_timing = ctk.CTkComboBox(row_cond_detail, variable=vp["check_timing"], values=TIMINGS, width=130, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly")
            cbo_timing.pack(side="left", padx=2)

            box_loop_img = self._build_image_template_row(box_loop_header, vp, block_dict=block)

            def _on_loop_mode_change(*_):
                mode = vp["stop_mode"].get()
                if mode == "依指定次數":
                    row_cond_detail.pack_forget()
                    box_loop_img.pack_forget()
                    lbl_cnt_title.configure(text="重複次數:")
                    lbl_cnt_hint.configure(text="次(0=無限)")
                elif "圖片" in mode:
                    row_cond_detail.pack_forget()
                    box_loop_img.pack(fill="x", pady=(2, 2))
                    lbl_cnt_title.configure(text="上限次數:")
                    lbl_cnt_hint.configure(text="次(0=不限)")
                else:
                    box_loop_img.pack_forget()
                    row_cond_detail.pack(fill="x", pady=(2, 2))
                    lbl_cnt_title.configure(text="上限次數:")
                    lbl_cnt_hint.configure(text="次(0=不限)")
                    if "符號" in mode or "圖案" in mode or "打勾" in mode or "叉叉" in mode:
                        ent_kw.configure(state="disabled")
                    else:
                        ent_kw.configure(state="normal")

            vp["stop_mode"].trace_add("write", _on_loop_mode_change)
            _on_loop_mode_change()

            tb_inner = ctk.CTkFrame(body, fg_color=COLOR_CARD_ITEM, corner_radius=6, border_width=1, border_color="#313244")
            tb_inner.pack(fill="x", pady=(2, 4))

            ctk.CTkLabel(tb_inner, text="加入積木:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(6, 4), pady=2)

            TYPE_LABELS = {
                "tap_coord": "👆 點擊座標",
                "multi_tap": "⚡ 連續點擊",
                "detect_click": "🔍 偵測點擊",
                "branch_if": "🔀 條件分支",
                "wait_condition": "⏳ 等待條件",
                "wait_sec": "⏱ 等待延遲",
                "swipe": "↔ 滑動手勢",
                "back_key": "📱 返回鍵",
                "send_telegram": "📱 Telegram 通知",
                "comment": "💬 備註說明",
            }
            LABEL_TO_TYPE = {v: k for k, v in TYPE_LABELS.items()}

            var_sel_type = tk.StringVar(value=TYPE_LABELS["tap_coord"])
            combo_type = ctk.CTkComboBox(tb_inner, variable=var_sel_type, values=list(TYPE_LABELS.values()), width=120, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly")
            combo_type.pack(side="left", padx=2, pady=2)

            btn_add_in = ctk.CTkButton(tb_inner, text="裝入", width=46, height=24, corner_radius=4, font=ctk.CTkFont(size=10, weight="bold"), fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, command=lambda target_loop=block, v_type=var_sel_type: self.add_inner_block(target_loop, LABEL_TO_TYPE.get(v_type.get(), "tap_coord")))
            btn_add_in.pack(side="left", padx=2, pady=2)

            btn_pull = ctk.CTkButton(tb_inner, text="移入上方積木", width=90, height=24, corner_radius=4, font=ctk.CTkFont(size=10), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, command=lambda target_loop=block: self.pull_prev_block_into_loop(target_loop))
            btn_pull.pack(side="right", padx=6, pady=2)

            inner_box = ctk.CTkFrame(body, fg_color=COLOR_INPUT_BG, corner_radius=6, border_width=1, border_color="#313244")
            inner_box.pack(fill="x", padx=(10, 0), pady=(2, 4))
            block["inner_container"] = inner_box

            lbl_end = ctk.CTkLabel(body, text="迴圈結束（條件達成或次數用完後繼續）", font=ctk.CTkFont(size=10, weight="bold"), text_color="#818CF8")
            lbl_end.pack(anchor="w", padx=2, pady=(2, 0))

        elif b_type == "wait_condition":
            vp["cond_mode"] = tk.StringVar(value=p.get("cond_mode", "出現 (Wait Appear)"))
            vp["target_type"] = tk.StringVar(value=p.get("target_type", "📝 僅文字"))
            vp["keywords"] = tk.StringVar(value=p.get("keywords", "確認, 確定"))
            vp["template_image"] = tk.StringVar(value=p.get("template_image", ""))
            vp["image_threshold"] = tk.DoubleVar(value=_safe_float(p.get("image_threshold", 0.80), 0.80))
            vp["image_multiscale"] = tk.BooleanVar(value=bool(p.get("image_multiscale", False)))
            vp["interval"] = tk.DoubleVar(value=_safe_float(p.get("interval", 1.0)))
            vp["timeout"] = tk.IntVar(value=_safe_int(p.get("timeout", 30)))
            vp["delay_after"] = tk.DoubleVar(value=_safe_float(p.get("delay_after", 0.5)))
            vp["delay"] = tk.DoubleVar(value=_safe_float(p.get("delay", p.get("delay_after", 0.5))))
            vp["on_timeout"] = tk.StringVar(value=p.get("on_timeout", "continue"))

            vp["click_mode"] = tk.StringVar(value=p.get("click_mode", "🎯 點擊目標中心"))
            vp["custom_x"] = tk.IntVar(value=_safe_int(p.get("custom_x", 960)))
            vp["custom_y"] = tk.IntVar(value=_safe_int(p.get("custom_y", 540)))
            vp["block_x1"] = tk.IntVar(value=_safe_int(p.get("block_x1", 800)))
            vp["block_y1"] = tk.IntVar(value=_safe_int(p.get("block_y1", 450)))
            vp["block_x2"] = tk.IntVar(value=_safe_int(p.get("block_x2", 1120)))
            vp["block_y2"] = tk.IntVar(value=_safe_int(p.get("block_y2", 630)))

            vp["repeat_enabled"] = tk.BooleanVar(value=bool(p.get("repeat_enabled", False)))
            vp["repeat_mode"] = tk.StringVar(value=p.get("repeat_mode", "指定次數"))
            vp["repeat_count"] = tk.IntVar(value=_safe_int(p.get("repeat_count", 10)))
            vp["repeat_interval"] = tk.DoubleVar(value=_safe_float(p.get("repeat_interval", 0.25)))
            vp["repeat_area"] = tk.StringVar(value=p.get("repeat_area", "跟隨命中目標"))
            vp["repeat_custom_x"] = tk.IntVar(value=_safe_int(p.get("repeat_custom_x", 960)))
            vp["repeat_custom_y"] = tk.IntVar(value=_safe_int(p.get("repeat_custom_y", 540)))

            def _fill_from_preview(target_x_var, target_y_var, desc_label: str):
                c_text = self.var_picked_coord.get()
                if "座標:" not in c_text:
                    messagebox.showinfo("提示", "請先在右側截圖畫面上點擊位置以獲取座標！", parent=self.parent)
                    return
                raw = c_text.replace("座標:", "").strip().strip("()")
                try:
                    x, y = [int(v.strip()) for v in raw.split(",")]
                    target_x_var.set(x)
                    target_y_var.set(y)
                    b_name = block["name"].get() if hasattr(block.get("name"), "get") else "等待條件"
                    self._log(f"已將選取座標 ({x}, {y}) 填入 [{b_name}] 之 {desc_label}")
                    self.auto_save_config()
                except Exception:
                    pass

            # 行 1: 條件、偵測類型與關鍵字
            row1 = ctk.CTkFrame(body, fg_color="transparent")
            row1.pack(fill="x", pady=2)
            ctk.CTkLabel(row1, text="條件:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkComboBox(row1, variable=vp["cond_mode"], values=["出現 (Wait Appear)", "消失 (Wait Disappear)"], width=135, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly").pack(side="left", padx=(2, 6))
            ctk.CTkLabel(row1, text="類型:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkComboBox(
                row1,
                variable=vp["target_type"],
                values=["📝 僅文字", "🖼️ 圖片特徵 (模板比對)", "✓ 打勾圖案", "✕ 叉叉/關閉", "🔀 文字或圖案"],
                width=140,
                height=26,
                corner_radius=4,
                fg_color=COLOR_INPUT_BG,
                border_color=COLOR_INPUT_BORDER,
                state="readonly"
            ).pack(side="left", padx=(2, 6))

            box_wait_kw = ctk.CTkFrame(row1, fg_color="transparent")
            ctk.CTkLabel(box_wait_kw, text="關鍵字:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(box_wait_kw, textvariable=vp["keywords"], width=130, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 4), fill="x", expand=True)

            box_wait_img = self._build_image_template_row(body, vp, block_dict=block)

            # 行 2: 頻率、限時、動作設定、延遲與超時
            row2 = ctk.CTkFrame(body, fg_color="transparent")
            row2.pack(fill="x", pady=2)
            ctk.CTkLabel(row2, text="頻率:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row2, textvariable=vp["interval"], width=36, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 1))
            ctk.CTkLabel(row2, text="s", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 4))

            ctk.CTkLabel(row2, text="限時:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row2, textvariable=vp["timeout"], width=36, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 1))
            ctk.CTkLabel(row2, text="s", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(row2, text="動作:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left")
            ACTION_MODES = ["🎯 點擊目標中心", "📍 點擊自訂座標", "🔲 自訂特定區塊", "⏳ 無動作(僅等待)"]
            combo_act = ctk.CTkComboBox(row2, variable=vp["click_mode"], values=ACTION_MODES, width=135, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly")
            combo_act.pack(side="left", padx=(2, 6))

            ctk.CTkLabel(row2, text="延遲:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row2, textvariable=vp["delay"], width=36, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 1))
            ctk.CTkLabel(row2, text="s", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(row2, text="超時:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkComboBox(row2, variable=vp["on_timeout"], values=["continue", "stop"], width=82, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly").pack(side="left", padx=(2, 0))

            def _toggle_wait_type(*_):
                tt = vp["target_type"].get()
                if "圖片" in tt or "模板" in tt:
                    box_wait_kw.pack_forget()
                    box_wait_img.pack(fill="x", pady=(2, 2), before=row2)
                else:
                    box_wait_img.pack_forget()
                    box_wait_kw.pack(side="left", fill="x", expand=True)
            vp["target_type"].trace_add("write", _toggle_wait_type)

            # 動作細項面板：自訂座標輸入
            box_custom_xy = ctk.CTkFrame(body, fg_color="transparent")
            ctk.CTkLabel(box_custom_xy, text="點擊座標 X:", font=ctk.CTkFont(size=11), text_color="#38BDF8").pack(side="left")
            ctk.CTkEntry(box_custom_xy, textvariable=vp["custom_x"], width=48, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 4))
            ctk.CTkLabel(box_custom_xy, text="Y:", font=ctk.CTkFont(size=11), text_color="#38BDF8").pack(side="left")
            ctk.CTkEntry(box_custom_xy, textvariable=vp["custom_y"], width=48, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(2, 6))
            ctk.CTkButton(box_custom_xy, text="填入選取座標", width=76, height=24, corner_radius=4, font=ctk.CTkFont(size=10, weight="bold"), fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, command=lambda: _fill_from_preview(vp["custom_x"], vp["custom_y"], "自訂座標")).pack(side="left")

            # 動作細項面板：自訂特定區塊輸入
            box_custom_block = ctk.CTkFrame(body, fg_color="transparent")
            ctk.CTkLabel(box_custom_block, text="區塊左上(X1,Y1):", font=ctk.CTkFont(size=10), text_color="#A78BFA").pack(side="left")
            ctk.CTkEntry(box_custom_block, textvariable=vp["block_x1"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=1)
            ctk.CTkEntry(box_custom_block, textvariable=vp["block_y1"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(1, 4))
            ctk.CTkButton(box_custom_block, text="填左上", width=46, height=22, corner_radius=4, font=ctk.CTkFont(size=9), fg_color="#6D28D9", hover_color="#5B21B6", command=lambda: _fill_from_preview(vp["block_x1"], vp["block_y1"], "區塊左上")).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(box_custom_block, text="右下(X2,Y2):", font=ctk.CTkFont(size=10), text_color="#A78BFA").pack(side="left")
            ctk.CTkEntry(box_custom_block, textvariable=vp["block_x2"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=1)
            ctk.CTkEntry(box_custom_block, textvariable=vp["block_y2"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(1, 4))
            ctk.CTkButton(box_custom_block, text="填右下", width=46, height=22, corner_radius=4, font=ctk.CTkFont(size=9), fg_color="#6D28D9", hover_color="#5B21B6", command=lambda: _fill_from_preview(vp["block_x2"], vp["block_y2"], "區塊右下")).pack(side="left")

            def _refresh_click_mode_ui(*_):
                cm = vp["click_mode"].get()
                if "自訂座標" in cm:
                    box_custom_block.pack_forget()
                    box_custom_xy.pack(fill="x", pady=(2, 2))
                elif "特定區塊" in cm or "自訂區塊" in cm:
                    box_custom_xy.pack_forget()
                    box_custom_block.pack(fill="x", pady=(2, 2))
                else:
                    box_custom_xy.pack_forget()
                    box_custom_block.pack_forget()

            vp["click_mode"].trace_add("write", _refresh_click_mode_ui)

            # 行 3: ⚡ 命中後連點（過場跳過）勾選框
            row_rep = ctk.CTkFrame(body, fg_color="transparent")
            row_rep.pack(fill="x", pady=(3, 1))
            ctk.CTkCheckBox(
                row_rep,
                text="⚡ 命中後連點（過場跳過）",
                variable=vp["repeat_enabled"],
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#F59E0B",
                width=18,
                height=18,
                checkbox_width=16,
                checkbox_height=16,
                corner_radius=4
            ).pack(side="left", padx=(0, 6))

            # 連點細項面板 (暗色圓角卡片)
            box_rep_detail = ctk.CTkFrame(body, fg_color="#181825", corner_radius=6, border_width=1, border_color="#334155")

            # 連點面板第 1 列: 模式 + 次數 + 間隔
            row_ro1 = ctk.CTkFrame(box_rep_detail, fg_color="transparent")
            row_ro1.pack(fill="x", padx=6, pady=(3, 2))

            ctk.CTkLabel(row_ro1, text="連點模式:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
            ctk.CTkOptionMenu(
                row_ro1,
                variable=vp["repeat_mode"],
                values=["指定次數", "持續連點"],
                width=88,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=10)
            ).pack(side="left", padx=(0, 6))

            box_ro_cnt = ctk.CTkFrame(row_ro1, fg_color="transparent")
            ctk.CTkLabel(box_ro_cnt, text="次數:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(box_ro_cnt, textvariable=vp["repeat_count"], width=38, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(box_ro_cnt, text="次", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(row_ro1, text="間隔:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row_ro1, textvariable=vp["repeat_interval"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(row_ro1, text="秒", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left")

            # 連點面板第 2 列: 連點位置 + 自訂座標輸入
            row_ro2 = ctk.CTkFrame(box_rep_detail, fg_color="transparent")
            row_ro2.pack(fill="x", padx=6, pady=(2, 4))

            ctk.CTkLabel(row_ro2, text="連點位置:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
            REP_AREAS = ["跟隨命中目標", "右下角區域", "中央區域", "右上角 (Skip)", "右半側中央", "自訂座標"]
            ctk.CTkOptionMenu(
                row_ro2,
                variable=vp["repeat_area"],
                values=REP_AREAS,
                width=110,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=10)
            ).pack(side="left", padx=(0, 6))

            box_rep_xy = ctk.CTkFrame(row_ro2, fg_color="transparent")
            ctk.CTkLabel(box_rep_xy, text="X:", font=ctk.CTkFont(size=10), text_color="#F59E0B").pack(side="left")
            ctk.CTkEntry(box_rep_xy, textvariable=vp["repeat_custom_x"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 2))
            ctk.CTkLabel(box_rep_xy, text="Y:", font=ctk.CTkFont(size=10), text_color="#F59E0B").pack(side="left")
            ctk.CTkEntry(box_rep_xy, textvariable=vp["repeat_custom_y"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
            ctk.CTkButton(
                box_rep_xy,
                text="填座標",
                width=46,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color="#D97706",
                hover_color="#B45309",
                command=lambda: _fill_from_preview(vp["repeat_custom_x"], vp["repeat_custom_y"], "連點自訂座標")
            ).pack(side="left")

            def _refresh_repeat_ui(*_):
                if vp["repeat_enabled"].get():
                    box_rep_detail.pack(fill="x", pady=(2, 4))
                    if "指定次數" in vp["repeat_mode"].get():
                        box_ro_cnt.pack(side="left", before=row_ro1.winfo_children()[-2])
                    else:
                        box_ro_cnt.pack_forget()

                    if "自訂" in vp["repeat_area"].get():
                        box_rep_xy.pack(side="left")
                    else:
                        box_rep_xy.pack_forget()
                else:
                    box_rep_detail.pack_forget()

            vp["repeat_enabled"].trace_add("write", _refresh_repeat_ui)
            vp["repeat_mode"].trace_add("write", _refresh_repeat_ui)
            vp["repeat_area"].trace_add("write", _refresh_repeat_ui)

            _toggle_wait_type()
            _refresh_click_mode_ui()
            _refresh_repeat_ui()

        elif b_type == "wait_sec":
            vp["seconds"] = tk.DoubleVar(value=p.get("seconds", 3.0))
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="等待秒數:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row, textvariable=vp["seconds"], width=50, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(4, 2))
            ctk.CTkLabel(row, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")

        elif b_type == "swipe":
            vp["x1"] = tk.IntVar(value=p.get("x1", 1500))
            vp["y1"] = tk.IntVar(value=p.get("y1", 540))
            vp["x2"] = tk.IntVar(value=p.get("x2", 400))
            vp["y2"] = tk.IntVar(value=p.get("y2", 540))
            vp["duration_ms"] = tk.IntVar(value=p.get("duration_ms", 400))
            vp["delay"] = tk.DoubleVar(value=p.get("delay", 1.0))

            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="起點(X,Y):", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row, textvariable=vp["x1"], width=46, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=1)
            ctk.CTkEntry(row, textvariable=vp["y1"], width=46, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(1, 6))

            ctk.CTkLabel(row, text="終點(X,Y):", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row, textvariable=vp["x2"], width=46, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=1)
            ctk.CTkEntry(row, textvariable=vp["y2"], width=46, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(1, 6))

            ctk.CTkLabel(row, text="耗時:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row, textvariable=vp["duration_ms"], width=48, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=1)
            ctk.CTkLabel(row, text="ms", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left")

        elif b_type == "back_key":
            vp["delay"] = tk.DoubleVar(value=p.get("delay", 1.2))
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="模擬 Android 返回鍵 (input keyevent 4)，延遲:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")
            ctk.CTkEntry(row, textvariable=vp["delay"], width=44, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(4, 2))
            ctk.CTkLabel(row, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")

        elif b_type == "comment":
            vp["note"] = tk.StringVar(value=p.get("note", "此處為備註說明文字，執行時不執行任何操作"))
            row = ctk.CTkFrame(body, fg_color=COLOR_CARD_ITEM, corner_radius=6, border_width=1, border_color="#D97706")
            row.pack(fill="x", pady=2, ipady=3)
            ctk.CTkLabel(row, text="備註:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#FDE68A").pack(side="left", padx=(6, 4))
            ent_note = ctk.CTkEntry(row, textvariable=vp["note"], font=ctk.CTkFont(size=11), height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)
            ent_note.pack(side="left", fill="x", expand=True, padx=(0, 6))
            vp["note"].trace_add("write", lambda *_: self.auto_save_config())

        elif b_type == "send_telegram":
            vp["message"] = tk.StringVar(value=p.get("message", "任務步驟執行完成！"))
            vp["attach_screenshot"] = tk.BooleanVar(value=bool(p.get("attach_screenshot", True)))
            vp["use_custom"] = tk.BooleanVar(value=bool(p.get("use_custom", False)))
            vp["custom_token"] = tk.StringVar(value=p.get("custom_token", ""))
            vp["custom_chat_id"] = tk.StringVar(value=p.get("custom_chat_id", ""))
            vp["delay_after"] = tk.DoubleVar(value=_safe_float(p.get("delay_after", 0.5)))

            for k in ("message", "attach_screenshot", "use_custom", "custom_token", "custom_chat_id", "delay_after"):
                vp[k].trace_add("write", lambda *_: self.auto_save_config())

            row1 = ctk.CTkFrame(body, fg_color="transparent")
            row1.pack(fill="x", pady=2)
            ctk.CTkLabel(row1, text="訊息:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#38BDF8").pack(side="left")
            ctk.CTkEntry(row1, textvariable=vp["message"], height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(4, 8), fill="x", expand=True)
            ctk.CTkCheckBox(row1, text="附帶截圖", variable=vp["attach_screenshot"], font=ctk.CTkFont(size=11), width=80, checkbox_width=16, checkbox_height=16).pack(side="left", padx=(0, 6))

            row2 = ctk.CTkFrame(body, fg_color="transparent")
            row2.pack(fill="x", pady=2)

            ctk.CTkCheckBox(row2, text="使用獨立 Token / Chat ID", variable=vp["use_custom"], font=ctk.CTkFont(size=11), checkbox_width=16, checkbox_height=16).pack(side="left")

            btn_test = ctk.CTkButton(row2, text="測試發送", width=68, height=24, corner_radius=4, font=ctk.CTkFont(size=10), fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, command=lambda target_b=block: self._test_block_telegram(target_b))
            btn_test.pack(side="right", padx=2)

            ctk.CTkLabel(row2, text="延遲:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="right")
            ctk.CTkEntry(row2, textvariable=vp["delay_after"], width=42, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="right", padx=(2, 4))
            ctk.CTkLabel(row2, text="秒", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="right")

            box_custom = ctk.CTkFrame(body, fg_color=COLOR_CARD_ITEM, corner_radius=6, border_width=1, border_color="#0284C7")

            row_c1 = ctk.CTkFrame(box_custom, fg_color="transparent")
            row_c1.pack(fill="x", padx=6, pady=2)
            ctk.CTkLabel(row_c1, text="Bot Token:", font=ctk.CTkFont(size=10), text_color="#38BDF8").pack(side="left")
            ctk.CTkEntry(row_c1, textvariable=vp["custom_token"], height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", fill="x", expand=True, padx=(4, 0))

            row_c2 = ctk.CTkFrame(box_custom, fg_color="transparent")
            row_c2.pack(fill="x", padx=6, pady=2)
            ctk.CTkLabel(row_c2, text="Chat ID:   ", font=ctk.CTkFont(size=10), text_color="#38BDF8").pack(side="left")
            ctk.CTkEntry(row_c2, textvariable=vp["custom_chat_id"], width=130, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER).pack(side="left", padx=(4, 0))
            ctk.CTkLabel(row_c2, text="（未勾選或留空時使用進階設定中的通用值）", font=ctk.CTkFont(size=9), text_color="#94A3B8").pack(side="left", padx=6)

            def _toggle_custom(*_):
                if vp["use_custom"].get():
                    box_custom.pack(fill="x", pady=(2, 2))
                else:
                    box_custom.pack_forget()

            vp["use_custom"].trace_add("write", _toggle_custom)
            _toggle_custom()

    def _bind_drag(self, handle, block_item):
        def on_start(e):
            self._drag_data = {"block": block_item, "y": e.y_root}

        def on_motion(e):
            d = getattr(self, "_drag_data", None)
            if not d or d["block"] not in self.blocks_list:
                return
            idx = self.blocks_list.index(d["block"])
            dy = e.y_root - d["y"]
            h = d["block"]["frame"].winfo_height() or 60
            if dy > h * 0.7 and idx < len(self.blocks_list) - 1:
                self.blocks_list[idx], self.blocks_list[idx + 1] = self.blocks_list[idx + 1], self.blocks_list[idx]
                self._repack_all_blocks()
                d["y"] = e.y_root
            elif dy < -h * 0.7 and idx > 0:
                self.blocks_list[idx], self.blocks_list[idx - 1] = self.blocks_list[idx - 1], self.blocks_list[idx]
                self._repack_all_blocks()
                d["y"] = e.y_root

        def on_end(e):
            self._drag_data = None
            self.auto_save_config()

        handle.bind("<Button-1>", on_start)
        handle.bind("<B1-Motion>", on_motion)
        handle.bind("<ButtonRelease-1>", on_end)

    def _repack_all_blocks(self):
        for b in self.blocks_list:
            b["frame"].pack_forget()
        for i, b in enumerate(self.blocks_list, start=1):
            b["frame"].pack(fill="x", padx=4, pady=3)
            b["lbl_num"].configure(text=f"#{i}")
            if b["type"] == "loop":
                in_list = b.get("inner_blocks_list", [])
                for j, cb in enumerate(in_list, start=1):
                    cb["frame"].pack_forget()
                    cb["frame"].pack(fill="x", padx=2, pady=2)
                    cb["lbl_num"].configure(text=f"#{i}.{j}")
        self.scroll_blocks.update_idletasks()

    def _renumber_blocks(self):
        self._repack_all_blocks()

    def move_block(self, block_item: Dict[str, Any], direction: int):
        if block_item in self.blocks_list:
            idx = self.blocks_list.index(block_item)
            target = idx + direction
            if 0 <= target < len(self.blocks_list):
                self.blocks_list[idx], self.blocks_list[target] = self.blocks_list[target], self.blocks_list[idx]
                self._repack_all_blocks()
                self.auto_save_config()
        elif block_item.get("parent_loop"):
            parent = block_item["parent_loop"]
            in_list = parent.get("inner_blocks_list", [])
            if block_item in in_list:
                idx = in_list.index(block_item)
                target = idx + direction
                if 0 <= target < len(in_list):
                    in_list[idx], in_list[target] = in_list[target], in_list[idx]
                    self._repack_all_blocks()
                    self.auto_save_config()

    def duplicate_block(self, block_item: Dict[str, Any]):
        serialized = self._serialize_single_block(block_item)
        p_loop = block_item.get("parent_loop")
        self.add_block(
            b_type=serialized["type"],
            params=dict(serialized["params"]),
            name=f"{serialized['name']} (複製)",
            enabled=serialized["enabled"],
            parent_loop=p_loop
        )

    def delete_block(self, block_item: Dict[str, Any]):
        if block_item in self.blocks_list:
            block_item["frame"].destroy()
            self.blocks_list.remove(block_item)
            self._renumber_blocks()
            self.auto_save_config()
        elif block_item.get("parent_loop"):
            parent = block_item["parent_loop"]
            in_list = parent.get("inner_blocks_list", [])
            if block_item in in_list:
                block_item["frame"].destroy()
                in_list.remove(block_item)
                self._renumber_blocks()
                self.auto_save_config()

    def _test_block_telegram(self, block: Dict[str, Any]):
        vp = block.get("var_params", {})
        custom_tok = vp.get("custom_token").get().strip() if "custom_token" in vp else ""
        custom_cid = vp.get("custom_chat_id").get().strip() if "custom_chat_id" in vp else ""
        use_custom = vp.get("use_custom").get() if "use_custom" in vp else False

        tok = (custom_tok if use_custom else "") or self.var_tg_token.get().strip()
        cid = (custom_cid if use_custom else "") or self.var_tg_chat_id.get().strip()

        if not tok or not cid:
            messagebox.showwarning("提示", "尚未設定 Telegram Bot Token 與 Chat ID！\n請在「進階設定」填寫，或在此積木勾選自訂。")
            return

        msg = vp.get("message").get().strip() if "message" in vp else "任務清單測試通知"
        if not msg:
            msg = "任務步驟執行完成！"
        attach_img = vp.get("attach_screenshot").get() if "attach_screenshot" in vp else True

        self._log(f"📱 正在測試發送積木 Telegram 通知:「{msg}」...")
        screen = None
        if attach_img:
            if self.bot and hasattr(self.bot, "capture_screen"):
                try:
                    screen = self.bot.capture_screen()
                except Exception:
                    screen = None
            elif self.current_screen_bgr is not None:
                screen = self.current_screen_bgr

        if self.bot and hasattr(self.bot, "send_telegram_notify"):
            success = self.bot.send_telegram_notify(
                token=tok,
                chat_id=cid,
                custom_text=msg,
                step_name="積木測試",
                screen_bgr=screen
            )
        else:
            success = self.engine._send_telegram_direct(tok, cid, msg, screen)

        if success:
            self._log("✅ 積木 Telegram 測試通知已送出！")

    def _fill_block_coords(self, target_block: Dict[str, Any]):
        c_text = self.var_picked_coord.get()
        if "座標:" not in c_text:
            messagebox.showinfo("提示", "請先在截圖上點擊位置以獲取座標！")
            return
        raw = c_text.replace("座標:", "").strip().strip("()")
        try:
            x, y = [int(v.strip()) for v in raw.split(",")]
        except Exception:
            return
        vp = target_block.get("var_params", {})
        b_name = target_block["name"].get() if hasattr(target_block.get("name"), "get") else "積木"
        if "x" in vp and "y" in vp:
            vp["x"].set(x)
            vp["y"].set(y)
            self._log(f"已將座標 ({x}, {y}) 填入 [{b_name}]")
            self.auto_save_config()
        elif "custom_x" in vp and "custom_y" in vp:
            vp["custom_x"].set(x)
            vp["custom_y"].set(y)
            self._log(f"已將座標 ({x}, {y}) 填入 [{b_name}] 自訂座標")
            self.auto_save_config()

    def select_block(self, block_item: Dict[str, Any]):
        self.selected_block_target = block_item
        self._update_all_selection_highlights()
        b_name = block_item["name"].get() if hasattr(block_item.get("name"), "get") else "積木"
        self._log(f"已選取目標積木 [{b_name}]")

    def _update_all_selection_highlights(self):
        target = getattr(self, "selected_block_target", None)
        for b in self.blocks_list:
            if b.get("frame"):
                info = BLOCK_TYPES.get(b["type"], BLOCK_TYPES["tap_coord"])
                if b is target:
                    b["frame"].configure(border_width=2, border_color="#F59E0B")
                else:
                    b["frame"].configure(border_width=1, border_color=info["color"])
            for cb in b.get("inner_blocks_list", []):
                if cb.get("frame"):
                    info = BLOCK_TYPES.get(cb["type"], BLOCK_TYPES["tap_coord"])
                    if cb is target:
                        cb["frame"].configure(border_width=2, border_color="#F59E0B")
                    else:
                        cb["frame"].configure(border_width=1, border_color=info["color"])

    def highlight_active_step(self, active_idx: int):
        def _ui_update():
            for i, b in enumerate(self.blocks_list):
                info = BLOCK_TYPES.get(b["type"], BLOCK_TYPES["tap_coord"])
                if i == active_idx:
                    b["frame"].configure(border_width=2, border_color="#10B981")
                else:
                    is_target = (b is getattr(self, "selected_block_target", None))
                    b["frame"].configure(border_width=2 if is_target else 1, border_color="#F59E0B" if is_target else info["color"])
        self.parent.after(0, _ui_update)

    def on_capture_screen(self):
        if not self.bot or not self.bot.device:
            if self.gui and hasattr(self.gui, "bot") and self.gui.bot and self.gui.bot.device:
                self.bot = self.gui.bot
            elif not self.bot or not self.bot.connect():
                if self.gui and getattr(self.gui, "current_screen_bgr", None) is not None:
                    self.current_screen_bgr = self.gui.current_screen_bgr
                    self._render_preview(self.current_screen_bgr)
                    self._log("📸 已直接同步主視窗畫面！點擊任一處可選取座標。")
                    return
                messagebox.showwarning("提示", "請先開啟模擬器並在主介面點擊「連線」！")
                return

        if self._capturing:
            return
        self._capturing = True
        self.btn_capture.configure(state="disabled")

        def work():
            screen = None
            err = None
            try:
                screen = self.bot.capture_screen()
            except Exception as e:
                err = e

            def done():
                self._capturing = False
                self.btn_capture.configure(state="normal")
                if screen is not None:
                    self.current_screen_bgr = screen
                    self._render_preview(screen)
                    self._log("📸 畫面擷取成功！點擊畫面任意位置即可選取座標。")
                else:
                    if self.gui and getattr(self.gui, "current_screen_bgr", None) is not None:
                        self.current_screen_bgr = self.gui.current_screen_bgr
                        self._render_preview(self.current_screen_bgr)
                        self._log("📸 已同步主視窗快取畫面。")
                    else:
                        self._log(f"❌ 擷取失敗: {err or '無法從裝置取得畫面'}")
                        messagebox.showerror("錯誤", f"無法從模擬器取得截圖{': ' + str(err) if err else ''}")

            self.parent.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def update_emulator_preview(self, screen_bgr: np.ndarray):
        if screen_bgr is None:
            return
        self.current_screen_bgr = screen_bgr
        self._render_preview(screen_bgr)

    def _render_preview(self, screen_bgr: np.ndarray):
        if screen_bgr is None:
            return
        try:
            h, w = screen_bgr.shape[:2]
            self.raw_screen_w, self.raw_screen_h = w, h

            avail_w = max(100, getattr(self, "canvas_w", self.lbl_canvas.winfo_width()) - 4)
            avail_h = max(100, getattr(self, "canvas_h", self.lbl_canvas.winfo_height()) - 4)
            scale = min(avail_w / w, avail_h / h)
            pw, ph = max(1, int(w * scale)), max(1, int(h * scale))
            self.preview_scale = scale
            self.preview_img_w, self.preview_img_h = pw, ph

            small = cv2.resize(screen_bgr, (pw, ph), interpolation=cv2.INTER_LINEAR)
            t = max(1, pw // 320)

            if self.selected_coord:
                sx, sy = self.selected_coord
                ssx, ssy = int(sx * scale), int(sy * scale)
                cv2.circle(small, (ssx, ssy), 5 * t, (0, 0, 255), -1)
                cv2.circle(small, (ssx, ssy), 10 * t, (0, 255, 255), t)
                cv2.line(small, (ssx - 8 * t, ssy), (ssx + 8 * t, ssy), (0, 255, 255), t)
                cv2.line(small, (ssx, ssy - 8 * t), (ssx, ssy + 8 * t), (0, 255, 255), t)
                cv2.putText(
                    small,
                    f"({sx},{sy})",
                    (min(pw - 80, ssx + 8 * t), max(18, ssy - 8 * t)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (0, 255, 255),
                    1
                )

            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            del small
            pil_img = Image.fromarray(rgb)
            del rgb
            self.preview_image_tk = ImageTk.PhotoImage(pil_img)
            self.lbl_canvas.configure(image=self.preview_image_tk, text="")
        except Exception:
            pass

    def _show_image(self):
        self._resize_job = None
        if self.current_screen_bgr is not None:
            self._render_preview(self.current_screen_bgr)

    def _on_preview_resize(self, e=None):
        if e and getattr(e, "width", 0) > 50 and getattr(e, "height", 0) > 50:
            self.canvas_w = e.width
            self.canvas_h = e.height
        if self._resize_job:
            self.parent.after_cancel(self._resize_job)
        self._resize_job = self.parent.after(120, self._show_image)

    def _preview_to_real(self, ex: int, ey: int) -> Optional[Tuple[int, int]]:
        if self.preview_scale <= 0 or self.raw_screen_w <= 0 or self.raw_screen_h <= 0:
            return None
        lbl_w = self.lbl_canvas.winfo_width()
        lbl_h = self.lbl_canvas.winfo_height()
        pad_x = max(0, (lbl_w - self.preview_img_w) // 2)
        pad_y = max(0, (lbl_h - self.preview_img_h) // 2)
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
        x, y = xy
        self.selected_coord = (x, y)
        self.var_picked_coord.set(f"座標: ({x}, {y})")
        self.parent.clipboard_clear()
        self.parent.clipboard_append(f"{x}, {y}")
        self._log(f"🎯 已選取並複製座標: ({x}, {y})")
        if self.current_screen_bgr is not None:
            self._render_preview(self.current_screen_bgr)

    def on_copy_picked_coord(self):
        c_text = self.var_picked_coord.get()
        if "座標:" in c_text:
            raw = c_text.replace("座標:", "").strip().strip("()")
            self.parent.clipboard_clear()
            self.parent.clipboard_append(raw)
            self._log(f"已複製座標到剪貼簿: {raw}")

    def on_fill_selected_block(self):
        c_text = self.var_picked_coord.get()
        if "座標:" not in c_text:
            messagebox.showinfo("提示", "請先在截圖上點擊位置以獲取座標！")
            return
        raw = c_text.replace("座標:", "").strip().strip("()")
        try:
            x, y = [int(v.strip()) for v in raw.split(",")]
        except Exception:
            return

        b = getattr(self, "selected_block_target", None)
        if not b:
            for blk in reversed(self.blocks_list):
                if "x" in blk.get("var_params", {}) or "custom_x" in blk.get("var_params", {}):
                    b = blk
                    break
                for in_b in reversed(blk.get("inner_blocks_list", [])):
                    if "x" in in_b.get("var_params", {}) or "custom_x" in in_b.get("var_params", {}):
                        b = in_b
                        break
                if b:
                    break

        if not b:
            messagebox.showinfo("提示", "請先點選一個具有座標設定的積木！")
            return

        vp = b["var_params"]
        b_name = b["name"].get() if hasattr(b.get("name"), "get") else "積木"
        if "x" in vp and "y" in vp:
            vp["x"].set(x)
            vp["y"].set(y)
            self._log(f"已將座標 ({x}, {y}) 填入 [{b_name}]")
        elif "custom_x" in vp and "custom_y" in vp:
            vp["custom_x"].set(x)
            vp["custom_y"].set(y)
            self._log(f"已將座標 ({x}, {y}) 填入 [{b_name}] 自訂座標")
        self.auto_save_config()

    def _fill_branch_from_picker(self, target_branch: Dict[str, Any]):
        c_text = self.var_picked_coord.get()
        if "座標:" not in c_text:
            messagebox.showinfo("提示", "請先在截圖上點擊位置以獲取座標！")
            return
        raw = c_text.replace("座標:", "").strip().strip("()")
        try:
            x, y = [int(v.strip()) for v in raw.split(",")]
        except Exception:
            return
        if "x" in target_branch and "y" in target_branch:
            target_branch["x"].set(x)
            target_branch["y"].set(y)
            b_name = target_branch.get("name", "條件分支")
            self._log(f"已將「{b_name}」座標填入為 ({x}, {y})")
            self.auto_save_config()

    def on_fill_branch_coord(self, branch: Any):
        c_text = self.var_picked_coord.get()
        if "座標:" not in c_text:
            messagebox.showinfo("提示", "請先在截圖上點擊位置以獲取座標！")
            return
        raw = c_text.replace("座標:", "").strip().strip("()")
        try:
            x, y = [int(v.strip()) for v in raw.split(",")]
        except Exception:
            return

        if not (0 <= self.selected_block_idx < len(self.blocks_list)):
            target_idx = -1
            for i, b in enumerate(self.blocks_list):
                if b["type"] == "branch_if":
                    target_idx = i
            if target_idx != -1:
                self.selected_block_idx = target_idx
            else:
                messagebox.showinfo("提示", "請先在積木區新增或點選「條件分支」積木！")
                return

        b = self.blocks_list[self.selected_block_idx]
        if b["type"] != "branch_if":
            target_idx = -1
            for i, blk in enumerate(self.blocks_list):
                if blk["type"] == "branch_if":
                    target_idx = i
                    break
            if target_idx != -1:
                self.selected_block_idx = target_idx
                b = self.blocks_list[target_idx]
            else:
                messagebox.showinfo("提示", "目前選取的不是「條件分支」積木！")
                return

        vp = b["var_params"]
        if branch == "else":
            if "else_x" in vp and "else_y" in vp:
                vp["else_x"].set(x)
                vp["else_y"].set(y)
                self._log(f"已將積木 #{self.selected_block_idx + 1} Else 座標設定為 ({x}, {y})")
        else:
            idx = 0
            if branch == "A":
                idx = 0
            elif branch == "B":
                idx = 1
            elif isinstance(branch, int):
                idx = branch
            elif isinstance(branch, str) and branch.isdigit():
                idx = int(branch)

            branches = vp.get("branches", [])
            if 0 <= idx < len(branches):
                branches[idx]["x"].set(x)
                branches[idx]["y"].set(y)
                b_name = branches[idx].get("name", f"分支 #{idx + 1}")
                self._log(f"已將積木 #{self.selected_block_idx + 1}「{b_name}」座標設定為 ({x}, {y})")
            else:
                messagebox.showinfo("提示", f"該積木目前只有 {len(branches)} 個分支，請先點擊積木內的「＋ 新增 Else If」！")
                return

        self.auto_save_config()

    def on_toggle_auto_refresh(self):
        if self.var_auto_preview.get():
            if not self.bot or not self.bot.device:
                messagebox.showwarning("提示", "請先連線模擬器")
                self.var_auto_preview.set(False)
                return
            self._schedule_auto_refresh(delay_ms=200)
        elif self._auto_preview_job:
            self.parent.after_cancel(self._auto_preview_job)
            self._auto_preview_job = None

    def _schedule_auto_refresh(self, delay_ms: int = 1500):
        if not self.var_auto_preview.get():
            return
        self._auto_preview_job = self.parent.after(delay_ms, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        self._auto_preview_job = None
        if not self.var_auto_preview.get():
            return
        if not self.bot or not self.bot.device:
            self.var_auto_preview.set(False)
            return

        def work():
            screen = None
            try:
                screen = self.bot.capture_screen()
            except Exception:
                pass

            def done():
                if screen is not None:
                    self.current_screen_bgr = screen
                    self._render_preview(screen)
                self._schedule_auto_refresh(delay_ms=1500)

            self.parent.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def on_run_tasks(self):
        if not self.blocks_list:
            messagebox.showinfo("提示", "程式區目前沒有任何積木，請先從左側加入積木！")
            return

        if self.bot and getattr(self.bot, "is_running", False):
            messagebox.showwarning("提示", "【聯賽自動刷關】正在執行中，請先停止聯賽腳本再啟動任務清單。")
            return

        active_blocks = self._serialize_all_blocks()
        loop_cnt = max(0, self.var_loop_count.get())

        self.btn_run.configure(state="disabled")
        self.btn_step.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        if hasattr(self, "indicator_light"):
            self.indicator_light.configure(text_color="#F59E0B")
        self.var_status_text.set("🟡 正在執行任務清單...")

        def _on_step(idx, cycle, total_cycles):
            self.highlight_active_step(idx)
            tot_str = str(total_cycles) if total_cycles > 0 else "∞"
            if idx >= 0:
                self.var_status_text.set(f"▶ 執行中 (輪次 {cycle}/{tot_str}，步驟 #{idx + 1})")
            else:
                self.var_status_text.set("🟢 任務已結束")

        def _on_finish(success, msg):
            def _finish_ui():
                self.btn_run.configure(state="normal")
                self.btn_step.configure(state="normal")
                self.btn_stop.configure(state="disabled")
                self.highlight_active_step(-1)
                st_icon = "🟢" if success else "⚠️"
                if hasattr(self, "indicator_light"):
                    self.indicator_light.configure(text_color="#10B981" if success else "#EF4444")
                self.var_status_text.set(f"{st_icon} {msg}")
            self.parent.after(0, _finish_ui)

        self.engine.global_settings.update(self.get_global_settings())
        self.engine.start(
            blocks_data=active_blocks,
            loop_count=loop_cnt,
            on_step_change=_on_step,
            on_finish=_on_finish,
            global_settings=self.get_global_settings()
        )

    def on_step_task(self):
        if not self.blocks_list:
            return
        idx = self.selected_block_idx if (0 <= self.selected_block_idx < len(self.blocks_list)) else 0
        block = self.blocks_list[idx]
        s_data = self._serialize_single_block(block)

        self.highlight_active_step(idx)
        self._log(f"👣 [單步執行] #{idx + 1} {s_data['name']}")

        self.engine.global_settings.update(self.get_global_settings())
        if self.bot and hasattr(self.bot, "set_allowed_languages"):
            self.bot.set_allowed_languages(
                allow_tc=bool(self.var_lang_tc.get()),
                allow_sc=bool(self.var_lang_sc.get()),
                allow_en=bool(self.var_lang_en.get())
            )

        def _worker():
            self.engine.execute_block(s_data["type"], s_data["params"])
            self.parent.after(500, lambda: self.highlight_active_step(-1))

        threading.Thread(target=_worker, daemon=True).start()

    def on_stop_tasks(self):
        self.engine.stop()
        if hasattr(self, "indicator_light"):
            self.indicator_light.configure(text_color="#EF4444")
        self.var_status_text.set("🔴 正在停止...")

    def _serialize_single_block(self, b: Dict[str, Any]) -> Dict[str, Any]:
        p = {}
        for k, v in b.get("var_params", {}).items():
            # 徹底忽略所有私有/臨時快取屬性 (如 _thumb_img, _btn 等)
            if str(k).startswith("_"):
                continue

            if k == "branches" and isinstance(v, list):
                p["branches"] = [
                    {
                        "name": str(br.get("name", "If")),
                        "keywords": str(br["keywords"].get() if hasattr(br.get("keywords"), "get") else br.get("keywords", "")),
                        "template_image": str(br["template_image"].get() if hasattr(br.get("template_image"), "get") else br.get("template_image", "")),
                        "threshold": float(br["threshold"].get() if hasattr(br.get("threshold"), "get") else br.get("threshold", 0.80)),
                        "multiscale": bool(br["multiscale"].get() if hasattr(br.get("multiscale"), "get") else br.get("multiscale", False)),
                        "x": int(br["x"].get() if hasattr(br.get("x"), "get") else br.get("x", 0)),
                        "y": int(br["y"].get() if hasattr(br.get("y"), "get") else br.get("y", 0))
                    }
                    for br in v
                ]
            elif hasattr(v, "get"):
                raw_v = v.get()
                if isinstance(raw_v, (str, int, float, bool)):
                    p[k] = raw_v
                elif raw_v is None:
                    p[k] = None
                else:
                    p[k] = str(raw_v)
            elif isinstance(v, (str, int, float, bool)):
                p[k] = v
            elif isinstance(v, (list, tuple)):
                p[k] = [x for x in v if isinstance(x, (str, int, float, bool, dict))]
            elif isinstance(v, dict):
                p[k] = {str(dk): dv for dk, dv in v.items() if not str(dk).startswith("_") and isinstance(dv, (str, int, float, bool, list, dict))}

        if b.get("type") == "loop":
            inner_list = b.get("inner_blocks_list", [])
            p["inner_blocks"] = [self._serialize_single_block(sb) for sb in inner_list]

        return {
            "type": b.get("type", "tap_coord"),
            "name": str(b["name"].get() if hasattr(b.get("name"), "get") else b.get("name", "積木")),
            "enabled": bool(b["enabled"].get() if hasattr(b.get("enabled"), "get") else b.get("enabled", True)),
            "params": p
        }

    def _serialize_all_blocks(self) -> List[Dict[str, Any]]:
        return [self._serialize_single_block(b) for b in self.blocks_list]

    def on_clear_blocks(self):
        if self.blocks_list and not messagebox.askyesno("確認", "確定要清空所有積木嗎？"):
            return
        for b in self.blocks_list:
            for cb in b.get("inner_blocks_list", []):
                if cb.get("frame"):
                    cb["frame"].destroy()
            if b.get("frame"):
                b["frame"].destroy()
        self.blocks_list.clear()
        self.selected_block_target = None
        self.auto_save_config()

    def load_preset(self, preset_key: str):
        preset = self.presets.get(preset_key) or DAILY_PRESETS.get(preset_key)
        if not preset:
            fpath = os.path.join(self.presets_dir, f"{preset_key}.json")
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        preset = json.load(f)
                except Exception:
                    pass
        if not preset:
            messagebox.showwarning("提示", f"找不到指定任務存檔：{preset_key}")
            return

        preset_title = preset.get("title", preset_key)
        if self.blocks_list and not messagebox.askyesno("載入任務存檔", f"載入任務設定「{preset_title}」將取代目前積木清單，是否繼續？"):
            return

        for b in self.blocks_list:
            for cb in b.get("inner_blocks_list", []):
                if cb.get("frame"):
                    cb["frame"].destroy()
            if b.get("frame"):
                b["frame"].destroy()
        self.blocks_list.clear()
        self.selected_block_target = None

        if "loop_count" in preset:
            self.var_loop_count.set(preset.get("loop_count", 1))

        for bd in preset.get("blocks", []):
            self.add_block(
                b_type=bd["type"],
                params=dict(bd.get("params", {})),
                name=bd.get("name", ""),
                enabled=bd.get("enabled", True)
            )
        self._log(f"已成功載入任務存檔: {preset_title} (共 {len(self.blocks_list)} 個步驟)")
        self.auto_save_config()

    def auto_save_config(self):
        try:
            parent_d = os.path.dirname(self.save_file)
            if parent_d and not os.path.exists(parent_d):
                os.makedirs(parent_d, exist_ok=True)
            data = {
                "version": "1.0",
                "loop_count": self.var_loop_count.get(),
                "global_settings": self.get_global_settings(),
                "blocks": self._serialize_all_blocks()
            }
            with open(self.save_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if self.gui and hasattr(self.gui, "auto_save_current_config"):
                self.gui.auto_save_current_config()
        except Exception as e:
            pass

    def load_config_auto(self):
        if not os.path.exists(self.save_file):
            return
        try:
            with open(self.save_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.var_loop_count.set(data.get("loop_count", 1))

            gs = data.get("global_settings", {})
            if gs and not self.gui:
                if "interval" in gs:
                    self.var_interval.set(gs["interval"])
                if "confidence" in gs:
                    self.var_confidence.set(gs["confidence"])
                if "idle_strategy" in gs:
                    self.var_idle_strategy.set(gs["idle_strategy"])
                if "lang_tc" in gs:
                    self.var_lang_tc.set(gs["lang_tc"])
                if "lang_sc" in gs:
                    self.var_lang_sc.set(gs["lang_sc"])
                if "lang_en" in gs:
                    self.var_lang_en.set(gs["lang_en"])
                if "tg_token" in gs:
                    self.var_tg_token.set(gs["tg_token"])
                if "tg_chat_id" in gs:
                    self.var_tg_chat_id.set(gs["tg_chat_id"])

            for b in self.blocks_list:
                for cb in b.get("inner_blocks_list", []):
                    if cb.get("frame"):
                        cb["frame"].destroy()
                if b.get("frame"):
                    b["frame"].destroy()
            self.blocks_list.clear()
            self.selected_block_target = None
            for bd in data.get("blocks", []):
                self.add_block(
                    b_type=bd["type"],
                    params=bd.get("params", {}),
                    name=bd.get("name", ""),
                    enabled=bd.get("enabled", True)
                )
        except Exception as e:
            self._log(f"讀取上次任務清單失敗: {e}")

    def save_as_new_preset(self):
        self.on_save_config_dialog(default_mode="new")

    def on_save_config_dialog(self, default_mode: str = "new"):
        """開啟任務設定存檔視窗：詢問使用者要存到哪裡，可直接自訂路徑與檔名儲存，不生成任何多餘資料夾"""
        if not self.blocks_list:
            if not messagebox.askyesno("提示", "目前任務清單是空的，確定要儲存空的任務嗎？"):
                return

        dlg = ctk.CTkToplevel(self.parent)
        dlg.title("💾 儲存任務設定")
        dlg.geometry("580x300")
        dlg.minsize(520, 260)
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
            text="💾 儲存任務設定 (Save Tasks)",
            font=ctk.CTkFont(family="Arial", size=16, weight="bold"),
            text_color="#FBBF24"
        ).pack(anchor="w")

        ctk.CTkLabel(
            header_box,
            text="請選擇或輸入任務設定檔要儲存到哪裡（.json 檔案）：",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_PRIMARY
        ).pack(anchor="w", pady=(4, 0))

        sec_path = ctk.CTkFrame(card, fg_color=COLOR_INPUT_BG, corner_radius=8, border_width=1, border_color=COLOR_CARD_BORDER)
        sec_path.pack(fill="x", padx=16, pady=(8, 12))

        sec_path_inner = ctk.CTkFrame(sec_path, fg_color="transparent")
        sec_path_inner.pack(fill="x", padx=12, pady=12)

        default_save_path = getattr(self, "save_file", None)
        if not default_save_path:
            default_save_path = os.path.join(self.presets_dir if hasattr(self, "presets_dir") else os.getcwd(), "task_flow_save.json")

        var_save_file = tk.StringVar(value=default_save_path)
        entry_save_file = ctk.CTkEntry(
            sec_path_inner,
            textvariable=var_save_file,
            font=ctk.CTkFont(family="Menlo", size=11),
            height=32,
            corner_radius=6,
            fg_color="#181825",
            border_color="#334155"
        )
        entry_save_file.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _do_browse_save():
            curr = var_save_file.get().strip()
            init_d = os.path.dirname(curr) if curr and os.path.isdir(os.path.dirname(curr)) else (self.presets_dir if hasattr(self, "presets_dir") else os.getcwd())
            init_f = os.path.basename(curr) if curr else "task_flow_save.json"
            if not init_f.endswith(".json"):
                init_f += ".json"
            f = filedialog.asksaveasfilename(
                parent=dlg,
                title="選擇存檔位置與檔案名稱",
                initialdir=init_d,
                initialfile=init_f,
                defaultextension=".json",
                filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
            )
            if f:
                var_save_file.set(os.path.abspath(f))

        ctk.CTkButton(
            sec_path_inner,
            text="📁 選擇位置",
            width=88,
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=_do_browse_save
        ).pack(side="left")

        def _do_save_file():
            p = var_save_file.get().strip()
            if not p:
                messagebox.showwarning("提示", "請輸入或選擇儲存路徑！", parent=dlg)
                return
            if not p.lower().endswith(".json"):
                p += ".json"
                var_save_file.set(p)

            target_path = os.path.abspath(p)
            if os.path.exists(target_path):
                fn = os.path.basename(target_path)
                if not messagebox.askyesno(
                    "⚠️ 檔案衝突提醒",
                    f"任務設定檔「{fn}」已經存在！\n\n路徑：{target_path}\n\n確定要覆蓋此設定檔嗎？\n（此動作將取代現有檔案內容，無法復原）",
                    parent=dlg
                ):
                    return

            try:
                parent_dir = os.path.dirname(target_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)

                data = {
                    "version": "1.0",
                    "loop_count": self.var_loop_count.get(),
                    "global_settings": self.get_global_settings(),
                    "blocks": self._serialize_all_blocks()
                }
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                self.save_file = target_path
                self.presets_dir = os.path.dirname(target_path)
                self.reload_presets()
                self._log(f"💾 任務設定已成功儲存至: {target_path}")
                messagebox.showinfo("儲存成功", f"✅ 任務設定已成功儲存至：\n{target_path}", parent=dlg)
                dlg.destroy()
            except Exception as ex:
                self._log(f"❌ 儲存任務設定失敗: {ex}")
                messagebox.showerror("錯誤", f"儲存失敗: {ex}", parent=dlg)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(10, 16))

        ctk.CTkButton(
            btn_row,
            text="確認儲存",
            width=100,
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=_do_save_file
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row,
            text="取消",
            width=72,
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=dlg.destroy
        ).pack(side="right")

    def on_load_config_dialog(self):
        path = filedialog.askopenfilename(
            initialdir=self.presets_dir if os.path.exists(self.presets_dir) else self.config_dir,
            title="載入任務清單",
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
        )
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.var_loop_count.set(data.get("loop_count", 1))

            gs = data.get("global_settings", {})
            if gs:
                if "interval" in gs:
                    self.var_interval.set(gs["interval"])
                if "confidence" in gs:
                    self.var_confidence.set(gs["confidence"])
                if "idle_strategy" in gs:
                    self.var_idle_strategy.set(gs["idle_strategy"])
                if "lang_tc" in gs:
                    self.var_lang_tc.set(gs["lang_tc"])
                if "lang_sc" in gs:
                    self.var_lang_sc.set(gs["lang_sc"])
                if "lang_en" in gs:
                    self.var_lang_en.set(gs["lang_en"])
                if "tg_token" in gs:
                    self.var_tg_token.set(gs["tg_token"])
                if "tg_chat_id" in gs:
                    self.var_tg_chat_id.set(gs["tg_chat_id"])

            for b in self.blocks_list:
                for cb in b.get("inner_blocks_list", []):
                    if cb.get("frame"):
                        cb["frame"].destroy()
                if b.get("frame"):
                    b["frame"].destroy()
            self.blocks_list.clear()
            self.selected_block_target = None
            for bd in data.get("blocks", []):
                self.add_block(
                    b_type=bd["type"],
                    params=bd.get("params", {}),
                    name=bd.get("name", ""),
                    enabled=bd.get("enabled", True)
                )
            messagebox.showinfo("成功", f"成功載入任務清單:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("錯誤", f"載入失敗: {e}")

    def get_block_choices(self) -> List[str]:
        choices = []
        for i, b in enumerate(self.blocks_list, start=1):
            name = b["name"].get() if hasattr(b["name"], "get") else b.get("name", "")
            b_type = b.get("type", "step")
            choices.append(f"#{i} {name} ({b_type})")
        return choices

    def get_preset_choices(self) -> List[str]:
        choices = []
        for k, v in self.presets.items():
            choices.append(f"{k}: {v.get('title', k)}")
        return choices

    def get_preset_data(self, preset_key: str) -> Optional[Dict[str, Any]]:
        if preset_key in self.presets:
            return self.presets[preset_key]
        if preset_key in DAILY_PRESETS:
            return DAILY_PRESETS[preset_key]
        fpath = os.path.join(self.presets_dir, f"{preset_key}.json")
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def get_block_data_by_choice(self, choice_str: str) -> Optional[Dict[str, Any]]:
        if not choice_str:
            return None
        import re
        m = re.match(r"^#(\d+)", choice_str.strip())
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(self.blocks_list):
                return self._serialize_single_block(self.blocks_list[idx])
        for b in self.blocks_list:
            name = b["name"].get() if hasattr(b["name"], "get") else b.get("name", "")
            if name and name in choice_str:
                return self._serialize_single_block(b)
        return None

    def on_theme_changed(self, mode: str):
        pass
