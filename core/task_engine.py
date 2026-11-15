"""
任務流程引擎 (TaskEngine) 與積木定義。

積木式的任務流程：點擊座標、連續點擊、偵測文字或圖片並點擊、條件分支、
迴圈、等待條件、等待秒數、滑動、返回鍵、備註、Telegram 通知，
並支援優先辨識步驟與多輪循環。
"""
import os
import time
import random
import threading
from typing import Optional, Dict, Any, List, Callable, Tuple

import cv2
import numpy as np

from core import notify, storage
from core.bot import is_check_mark, is_cross_mark
from core.textutil import safe_float as _safe_float, safe_int as _safe_int

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
            "target_type": "僅文字",
            "keywords": "確認, 確定",
            "template_image": "",
            "image_threshold": 0.80,
            "image_multiscale": False,
            "timeout": 10,
            "click_mode": "點擊目標中心",
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
            "stop_conditions": [],
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
            "target_type": "僅文字",
            "keywords": "確認, 確定",
            "template_image": "",
            "image_threshold": 0.80,
            "image_multiscale": False,
            "interval": 1.0,
            "timeout": 30,
            "click_mode": "點擊目標中心",
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

        self.priority_blocks: List[Dict[str, Any]] = []
        self.on_priority_hit: Optional[Callable[[int], None]] = None

        self.current_block_idx = -1
        self.current_cycle = 0
        self.total_cycles = 1
        self.active_candidates: List[Dict[str, Any]] = []

    def _get_scan_interval(self) -> float:
        """取得掃描/刷新間隔 (秒)，吃到循序腳本的快速刷設定 (0=極速無延遲)"""
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

    @staticmethod
    def parse_template_images_list(val: Any) -> List[str]:
        """
        將設定值解析為圖片路徑/檔名列表，支援字串逗號/分號/換行分隔或原本就為 list
        例: "img1.png, img2.png" -> ["img1.png", "img2.png"]
        """
        if not val:
            return []
        if isinstance(val, (list, tuple)):
            res = []
            for item in val:
                s = str(item).strip().strip('"').strip("'").strip()
                if s:
                    res.append(s)
            return res
        s_val = str(val).strip()
        if not s_val:
            return []
        normalized = s_val.replace("，", ",").replace(";", ",").replace("；", ",").replace("\n", ",")
        parts = [p.strip().strip('"').strip("'").strip() for p in normalized.split(",") if p.strip()]
        return [p for p in parts if p]

    def resolve_image_path(self, p: str) -> Optional[str]:
        """解析圖片模板路徑（絕對路徑，或相對於存檔資料夾／專案資料夾）。"""
        if not p:
            return None
        p = str(p).strip().strip('"').strip("'").strip()
        if not p:
            return None
        search_dirs: List[str] = []
        for k in ("presets_dir", "storage_dir", "task_presets_dir", "templates_dir", "config_dir"):
            d = self.global_settings.get(k)
            if d and os.path.isdir(d) and d not in search_dirs:
                search_dirs.append(d)
        if self.bot:
            for attr in ("storage_dir", "task_presets_dir", "templates_dir", "config_dir"):
                d = getattr(self.bot, attr, None)
                if d and os.path.isdir(d) and d not in search_dirs:
                    search_dirs.append(d)
        return storage.resolve_image_path(p, search_dirs)

    def start(
        self,
        blocks_data: List[Dict[str, Any]],
        priority_blocks_data: Optional[List[Dict[str, Any]]] = None,
        loop_count: int = 1,
        on_step_change: Optional[Callable[[int, int, int], None]] = None,
        on_finish: Optional[Callable[[bool, str], None]] = None,
        global_settings: Optional[Dict[str, Any]] = None,
        on_priority_hit: Optional[Callable[[int], None]] = None
    ):
        if self.is_running:
            return

        if global_settings:
            self.global_settings.update(global_settings)

        self.priority_blocks = [b for b in (priority_blocks_data or []) if b.get("enabled", True)]
        self.on_priority_hit = on_priority_hit

        # 套用語言過濾設定至 bot
        if self.bot and hasattr(self.bot, "set_allowed_languages"):
            self.bot.set_allowed_languages(
                allow_tc=bool(self.global_settings.get("lang_tc", True)),
                allow_sc=bool(self.global_settings.get("lang_sc", False)),
                allow_en=bool(self.global_settings.get("lang_en", True))
            )

        if not self.bot or not self.bot.device:
            if not self.bot.connect():
                self._log("無法執行：尚未連線到模擬器裝置！")
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
                    self._log(f"開始執行第 {cycle}/{self.total_cycles if self.total_cycles > 0 else '∞'} 輪任務...")

                    for idx, block in enumerate(blocks_data):
                        if self._stop_event.is_set():
                            break
                        if not block.get("enabled", True):
                            continue

                        # 優先辨識檢查：比照循序腳本，在執行此步驟前，先檢查是否有優先動作需要攔截執行
                        prio_hits = 0
                        while self._check_and_exec_priority(f"步驟 #{idx + 1} 前"):
                            prio_hits += 1
                            if self._stop_event.is_set() or prio_hits >= 10:
                                break
                            time.sleep(0.3)

                        if self._stop_event.is_set():
                            break

                        self.current_block_idx = idx
                        if on_step_change:
                            on_step_change(idx, cycle, self.total_cycles)

                        b_name = block.get("name", "未命名步驟")
                        b_type = block.get("type", "tap_coord")
                        params = block.get("params", {})

                        next_candidates = self._build_next_candidates(
                            current_idx=idx,
                            blocks=blocks_data,
                            is_loop=False,
                            cycle=cycle,
                            total_cycles=self.total_cycles
                        )

                        self._log(f"步驟 #{idx + 1} [{b_name}] ({BLOCK_TYPES.get(b_type, {}).get('title', b_type)})")
                        step_ok = self.execute_block(b_type, params, next_candidates=next_candidates)

                        if not step_ok and params.get("on_timeout") == "stop":
                            self._log(f"步驟 #{idx + 1} 觸發超時終止設定，任務停止。")
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
                self._log(f"執行異常: {e}")
                success = False
                msg = str(e)
            finally:
                self.is_running = False
                self.current_block_idx = -1
                if on_step_change:
                    on_step_change(-1, self.current_cycle, self.total_cycles)
                self._log("任務清單已停止。")
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
        priority_blocks_data: Optional[List[Dict[str, Any]]] = None,
        loop_count: int = 1,
        on_step_change: Optional[Callable[[int, int, int], None]] = None,
        global_settings: Optional[Dict[str, Any]] = None,
        on_priority_hit: Optional[Callable[[int], None]] = None
    ) -> bool:
        """
        同步執行任務清單 (專供循序腳本事件跳轉或單步呼叫使用，執行完成後回傳)
        """
        if global_settings:
            self.global_settings.update(global_settings)

        self.priority_blocks = [b for b in (priority_blocks_data or []) if b.get("enabled", True)]
        self.on_priority_hit = on_priority_hit

        if self.bot and hasattr(self.bot, "set_allowed_languages"):
            self.bot.set_allowed_languages(
                allow_tc=bool(self.global_settings.get("lang_tc", True)),
                allow_sc=bool(self.global_settings.get("lang_sc", False)),
                allow_en=bool(self.global_settings.get("lang_en", True))
            )

        if not self.bot or not self.bot.device:
            if not self.bot or not self.bot.connect():
                self._log("無法執行任務清單：尚未連線至模擬器裝置！")
                return False

        self._stop_event.clear()
        self.is_running = True
        success = True
        total = loop_count

        try:
            for cycle in range(1, total + 1):
                if self._stop_event.is_set():
                    break
                self._log(f"[任務跳轉] 開始執行第 {cycle}/{total} 輪 (共 {len(blocks_data)} 個步驟)...")

                for idx, block in enumerate(blocks_data):
                    if self._stop_event.is_set():
                        break
                    if not block.get("enabled", True):
                        continue

                    # 優先動作檢查
                    prio_hits = 0
                    while self._check_and_exec_priority(f"步驟 #{idx + 1} 前"):
                        prio_hits += 1
                        if self._stop_event.is_set() or prio_hits >= 10:
                            break
                        time.sleep(0.3)

                    if self._stop_event.is_set():
                        break

                    self.current_block_idx = idx
                    if on_step_change:
                        on_step_change(idx, cycle, total)

                    b_name = block.get("name", "未命名步驟")
                    b_type = block.get("type", "tap_coord")
                    params = block.get("params", {})

                    next_candidates = self._build_next_candidates(
                        current_idx=idx,
                        blocks=blocks_data,
                        is_loop=False,
                        cycle=cycle,
                        total_cycles=total
                    )

                    self._log(f"步驟 #{idx + 1} [{b_name}] ({BLOCK_TYPES.get(b_type, {}).get('title', b_type)})")
                    step_ok = self.execute_block(b_type, params, next_candidates=next_candidates)

                    if not step_ok and params.get("on_timeout") == "stop":
                        self._log(f"步驟 #{idx + 1} 觸發超時終止設定，任務停止。")
                        success = False
                        self._stop_event.set()
                        break

                if self._stop_event.is_set():
                    break
                if cycle < total:
                    time.sleep(0.5)

        except Exception as e:
            self._log(f"任務跳轉執行異常: {e}")
            success = False
        finally:
            self.is_running = False
            self.current_block_idx = -1
            if on_step_change:
                on_step_change(-1, 0, 0)

        return success

    def _check_priority_on_frame(
        self,
        screen: Optional[np.ndarray] = None,
        screen_gray: Optional[np.ndarray] = None,
        det_results: Optional[List[Dict[str, Any]]] = None,
        context_desc: str = ""
    ) -> Tuple[bool, Optional[np.ndarray], Optional[List[Dict[str, Any]]]]:
        """
        在指定畫面幀 (或即時截圖) 上檢查優先辨識步驟：
        比照循序腳本，優先級嚴格大於一般流程的每一個步驟。
        遍歷 priority_blocks，若有任何優先積木命中 (圖片模板、符號、或文字 OCR)，
        立即插隊執行對應點擊或連點跳過過場，並記錄日誌。
        回傳 (hit: bool, screen_gray, det_results)，方便後續步驟直接複用計算結果，避免重複截圖與重複 OCR！
        """
        if not self.priority_blocks or self._stop_event.is_set():
            return False, screen_gray, det_results

        if screen is None:
            if not self.bot or not hasattr(self.bot, "capture_screen"):
                return False, screen_gray, det_results
            try:
                screen = self.bot.capture_screen()
            except Exception:
                return False, screen_gray, det_results

        if screen is None:
            return False, screen_gray, det_results

        img_h, img_w = screen.shape[:2]

        for p_idx, p_block in enumerate(self.priority_blocks):
            if self._stop_event.is_set():
                return False, screen_gray, det_results
            if not p_block.get("enabled", True):
                continue

            b_name = p_block.get("name", f"優先步驟 #{p_idx + 1}")
            b_type = p_block.get("type", "detect_click")
            p = p_block.get("params", {})

            # 判斷辨識目標類型與全域 OCR 限制
            tpl_img = p.get("template_image", "").strip()
            target_type = str(p.get("target_type", "僅文字"))
            disable_ocr = bool(self.global_settings.get("disable_ocr", False))

            is_pure_img = ("圖片" in target_type or "image" in target_type.lower() or "模板" in target_type) and ("文字" not in target_type)
            is_hybrid = ("文字或圖案" in target_type or "hybrid" in target_type.lower())
            is_check = ("打勾" in target_type or "check" in target_type.lower())
            is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)

            tpl_list = self.parse_template_images_list(tpl_img)

            # 1. 純圖片特徵比對模式 (STRICT PURE IMAGE MATCHING)
            # 只要是圖片模式，只進行圖片模板比對，未命中直接跳過，絕對禁止 fall through 執行文字 OCR！
            if is_pure_img or (not is_check and not is_cross and not is_hybrid and bool(tpl_list)):
                if not tpl_list:
                    continue
                if screen_gray is None:
                    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
                img_multi = bool(p.get("image_multiscale", False))
                if hasattr(self.bot, "match_template"):
                    matched_item = None
                    for single_tpl in tpl_list:
                        m_res = self.bot.match_template(screen_gray, single_tpl, threshold=img_thresh, multi_scale=img_multi)
                        if m_res is not None:
                            matched_item = (single_tpl, m_res)
                            break
                    if matched_item is not None:
                        matched_tpl, m_res = matched_item
                        tx, ty, score_val, bbox = m_res
                        fname = os.path.basename(matched_tpl)
                        ctx_info = f" [{context_desc}]" if context_desc else ""
                        self._log(f"[優先辨識: {b_name}] 命中圖片「{fname}」(相似度 {score_val:.2f}){ctx_info} → 優先執行動作！")
                        if self.on_priority_hit:
                            try:
                                self.on_priority_hit(p_idx)
                            except Exception:
                                pass
                        self._handle_detect_hit(
                            hit_name=f"優先圖片「{fname}」",
                            hit_center=(tx, ty),
                            p=p,
                            img_shape=(img_h, img_w),
                            is_image=True,
                            template_img=matched_tpl,
                            img_thresh=img_thresh,
                            img_multiscale=img_multi,
                            next_candidates=self.active_candidates
                        )
                        if self.on_priority_hit:
                            try:
                                self.on_priority_hit(-1)
                            except Exception:
                                pass
                        return True, screen_gray, det_results
                # 純圖片模式未命中圖片時，直接檢查下一個優先積木，徹底杜絕任何文字 OCR 誤判！
                continue

            # 若全域開關已停用文字辨識 (0-OCR / 純圖片模式)：跳過任何文字與符號辨識
            if disable_ocr and not (is_hybrid and tpl_list):
                continue

            # 2. 雙重模式 (文字或圖案) 之圖片優先判定
            if is_hybrid and tpl_list:
                if screen_gray is None:
                    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
                img_multi = bool(p.get("image_multiscale", False))
                if hasattr(self.bot, "match_template"):
                    matched_item = None
                    for single_tpl in tpl_list:
                        m_res = self.bot.match_template(screen_gray, single_tpl, threshold=img_thresh, multi_scale=img_multi)
                        if m_res is not None:
                            matched_item = (single_tpl, m_res)
                            break
                    if matched_item is not None:
                        matched_tpl, m_res = matched_item
                        tx, ty, score_val, bbox = m_res
                        fname = os.path.basename(matched_tpl)
                        ctx_info = f" [{context_desc}]" if context_desc else ""
                        self._log(f"[優先辨識: {b_name}] 命中圖案「{fname}」(相似度 {score_val:.2f}){ctx_info} → 優先執行動作！")
                        if self.on_priority_hit:
                            try:
                                self.on_priority_hit(p_idx)
                            except Exception:
                                pass
                        self._handle_detect_hit(
                            hit_name=f"優先圖案「{fname}」",
                            hit_center=(tx, ty),
                            p=p,
                            img_shape=(img_h, img_w),
                            is_image=True,
                            template_img=matched_tpl,
                            img_thresh=img_thresh,
                            img_multiscale=img_multi,
                            next_candidates=self.active_candidates
                        )
                        if self.on_priority_hit:
                            try:
                                self.on_priority_hit(-1)
                            except Exception:
                                pass
                        return True, screen_gray, det_results
                # 若雙重模式未中圖片且全域停用 OCR，跳過下方的文字比對
                if disable_ocr:
                    continue

            # 3. 特殊符號 (打勾/叉叉) 或 文字 OCR 比對 (僅限非純圖片模式且全域未禁用 OCR 時)
            raw_kws = p.get("keywords", "")
            kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]

            if (is_check or is_cross or kws) and not disable_ocr:
                if det_results is None:
                    det_results = self.bot.scan_text(screen)

                # 特殊符號
                if is_check or is_cross:
                    for item in det_results:
                        sym = item.get("symbol")
                        txt = item.get("text", "")
                        if is_check and is_check_mark(sym, txt):
                            ctx_info = f" [{context_desc}]" if context_desc else ""
                            self._log(f"[優先辨識: {b_name}] 命中打勾符號 [{txt}]{ctx_info} → 優先執行動作！")
                            if self.on_priority_hit:
                                try:
                                    self.on_priority_hit(p_idx)
                                except Exception:
                                    pass
                            self._handle_detect_hit(
                                hit_name=f"打勾符號 [{txt}]",
                                hit_center=item["center"],
                                p=p,
                                img_shape=(img_h, img_w),
                                raw_kws=raw_kws,
                                is_check=True,
                                next_candidates=self.active_candidates
                            )
                            if self.on_priority_hit:
                                try:
                                    self.on_priority_hit(-1)
                                except Exception:
                                    pass
                            return True, screen_gray, det_results
                        if is_cross and is_cross_mark(sym, txt):
                            ctx_info = f" [{context_desc}]" if context_desc else ""
                            self._log(f"[優先辨識: {b_name}] 命中叉叉符號 [{txt}]{ctx_info} → 優先執行動作！")
                            if self.on_priority_hit:
                                try:
                                    self.on_priority_hit(p_idx)
                                except Exception:
                                    pass
                            self._handle_detect_hit(
                                hit_name=f"叉叉符號 [{txt}]",
                                hit_center=item["center"],
                                p=p,
                                img_shape=(img_h, img_w),
                                raw_kws=raw_kws,
                                is_cross=True,
                                next_candidates=self.active_candidates
                            )
                            if self.on_priority_hit:
                                try:
                                    self.on_priority_hit(-1)
                                except Exception:
                                    pass
                            return True, screen_gray, det_results

                # 文字關鍵字
                if kws and not disable_ocr:
                    conf_thresh = self._get_confidence()
                    for kw in kws:
                        for item in det_results:
                            matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                            if matched and ratio >= conf_thresh:
                                ctx_info = f" [{context_desc}]" if context_desc else ""
                                self._log(f"[優先辨識: {b_name}] 命中文字「{item.get('text')}」(匹配「{kw}」){ctx_info} → 優先執行動作！")
                                if self.on_priority_hit:
                                    try:
                                        self.on_priority_hit(p_idx)
                                    except Exception:
                                        pass
                                self._handle_detect_hit(
                                    hit_name=f"優先文字「{item.get('text')}」",
                                    hit_center=item["center"],
                                    p=p,
                                    img_shape=(img_h, img_w),
                                    raw_kws=raw_kws,
                                    next_candidates=self.active_candidates
                                )
                                if self.on_priority_hit:
                                    try:
                                        self.on_priority_hit(-1)
                                    except Exception:
                                        pass
                                return True, screen_gray, det_results

            # 3. 條件分支 (branch_if) 若被設為優先步驟
            if b_type == "branch_if":
                branches = p.get("branches", [])
                if branches:
                    if screen_gray is None:
                        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    for b_idx, branch in enumerate(branches):
                        b_tpl = branch.get("template_image", "").strip()
                        b_tpl_list = self.parse_template_images_list(b_tpl)
                        if b_tpl_list and hasattr(self.bot, "match_template"):
                            br_thresh = _safe_float(branch.get("threshold", 0.80), 0.80)
                            br_multi = bool(branch.get("multiscale", False))
                            matched_b_res = None
                            for single_b_tpl in b_tpl_list:
                                m_res = self.bot.match_template(screen_gray, single_b_tpl, threshold=br_thresh, multi_scale=br_multi)
                                if m_res is not None:
                                    matched_b_res = (single_b_tpl, m_res)
                                    break
                            if matched_b_res is not None:
                                hit_b_tpl, m_res = matched_b_res
                                bx = _safe_int(branch.get("x", 960))
                                by = _safe_int(branch.get("y", 540))
                                ctx_info = f" [{context_desc}]" if context_desc else ""
                                self._log(f"[優先辨識: {b_name}] 命中分支圖片「{os.path.basename(hit_b_tpl)}」{ctx_info} → 點擊 ({bx}, {by})")
                                if self.on_priority_hit:
                                    try:
                                        self.on_priority_hit(p_idx)
                                    except Exception:
                                        pass
                                self.bot.tap(bx, by)
                                if self.on_priority_hit:
                                    try:
                                        self.on_priority_hit(-1)
                                    except Exception:
                                        pass
                                self._sleep_interruptible(1.0, check_priority=False)
                                return True, screen_gray, det_results

        return False, screen_gray, det_results

    def _check_and_exec_priority(self, context_desc: str = "") -> bool:
        """舊版相容介面：即時截圖並執行優先步驟檢查，回傳是否命中"""
        hit, _, _ = self._check_priority_on_frame(context_desc=context_desc)
        return hit

    def _build_next_candidates(
        self,
        current_idx: int,
        blocks: List[Dict[str, Any]],
        is_loop: bool = False,
        cycle: int = 1,
        total_cycles: int = 1,
        outer_candidates: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        構建當前步驟之後的候選步驟清單 (供命中後連點精確判斷何時結束過場跳過)
        """
        candidates: List[Dict[str, Any]] = []

        def _flatten_block(b: Dict[str, Any]) -> List[Dict[str, Any]]:
            """展開積木，若為迴圈積木則提取內部有效子步驟"""
            if not b.get("enabled", True):
                return []
            b_type = b.get("type", "")
            if b_type == "loop":
                in_blocks = b.get("params", {}).get("inner_blocks", [])
                res = []
                for ib in in_blocks:
                    if ib.get("enabled", True):
                        res.extend(_flatten_block(ib))
                return res
            return [b]

        # 1. 當前清單中後續的步驟 (idx + 1 到結尾)
        for i in range(current_idx + 1, len(blocks)):
            candidates.extend(_flatten_block(blocks[i]))

        # 2. 如果是迴圈內部 (is_loop)
        if is_loop:
            # 若迴圈還會進行下一輪 (無限次 0，或 cycle < total_cycles)
            if total_cycles == 0 or cycle < total_cycles:
                # 迴圈下一輪會回到迴圈開頭 (從 0 到 current_idx)
                for i in range(0, min(current_idx + 1, len(blocks))):
                    candidates.extend(_flatten_block(blocks[i]))
            else:
                # 迴圈已經是最後一輪，若有外部後續步驟，加入外部候選
                if outer_candidates:
                    for ob in outer_candidates:
                        candidates.extend(_flatten_block(ob))
        else:
            # 3. 主流程如果多輪 (total_cycles == 0 或 cycle < total_cycles)
            if total_cycles == 0 or cycle < total_cycles:
                for i in range(0, min(current_idx + 1, len(blocks))):
                    candidates.extend(_flatten_block(blocks[i]))

        # 過濾重複對象並保持順序
        seen_ids = set()
        unique_cands = []
        for c in candidates:
            c_id = id(c)
            if c_id not in seen_ids:
                seen_ids.add(c_id)
                unique_cands.append(c)

        return unique_cands

    def _is_block_target_present(
        self,
        screen: np.ndarray,
        block: Dict[str, Any],
        screen_gray: Optional[np.ndarray] = None,
        det_results: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, str, Optional[np.ndarray], Optional[List[Dict[str, Any]]]]:
        """
        快速檢測候選積木的目標 (圖片、符號、關鍵字) 是否出現在畫面上
        回傳: (is_present, match_desc, updated_gray, updated_det_results)
        """
        if not block or not block.get("enabled", True):
            return False, "", screen_gray, det_results

        b_type = block.get("type", "")
        p = block.get("params", {})
        disable_ocr = bool(self.global_settings.get("disable_ocr", False))

        # 1. 偵測點擊 (detect_click) 或 等待條件 (wait_condition)
        if b_type in ("detect_click", "wait_condition"):
            cond_mode = str(p.get("cond_mode", "出現 (Wait Appear)"))
            is_wait_disappear = ("消失" in cond_mode or "disappear" in cond_mode.lower())

            target_type = str(p.get("target_type", "僅文字"))
            template_img = str(p.get("template_image", "")).strip()
            raw_kws = str(p.get("keywords", ""))
            img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
            img_multi = bool(p.get("image_multiscale", False))

            is_image = ("圖片" in target_type or "image" in target_type.lower() or "模板" in target_type) and ("文字" not in target_type)
            is_hybrid = ("文字或圖案" in target_type or "hybrid" in target_type.lower())
            is_check = ("打勾" in target_type or "check" in target_type.lower())
            is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)

            present = False
            match_desc = ""

            # 1.1 圖片比對 (優先且嚴格)
            tpl_list = self.parse_template_images_list(template_img)
            if (is_image or is_hybrid or tpl_list) and tpl_list:
                if screen_gray is None:
                    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                if hasattr(self.bot, "match_template"):
                    for single_tpl in tpl_list:
                        m_res = self.bot.match_template(screen_gray, single_tpl, threshold=img_thresh, multi_scale=img_multi)
                        if m_res is not None:
                            present = True
                            match_desc = f"圖片「{os.path.basename(single_tpl)}」(相似度 {m_res[2]:.2f})"
                            break

            # 1.2 符號與文字比對 (僅在未關閉 OCR 且非純圖片時)
            if not present and not is_image and not disable_ocr:
                kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
                if is_check or is_cross or kws:
                    if det_results is None and hasattr(self.bot, "scan_text"):
                        det_results = self.bot.scan_text(screen)

                    if det_results:
                        if is_check or is_cross:
                            for item in det_results:
                                sym = item.get("symbol")
                                txt = item.get("text", "")
                                if is_check and is_check_mark(sym, txt):
                                    present = True
                                    match_desc = f"打勾圖案 [{txt}]"
                                    break
                                if is_cross and is_cross_mark(sym, txt):
                                    present = True
                                    match_desc = f"叉叉圖案 [{txt}]"
                                    break

                        if not present and kws:
                            conf_thresh = self._get_confidence()
                            for kw in kws:
                                for item in det_results:
                                    matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                                    if matched and ratio >= conf_thresh:
                                        present = True
                                        match_desc = f"文字「{item.get('text')}」(匹配「{kw}」)"
                                        break
                                if present:
                                    break

            if is_wait_disappear:
                # 若等待的是消失，只要畫面中不存在該目標即視為達成
                if not present:
                    return True, "目標已消失", screen_gray, det_results
                return False, "", screen_gray, det_results
            else:
                if present:
                    return True, match_desc, screen_gray, det_results
                return False, "", screen_gray, det_results

        # 2. 條件分支 (branch_if)
        elif b_type == "branch_if":
            branches = p.get("branches", [])
            for br in branches:
                b_tpl = str(br.get("template_image", "")).strip()
                b_kws = str(br.get("keywords", ""))
                b_thresh = _safe_float(br.get("threshold", 0.80), 0.80)
                b_multi = bool(br.get("multiscale", False))

                b_tpl_list = self.parse_template_images_list(b_tpl)
                if b_tpl_list and hasattr(self.bot, "match_template"):
                    if screen_gray is None:
                        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    for single_b_tpl in b_tpl_list:
                        m = self.bot.match_template(screen_gray, single_b_tpl, threshold=b_thresh, multi_scale=b_multi)
                        if m is not None:
                            return True, f"分支[{br.get('name')}] 圖片「{os.path.basename(single_b_tpl)}」", screen_gray, det_results

                if b_kws and not disable_ocr:
                    if det_results is None and hasattr(self.bot, "scan_text"):
                        det_results = self.bot.scan_text(screen)
                    if det_results:
                        conf_thresh = self._get_confidence()
                        for kw in [k.strip() for k in b_kws.replace("，", ",").split(",") if k.strip()]:
                            for item in det_results:
                                matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                                if matched and ratio >= conf_thresh:
                                    return True, f"分支[{br.get('name')}] 文字「{item.get('text')}」", screen_gray, det_results

        # 3. 迴圈容器 (loop) - 檢查其第一個有效子步驟
        elif b_type == "loop":
            inner_blocks = p.get("inner_blocks", [])
            for ib in inner_blocks:
                if ib.get("enabled", True):
                    return self._is_block_target_present(screen, ib, screen_gray=screen_gray, det_results=det_results)

        return False, "", screen_gray, det_results

    def execute_block(
        self,
        b_type: str,
        params: Dict[str, Any],
        next_candidates: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """執行單個積木動作"""
        self.active_candidates = next_candidates or []
        if b_type == "tap_coord":
            return self._exec_tap_coord(params)
        elif b_type == "multi_tap":
            return self._exec_multi_tap(params)
        elif b_type == "detect_click":
            return self._exec_detect_click(params, next_candidates=next_candidates)
        elif b_type == "branch_if":
            return self._exec_branch_if(params)
        elif b_type == "loop":
            return self._exec_loop(params, outer_candidates=next_candidates)
        elif b_type == "wait_condition":
            return self._exec_wait_condition(params, next_candidates=next_candidates)
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

    def _sleep_interruptible(self, seconds: float, check_priority: bool = True) -> bool:
        """可被停止中斷的睡眠，支援在等待睡眠期間插隊檢查優先辨識"""
        end_time = time.time() + seconds
        last_prio_check = 0.0
        while time.time() < end_time:
            if self._stop_event.is_set():
                return False
            now = time.time()
            if check_priority and self.priority_blocks and (now - last_prio_check >= 0.8):
                last_prio_check = now
                if self._check_and_exec_priority("延遲等待中"):
                    pass
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

    def _evaluate_single_condition(
        self,
        cond: Dict[str, Any],
        screen: np.ndarray,
        screen_gray: Optional[np.ndarray] = None,
        det_results: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, str, Optional[np.ndarray], Optional[List[Dict[str, Any]]]]:
        """
        評估單一條件規則在當前畫面幀上是否成立：
        支援：圖片出現/消失 (支援多圖比對與路徑解析)、文字出現/消失、打勾/叉叉、文字或圖案任一出現/消失
        回傳: (is_met, desc, screen_gray, det_results)
        """
        mode = str(cond.get("mode", cond.get("stop_mode", "偵測到圖片出現"))).strip()
        if mode in ("依指定次數", "無 (僅點滿次數)"):
            return False, "", screen_gray, det_results

        is_disappear = ("消失" in mode or "disappear" in mode.lower())
        is_appear = not is_disappear
        is_check = ("打勾" in mode or "check" in mode.lower())
        is_cross = ("叉叉" in mode or "cross" in mode.lower())
        is_hybrid = ("文字或圖案" in mode or "文字或圖片" in mode or "hybrid" in mode.lower())

        raw_tpl = str(cond.get("template_image", "")).strip()
        is_image = ("圖片" in mode or "image" in mode.lower() or "模板" in mode or is_hybrid or bool(raw_tpl))
        is_pure_img = is_image and not is_hybrid and ("文字" not in mode)

        raw_kws = str(cond.get("keywords", cond.get("stop_keywords", ""))).strip()
        threshold = _safe_float(cond.get("image_threshold", cond.get("threshold", 0.80)), 0.80)
        multiscale = bool(cond.get("image_multiscale", cond.get("multiscale", False)))
        disable_ocr = bool(self.global_settings.get("disable_ocr", False))

        img_matched = False
        matched_img_desc = ""
        tpl_list = self.parse_template_images_list(raw_tpl) if (is_image or raw_tpl) else []

        # 1. 圖片比對 (支援多圖，依序測試)
        if tpl_list and hasattr(self.bot, "match_template"):
            if screen_gray is None:
                screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            for single_tpl in tpl_list:
                resolved = self.resolve_image_path(single_tpl) or single_tpl
                m_res = self.bot.match_template(
                    screen_gray,
                    resolved,
                    threshold=threshold,
                    multi_scale=multiscale
                )
                if m_res is not None:
                    img_matched = True
                    matched_img_desc = f"圖片「{os.path.basename(resolved)}」(相似度 {m_res[2]:.2f})"
                    break

        # 2. 文字與符號比對 (若非純圖片模式且未關閉 OCR)
        txt_matched = False
        matched_txt_desc = ""
        sym_matched = False
        matched_sym_desc = ""

        if not is_pure_img and not disable_ocr:
            kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
            if is_check or is_cross or kws:
                if det_results is None and hasattr(self.bot, "scan_text"):
                    det_results = self.bot.scan_text(screen)
                if det_results:
                    if is_check or is_cross:
                        for item in det_results:
                            sym = item.get("symbol")
                            txt = item.get("text", "")
                            if is_check and is_check_mark(sym, txt):
                                sym_matched = True
                                matched_sym_desc = f"打勾圖案 [{txt}]"
                                break
                            if is_cross and is_cross_mark(sym, txt):
                                sym_matched = True
                                matched_sym_desc = f"叉叉圖案 [{txt}]"
                                break

                    if kws:
                        conf_thresh = self._get_confidence()
                        for kw in kws:
                            for item in det_results:
                                matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                                if matched and ratio >= conf_thresh:
                                    txt_matched = True
                                    matched_txt_desc = f"關鍵字「{kw}」({item.get('text')})"
                                    break
                            if txt_matched:
                                break

        # 3. 判斷條件達成 (出現 / 消失)
        if is_appear:
            if is_hybrid:
                if img_matched:
                    return True, f"偵測到{matched_img_desc}出現", screen_gray, det_results
                if txt_matched:
                    return True, f"偵測到{matched_txt_desc}出現", screen_gray, det_results
                if sym_matched:
                    return True, f"偵測到{matched_sym_desc}出現", screen_gray, det_results
            elif is_pure_img or ("圖片" in mode and not raw_kws and not is_check and not is_cross):
                if img_matched:
                    return True, f"偵測到{matched_img_desc}出現", screen_gray, det_results
            elif is_check or is_cross:
                if sym_matched:
                    return True, f"偵測到{matched_sym_desc}出現", screen_gray, det_results
            else:
                if txt_matched:
                    return True, f"偵測到{matched_txt_desc}出現", screen_gray, det_results
        else: # is_disappear
            if is_hybrid:
                if (tpl_list or raw_kws or is_check or is_cross) and (not tpl_list or not img_matched) and (not raw_kws or not txt_matched) and not sym_matched:
                    return True, "指定之圖片與文字皆已消失", screen_gray, det_results
            elif is_pure_img or ("圖片" in mode and not raw_kws):
                if tpl_list and not img_matched:
                    all_names = ", ".join([os.path.basename(x) for x in tpl_list])
                    return True, f"圖片「{all_names}」已消失", screen_gray, det_results
            elif is_check or is_cross:
                if not sym_matched:
                    target_name = "打勾圖案" if is_check else "叉叉圖案"
                    return True, f"{target_name}已消失", screen_gray, det_results
            else:
                if raw_kws and not txt_matched:
                    return True, f"目標「{raw_kws}」已消失", screen_gray, det_results

        return False, "", screen_gray, det_results

    def _check_condition_met(
        self,
        stop_mode: str,
        raw_keywords: str,
        template_image: str = "",
        threshold: float = 0.80,
        multiscale: bool = False,
        stop_conditions: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, str]:
        """檢測當前畫面是否滿足終止條件 (支援單一條件、混合條件、多圖比對、或複數條件清單)"""
        if not self.bot:
            return False, ""

        if stop_mode in ("依指定次數", "無 (僅點滿次數)"):
            return False, ""

        screen = None
        try:
            screen = self.bot.capture_screen()
        except Exception:
            pass

        if screen is None:
            return False, ""

        screen_gray = None
        det_results = None

        # 同步優先動作檢查 (共享同一畫面幀)
        if self.priority_blocks:
            p_hit, screen_gray, det_results = self._check_priority_on_frame(
                screen=screen,
                screen_gray=screen_gray,
                det_results=det_results,
                context_desc="條件檢測中"
            )
            if p_hit:
                # 優先動作執行後畫面可能改變，重新截圖以確認當前條件
                try:
                    screen = self.bot.capture_screen()
                    screen_gray = None
                    det_results = None
                except Exception:
                    pass
                if screen is None:
                    return False, ""

        # 1. 複數條件判斷 (若 stop_conditions 存在且非空)
        is_multi = (stop_mode in ("複數條件 (多條件任一達成即停止)", "複數條件 (多條件任一達成)", "複數條件", "多條件") or bool(stop_conditions))
        if is_multi and stop_conditions:
            for c_idx, cond in enumerate(stop_conditions):
                if not cond.get("enabled", True):
                    continue
                c_name = cond.get("name", f"條件 #{c_idx + 1}")
                met, desc, screen_gray, det_results = self._evaluate_single_condition(
                    cond=cond,
                    screen=screen,
                    screen_gray=screen_gray,
                    det_results=det_results
                )
                if met:
                    return True, f"[{c_name}] {desc}"
            return False, ""

        # 2. 單一條件判斷 (相容一般單條件與連續點擊)
        single_cond = {
            "mode": stop_mode,
            "keywords": raw_keywords,
            "template_image": template_image,
            "image_threshold": threshold,
            "image_multiscale": multiscale
        }
        met, desc, _, _ = self._evaluate_single_condition(
            cond=single_cond,
            screen=screen,
            screen_gray=screen_gray,
            det_results=det_results
        )
        return met, desc

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
        self._log(f"  開始連續點擊 ({x}, {y}) [預計 {tot_str} 次，間隔 {interval:.2f}s，停止條件: {stop_mode}]")

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
                    self._log(f"  觸發停止條件！{desc}，停止連點 (共完成 {taps_done} 次)")
                    break

            if count == 0 or taps_done < count:
                if not self._sleep_interruptible(interval):
                    return False

        self._log(f"  連續點擊結束，共執行 {taps_done} 次點擊。")
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
        is_cross: bool = False,
        next_candidates: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        處理偵測命中後的動作執行：
        1. 依動作模式計算點擊位置 (目標中心、自訂座標、自訂特定區塊、無動作僅等待)
        2. 命中後連點 (跟隨目標、自訂座標、右下角、中央、右上Skip、右半中央；比照循序腳本，持續連點跳過過場直到下一步驟出現)
        3. 執行結束延遲
        """
        img_h, img_w = img_shape
        click_mode = str(p.get("click_mode", "點擊目標中心")).strip()
        cx = _safe_int(p.get("custom_x", 960))
        cy = _safe_int(p.get("custom_y", 540))
        bx1 = _safe_int(p.get("block_x1", 800))
        by1 = _safe_int(p.get("block_y1", 450))
        bx2 = _safe_int(p.get("block_x2", 1120))
        by2 = _safe_int(p.get("block_y2", 630))

        # 1. 計算第一階段點擊目標座標
        click_coord = None
        is_custom_xy = (
            click_mode in ("custom_coord", "自訂座標", "點擊自訂座標", "點擊指定座標 (自訂)")
            or "自訂座標" in click_mode
            or "指定座標" in click_mode
        )
        is_custom_block = (
            click_mode in ("custom_block", "自訂特定區塊", "自訂特定區塊")
            or "特定區塊" in click_mode
            or "自訂區塊" in click_mode
        )
        is_wait_only = (
            click_mode in ("wait_only", "無動作", "無動作(僅等待)", "無動作(僅等待)")
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
            # 點擊目標中心 (預設)
            click_coord = (hit_center[0] + random.randint(-3, 3), hit_center[1] + random.randint(-3, 3))

        # 2. 執行第一階段點擊
        if click_coord is not None:
            self._log(f"  命中【{hit_name}】→ 點擊目標 ({click_coord[0]}, {click_coord[1]})")
            self.bot.tap(click_coord[0], click_coord[1])
        else:
            self._log(f"  命中【{hit_name}】(設定為無動作/僅等待，不執行單次點擊)")

        # 3. 命中後連點（過場跳過）
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
                self._log(f"  [命中後連點] 在「{rep_area}」({base_x}, {base_y}) 連點 {rep_count} 次 (間隔 {rep_interval:.2f}s)...")
                for c in range(rep_count):
                    if self._stop_event.is_set():
                        return False
                    rx = base_x + random.randint(-8, 8)
                    ry = base_y + random.randint(-8, 8)
                    self.bot.tap(rx, ry, delay_range=(min_spd, max_spd))
            else:
                # 持續連點跳過過場 (直到下一步驟出現或觸發優先動作)
                valid_cands = []
                if next_candidates:
                    for cand in next_candidates:
                        c_type = cand.get("type", "")
                        if c_type in ("detect_click", "wait_condition", "branch_if", "loop"):
                            valid_cands.append(cand)

                cands_desc = ""
                if valid_cands:
                    cand_names = [f"[{c.get('name', '未命名')}]" for c in valid_cands[:3]]
                    cands_desc = f" (持續連點直到下一步驟 {' / '.join(cand_names)} 出現)"

                self._log(f"  [命中後連點] 正在持續連點「{rep_area}」({base_x}, {base_y}) 跳過過場{cands_desc}...")
                tap_cnt = 0
                max_continuous_taps = 1200  # 安全防卡死上限 (約 4~5 分鐘)
                orig_disappeared = False     # 追蹤原目標是否已消失 (防止單步驟循環時被剛點擊未消失的原目標早退)
                initial_tap_grace = 4        # 前 4 次點擊為寬限期，不判定同名目標

                while tap_cnt < max_continuous_taps:
                    if self._stop_event.is_set():
                        return False

                    rx = base_x + random.randint(-8, 8)
                    ry = base_y + random.randint(-8, 8)
                    self.bot.tap(rx, ry, delay_range=(min_spd, max_spd))
                    tap_cnt += 1

                    # 每隔 3 次點擊檢測一次畫面 (反應極速且節省 CPU)
                    if tap_cnt % 3 == 0:
                        chk_screen = self.bot.capture_screen()
                        if chk_screen is not None:
                            chk_gray = None
                            chk_det = None
                            hit_next = False

                            # 1. 同步優先動作檢查 (共享同一畫面幀)
                            if self.priority_blocks:
                                p_hit, chk_gray, chk_det = self._check_priority_on_frame(
                                    screen=chk_screen,
                                    screen_gray=chk_gray,
                                    det_results=chk_det,
                                    context_desc="連點中途"
                                )
                                if p_hit:
                                    self._log(f"  連點中途觸發其他優先動作，結束當前連點切換！")
                                    break

                            # 追蹤原目標是否還在畫面上
                            if not orig_disappeared:
                                still_there = False
                                if is_image and template_img:
                                    if chk_gray is None:
                                        chk_gray = cv2.cvtColor(chk_screen, cv2.COLOR_BGR2GRAY)
                                    if hasattr(self.bot, "match_template"):
                                        chk_tpl_list = self.parse_template_images_list(template_img)
                                        for single_tpl in chk_tpl_list:
                                            m = self.bot.match_template(chk_gray, single_tpl, threshold=img_thresh, multi_scale=img_multiscale)
                                            if m:
                                                still_there = True
                                                break
                                else:
                                    if chk_det is None and hasattr(self.bot, "scan_text"):
                                        chk_det = self.bot.scan_text(chk_screen)
                                    if chk_det is None:
                                        chk_det = []
                                    if is_check or is_cross:
                                        for it in chk_det:
                                            s = it.get("symbol"); t = it.get("text", "")
                                            if is_check and is_check_mark(s, t):
                                                still_there = True; break
                                            if is_cross and is_cross_mark(s, t):
                                                still_there = True; break
                                    if not still_there and raw_kws:
                                        conf_thresh = self._get_confidence()
                                        for kw in [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]:
                                            for it in chk_det:
                                                matched, ratio = self.bot._is_text_matched(kw, it.get("text", ""), similarity_threshold=conf_thresh)
                                                if matched and ratio >= conf_thresh:
                                                    still_there = True; break
                                            if still_there: break
                                if not still_there:
                                    orig_disappeared = True

                            # 檢測候選下一步驟
                            if valid_cands:
                                for cand in valid_cands:
                                    cand_p = cand.get("params", {})
                                    cand_tpl = cand_p.get("template_image", "").strip()
                                    cand_kws = cand_p.get("keywords", "")

                                    # 如果候選步驟的目標和原目標相同 (例如單步驟循環)，且原目標尚未消失或仍在寬限期內，則略過此輪比對
                                    curr_tpl_set = set(self.parse_template_images_list(template_img))
                                    cand_tpl_set = set(self.parse_template_images_list(cand_tpl))
                                    is_same_target = (is_image and bool(curr_tpl_set & cand_tpl_set)) or (raw_kws and cand_kws and raw_kws == cand_kws)
                                    if is_same_target and (not orig_disappeared or tap_cnt <= initial_tap_grace):
                                        continue

                                    pres, desc_m, chk_gray, chk_det = self._is_block_target_present(
                                        chk_screen, cand, screen_gray=chk_gray, det_results=chk_det
                                    )
                                    if pres:
                                        c_name = cand.get("name", "下一步驟")
                                        self._log(f"  [命中後連點] 偵測到下一步驟 [{c_name}]（{desc_m}）已出現，過場跳過完成！(共連點 {tap_cnt} 次)")
                                        hit_next = True
                                        break

                                if hit_next:
                                    break
                            else:
                                # 若完全沒有下一步驟 (例如獨立單步執行且無後續)，則在原目標消失後多連點數次確認過場完成後退出
                                if orig_disappeared and tap_cnt >= 12:
                                    self._log(f"  [命中後連點] 原目標已消失且無後續步驟，過場跳過完成！(共連點 {tap_cnt} 次)")
                                    break

                if tap_cnt >= max_continuous_taps:
                    self._log(f"  [命中後連點] 已達安全連點上限 ({tap_cnt} 次)，停止連點以防卡死。")

        # 4. 執行結束延遲
        delay = max(0.0, _safe_float(p.get("delay", 1.5)))
        if delay > 0:
            self._sleep_interruptible(delay, check_priority=False)

        return True

    def _exec_detect_click(
        self,
        p: Dict[str, Any],
        next_candidates: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        target_type = p.get("target_type", "僅文字")
        raw_kws = p.get("keywords", "")
        template_img = p.get("template_image", "").strip()
        img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
        img_multiscale = bool(p.get("image_multiscale", False))
        raw_timeout = _safe_int(p.get("timeout", 10))
        is_infinite = (raw_timeout <= 0)
        timeout = 0 if is_infinite else max(1, raw_timeout)

        disable_ocr = bool(self.global_settings.get("disable_ocr", False))
        is_image_mode = ("圖片" in target_type or "image" in target_type.lower() or "模板" in target_type) and ("文字" not in target_type)
        is_check = ("打勾" in target_type or "check" in target_type.lower())
        is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)

        tpl_list = self.parse_template_images_list(template_img)
        kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
        scan_delay = self._get_scan_interval()
        deadline = float("inf") if is_infinite else (time.time() + timeout)

        desc_target = (
            f"圖片「{', '.join([os.path.basename(x) for x in tpl_list])}」"
            if is_image_mode and tpl_list
            else (f"文字/符號「{raw_kws}」" if raw_kws else target_type)
        )

        if not is_image_mode and disable_ocr:
            self._log(f"  全域已關閉文字辨識 (純圖片模式 / 0-OCR)，跳過文字目標【{desc_target}】。")
            return False

        timeout_desc = "無限秒" if is_infinite else f"{timeout}s"
        self._log(f"  等待目標【{desc_target}】出現 (限時 {timeout_desc}, 刷新速度 {scan_delay:.2f}s)...")

        while is_infinite or time.time() < deadline:
            if self._stop_event.is_set():
                return False

            screen = self.bot.capture_screen()
            if screen is not None:
                img_h, img_w = screen.shape[:2]
                screen_gray = None
                det_results = None

                # 同步優先動作檢查 (共享同一畫面幀，並刷新超時)
                if self.priority_blocks:
                    p_hit, screen_gray, det_results = self._check_priority_on_frame(
                        screen=screen,
                        screen_gray=screen_gray,
                        det_results=det_results,
                        context_desc="等待目標出現中"
                    )
                    if p_hit:
                        if not is_infinite:
                            deadline = time.time() + timeout  # 刷新超時，不扣除當前步驟的等待時間
                        time.sleep(0.1)
                        continue

                # 1. 圖片模板模式
                if is_image_mode:
                    if not tpl_list:
                        self._log("  未指定模板圖檔，無法進行圖片比對！")
                        return False
                    if screen_gray is None:
                        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    if hasattr(self.bot, "match_template"):
                        for single_tpl in tpl_list:
                            res = self.bot.match_template(
                                screen_gray,
                                single_tpl,
                                threshold=img_thresh,
                                multi_scale=img_multiscale
                            )
                            if res is not None:
                                tx, ty, score_val, bbox = res
                                img_name = os.path.basename(single_tpl)
                                return self._handle_detect_hit(
                                    hit_name=f"圖片模板「{img_name}」(相似度 {score_val:.2f})",
                                    hit_center=(tx, ty),
                                    p=p,
                                    img_shape=(img_h, img_w),
                                    is_image=True,
                                    template_img=single_tpl,
                                    img_thresh=img_thresh,
                                    img_multiscale=img_multiscale,
                                    next_candidates=next_candidates
                                )
                else:
                    # 2. 文字/符號 OCR 模式
                    if det_results is None and hasattr(self.bot, "scan_text"):
                        det_results = self.bot.scan_text(screen)
                    if det_results is None:
                        det_results = []

                    # 優先比對符號
                    if is_check or is_cross:
                        for item in det_results:
                            sym = item.get("symbol")
                            txt = item.get("text", "")
                            if is_check and is_check_mark(sym, txt):
                                return self._handle_detect_hit(
                                    hit_name=f"打勾符號 [{txt}]",
                                    hit_center=item["center"],
                                    p=p,
                                    img_shape=(img_h, img_w),
                                    raw_kws=raw_kws,
                                    is_check=True,
                                    next_candidates=next_candidates
                                )
                            if is_cross and is_cross_mark(sym, txt):
                                return self._handle_detect_hit(
                                    hit_name=f"叉叉符號 [{txt}]",
                                    hit_center=item["center"],
                                    p=p,
                                    img_shape=(img_h, img_w),
                                    raw_kws=raw_kws,
                                    is_cross=True,
                                    next_candidates=next_candidates
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
                                    raw_kws=raw_kws,
                                    next_candidates=next_candidates
                                )

            time.sleep(scan_delay)

        self._log(f"  等待超時 ({timeout}s 未偵測到目標【{desc_target}】)")
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

        raw_timeout = _safe_int(p.get("timeout", 8))
        is_infinite = (raw_timeout <= 0)
        timeout = 0 if is_infinite else max(1, raw_timeout)
        delay = _safe_float(p.get("delay", 1.5))

        scan_delay = self._get_scan_interval()
        conf_thresh = self._get_confidence()
        disable_ocr = bool(self.global_settings.get("disable_ocr", False))
        deadline = float("inf") if is_infinite else (time.time() + timeout)
        timeout_desc = "無限秒" if is_infinite else f"{timeout}s"
        self._log(f"  正在判斷多分支條件 (共有 {len(branches)} 個分支, 限時 {timeout_desc}, 刷新速度 {scan_delay:.2f}s)...")

        while is_infinite or time.time() < deadline:
            if self._stop_event.is_set():
                return False

            screen = self.bot.capture_screen()
            if screen is not None:
                screen_gray = None
                det_results = None

                # 同步優先動作檢查 (共享同一畫面幀，並刷新超時)
                if self.priority_blocks:
                    p_hit, screen_gray, det_results = self._check_priority_on_frame(
                        screen=screen,
                        screen_gray=screen_gray,
                        det_results=det_results,
                        context_desc="分支判斷中"
                    )
                    if p_hit:
                        if not is_infinite:
                            deadline = time.time() + timeout  # 刷新超時，不扣除當前步驟的等待時間
                        time.sleep(0.1)
                        continue

                # 依序檢查 If 以及各個 Else If 分支
                for b_idx, branch in enumerate(branches):
                    b_tag = branch.get("name", "If" if b_idx == 0 else f"Else If {b_idx}")
                    tpl_img = branch.get("template_image", "").strip()
                    raw_kws = branch.get("keywords", "")
                    kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
                    bx = _safe_int(branch.get("x", 960))
                    by = _safe_int(branch.get("y", 540))

                    # 1. 優先判斷分支圖片模板
                    b_tpl_list = self.parse_template_images_list(tpl_img)
                    if b_tpl_list and hasattr(self.bot, "match_template"):
                        if screen_gray is None:
                            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                        br_thresh = _safe_float(branch.get("threshold", 0.80), 0.80)
                        br_multi = bool(branch.get("multiscale", False))
                        matched_b_res = None
                        for single_b_tpl in b_tpl_list:
                            m_res = self.bot.match_template(screen_gray, single_b_tpl, threshold=br_thresh, multi_scale=br_multi)
                            if m_res is not None:
                                matched_b_res = (single_b_tpl, m_res)
                                break
                        if matched_b_res is not None:
                            hit_b_tpl, m_res = matched_b_res
                            self._log(f"  命中分支 [{b_tag}] 圖片「{os.path.basename(hit_b_tpl)}」(相似度 {m_res[2]:.2f}) 點擊座標 ({bx}, {by})")
                            self.bot.tap(bx, by)
                            self._sleep_interruptible(delay)
                            return True

                    # 2. 判斷分支關鍵字 (OCR，僅在未關閉文字辨識時執行)
                    if kws and not disable_ocr:
                        if det_results is None:
                            det_results = self.bot.scan_text(screen)
                        for kw in kws:
                            for item in det_results:
                                matched, ratio = self.bot._is_text_matched(kw, item.get("text", ""), similarity_threshold=conf_thresh)
                                if matched and ratio >= conf_thresh:
                                    self._log(f"  命中分支 [{b_tag}] 關鍵字「{kw}」點擊座標 ({bx}, {by})")
                                    self.bot.tap(bx, by)
                                    self._sleep_interruptible(delay)
                                    return True

            time.sleep(scan_delay)

        # 全部 If / Else If 皆未命中 執行 Else
        if else_act == "click_coord":
            self._log(f"  所有分支皆未命中，執行 Else 點擊 ({ex}, {ey})")
            self.bot.tap(ex, ey)
            self._sleep_interruptible(delay)
        else:
            self._log("  所有分支皆未命中，跳過此條件區塊。")
        return True

    def _exec_loop(self, p: Dict[str, Any], outer_candidates: Optional[List[Dict[str, Any]]] = None) -> bool:
        """迴圈容器：重複執行內部包含的積木步驟 (支援 While 條件與指定次數，支援單一條件、多圖比對與複數條件清單)"""
        stop_mode = p.get("stop_mode", "依指定次數")
        raw_kws = p.get("keywords", p.get("stop_keywords", ""))
        template_img = p.get("template_image", "").strip()
        img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
        img_multiscale = bool(p.get("image_multiscale", False))
        count = max(0, _safe_int(p.get("count", 3)))
        check_timing = p.get("check_timing", "每輪開始與結束")
        delay_after = max(0.0, _safe_float(p.get("delay_after", 0.5)))
        inner_blocks = p.get("inner_blocks", [])
        stop_conditions = p.get("stop_conditions", [])

        if not inner_blocks:
            self._log("  迴圈內無任何積木步驟，跳過執行。")
            return True

        is_multi_cond = (
            stop_mode in (
                "複數條件 (多條件任一達成即停止)",
                "複數條件 (多條件任一達成)",
                "複數條件",
                "多條件"
            )
            or bool(stop_conditions and stop_mode != "依指定次數")
        )
        is_cond_mode = (stop_mode != "依指定次數" and "無" not in stop_mode) or is_multi_cond
        tot_str = str(count) if count > 0 else "∞"
        if is_cond_mode:
            if is_multi_cond and stop_conditions:
                active_cnt = len([c for c in stop_conditions if c.get("enabled", True)])
                target_desc = f"複數條件 ({active_cnt} 項自訂條件)"
            elif template_img:
                tpls = self.parse_template_images_list(template_img)
                if len(tpls) > 1:
                    target_desc = f"圖片 ({len(tpls)} 張: {', '.join(os.path.basename(t) for t in tpls)})"
                elif tpls:
                    target_desc = f"圖片「{os.path.basename(tpls[0])}」"
                else:
                    target_desc = f"圖片「{template_img}」"
            else:
                target_desc = f"「{raw_kws}」" if raw_kws else stop_mode
            self._log(f"  進入 While 條件迴圈 [停止條件: {stop_mode} {target_desc}，上限: {tot_str} 次，內含 {len(inner_blocks)} 個步驟]...")
        else:
            self._log(f"  進入重複迴圈 [共 {tot_str} 次，內含 {len(inner_blocks)} 個步驟]...")

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
                    multiscale=img_multiscale,
                    stop_conditions=stop_conditions if is_multi_cond else None
                )
                if met:
                    self._log(f"  迴圈終止！在第 {cycle} 輪開始前觸發停止條件 ({desc})")
                    break

            self._log(f"    ── 迴圈第 {cycle}/{tot_str} 輪 ──")
            broken_by_step = False

            for s_idx, sb in enumerate(inner_blocks):
                if self._stop_event.is_set():
                    return False
                if not sb.get("enabled", True):
                    continue

                # 迴圈內部步驟執行前優先動作檢查
                prio_hits = 0
                while self._check_and_exec_priority(f"迴圈子步驟 #{s_idx + 1} 前"):
                    prio_hits += 1
                    if self._stop_event.is_set() or prio_hits >= 10:
                        break
                    time.sleep(0.3)

                if self._stop_event.is_set():
                    return False

                sb_type = sb.get("type", "tap_coord")
                sb_name = sb.get("name", f"子步驟 #{s_idx + 1}")
                sb_params = sb.get("params", {})
                self._log(f"      [{sb_name}] ({BLOCK_TYPES.get(sb_type, {}).get('title', sb_type)})")

                # 計算此子步驟之後的候選步驟 (供持續連點精準判斷何時跳過動畫)
                sub_candidates = self._build_next_candidates(
                    current_idx=s_idx,
                    blocks=inner_blocks,
                    is_loop=True,
                    cycle=cycle,
                    total_cycles=count,
                    outer_candidates=outer_candidates
                )
                ok = self.execute_block(sb_type, sb_params, next_candidates=sub_candidates)
                if not ok and sb_params.get("on_timeout") == "stop":
                    self._log(f"      子步驟觸發超時終止，中斷迴圈。")
                    return False

                # 每個子步驟後檢查
                if is_cond_mode and "子步驟" in check_timing:
                    met, desc = self._check_condition_met(
                        stop_mode,
                        raw_kws,
                        template_image=template_img,
                        threshold=img_thresh,
                        multiscale=img_multiscale,
                        stop_conditions=stop_conditions if is_multi_cond else None
                    )
                    if met:
                        self._log(f"  迴圈終止！在子步驟 [{sb_name}] 執行後觸發停止條件 ({desc})")
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
                    multiscale=img_multiscale,
                    stop_conditions=stop_conditions if is_multi_cond else None
                )
                if met:
                    self._log(f"  迴圈終止！第 {cycle} 輪結束時觸發停止條件 ({desc})")
                    break

            cycle += 1
            time.sleep(0.1)

        self._log(f"  迴圈結束！共完成 {rounds_done} 輪。")
        if delay_after > 0:
            self._sleep_interruptible(delay_after)
        return True

    def _exec_wait_condition(
        self,
        p: Dict[str, Any],
        next_candidates: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """等待指定條件達成 (畫面出現或消失特定文字/圖片/符號)，期間依設定的頻率 (秒) 循環檢測"""
        cond_mode = p.get("cond_mode", "出現 (Wait Appear)")
        is_wait_disappear = ("消失" in cond_mode or "disappear" in cond_mode.lower())
        is_wait_appear = not is_wait_disappear
        target_type = p.get("target_type", "僅文字")
        raw_kws = p.get("keywords", "")
        template_img = p.get("template_image", "").strip()
        tpl_list = self.parse_template_images_list(template_img)
        img_thresh = _safe_float(p.get("image_threshold", 0.80), 0.80)
        img_multiscale = bool(p.get("image_multiscale", False))
        disable_ocr = bool(self.global_settings.get("disable_ocr", False))

        is_image_mode = ("圖片" in target_type or "image" in target_type.lower() or "模板" in target_type) and ("文字" not in target_type)
        is_check = ("打勾" in target_type or "check" in target_type.lower())
        is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)

        scan_delay = self._get_scan_interval()
        default_interval = scan_delay if "interval" not in p else _safe_float(p.get("interval", scan_delay))
        interval = max(0.02, default_interval)

        raw_timeout = _safe_int(p.get("timeout", 30))
        is_infinite = (raw_timeout <= 0)
        timeout = 0 if is_infinite else max(1, raw_timeout)
        delay_after = max(0.0, _safe_float(p.get("delay_after", 0.5)))
        on_timeout = p.get("on_timeout", "continue")

        mode_str = "出現" if is_wait_appear else "消失"
        if is_image_mode:
            fnames = ", ".join([os.path.basename(x) for x in tpl_list])
            desc = f"圖片「{fnames}」" if fnames else "未指定圖片模板"
        else:
            kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
            desc = f"{target_type} [{raw_kws}]" if kws else target_type

        if not is_image_mode and disable_ocr:
            self._log(f"  全域已關閉文字辨識 (純圖片模式 / 0-OCR)，跳過文字條件等待【{desc}】。")
            return False

        timeout_desc = "無限秒" if is_infinite else f"{timeout}s"
        self._log(f"  等待「{desc}」{mode_str} (每 {interval:.2f}s 偵測一次，限時 {timeout_desc})...")

        start_time = time.time()
        deadline = float("inf") if is_infinite else (start_time + timeout)

        while is_infinite or time.time() < deadline:
            if self._stop_event.is_set():
                return False

            screen = self.bot.capture_screen()
            present = False
            matched_desc = ""
            matched_tpl = ""
            hit_coord = (_safe_int(p.get("custom_x", 960)), _safe_int(p.get("custom_y", 540)))

            if screen is not None:
                screen_gray = None
                det_results = None

                # 同步優先動作檢查 (共享同一畫面幀，並刷新超時)
                if self.priority_blocks:
                    p_hit, screen_gray, det_results = self._check_priority_on_frame(
                        screen=screen,
                        screen_gray=screen_gray,
                        det_results=det_results,
                        context_desc="等待條件達成中"
                    )
                    if p_hit:
                        if not is_infinite:
                            deadline = time.time() + timeout  # 刷新超時，不扣除當前步驟的等待時間
                        time.sleep(0.1)
                        continue

                if is_image_mode:
                    if tpl_list and hasattr(self.bot, "match_template"):
                        if screen_gray is None:
                            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                        for single_tpl in tpl_list:
                            m_res = self.bot.match_template(
                                screen_gray,
                                single_tpl,
                                threshold=img_thresh,
                                multi_scale=img_multiscale
                            )
                            if m_res is not None:
                                present = True
                                hit_coord = (int(m_res[0]), int(m_res[1]))
                                matched_desc = f"圖片「{os.path.basename(single_tpl)}」(相似度 {m_res[2]:.2f})"
                                matched_tpl = single_tpl
                                break
                else:
                    if det_results is None and hasattr(self.bot, "scan_text"):
                        det_results = self.bot.scan_text(screen)
                    if det_results is None:
                        det_results = []

                    # 優先比對符號
                    if is_check or is_cross:
                        for item in det_results:
                            sym = item.get("symbol")
                            txt = item.get("text", "")
                            if is_check and is_check_mark(sym, txt):
                                present = True
                                hit_coord = item["center"]
                                matched_desc = f"打勾圖案 [{txt}]"
                                break
                            if is_cross and is_cross_mark(sym, txt):
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
                self._log(f"  條件達成！已偵測到「{matched_desc}」出現 (耗時 {elapsed:.1f}s)")
                return self._handle_detect_hit(
                    hit_name=matched_desc,
                    hit_center=hit_coord,
                    p=p,
                    img_shape=(screen.shape[0], screen.shape[1]),
                    is_image=is_image_mode,
                    template_img=matched_tpl if is_image_mode and matched_tpl else template_img,
                    img_thresh=img_thresh,
                    img_multiscale=img_multiscale,
                    raw_kws=raw_kws,
                    is_check=is_check,
                    is_cross=is_cross,
                    next_candidates=next_candidates
                )
            elif not is_wait_appear and not present:
                self._log(f"  條件達成！目標「{desc}」已消失 (耗時 {elapsed:.1f}s)")
                click_mode = str(p.get("click_mode", "無動作(僅等待)")).strip()
                is_wait_only = ("無動作" in click_mode or "僅等待" in click_mode or click_mode == "wait_only")
                if not is_wait_only:
                    return self._handle_detect_hit(
                        hit_name=f"目標消失「{desc}」",
                        hit_center=(p.get("custom_x", 960), p.get("custom_y", 540)),
                        p=p,
                        img_shape=(screen.shape[0], screen.shape[1]) if screen is not None else (1080, 1920),
                        is_image=False,
                        next_candidates=next_candidates
                    )
                if delay_after > 0:
                    self._sleep_interruptible(delay_after)
                return True

            if not self._sleep_interruptible(interval):
                return False

        self._log(f"  等待超時 ({timeout}s 未滿足「{desc}」{mode_str} 條件)")
        if delay_after > 0:
            self._sleep_interruptible(delay_after)
        return (on_timeout != "stop")

    def _exec_wait_sec(self, p: Dict[str, Any]) -> bool:
        sec = max(0.1, _safe_float(p.get("seconds", 3.0)))
        self._log(f"  等待 {sec:.1f} 秒...")
        return self._sleep_interruptible(sec)

    def _exec_swipe(self, p: Dict[str, Any]) -> bool:
        x1 = _safe_int(p.get("x1", 1500))
        y1 = _safe_int(p.get("y1", 540))
        x2 = _safe_int(p.get("x2", 400))
        y2 = _safe_int(p.get("y2", 540))
        dur = max(50, _safe_int(p.get("duration_ms", 400)))
        delay = _safe_float(p.get("delay", 1.0))

        self._log(f"  ↔ 滑動手勢: ({x1}, {y1}) ({x2}, {y2}) [{dur}ms]")
        if self.bot.device:
            try:
                self.bot.device.shell(f"input swipe {x1} {y1} {x2} {y2} {dur}")
            except Exception as e:
                self._log(f"  滑動指令失敗: {e}")
        self._sleep_interruptible(delay)
        return True

    def _exec_back_key(self, p: Dict[str, Any]) -> bool:
        delay = _safe_float(p.get("delay", 1.2))
        self._log("  按下模擬器返回鍵 (Back)")
        if self.bot.device:
            try:
                self.bot.device.shell("input keyevent 4")
            except Exception as e:
                self._log(f"  返回鍵指令失敗: {e}")
        self._sleep_interruptible(delay)
        return True

    def _exec_comment(self, p: Dict[str, Any]) -> bool:
        """備註方塊：無程式功能，僅於日誌輸出備註提示"""
        note = p.get("note", "").strip()
        if note:
            self._log(f"  [備註] {note}")
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
            self._log("[Telegram] 尚未設定 Bot Token 或 Chat ID！請在「通用進階」面板填寫或在積木內自訂。")
            if delay_after > 0:
                self._sleep_interruptible(delay_after)
            return True

        self._log(f"正在發送 Telegram 通知:「{msg}」{' (附帶截圖)' if attach_img else ''}...")

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
            self._log(f"[Telegram] 通知已成功發送！")
        else:
            self._log(f"[Telegram] 通知發送請求已送出 (請確認網路連線與 Token/Chat ID 正確)")

        if delay_after > 0:
            self._sleep_interruptible(delay_after)
        return True

    def _send_telegram_direct(self, token: str, chat_id: str, text: str, screen_bgr: Optional[np.ndarray] = None) -> bool:
        """沒有 bot 可代發時，直接以共用通知模組在背景發送。"""
        return notify.send_telegram_async(
            token, chat_id, notify.format_notification(text, "任務流程"), screen_bgr
        )
