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

import cv2
import numpy as np
from PIL import Image, ImageTk


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
COLOR_BLOCK_BG = "#f8fafc"         # 積木卡片底色 (淺米灰)

BLOCK_TYPES = {
    "tap_coord": {
        "title": "👆 點擊指定座標",
        "badge": "動作",
        "color": COLOR_BLOCK_ACTION,
        "default_name": "點擊座標",
        "default_params": {"x": 960, "y": 540, "delay": 1.5, "repeat": 1}
    },
    "multi_tap": {
        "title": "⚡ 連續點擊 (可設停止條件)",
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
            "check_every": 1,
            "delay_after": 0.5
        }
    },
    "detect_click": {
        "title": "🔍 偵測文字/圖案並點擊",
        "badge": "偵測",
        "color": COLOR_BLOCK_DETECT,
        "default_name": "等待並點擊",
        "default_params": {
            "target_type": "📝 僅文字",
            "keywords": "確認, 確定",
            "timeout": 10,
            "click_mode": "click_text",
            "custom_x": 960,
            "custom_y": 540,
            "delay": 1.5,
            "on_timeout": "continue"
        }
    },
    "branch_if": {
        "title": "🔀 判斷文字點擊不同座標",
        "badge": "條件",
        "color": COLOR_BLOCK_BRANCH,
        "default_name": "文字條件分支",
        "default_params": {
            "timeout": 8,
            "delay": 1.5,
            "else_action": "skip",
            "else_x": 960,
            "else_y": 950,
            "branches": [
                {"name": "If", "keywords": "勝利, 挑戰成功", "x": 1650, "y": 950},
                {"name": "Else If", "keywords": "失敗, 挑戰失敗", "x": 960, "y": 950}
            ]
        }
    },
    "loop": {
        "title": "🔁 迴圈容器 (While 條件/重複次數)",
        "badge": "迴圈",
        "color": COLOR_BLOCK_LOOP,
        "default_name": "迴圈容器",
        "default_params": {
            "stop_mode": "依指定次數",
            "count": 3,
            "keywords": "",
            "check_timing": "每輪開始與結束",
            "delay_after": 0.5,
            "inner_blocks": []
        }
    },
    "wait_condition": {
        "title": "⏳ 等待指定條件",
        "badge": "等待",
        "color": "#8b5cf6",
        "default_name": "等待條件達成",
        "default_params": {
            "cond_mode": "出現 (Wait Appear)",
            "target_type": "📝 僅文字",
            "keywords": "確認, 確定",
            "interval": 1.0,
            "timeout": 30,
            "delay_after": 0.5,
            "on_timeout": "continue"
        }
    },
    "wait_sec": {
        "title": "⏱ 等待指定秒數",
        "badge": "流程",
        "color": COLOR_BLOCK_WAIT,
        "default_name": "等待延遲",
        "default_params": {"seconds": 3.0}
    },
    "swipe": {
        "title": "↔ 滑動螢幕手勢",
        "badge": "手勢",
        "color": COLOR_BLOCK_SWIPE,
        "default_name": "滑動螢幕",
        "default_params": {"x1": 1500, "y1": 540, "x2": 400, "y2": 540, "duration_ms": 400, "delay": 1.0}
    },
    "back_key": {
        "title": "📱 模擬返回鍵 (Back)",
        "badge": "系統",
        "color": COLOR_BLOCK_BACK,
        "default_name": "返回上一頁",
        "default_params": {"delay": 1.2}
    },
    "comment": {
        "title": "💬 備註 / 流程說明",
        "badge": "備註",
        "color": COLOR_BLOCK_COMMENT,
        "default_name": "備註說明",
        "default_params": {"note": "此處為備註說明文字，執行時不執行任何操作"}
    },
    "send_telegram": {
        "title": "📱 傳送 Telegram 通知",
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

# 每日任務預設範本
DAILY_PRESETS = {
    "daily_mailbox": {
        "title": "📦 每日簽到與信箱領取",
        "desc": "自動點擊主頁信箱 ➜ 全部領取 ➜ 確認 ➜ 返回 ➜ 發送通知",
        "blocks": [
            {"type": "comment", "name": "流程說明", "enabled": True, "params": {"note": "每日信箱自動領取所有禮物與體力"}},
            {"type": "tap_coord", "name": "點擊右上信箱圖示", "enabled": True, "params": {"x": 1780, "y": 75, "delay": 2.0, "repeat": 1}},
            {"type": "detect_click", "name": "點擊全部領取", "enabled": True, "params": {"target_type": "📝 僅文字", "keywords": "全部領取, 領取全部, 領取", "timeout": 8, "click_mode": "click_text", "custom_x": 0, "custom_y": 0, "delay": 1.8, "on_timeout": "continue"}},
            {"type": "detect_click", "name": "確認彈窗領取", "enabled": True, "params": {"target_type": "📝 僅文字", "keywords": "確認, 確定, OK", "timeout": 6, "click_mode": "click_text", "custom_x": 0, "custom_y": 0, "delay": 1.5, "on_timeout": "continue"}},
            {"type": "back_key", "name": "關閉信箱返回主頁", "enabled": True, "params": {"delay": 1.2}},
            {"type": "send_telegram", "name": "發送領取完成通知", "enabled": True, "params": {"message": "📬 每日信箱所有禮物與體力已領取完畢！", "attach_screenshot": True, "use_custom": False, "delay_after": 0.5}}
        ]
    },
    "friend_hearts": {
        "title": "🤝 好友送心與點數",
        "desc": "進入好友選單 ➜ 一鍵送出友情點數 ➜ 確認 ➜ 返回",
        "blocks": [
            {"type": "tap_coord", "name": "點擊好友選單", "enabled": True, "params": {"x": 1620, "y": 75, "delay": 2.2, "repeat": 1}},
            {"type": "detect_click", "name": "點擊一併贈送/全部發送", "enabled": True, "params": {"target_type": "📝 僅文字", "keywords": "一併贈送, 全部贈送, 全部發送, 送點數", "timeout": 8, "click_mode": "click_text", "custom_x": 0, "custom_y": 0, "delay": 1.8, "on_timeout": "continue"}},
            {"type": "detect_click", "name": "確認贈送完畢", "enabled": True, "params": {"target_type": "📝 僅文字", "keywords": "確認, 確定", "timeout": 6, "click_mode": "click_text", "custom_x": 0, "custom_y": 0, "delay": 1.5, "on_timeout": "continue"}},
            {"type": "back_key", "name": "返回主選單", "enabled": True, "params": {"delay": 1.2}}
        ]
    },
    "branch_example": {
        "title": "🔀 勝負判斷分支範本",
        "desc": "判斷勝負畫面：若勝利點擊領取，若失敗點擊退出",
        "blocks": [
            {"type": "wait_sec", "name": "等待結算畫面載入", "enabled": True, "params": {"seconds": 3.0}},
            {"type": "branch_if", "name": "判斷勝負並點擊對應座標", "enabled": True, "params": {
                "timeout": 10, "delay": 2.0,
                "else_action": "skip", "else_x": 960, "else_y": 950,
                "branches": [
                    {"name": "If", "keywords": "勝利, 挑戰成功, 獲勝", "x": 1650, "y": 950},
                    {"name": "Else If", "keywords": "失敗, 挑戰失敗", "x": 960, "y": 950}
                ]
            }},
            {"type": "detect_click", "name": "點擊下一步或確認", "enabled": True, "params": {"target_type": "📝 僅文字", "keywords": "下一步, 確定, 確認", "timeout": 8, "click_mode": "click_text", "custom_x": 0, "custom_y": 0, "delay": 1.5, "on_timeout": "continue"}}
        ]
    },
    "league_cycle": {
        "title": "🏆 每日聯賽刷關循環 (3場)",
        "desc": "循環執行準備比賽 ➜ 開始比賽 ➜ 結算確認",
        "blocks": [
            {"type": "detect_click", "name": "準備進入比賽", "enabled": True, "params": {"target_type": "📝 僅文字", "keywords": "準備, 挑戰, 出戰", "timeout": 12, "click_mode": "click_text", "custom_x": 0, "custom_y": 0, "delay": 2.5, "on_timeout": "continue"}},
            {"type": "detect_click", "name": "點擊開始比賽", "enabled": True, "params": {"target_type": "📝 僅文字", "keywords": "開始, 比賽開始", "timeout": 10, "click_mode": "click_text", "custom_x": 0, "custom_y": 0, "delay": 3.5, "on_timeout": "continue"}},
            {"type": "wait_condition", "name": "等待比賽結束進入結算", "enabled": True, "params": {
                "cond_mode": "出現 (Wait Appear)", "target_type": "📝 僅文字", "keywords": "勝利, 失敗, 挑戰成功, 結算, 確定",
                "interval": 2.0, "timeout": 120, "delay_after": 1.0, "on_timeout": "continue"
            }},
            {"type": "detect_click", "name": "結算領取獎勵", "enabled": True, "params": {"target_type": "📝 僅文字", "keywords": "確認, 確定, 領取, 下一步", "timeout": 25, "click_mode": "click_text", "custom_x": 0, "custom_y": 0, "delay": 2.5, "on_timeout": "continue"}}
        ]
    },
    "repeat_upgrade_example": {
        "title": "🔁 迴圈連續強化範本 (While 條件)",
        "desc": "迴圈重複強化，直到偵測到完成文字或滿 10 次退出",
        "blocks": [
            {"type": "comment", "name": "流程說明", "enabled": True, "params": {"note": "示範在迴圈容器內設定 While 停止條件 (文字出現/最多10次)"}},
            {"type": "loop", "name": "重複強化 (直到升級完成)", "enabled": True, "params": {
                "stop_mode": "偵測到文字出現",
                "keywords": "強化成功, 等級上限, MAX, 完成",
                "count": 10,
                "check_timing": "每輪開始與結束",
                "delay_after": 0.5,
                "inner_blocks": [
                    {"type": "multi_tap", "name": "連續點擊強化鈕", "enabled": True, "params": {
                        "x": 1600, "y": 800, "count": 6, "interval": 0.25,
                        "stop_mode": "無 (僅點滿次數)", "stop_keywords": "", "check_every": 2, "delay_after": 0.5
                    }},
                    {"type": "detect_click", "name": "確認彈窗", "enabled": True, "params": {
                        "target_type": "📝 僅文字", "keywords": "確認, 確定", "timeout": 4, "click_mode": "click_text", "custom_x": 0, "custom_y": 0, "delay": 1.0, "on_timeout": "continue"
                    }},
                    {"type": "wait_sec", "name": "冷卻緩衝", "enabled": True, "params": {"seconds": 1.0}}
                ]
            }}
        ]
    }
}


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

    def _check_condition_met(self, stop_mode: str, raw_keywords: str) -> Tuple[bool, str]:
        """檢測當前畫面是否滿足終止條件 (文字出現/消失、打勾/叉叉符號)"""
        if not self.bot:
            return False, ""

        if stop_mode in ("依指定次數", "無 (僅點滿次數)"):
            return False, ""

        is_disappear = ("消失" in stop_mode or "disappear" in stop_mode.lower())
        is_check = ("打勾" in stop_mode or "check" in stop_mode.lower())
        is_cross = ("叉叉" in stop_mode or "cross" in stop_mode.lower())
        is_appear = (not is_disappear)

        kws = [k.strip() for k in raw_keywords.replace("，", ",").split(",") if k.strip()]

        screen = None
        try:
            screen = self.bot.capture_screen()
        except Exception:
            pass

        if screen is None:
            return False, ""

        det_results = self.bot.scan_text(screen)
        present = False
        matched_desc = ""

        # 符號比對
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
                met, desc = self._check_condition_met(stop_mode, raw_kws)
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

    def _exec_detect_click(self, p: Dict[str, Any]) -> bool:
        target_type = p.get("target_type", "📝 僅文字")
        raw_kws = p.get("keywords", "")
        timeout = max(1, _safe_int(p.get("timeout", 10)))
        click_mode = p.get("click_mode", "click_text")
        cx = _safe_int(p.get("custom_x", 960))
        cy = _safe_int(p.get("custom_y", 540))
        delay = _safe_float(p.get("delay", 1.5))

        kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
        is_check = ("打勾" in target_type or "check" in target_type.lower())
        is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)

        scan_delay = self._get_scan_interval()
        conf_thresh = self._get_confidence()
        deadline = time.time() + timeout
        self._log(f"  🔍 等待目標出現 (限時 {timeout}s, 刷新速度 {scan_delay:.2f}s)...")

        while time.time() < deadline:
            if self._stop_event.is_set():
                return False

            screen = self.bot.capture_screen()
            if screen is not None:
                det_results = self.bot.scan_text(screen)

                # 優先比對符號
                if is_check or is_cross:
                    for item in det_results:
                        sym = item.get("symbol")
                        txt = item.get("text", "")
                        if is_check and (sym == "check" or txt in ("[打勾]", "✓", "✔", "√") or (len(txt) == 1 and txt.upper() == "V")):
                            return self._do_click(click_mode, item, cx, cy, delay)
                        if is_cross and (sym == "cross" or txt in ("[叉叉]", "✕", "✖", "×", "X", "x")):
                            return self._do_click(click_mode, item, cx, cy, delay)

                # 比對關鍵字
                for kw in kws:
                    for item in det_results:
                        matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                        if matched and ratio >= conf_thresh:
                            return self._do_click(click_mode, item, cx, cy, delay)

            time.sleep(scan_delay)

        self._log(f"  ⚠️ 等待超時 ({timeout}s 未偵測到目標)")
        return False

    def _do_click(self, click_mode: str, item: Dict[str, Any], cx: int, cy: int, delay: float) -> bool:
        if click_mode == "custom_coord":
            tx, ty = cx, cy
        else:
            tx, ty = item["center"]
        self._log(f"  🎯 命中目標 [{item.get('text')}]，點擊座標 ({tx}, {ty})")
        self.bot.tap(tx, ty)
        self._sleep_interruptible(delay)
        return True

    def _exec_branch_if(self, p: Dict[str, Any]) -> bool:
        """條件分支：判斷當前畫面文字來去點擊不同的座標 (支援多個 If 與 Else If)"""
        branches = p.get("branches")
        if not branches:
            branches = []
            if p.get("cond_a_kws") or p.get("cond_a_x"):
                branches.append({
                    "name": "If",
                    "keywords": p.get("cond_a_kws", ""),
                    "x": _safe_int(p.get("cond_a_x", 1650)),
                    "y": _safe_int(p.get("cond_a_y", 950))
                })
            if p.get("cond_b_kws") or p.get("cond_b_x"):
                branches.append({
                    "name": "Else If",
                    "keywords": p.get("cond_b_kws", ""),
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
                det_results = self.bot.scan_text(screen)

                # 依序檢查 If 以及各個 Else If 分支
                for b_idx, branch in enumerate(branches):
                    b_tag = branch.get("name", "If" if b_idx == 0 else f"Else If {b_idx}")
                    raw_kws = branch.get("keywords", "")
                    kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
                    bx = _safe_int(branch.get("x", 960))
                    by = _safe_int(branch.get("y", 540))

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
            target_desc = f"「{raw_kws}」" if raw_kws else stop_mode
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
                met, desc = self._check_condition_met(stop_mode, raw_kws)
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
                    met, desc = self._check_condition_met(stop_mode, raw_kws)
                    if met:
                        self._log(f"  🛑 迴圈終止！在子步驟 [{sb_name}] 執行後觸發停止條件 ({desc})")
                        broken_by_step = True
                        break

            rounds_done += 1
            if broken_by_step:
                break

            # 每輪結束後檢查 (Do-While 模式)
            if is_cond_mode and ("結束" in check_timing or "Do-While" in check_timing):
                met, desc = self._check_condition_met(stop_mode, raw_kws)
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
        """等待指定條件達成 (畫面出現或消失特定文字/符號)，期間依設定的頻率 (秒) 循環檢測"""
        cond_mode = p.get("cond_mode", "出現 (Wait Appear)")
        is_wait_disappear = ("消失" in cond_mode or "disappear" in cond_mode.lower())
        is_wait_appear = not is_wait_disappear
        target_type = p.get("target_type", "📝 僅文字")
        raw_kws = p.get("keywords", "")

        scan_delay = self._get_scan_interval()
        default_interval = scan_delay if "interval" not in p else _safe_float(p.get("interval", scan_delay))
        interval = max(0.02, default_interval)

        timeout = max(1, _safe_int(p.get("timeout", 30)))
        delay_after = max(0.0, _safe_float(p.get("delay_after", 0.5)))
        on_timeout = p.get("on_timeout", "continue")

        kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
        is_check = ("打勾" in target_type or "check" in target_type.lower())
        is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)

        mode_str = "出現" if is_wait_appear else "消失"
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

            if screen is not None:
                det_results = self.bot.scan_text(screen)

                # 優先比對符號
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

                # 比對關鍵字
                conf_thresh = self._get_confidence()
                if not present:
                    for kw in kws:
                        for item in det_results:
                            matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                            if matched and ratio >= conf_thresh:
                                present = True
                                matched_desc = f"關鍵字「{kw}」({item.get('text')})"
                                break
                        if present:
                            break

            elapsed = time.time() - start_time
            if is_wait_appear and present:
                self._log(f"  ✅ 條件達成！已偵測到 {matched_desc} 出現 (耗時 {elapsed:.1f}s)")
                if delay_after > 0:
                    self._sleep_interruptible(delay_after)
                return True
            elif not is_wait_appear and not present:
                self._log(f"  ✅ 條件達成！目標已從畫面消失 (耗時 {elapsed:.1f}s)")
                if delay_after > 0:
                    self._sleep_interruptible(delay_after)
                return True

            if not self._sleep_interruptible(interval):
                return False

        self._log(f"  ⚠️ 等待超時 ({timeout}s 未滿足「{desc}」{mode_str} 條件)")
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
# 任務清單 GUI 頁籤 (TaskFlowTab)
# ==========================================
class TaskFlowTab:
    """Scratch 積木式日常任務編程頁籤"""

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

        # 連接父層 GUI 的全域通用進階變數 (與聯賽自動刷頁面雙向同步共享)
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
        self.blocks_list: List[Dict[str, Any]] = []  # 積木資料模型
        self.selected_block_idx: int = -1             # 當前選取的積木索引
        self.selected_block_target: Optional[Dict[str, Any]] = None  # 當前選取的積木物件 (支援頂層或迴圈內部積木)

        # 語言與參數監聽
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

        # 狀態與控制變數
        self.var_loop_count = tk.IntVar(value=1)
        self.var_status_text = tk.StringVar(value="🟢 閒置中")
        self.var_auto_preview = tk.BooleanVar(value=False)
        self.var_preview_coords = tk.StringVar(value="")
        self.var_picked_coord = tk.StringVar(value="尚未選取座標")

        # 截圖與預覽控制 (完全比照 gui.py 聯賽預覽核心邏輯)
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

        self.config_dir = os.path.dirname(os.path.abspath(__file__))
        self.save_file = os.path.join(self.config_dir, "tasks_flow.json")

        self._build_ui()
        self.load_config_auto()

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
        # 3 欄式主畫面配置：左欄積木庫 | 中欄程式畫布 | 右欄截圖取點
        paned = ttk.PanedWindow(self.parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 1. 左側：Scratch 積木工具庫
        frame_palette = ttk.Frame(paned, padding=4)
        paned.add(frame_palette, weight=1)

        # 2. 中間：程式積木工作區
        frame_program = ttk.Frame(paned, padding=4)
        paned.add(frame_program, weight=3)

        # 3. 右側：截圖與座標吸管輔助區
        frame_picker = ttk.Frame(paned, padding=4)
        paned.add(frame_picker, weight=2)

        self._build_palette_panel(frame_palette)
        self._build_program_panel(frame_program)
        self._build_picker_panel(frame_picker)

    # -------------------------------------------------------------------------
    # 左側：積木工具庫 (Block Palette)
    # -------------------------------------------------------------------------
    def _build_palette_panel(self, parent):
        box_hdr = ttk.LabelFrame(parent, text="🧩 Scratch 積木庫", padding=6)
        box_hdr.pack(fill=tk.BOTH, expand=True)

        lbl_tip = ttk.Label(
            box_hdr,
            text="點擊積木即可加入程式區：",
            font=("Microsoft JhengHei", 9, "bold"),
            foreground="#475569"
        )
        lbl_tip.pack(anchor="w", pady=(0, 6))

        # 建立積木按鈕
        for b_type, info in BLOCK_TYPES.items():
            btn_f = tk.Frame(box_hdr, bg=info["color"], bd=0, relief=tk.RAISED, cursor="hand2")
            btn_f.pack(fill=tk.X, pady=3, ipady=3)

            lbl_badge = tk.Label(btn_f, text=f"[{info['badge']}]", bg=info["color"], fg="#ffffff", font=("Arial", 8, "bold"))
            lbl_badge.pack(side=tk.LEFT, padx=(6, 2))

            lbl_name = tk.Label(btn_f, text=info["title"], bg=info["color"], fg="#ffffff", font=("Arial", 9, "bold"))
            lbl_name.pack(side=tk.LEFT, padx=2)

            lbl_add = tk.Label(btn_f, text="＋", bg=info["color"], fg="#ffffff", font=("Arial", 11, "bold"))
            lbl_add.pack(side=tk.RIGHT, padx=6)

            # 點擊加入事件
            for w in (btn_f, lbl_badge, lbl_name, lbl_add):
                w.bind("<Button-1>", lambda e, bt=b_type: self.add_block(bt))

        ttk.Separator(box_hdr, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(12, 8))

        lbl_preset = ttk.Label(box_hdr, text="💡 常用日常任務範本：", font=("Microsoft JhengHei", 9, "bold"), foreground="#475569")
        lbl_preset.pack(anchor="w", pady=(0, 4))

        for p_key, p_val in DAILY_PRESETS.items():
            btn_p = ttk.Button(
                box_hdr,
                text=p_val["title"],
                command=lambda pk=p_key: self.load_preset(pk)
            )
            btn_p.pack(fill=tk.X, pady=2)

    # -------------------------------------------------------------------------
    # 中間：程式積木工作區 (Program Script Area)
    # -------------------------------------------------------------------------
    def _build_program_panel(self, parent):
        box = ttk.LabelFrame(parent, text="💻 任務程式區 (依序向下執行)", padding=6)
        box.pack(fill=tk.BOTH, expand=True)

        # 頂部控制列
        tb = ttk.Frame(box)
        tb.pack(fill=tk.X, pady=(0, 6))
        self.bar_tb = tb

        self.btn_run = ttk.Button(tb, text="▶ 執行全部", width=9, command=self.on_run_tasks)
        self.btn_run.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_step = ttk.Button(tb, text="👣 單步", width=5, command=self.on_step_task)
        self.btn_step.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_stop = ttk.Button(tb, text="■ 停止", width=6, command=self.on_stop_tasks, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(tb, text="循環:").pack(side=tk.LEFT)
        sp_loop = ttk.Spinbox(tb, from_=0, to=999, textvariable=self.var_loop_count, width=4)
        sp_loop.pack(side=tk.LEFT, padx=(2, 2))
        ttk.Label(tb, text="次 (0=無限)", font=("Arial", 8), foreground="#64748b").pack(side=tk.LEFT, padx=(0, 6))

        # 進階設定按鈕 (折疊切換)
        self.btn_adv = ttk.Button(tb, text="⚙ 通用進階 ▸", command=self._toggle_advanced)
        self.btn_adv.pack(side=tk.LEFT, padx=(6, 0))

        ttk.Button(tb, text="清空", width=4, command=self.on_clear_blocks).pack(side=tk.RIGHT)
        ttk.Button(tb, text="載入", width=4, command=self.on_load_config_dialog).pack(side=tk.RIGHT, padx=2)
        ttk.Button(tb, text="存檔", width=4, command=self.on_save_config_dialog).pack(side=tk.RIGHT)

        # 建立通用進階設定面板 (預設收合)
        self._build_advanced_panel(box)

        # 狀態標籤列
        bar_status = tk.Frame(box, bg="#f1f5f9", bd=1, relief=tk.SUNKEN)
        bar_status.pack(fill=tk.X, pady=(0, 6), ipady=2)
        lbl_st = tk.Label(bar_status, textvariable=self.var_status_text, bg="#f1f5f9", font=("Arial", 9, "bold"), fg="#0f172a")
        lbl_st.pack(side=tk.LEFT, padx=6)

        # 滾動積木畫布
        area = ttk.Frame(box)
        area.pack(fill=tk.BOTH, expand=True)

        self.canvas_blocks = tk.Canvas(area, borderwidth=0, highlightthickness=0, bg="#ffffff")
        self.scroll_blocks = ttk.Scrollbar(area, orient="vertical", command=self.canvas_blocks.yview)
        self.inner_blocks = ttk.Frame(self.canvas_blocks)
        self.canvas_window = self.canvas_blocks.create_window((0, 0), window=self.inner_blocks, anchor="nw")
        self.canvas_blocks.configure(yscrollcommand=self.scroll_blocks.set)

        self.inner_blocks.bind(
            "<Configure>", lambda e: self.canvas_blocks.configure(scrollregion=self.canvas_blocks.bbox("all"))
        )
        self.canvas_blocks.bind(
            "<Configure>", lambda e: self.canvas_blocks.itemconfig(self.canvas_window, width=e.width)
        )

        self.canvas_blocks.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scroll_blocks.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_advanced_panel(self, parent):
        """建立通用進階設定面板 (與聯賽自動刷通用連動)"""
        f = ttk.LabelFrame(parent, text="⚙ 通用進階設定 (與聯賽自動刷共享連動)", padding=(8, 6, 8, 8))
        self.adv_frame = f

        # 第 0 列：掃描刷新速度 (秒)
        ttk.Label(f, text="掃描刷新速度:").grid(row=0, column=0, sticky="w", pady=2)
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
        ttk.Label(row_speed, text="秒 (0為極速無延遲，與聯賽快速刷共享)", font=("Arial", 9), foreground="#6b7280").pack(side=tk.LEFT, padx=(4, 0))

        # 第 1 列：辨識門檻
        ttk.Label(f, text="OCR辨識門檻:").grid(row=1, column=0, sticky="w", pady=2)
        row_conf = ttk.Frame(f)
        row_conf.grid(row=1, column=1, sticky="w", padx=8)
        scale_conf = ttk.Scale(
            row_conf, from_=0.40, to=0.95, variable=self.var_confidence, orient=tk.HORIZONTAL,
            length=140, command=lambda v: self.lbl_conf_val.config(text=f"{float(v):.2f}")
        )
        scale_conf.pack(side=tk.LEFT, padx=(0, 6))
        self.lbl_conf_val = ttk.Label(row_conf, text=f"{self.var_confidence.get():.2f}", width=5)
        self.lbl_conf_val.pack(side=tk.LEFT)

        # 第 2 列：找不到時策略
        ttk.Label(f, text="找不到目標時:").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Combobox(
            f, textvariable=self.var_idle_strategy, values=["快速跳過", "等待下輪", "隨機點擊", "固定點擊", "不動作"], state="readonly", width=12
        ).grid(row=2, column=1, sticky="w", padx=8)

        # 第 3 列：分隔線
        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 4))

        # 第 4 列：語言辨識過濾
        row_lang_hdr = ttk.Frame(f)
        row_lang_hdr.grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))
        tk.Label(row_lang_hdr, text="🔤 辨識語言過濾 (降低誤判率)", font=("Arial", 9, "bold"), fg="#0284c7").pack(side=tk.LEFT)

        row_lang_boxes = ttk.Frame(f)
        row_lang_boxes.grid(row=5, column=0, columnspan=3, sticky="w", pady=(2, 2))
        ttk.Checkbutton(row_lang_boxes, text="繁體中文", variable=self.var_lang_tc).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(row_lang_boxes, text="簡體中文", variable=self.var_lang_sc).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(row_lang_boxes, text="英文與數字", variable=self.var_lang_en).pack(side=tk.LEFT, padx=(0, 8))

        lbl_lang_tip = ttk.Label(
            f,
            text="💡 提示：若遊戲為繁體版，建議關閉「簡體中文」，可完全杜絕背景雜訊被誤判為簡體字。",
            font=("Microsoft JhengHei", 8),
            foreground="#6b7280"
        )
        lbl_lang_tip.grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 4))

        # 第 7 列：Telegram 推播通知設定
        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(6, 4))

        row_tg_hdr = ttk.Frame(f)
        row_tg_hdr.grid(row=8, column=0, columnspan=3, sticky="ew", pady=2)
        tk.Label(row_tg_hdr, text="📱 Telegram 推播通知設定 (通用 Token / Chat ID)", font=("Arial", 9, "bold"), fg="#0284c7").pack(side=tk.LEFT)
        ttk.Button(row_tg_hdr, text="📨 發送測試訊息", width=12, command=self.on_test_telegram_message).pack(side=tk.RIGHT, padx=4)

        row_tg_1 = ttk.Frame(f)
        row_tg_1.grid(row=9, column=0, columnspan=3, sticky="ew", pady=1)
        ttk.Label(row_tg_1, text="Bot Token:").pack(side=tk.LEFT)
        ttk.Entry(row_tg_1, textvariable=self.var_tg_token, width=32).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        row_tg_2 = ttk.Frame(f)
        row_tg_2.grid(row=10, column=0, columnspan=3, sticky="ew", pady=1)
        ttk.Label(row_tg_2, text="Chat ID:   ").pack(side=tk.LEFT)
        ttk.Entry(row_tg_2, textvariable=self.var_tg_chat_id, width=18).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(row_tg_2, text="(兩頁面通用，任一處修改自動同步儲存)", font=("Arial", 8), foreground="#64748b").pack(side=tk.LEFT, padx=(8, 0))

        f.columnconfigure(1, weight=1)

    def _toggle_advanced(self):
        self._adv_open = not self._adv_open
        if self._adv_open:
            self.adv_frame.pack(fill=tk.X, after=self.bar_tb, pady=(0, 6))
            self.btn_adv.config(text="⚙ 通用進階 ▾")
        else:
            self.adv_frame.pack_forget()
            self.btn_adv.config(text="⚙ 通用進階 ▸")

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

    # -------------------------------------------------------------------------
    # 右側：截圖預覽與座標吸管 (Screen & Coordinate Picker)
    # -------------------------------------------------------------------------
    def _build_picker_panel(self, parent):
        box = ttk.LabelFrame(parent, text="🎯 截圖與座標吸管", padding=6)
        box.pack(fill=tk.BOTH, expand=True)

        tools = ttk.Frame(box)
        tools.pack(fill=tk.X)
        self.btn_capture = ttk.Button(tools, text="📸 立即截圖", width=9, command=self.on_capture_screen)
        self.btn_capture.pack(side=tk.LEFT)
        ttk.Checkbutton(tools, text="自動刷新", variable=self.var_auto_preview, command=self.on_toggle_auto_refresh).pack(side=tk.LEFT, padx=8)

        # 頂部即時座標顯示 (同 gui.py Menlo 11 bold 藍色字樣)
        lbl_coord_rt = tk.Label(tools, textvariable=self.var_preview_coords, fg="#2563eb", font=("Menlo", 11, "bold"))
        lbl_coord_rt.pack(side=tk.RIGHT)

        # 固定大小容器，避免圖片尺寸變動造成版面跳動 (同 gui.py)
        holder = tk.Frame(box, width=340, height=240, bg="#1e293b")
        holder.pack_propagate(False)
        holder.pack(fill=tk.BOTH, expand=True, pady=(6, 4))
        holder.bind("<Configure>", self._on_preview_resize)

        self.lbl_canvas = tk.Label(
            holder,
            text="連線後點擊「立即截圖」\n點擊畫面任一處即可直接選取座標！",
            bg="#1e293b",
            fg="#94a3b8",
            cursor="crosshair",
            anchor=tk.CENTER
        )
        self.lbl_canvas.pack(fill=tk.BOTH, expand=True)
        self.lbl_canvas.bind("<Motion>", self._on_preview_mouse_move)
        self.lbl_canvas.bind("<Leave>", lambda e: self.var_preview_coords.set(""))
        self.lbl_canvas.bind("<Button-1>", self._on_preview_click)

        # 座標資訊與填入工具列
        coord_box = ttk.Frame(box)
        coord_box.pack(fill=tk.X, pady=(4, 0))

        lbl_c = ttk.Label(coord_box, textvariable=self.var_picked_coord, font=("Arial", 10, "bold"), foreground="#0284c7")
        lbl_c.pack(anchor="w", pady=(0, 4))

        row_fill = ttk.Frame(coord_box)
        row_fill.pack(fill=tk.X, pady=2)
        ttk.Button(row_fill, text="🎯 填入當前選取積木", command=self.on_fill_selected_block).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(row_fill, text="📋 複製", width=5, command=self.on_copy_picked_coord).pack(side=tk.LEFT)

        row_cond = ttk.Frame(coord_box)
        row_cond.pack(fill=tk.X, pady=2)
        ttk.Button(row_cond, text="🔀 填入 If 分支", command=lambda: self.on_fill_branch_coord(0)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(row_cond, text="🔀 填入 Else If 1", command=lambda: self.on_fill_branch_coord(1)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(row_cond, text="⏩ 填入 Else", width=8, command=lambda: self.on_fill_branch_coord("else")).pack(side=tk.LEFT)

    # -------------------------------------------------------------------------
    # 積木卡片動態建立與管理
    # -------------------------------------------------------------------------
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

        # 若是迴圈積木且包含預設/儲存的內部積木，遞迴建立子積木
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
            self.parent.after(50, lambda: self.canvas_blocks.yview_moveto(1.0))

        return block_item

    def add_inner_block(self, loop_item: Dict[str, Any], b_type: str):
        """將指定類型積木直接裝入迴圈容器中"""
        self.add_block(b_type=b_type, parent_loop=loop_item)

    def pull_prev_block_into_loop(self, loop_item: Dict[str, Any]):
        """將迴圈正上方的積木移入並裝進此迴圈中"""
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
        """將子積木移出迴圈，放回主任務流程中"""
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
        p = block_item["params"]

        # 卡片最外層 Frame (若是子積木，置入迴圈的 inner_container)
        target_parent = parent_loop["inner_container"] if (parent_loop and "inner_container" in parent_loop) else self.inner_blocks
        card = tk.Frame(target_parent, bg=COLOR_BLOCK_BG, bd=2 if b_type == "loop" else 1, relief=tk.SOLID)
        card.pack(fill=tk.X, padx=4, pady=3)
        block_item["frame"] = card

        # 頂部標題列 (Scratch 風格標籤列)
        hdr = tk.Frame(card, bg=info["color"], cursor="hand2")
        hdr.pack(fill=tk.X)

        # 拖曳手柄與勾選
        lbl_drag = tk.Label(hdr, text=" ☰ ", bg=info["color"], fg="#ffffff", font=("Arial", 10, "bold"), cursor="fleur")
        lbl_drag.pack(side=tk.LEFT)
        self._bind_drag(lbl_drag, block_item)

        chk_en = tk.Checkbutton(hdr, variable=block_item["enabled"], bg=info["color"], activebackground=info["color"])
        chk_en.pack(side=tk.LEFT)

        lbl_num = tk.Label(hdr, text="#0", bg=info["color"], fg="#ffffff", font=("Arial", 9, "bold"))
        lbl_num.pack(side=tk.LEFT, padx=2)
        block_item["lbl_num"] = lbl_num

        ent_name = ttk.Entry(hdr, textvariable=block_item["name"], width=16)
        ent_name.pack(side=tk.LEFT, padx=4)

        # 標籤類型徽章
        lbl_type = tk.Label(hdr, text=f"[{info['badge']}]", bg=info["color"], fg="#ffffff", font=("Arial", 8))
        lbl_type.pack(side=tk.LEFT, padx=2)

        # 右側控制按鈕：選取為目前積木、上移、下移、複製、刪除
        btn_del = tk.Label(hdr, text=" ✕ ", bg=info["color"], fg="#fee2e2", font=("Arial", 9, "bold"), cursor="hand2")
        btn_del.pack(side=tk.RIGHT)
        btn_del.bind("<Button-1>", lambda e: self.delete_block(block_item))

        btn_dup = tk.Label(hdr, text=" 📋 ", bg=info["color"], fg="#ffffff", font=("Arial", 8), cursor="hand2")
        btn_dup.pack(side=tk.RIGHT)
        btn_dup.bind("<Button-1>", lambda e: self.duplicate_block(block_item))

        btn_down = tk.Label(hdr, text=" ▼ ", bg=info["color"], fg="#ffffff", font=("Arial", 8), cursor="hand2")
        btn_down.pack(side=tk.RIGHT)
        btn_down.bind("<Button-1>", lambda e: self.move_block(block_item, 1))

        btn_up = tk.Label(hdr, text=" ▲ ", bg=info["color"], fg="#ffffff", font=("Arial", 8), cursor="hand2")
        btn_up.pack(side=tk.RIGHT)
        btn_up.bind("<Button-1>", lambda e: self.move_block(block_item, -1))

        if parent_loop:
            btn_out = tk.Label(hdr, text=" ⏏移出 ", bg=info["color"], fg="#fed7aa", font=("Arial", 8, "bold"), cursor="hand2")
            btn_out.pack(side=tk.RIGHT, padx=2)
            btn_out.bind("<Button-1>", lambda e: self.move_out_of_loop(block_item))

        btn_pick = tk.Label(hdr, text=" 🎯選中 ", bg=info["color"], fg="#fef08a", font=("Arial", 8, "bold"), cursor="hand2")
        btn_pick.pack(side=tk.RIGHT, padx=4)
        btn_pick.bind("<Button-1>", lambda e: self.select_block(block_item))

        # 內容參數區
        body = tk.Frame(card, bg="#ffffff", padx=8, pady=6)
        body.pack(fill=tk.X)
        block_item["body_frame"] = body

        self._build_block_fields(block_item, body)

    def _build_block_fields(self, block: Dict[str, Any], body: tk.Frame):
        b_type = block["type"]
        p = block["params"]
        vp = block["var_params"]

        if b_type == "tap_coord":
            vp["x"] = tk.IntVar(value=p.get("x", 960))
            vp["y"] = tk.IntVar(value=p.get("y", 540))
            vp["delay"] = tk.DoubleVar(value=p.get("delay", 1.5))
            vp["repeat"] = tk.IntVar(value=p.get("repeat", 1))

            row = tk.Frame(body, bg="#ffffff")
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text="座標 X:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=vp["x"], width=5).pack(side=tk.LEFT, padx=(1, 4))
            tk.Label(row, text="Y:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=vp["y"], width=5).pack(side=tk.LEFT, padx=(1, 4))
            btn_fill = ttk.Button(row, text="🎯填入", width=5, command=lambda target=block: self._fill_block_coords(target))
            btn_fill.pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(row, text="延遲:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row, from_=0.1, to=30.0, increment=0.5, textvariable=vp["delay"], width=4).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row, text="秒", bg="#ffffff").pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(row, text="點擊次數:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row, from_=1, to=50, increment=1, textvariable=vp["repeat"], width=3).pack(side=tk.LEFT, padx=(2, 0))

        elif b_type == "multi_tap":
            vp["x"] = tk.IntVar(value=_safe_int(p.get("x", 960)))
            vp["y"] = tk.IntVar(value=_safe_int(p.get("y", 540)))
            vp["count"] = tk.IntVar(value=_safe_int(p.get("count", 10)))
            vp["interval"] = tk.DoubleVar(value=_safe_float(p.get("interval", 0.3)))
            vp["stop_mode"] = tk.StringVar(value=p.get("stop_mode", "無 (僅點滿次數)"))
            vp["stop_keywords"] = tk.StringVar(value=p.get("stop_keywords", "確認, 確定, 完成, 上限"))
            vp["check_every"] = tk.IntVar(value=_safe_int(p.get("check_every", 1)))
            vp["delay_after"] = tk.DoubleVar(value=_safe_float(p.get("delay_after", 0.5)))

            row1 = tk.Frame(body, bg="#ffffff")
            row1.pack(fill=tk.X, pady=2)
            tk.Label(row1, text="座標 X:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(row1, textvariable=vp["x"], width=5).pack(side=tk.LEFT, padx=(1, 4))
            tk.Label(row1, text="Y:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(row1, textvariable=vp["y"], width=5).pack(side=tk.LEFT, padx=(1, 4))
            btn_fill = ttk.Button(row1, text="🎯填入", width=5, command=lambda target=block: self._fill_block_coords(target))
            btn_fill.pack(side=tk.LEFT, padx=(0, 10))

            tk.Label(row1, text="點擊次數:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row1, from_=0, to=9999, increment=5, textvariable=vp["count"], width=5).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row1, text="次 (0=無限)", bg="#ffffff").pack(side=tk.LEFT, padx=(0, 10))

            tk.Label(row1, text="間隔:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row1, from_=0.05, to=10.0, increment=0.1, textvariable=vp["interval"], width=4).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row1, text="秒/次", bg="#ffffff").pack(side=tk.LEFT)

            row2 = tk.Frame(body, bg="#ffffff")
            row2.pack(fill=tk.X, pady=2)
            tk.Label(row2, text="🛑 停止條件:", bg="#ffffff", font=("Arial", 9, "bold"), fg="#c2410c").pack(side=tk.LEFT)
            combo_stop = ttk.Combobox(row2, textvariable=vp["stop_mode"], values=[
                "無 (僅點滿次數)",
                "偵測到文字出現",
                "偵測到文字消失",
                "偵測到打勾圖案",
                "偵測到叉叉圖案"
            ], state="readonly", width=14)
            combo_stop.pack(side=tk.LEFT, padx=(2, 6))

            box_kws = tk.Frame(row2, bg="#ffffff")
            tk.Label(box_kws, text="關鍵字:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(box_kws, textvariable=vp["stop_keywords"], width=16).pack(side=tk.LEFT, padx=(2, 6))

            def _toggle_stop_kws(*_):
                sm = vp["stop_mode"].get()
                if "文字" in sm:
                    box_kws.pack(side=tk.LEFT)
                else:
                    box_kws.pack_forget()
            vp["stop_mode"].trace_add("write", _toggle_stop_kws)
            _toggle_stop_kws()

            tk.Label(row2, text="每:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row2, from_=1, to=20, increment=1, textvariable=vp["check_every"], width=3).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row2, text="次檢查", bg="#ffffff").pack(side=tk.LEFT, padx=(0, 8))

            tk.Label(row2, text="結束延遲:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row2, from_=0.0, to=30.0, increment=0.5, textvariable=vp["delay_after"], width=4).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row2, text="秒", bg="#ffffff").pack(side=tk.LEFT)

        elif b_type == "detect_click":
            vp["target_type"] = tk.StringVar(value=p.get("target_type", "📝 僅文字"))
            vp["keywords"] = tk.StringVar(value=p.get("keywords", "確認, 確定"))
            vp["timeout"] = tk.IntVar(value=p.get("timeout", 10))
            vp["click_mode"] = tk.StringVar(value=p.get("click_mode", "click_text"))
            vp["custom_x"] = tk.IntVar(value=p.get("custom_x", 960))
            vp["custom_y"] = tk.IntVar(value=p.get("custom_y", 540))
            vp["delay"] = tk.DoubleVar(value=p.get("delay", 1.5))
            vp["on_timeout"] = tk.StringVar(value=p.get("on_timeout", "continue"))

            row1 = tk.Frame(body, bg="#ffffff")
            row1.pack(fill=tk.X, pady=2)
            tk.Label(row1, text="類型:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Combobox(row1, textvariable=vp["target_type"], values=["📝 僅文字", "✓ 打勾圖案", "✕ 叉叉/關閉", "🔀 文字或圖案"], state="readonly", width=9).pack(side=tk.LEFT, padx=(2, 8))
            tk.Label(row1, text="關鍵字:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(row1, textvariable=vp["keywords"], width=20).pack(side=tk.LEFT, padx=(2, 8), fill=tk.X, expand=True)

            row2 = tk.Frame(body, bg="#ffffff")
            row2.pack(fill=tk.X, pady=2)
            tk.Label(row2, text="超時:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row2, from_=1, to=300, increment=1, textvariable=vp["timeout"], width=4).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row2, text="秒", bg="#ffffff").pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(row2, text="動作:", bg="#ffffff").pack(side=tk.LEFT)
            combo_act = ttk.Combobox(row2, textvariable=vp["click_mode"], values=["click_text", "custom_coord"], state="readonly", width=10)
            combo_act.pack(side=tk.LEFT, padx=(2, 8))

            box_xy = tk.Frame(row2, bg="#ffffff")
            tk.Label(box_xy, text="X:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(box_xy, textvariable=vp["custom_x"], width=5).pack(side=tk.LEFT, padx=(1, 4))
            tk.Label(box_xy, text="Y:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(box_xy, textvariable=vp["custom_y"], width=5).pack(side=tk.LEFT, padx=(1, 6))

            def _toggle_xy(*_):
                if vp["click_mode"].get() == "custom_coord":
                    box_xy.pack(side=tk.LEFT)
                else:
                    box_xy.pack_forget()
            vp["click_mode"].trace_add("write", _toggle_xy)
            _toggle_xy()

            tk.Label(row2, text="延遲:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row2, from_=0.1, to=30.0, increment=0.5, textvariable=vp["delay"], width=4).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row2, text="秒", bg="#ffffff").pack(side=tk.LEFT)

        elif b_type == "branch_if":
            branches_data = p.get("branches")
            if not branches_data:
                branches_data = []
                if p.get("cond_a_kws") or p.get("cond_a_x"):
                    branches_data.append({
                        "name": "If",
                        "keywords": p.get("cond_a_kws", "勝利, 挑戰成功"),
                        "x": _safe_int(p.get("cond_a_x", 1650)),
                        "y": _safe_int(p.get("cond_a_y", 950))
                    })
                if p.get("cond_b_kws") or p.get("cond_b_x"):
                    branches_data.append({
                        "name": "Else If",
                        "keywords": p.get("cond_b_kws", "失敗, 挑戰失敗"),
                        "x": _safe_int(p.get("cond_b_x", 960)),
                        "y": _safe_int(p.get("cond_b_y", 950))
                    })
                if not branches_data:
                    branches_data = [
                        {"name": "If", "keywords": "勝利, 挑戰成功", "x": 1650, "y": 950},
                        {"name": "Else If", "keywords": "失敗, 挑戰失敗", "x": 960, "y": 950}
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
                    "x": tk.IntVar(value=_safe_int(bd.get("x", 960))),
                    "y": tk.IntVar(value=_safe_int(bd.get("y", 540)))
                })

            # 頂部控制列：新增分支按鈕、超時、延遲
            row_ctrl = tk.Frame(body, bg="#ffffff")
            row_ctrl.pack(fill=tk.X, pady=(0, 4))
            tk.Label(row_ctrl, text="🔀 條件分支:", bg="#ffffff", font=("Arial", 9, "bold"), fg="#d97706").pack(side=tk.LEFT)

            btn_add_br = ttk.Button(row_ctrl, text="＋ 新增 Else If", command=lambda: _add_branch())
            btn_add_br.pack(side=tk.LEFT, padx=(6, 12))

            tk.Label(row_ctrl, text="限時:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row_ctrl, from_=1, to=120, textvariable=vp["timeout"], width=3).pack(side=tk.LEFT, padx=2)
            tk.Label(row_ctrl, text="s  延遲:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row_ctrl, from_=0.1, to=30.0, increment=0.5, textvariable=vp["delay"], width=4).pack(side=tk.LEFT, padx=2)
            tk.Label(row_ctrl, text="s", bg="#ffffff").pack(side=tk.LEFT)

            # 動態分支容器
            branches_box = tk.Frame(body, bg="#ffffff")
            branches_box.pack(fill=tk.X)

            def _render_branch_rows():
                for widget in branches_box.winfo_children():
                    widget.destroy()

                for idx, br in enumerate(vp["branches"]):
                    is_first = (idx == 0)
                    br["name"] = "If" if is_first else f"Else If {idx}"

                    row = tk.Frame(branches_box, bg="#f8fafc", bd=1, relief=tk.SOLID)
                    row.pack(fill=tk.X, pady=2, ipady=1)

                    badge_bg = "#d97706" if is_first else "#0284c7"
                    lbl_badge = tk.Label(row, text=f" {br['name']} ", bg=badge_bg, fg="#ffffff", font=("Arial", 8, "bold"), width=9)
                    lbl_badge.pack(side=tk.LEFT, padx=(2, 6))

                    tk.Label(row, text="若包含:", bg="#f8fafc").pack(side=tk.LEFT)
                    ttk.Entry(row, textvariable=br["keywords"], width=15).pack(side=tk.LEFT, padx=(2, 6))

                    tk.Label(row, text="➜ 點擊 X:", bg="#f8fafc").pack(side=tk.LEFT)
                    ttk.Entry(row, textvariable=br["x"], width=5).pack(side=tk.LEFT, padx=1)
                    tk.Label(row, text="Y:", bg="#f8fafc").pack(side=tk.LEFT)
                    ttk.Entry(row, textvariable=br["y"], width=5).pack(side=tk.LEFT, padx=(1, 4))

                    btn_fill = ttk.Button(row, text="🎯填入", width=5, command=lambda target=br: self._fill_branch_from_picker(target))
                    btn_fill.pack(side=tk.LEFT, padx=2)

                    if not is_first:
                        lbl_del = tk.Label(row, text=" ✕ ", bg="#f8fafc", fg="#dc2626", font=("Arial", 9, "bold"), cursor="hand2")
                        lbl_del.pack(side=tk.RIGHT, padx=4)
                        lbl_del.bind("<Button-1>", lambda e, target_idx=idx: _remove_branch(target_idx))

            def _add_branch():
                new_idx = len(vp["branches"])
                vp["branches"].append({
                    "name": f"Else If {new_idx}",
                    "keywords": tk.StringVar(value=""),
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

            # 底部 Else 行
            row_else = tk.Frame(body, bg="#f8fafc", bd=1, relief=tk.SOLID)
            row_else.pack(fill=tk.X, pady=(3, 0), ipady=1)

            lbl_else_badge = tk.Label(row_else, text=" Else ", bg="#64748b", fg="#ffffff", font=("Arial", 8, "bold"), width=9)
            lbl_else_badge.pack(side=tk.LEFT, padx=(2, 6))

            tk.Label(row_else, text="若皆不符合:", bg="#f8fafc").pack(side=tk.LEFT)
            combo_else = ttk.Combobox(row_else, textvariable=vp["else_action"], values=["skip", "click_coord"], state="readonly", width=9)
            combo_else.pack(side=tk.LEFT, padx=(2, 6))

            box_else_xy = tk.Frame(row_else, bg="#f8fafc")
            tk.Label(box_else_xy, text="X:", bg="#f8fafc").pack(side=tk.LEFT)
            ttk.Entry(box_else_xy, textvariable=vp["else_x"], width=5).pack(side=tk.LEFT, padx=1)
            tk.Label(box_else_xy, text="Y:", bg="#f8fafc").pack(side=tk.LEFT)
            ttk.Entry(box_else_xy, textvariable=vp["else_y"], width=5).pack(side=tk.LEFT, padx=(1, 4))
            btn_fill_else = ttk.Button(box_else_xy, text="🎯填入", width=5, command=lambda: self.on_fill_branch_coord("else"))
            btn_fill_else.pack(side=tk.LEFT, padx=2)

            def _toggle_else(*_):
                if vp["else_action"].get() == "click_coord":
                    box_else_xy.pack(side=tk.LEFT)
                else:
                    box_else_xy.pack_forget()
            vp["else_action"].trace_add("write", _toggle_else)
            _toggle_else()

        elif b_type == "loop":
            vp["stop_mode"] = tk.StringVar(value=p.get("stop_mode", "依指定次數"))
            vp["count"] = tk.IntVar(value=_safe_int(p.get("count", 3)))
            vp["keywords"] = tk.StringVar(value=p.get("keywords", p.get("stop_keywords", "")))
            vp["check_timing"] = tk.StringVar(value=p.get("check_timing", "每輪開始與結束"))
            vp["delay_after"] = tk.DoubleVar(value=_safe_float(p.get("delay_after", 0.5)))

            # 迴圈控制頂部容器
            box_loop_header = tk.Frame(body, bg="#ffffff")
            box_loop_header.pack(fill=tk.X, pady=(0, 4))

            # 第 1 列：停止條件與次數/延遲
            row_loop_ctrl = tk.Frame(box_loop_header, bg="#ffffff")
            row_loop_ctrl.pack(fill=tk.X, pady=(0, 2))

            tk.Label(row_loop_ctrl, text="🔁 停止條件:", bg="#ffffff", font=("Arial", 9, "bold"), fg="#4f46e5").pack(side=tk.LEFT)
            LOOP_MODES = [
                "依指定次數",
                "偵測到文字出現",
                "偵測到文字消失",
                "偵測到打勾圖案",
                "偵測到叉叉圖案"
            ]
            cbo_mode = ttk.Combobox(row_loop_ctrl, textvariable=vp["stop_mode"], values=LOOP_MODES, state="readonly", width=14)
            cbo_mode.pack(side=tk.LEFT, padx=3)

            lbl_cnt_title = tk.Label(row_loop_ctrl, text="次數:", bg="#ffffff", font=("Arial", 9))
            lbl_cnt_title.pack(side=tk.LEFT, padx=(4, 2))
            spn_cnt = ttk.Spinbox(row_loop_ctrl, from_=0, to=999, textvariable=vp["count"], width=4)
            spn_cnt.pack(side=tk.LEFT)
            lbl_cnt_hint = tk.Label(row_loop_ctrl, text="次 (0=無限)", bg="#ffffff", font=("Arial", 8), fg="#64748b")
            lbl_cnt_hint.pack(side=tk.LEFT, padx=(2, 6))

            tk.Label(row_loop_ctrl, text="延遲:", bg="#ffffff", font=("Arial", 8), fg="#475569").pack(side=tk.LEFT, padx=(2, 1))
            ttk.Spinbox(row_loop_ctrl, from_=0.0, to=60.0, increment=0.5, textvariable=vp["delay_after"], width=4).pack(side=tk.LEFT)
            tk.Label(row_loop_ctrl, text="s", bg="#ffffff", font=("Arial", 8), fg="#64748b").pack(side=tk.LEFT)

            # 第 2 列：條件細節 (關鍵字與檢查時機，在條件模式下展開)
            row_cond_detail = tk.Frame(box_loop_header, bg="#ffffff")

            lbl_kw_title = tk.Label(row_cond_detail, text="🔍 停止關鍵字:", bg="#ffffff", font=("Arial", 8, "bold"), fg="#334155")
            lbl_kw_title.pack(side=tk.LEFT)
            ent_kw = ttk.Entry(row_cond_detail, textvariable=vp["keywords"], width=18)
            ent_kw.pack(side=tk.LEFT, padx=(2, 6))

            tk.Label(row_cond_detail, text="檢查時機:", bg="#ffffff", font=("Arial", 8), fg="#334155").pack(side=tk.LEFT)
            TIMINGS = [
                "每輪開始與結束",
                "每輪開始前 (While)",
                "每輪結束後 (Do-While)",
                "每個子步驟後"
            ]
            cbo_timing = ttk.Combobox(row_cond_detail, textvariable=vp["check_timing"], values=TIMINGS, state="readonly", width=14)
            cbo_timing.pack(side=tk.LEFT, padx=2)

            def _on_loop_mode_change(*_):
                mode = vp["stop_mode"].get()
                if mode == "依指定次數":
                    row_cond_detail.pack_forget()
                    lbl_cnt_title.config(text="重複次數:")
                    lbl_cnt_hint.config(text="次 (0=無限)")
                else:
                    row_cond_detail.pack(fill=tk.X, pady=(2, 2))
                    lbl_cnt_title.config(text="上限次數:")
                    lbl_cnt_hint.config(text="次 (0=不限)")
                    if "符號" in mode or "圖案" in mode or "打勾" in mode or "叉叉" in mode:
                        ent_kw.config(state="disabled")
                    else:
                        ent_kw.config(state="normal")

            vp["stop_mode"].trace_add("write", _on_loop_mode_change)
            _on_loop_mode_change()

            # 裝入積木工具列
            tb_inner = tk.Frame(body, bg="#f1f5f9", bd=1, relief=tk.SOLID)
            tb_inner.pack(fill=tk.X, pady=(2, 4), ipady=2)

            tk.Label(tb_inner, text="➕ 裝入新積木:", bg="#f1f5f9", font=("Arial", 8, "bold"), fg="#334155").pack(side=tk.LEFT, padx=(4, 4))

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
            combo_type = ttk.Combobox(tb_inner, textvariable=var_sel_type, values=list(TYPE_LABELS.values()), state="readonly", width=12)
            combo_type.pack(side=tk.LEFT, padx=2)

            btn_add_in = ttk.Button(tb_inner, text="裝入", width=5, command=lambda target_loop=block, v_type=var_sel_type: self.add_inner_block(target_loop, LABEL_TO_TYPE.get(v_type.get(), "tap_coord")))
            btn_add_in.pack(side=tk.LEFT, padx=2)

            btn_pull = ttk.Button(tb_inner, text="📥 將上方積木移入", command=lambda target_loop=block: self.pull_prev_block_into_loop(target_loop))
            btn_pull.pack(side=tk.RIGHT, padx=4)

            # 內部積木容器 (C-Block 槽位，具備左側縮排與底色)
            inner_box = tk.Frame(body, bg="#e0e7ff", bd=1, relief=tk.GROOVE)
            inner_box.pack(fill=tk.X, padx=(10, 0), pady=(2, 4))
            block["inner_container"] = inner_box

            # 迴圈底座結尾
            lbl_end = tk.Label(body, text="⮑ 迴圈結束 (依條件滿足或達到次數後進入下一步)", bg="#ffffff", fg="#6366f1", font=("Arial", 8, "bold"))
            lbl_end.pack(anchor="w", padx=2, pady=(2, 0))

        elif b_type == "wait_condition":
            vp["cond_mode"] = tk.StringVar(value=p.get("cond_mode", "出現 (Wait Appear)"))
            vp["target_type"] = tk.StringVar(value=p.get("target_type", "📝 僅文字"))
            vp["keywords"] = tk.StringVar(value=p.get("keywords", "確認, 確定"))
            vp["interval"] = tk.DoubleVar(value=_safe_float(p.get("interval", 1.0)))
            vp["timeout"] = tk.IntVar(value=_safe_int(p.get("timeout", 30)))
            vp["delay_after"] = tk.DoubleVar(value=_safe_float(p.get("delay_after", 0.5)))
            vp["on_timeout"] = tk.StringVar(value=p.get("on_timeout", "continue"))

            row1 = tk.Frame(body, bg="#ffffff")
            row1.pack(fill=tk.X, pady=2)
            tk.Label(row1, text="條件:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Combobox(row1, textvariable=vp["cond_mode"], values=["出現 (Wait Appear)", "消失 (Wait Disappear)"], state="readonly", width=16).pack(side=tk.LEFT, padx=(2, 8))
            tk.Label(row1, text="類型:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Combobox(row1, textvariable=vp["target_type"], values=["📝 僅文字", "✓ 打勾圖案", "✕ 叉叉/關閉", "🔀 文字或圖案"], state="readonly", width=9).pack(side=tk.LEFT, padx=(2, 8))
            tk.Label(row1, text="關鍵字:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(row1, textvariable=vp["keywords"], width=20).pack(side=tk.LEFT, padx=(2, 4), fill=tk.X, expand=True)

            row2 = tk.Frame(body, bg="#ffffff")
            row2.pack(fill=tk.X, pady=2)
            tk.Label(row2, text="更新頻率:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row2, from_=0.1, to=30.0, increment=0.5, textvariable=vp["interval"], width=4).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row2, text="秒/次", bg="#ffffff").pack(side=tk.LEFT, padx=(0, 10))

            tk.Label(row2, text="最長限時:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row2, from_=1, to=600, increment=5, textvariable=vp["timeout"], width=4).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row2, text="秒", bg="#ffffff").pack(side=tk.LEFT, padx=(0, 10))

            tk.Label(row2, text="達成後延遲:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row2, from_=0.0, to=30.0, increment=0.5, textvariable=vp["delay_after"], width=4).pack(side=tk.LEFT, padx=(2, 2))
            tk.Label(row2, text="秒", bg="#ffffff").pack(side=tk.LEFT, padx=(0, 10))

            tk.Label(row2, text="超時:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Combobox(row2, textvariable=vp["on_timeout"], values=["continue", "stop"], state="readonly", width=8).pack(side=tk.LEFT, padx=(2, 0))

        elif b_type == "wait_sec":
            vp["seconds"] = tk.DoubleVar(value=p.get("seconds", 3.0))
            row = tk.Frame(body, bg="#ffffff")
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text="等待秒數:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row, from_=0.1, to=300.0, increment=0.5, textvariable=vp["seconds"], width=5).pack(side=tk.LEFT, padx=(4, 2))
            tk.Label(row, text="秒", bg="#ffffff").pack(side=tk.LEFT)

        elif b_type == "swipe":
            vp["x1"] = tk.IntVar(value=p.get("x1", 1500))
            vp["y1"] = tk.IntVar(value=p.get("y1", 540))
            vp["x2"] = tk.IntVar(value=p.get("x2", 400))
            vp["y2"] = tk.IntVar(value=p.get("y2", 540))
            vp["duration_ms"] = tk.IntVar(value=p.get("duration_ms", 400))
            vp["delay"] = tk.DoubleVar(value=p.get("delay", 1.0))

            row = tk.Frame(body, bg="#ffffff")
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text="起點 (X,Y):", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=vp["x1"], width=5).pack(side=tk.LEFT, padx=1)
            ttk.Entry(row, textvariable=vp["y1"], width=5).pack(side=tk.LEFT, padx=(1, 6))
            tk.Label(row, text="終點 (X,Y):", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=vp["x2"], width=5).pack(side=tk.LEFT, padx=1)
            ttk.Entry(row, textvariable=vp["y2"], width=5).pack(side=tk.LEFT, padx=(1, 6))
            tk.Label(row, text="耗時:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row, from_=100, to=3000, increment=100, textvariable=vp["duration_ms"], width=4).pack(side=tk.LEFT, padx=1)
            tk.Label(row, text="ms", bg="#ffffff").pack(side=tk.LEFT)

        elif b_type == "back_key":
            vp["delay"] = tk.DoubleVar(value=p.get("delay", 1.2))
            row = tk.Frame(body, bg="#ffffff")
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text="模擬 Android 返回鍵 (input keyevent 4)，點擊後延遲:", bg="#ffffff").pack(side=tk.LEFT)
            ttk.Spinbox(row, from_=0.1, to=30.0, increment=0.2, textvariable=vp["delay"], width=4).pack(side=tk.LEFT, padx=(4, 2))
            tk.Label(row, text="秒", bg="#ffffff").pack(side=tk.LEFT)

        elif b_type == "comment":
            vp["note"] = tk.StringVar(value=p.get("note", "此處為備註說明文字，執行時不執行任何操作"))
            row = tk.Frame(body, bg="#fffbeb", bd=1, relief=tk.SOLID)
            row.pack(fill=tk.X, pady=2, ipady=3)
            tk.Label(row, text="📝 備註內容:", bg="#fffbeb", font=("Arial", 9, "bold"), fg="#92400e").pack(side=tk.LEFT, padx=(6, 4))
            ent_note = ttk.Entry(row, textvariable=vp["note"], font=("Microsoft JhengHei", 9))
            ent_note.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
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

            # 第 1 列：通知訊息內容與截圖核取方塊
            row1 = tk.Frame(body, bg="#ffffff")
            row1.pack(fill=tk.X, pady=2)
            tk.Label(row1, text="訊息:", bg="#ffffff", font=("Arial", 9, "bold"), fg="#0284c7").pack(side=tk.LEFT)
            ttk.Entry(row1, textvariable=vp["message"], width=24).pack(side=tk.LEFT, padx=(4, 8), fill=tk.X, expand=True)
            ttk.Checkbutton(row1, text="📸 附帶截圖", variable=vp["attach_screenshot"]).pack(side=tk.LEFT, padx=(0, 6))

            # 第 2 列：設定自訂切換、延遲與測試發送按鈕
            row2 = tk.Frame(body, bg="#ffffff")
            row2.pack(fill=tk.X, pady=2)

            ttk.Checkbutton(row2, text="⚙️ 自訂獨立 Token / Chat ID", variable=vp["use_custom"]).pack(side=tk.LEFT)

            btn_test = ttk.Button(row2, text="📨 測試發送", width=9, command=lambda target_b=block: self._test_block_telegram(target_b))
            btn_test.pack(side=tk.RIGHT, padx=2)

            tk.Label(row2, text="延遲:", bg="#ffffff").pack(side=tk.RIGHT)
            ttk.Spinbox(row2, from_=0.0, to=30.0, increment=0.5, textvariable=vp["delay_after"], width=4).pack(side=tk.RIGHT, padx=(2, 4))
            tk.Label(row2, text="秒", bg="#ffffff").pack(side=tk.RIGHT)

            # 自訂 Token / Chat ID 摺疊區
            box_custom = tk.Frame(body, bg="#f0f9ff", bd=1, relief=tk.SOLID)

            row_c1 = tk.Frame(box_custom, bg="#f0f9ff")
            row_c1.pack(fill=tk.X, padx=4, pady=2)
            tk.Label(row_c1, text="Bot Token:", bg="#f0f9ff", font=("Arial", 8)).pack(side=tk.LEFT)
            ttk.Entry(row_c1, textvariable=vp["custom_token"], width=28).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

            row_c2 = tk.Frame(box_custom, bg="#f0f9ff")
            row_c2.pack(fill=tk.X, padx=4, pady=2)
            tk.Label(row_c2, text="Chat ID:   ", bg="#f0f9ff", font=("Arial", 8)).pack(side=tk.LEFT)
            ttk.Entry(row_c2, textvariable=vp["custom_chat_id"], width=18).pack(side=tk.LEFT, padx=(4, 0))
            tk.Label(row_c2, text="(未勾選或留空時自動套用通用進階設定)", bg="#f0f9ff", font=("Arial", 8), fg="#64748b").pack(side=tk.LEFT, padx=6)

            def _toggle_custom(*_):
                if vp["use_custom"].get():
                    box_custom.pack(fill=tk.X, pady=(2, 2))
                else:
                    box_custom.pack_forget()

            vp["use_custom"].trace_add("write", _toggle_custom)
            _toggle_custom()

    def _bind_drag(self, handle, block_item):
        """跨平台滑鼠拖曳換位"""
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
            b["frame"].pack(fill=tk.X, padx=4, pady=3)
            b["lbl_num"].config(text=f"#{i}")
            if b["type"] == "loop":
                in_list = b.get("inner_blocks_list", [])
                for j, cb in enumerate(in_list, start=1):
                    cb["frame"].pack_forget()
                    cb["frame"].pack(fill=tk.X, padx=2, pady=2)
                    cb["lbl_num"].config(text=f"#{i}.{j}")
        self.canvas_blocks.update_idletasks()

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
        """測試指定積木的 Telegram 發送"""
        vp = block.get("var_params", {})
        custom_tok = vp.get("custom_token").get().strip() if "custom_token" in vp else ""
        custom_cid = vp.get("custom_chat_id").get().strip() if "custom_chat_id" in vp else ""
        use_custom = vp.get("use_custom").get() if "use_custom" in vp else False

        tok = (custom_tok if use_custom else "") or self.var_tg_token.get().strip()
        cid = (custom_cid if use_custom else "") or self.var_tg_chat_id.get().strip()

        if not tok or not cid:
            messagebox.showwarning("提示", "尚未設定 Telegram Bot Token 與 Chat ID！\n請在「⚙ 通用進階」填寫，或在此積木勾選自訂。")
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
        """直接將截圖吸取的座標填入指定積木的 (x, y) 變數中"""
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
        if "x" in vp and "y" in vp:
            vp["x"].set(x)
            vp["y"].set(y)
            b_name = target_block["name"].get() if hasattr(target_block.get("name"), "get") else "積木"
            self._log(f"已將座標 ({x}, {y}) 填入 [{b_name}]")
            self.auto_save_config()

    def select_block(self, block_item: Dict[str, Any]):
        """將該積木標記為選取目標，以便將截圖吸取的座標填入"""
        self.selected_block_target = block_item
        self._update_all_selection_highlights()
        b_name = block_item["name"].get() if hasattr(block_item.get("name"), "get") else "積木"
        self._log(f"已選取目標積木 [{b_name}]")

    def _update_all_selection_highlights(self):
        target = getattr(self, "selected_block_target", None)
        for b in self.blocks_list:
            if b.get("frame"):
                b["frame"].config(bd=2, relief=tk.RIDGE if b is target else tk.SOLID)
            for cb in b.get("inner_blocks_list", []):
                if cb.get("frame"):
                    cb["frame"].config(bd=2, relief=tk.RIDGE if cb is target else tk.SOLID)

    def highlight_active_step(self, active_idx: int):
        """執行時光環高亮目前積木"""
        def _ui_update():
            for i, b in enumerate(self.blocks_list):
                if i == active_idx:
                    b["frame"].config(bg="#fef08a", bd=3)
                    b["lbl_num"].config(bg=COLOR_BLOCK_ACTIVE)
                else:
                    b["frame"].config(bg=COLOR_BLOCK_BG, bd=1)
                    info = BLOCK_TYPES.get(b["type"], BLOCK_TYPES["tap_coord"])
                    b["lbl_num"].config(bg=info["color"])
        self.parent.after(0, _ui_update)

    # -------------------------------------------------------------------------
    # 座標吸管與截圖預覽 (Coordinate Picker)
    # -------------------------------------------------------------------------
    def on_capture_screen(self):
        """背景擷取畫面，完全照抄聯賽自動刷關的 _capture_async 邏輯"""
        if not self.bot or not self.bot.device:
            # 嘗試向父層 GUI 取得連線
            if self.gui and hasattr(self.gui, "bot") and self.gui.bot and self.gui.bot.device:
                self.bot = self.gui.bot
            elif not self.bot or not self.bot.connect():
                # 檢查父層是否有已擷取的畫面
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
        self.btn_capture.config(state=tk.DISABLED)

        def work():
            screen = None
            err = None
            try:
                screen = self.bot.capture_screen()
            except Exception as e:
                err = e

            def done():
                self._capturing = False
                self.btn_capture.config(state=tk.NORMAL)
                if screen is not None:
                    self.current_screen_bgr = screen
                    self._render_preview(screen)
                    self._log("📸 畫面擷取成功！點擊畫面任意位置即可選取座標。")
                else:
                    # 備援：若本次擷取失敗但主頁面有快取畫面，嘗試使用
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
        """由外部 (如聯賽背景執行緒或自動刷新) 直接推播最新畫面，零延遲同步"""
        if screen_bgr is None:
            return
        self.current_screen_bgr = screen_bgr
        self._render_preview(screen_bgr)

    def _render_preview(self, screen_bgr: np.ndarray):
        """手動截圖與改範圍專用預覽渲染 (完全照抄 gui.py _render_preview 邏輯)"""
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

            # 若有選取的座標，在畫面上繪製醒目的十字準心與圓圈
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
        """計算視窗滑鼠座標對應回遊戲實際原始解析度座標 (完全照抄 gui.py _preview_to_real 邏輯)"""
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
        """直接將截圖吸取的座標填入指定的分支資料字典"""
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

    # -------------------------------------------------------------------------
    # 執行控制 (Run, Step, Stop)
    # -------------------------------------------------------------------------
    def on_run_tasks(self):
        if not self.blocks_list:
            messagebox.showinfo("提示", "程式區目前沒有任何積木，請先從左側加入積木！")
            return

        if self.bot and self.bot.is_running:
            messagebox.showwarning("提示", "【聯賽自動刷關】正在執行中，請先停止聯賽腳本再啟動任務清單。")
            return

        active_blocks = self._serialize_all_blocks()
        loop_cnt = max(0, self.var_loop_count.get())

        self.btn_run.config(state=tk.DISABLED)
        self.btn_step.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
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
                self.btn_run.config(state=tk.NORMAL)
                self.btn_step.config(state=tk.NORMAL)
                self.btn_stop.config(state=tk.DISABLED)
                self.highlight_active_step(-1)
                st_icon = "🟢" if success else "⚠️"
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
        """單步執行目前選中的積木"""
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
        self.var_status_text.set("🔴 正在停止...")

    # -------------------------------------------------------------------------
    # 序列化與範本/設定檔存取 (JSON)
    # -------------------------------------------------------------------------
    def _serialize_single_block(self, b: Dict[str, Any]) -> Dict[str, Any]:
        p = {}
        for k, v in b["var_params"].items():
            if k == "branches" and isinstance(v, list):
                p["branches"] = [
                    {
                        "name": br.get("name", "If"),
                        "keywords": br["keywords"].get() if hasattr(br.get("keywords"), "get") else br.get("keywords", ""),
                        "x": br["x"].get() if hasattr(br.get("x"), "get") else br.get("x", 0),
                        "y": br["y"].get() if hasattr(br.get("y"), "get") else br.get("y", 0)
                    }
                    for br in v
                ]
            elif hasattr(v, "get"):
                p[k] = v.get()
            else:
                p[k] = v

        if b["type"] == "loop":
            inner_list = b.get("inner_blocks_list", [])
            p["inner_blocks"] = [self._serialize_single_block(sb) for sb in inner_list]

        return {
            "type": b["type"],
            "name": b["name"].get() if hasattr(b["name"], "get") else b["name"],
            "enabled": b["enabled"].get() if hasattr(b["enabled"], "get") else b["enabled"],
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
        preset = DAILY_PRESETS.get(preset_key)
        if not preset:
            return
        if self.blocks_list and not messagebox.askyesno("載入範本", f"載入「{preset['title']}」將取代目前積木清單，是否繼續？"):
            return

        for b in self.blocks_list:
            for cb in b.get("inner_blocks_list", []):
                if cb.get("frame"):
                    cb["frame"].destroy()
            if b.get("frame"):
                b["frame"].destroy()
        self.blocks_list.clear()

        for bd in preset["blocks"]:
            self.add_block(
                b_type=bd["type"],
                params=dict(bd.get("params", {})),
                name=bd.get("name", ""),
                enabled=bd.get("enabled", True)
            )
        self._log(f"已成功載入範本: {preset['title']}")

    def auto_save_config(self):
        try:
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
        except Exception:
            pass

    def load_config_auto(self):
        if not os.path.exists(self.save_file):
            # 預設載入日常範本
            self.load_preset("daily_mailbox")
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

    def on_save_config_dialog(self):
        path = filedialog.asksaveasfilename(
            initialdir=self.config_dir,
            title="儲存任務清單",
            defaultextension=".json",
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
        )
        if not path:
            return
        try:
            data = {
                "version": "1.0",
                "loop_count": self.var_loop_count.get(),
                "global_settings": self.get_global_settings(),
                "blocks": self._serialize_all_blocks()
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"任務清單已儲存至:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("錯誤", f"存檔失敗: {e}")

    def on_load_config_dialog(self):
        path = filedialog.askopenfilename(
            initialdir=self.config_dir,
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
