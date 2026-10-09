"""
棒球手遊自動化腳本 - 核心邏輯模組 (支援全域模擬器掃描、ADB 自動修復、文字模糊比對與全域異常攔截)
"""
import os
import sys
import gc
import time
import random
import logging
import subprocess
import difflib
import threading
import shutil
from typing import Optional, Tuple, Dict, List, Callable, Any

import requests
import cv2
import numpy as np
from ppadb.client import Client as AdbClient
from ppadb.device import Device
from rapidocr_onnxruntime import RapidOCR

logger = logging.getLogger("BaseballBot")

# =========================================================================
# 語言分類與過濾快取 (繁體中文 Big5、簡體中文 GB2312、英文 ASCII)
# =========================================================================
_CHAR_LANG_CACHE: Dict[str, str] = {}

def classify_char(ch: str) -> str:
    """
    分類單一字元:
    'en': ASCII 英文與數字 (a-z, A-Z, 0-9)
    'tc_only': 繁體中文專用字 (可編碼進 big5 但不可編碼進 gb2312)
    'sc_only': 簡體中文專用字 (可編碼進 gb2312 但不可編碼進 big5)
    'shared_cjk': 繁簡通用漢字 (兩者皆可編碼)
    'rare_cjk': 罕見漢字 (兩者皆無法以基本集編碼)
    'sym': 標點符號、特殊符號
    """
    cached = _CHAR_LANG_CACHE.get(ch)
    if cached is not None:
        return cached
    if ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('0' <= ch <= '9'):
        res = 'en'
    elif '\u4e00' <= ch <= '\u9fff':
        b5 = False
        gb = False
        try:
            ch.encode('big5')
            b5 = True
        except Exception:
            pass
        try:
            ch.encode('gb2312')
            gb = True
        except Exception:
            pass
        if b5 and not gb:
            res = 'tc_only'
        elif gb and not b5:
            res = 'sc_only'
        elif b5 and gb:
            res = 'shared_cjk'
        else:
            res = 'rare_cjk'
    else:
        res = 'sym'
    _CHAR_LANG_CACHE[ch] = res
    return res


class BaseballBot:
    """棒球手遊聯賽自動化刷關核心"""

    def __init__(
        self,
        adb_host: str = "127.0.0.1",
        adb_port: int = 5037,
        confidence_threshold: float = 0.65,
        log_callback: Optional[Callable[[str], None]] = None,
        on_frame_callback: Optional[Callable[[np.ndarray, List[Dict[str, Any]], Optional[Tuple[Any, ...]], Optional[Tuple[int, int]]], None]] = None
    ):
        self.adb_host = adb_host
        self.adb_port = adb_port
        self.confidence_threshold = confidence_threshold
        self.log_callback = log_callback
        self.on_frame_callback = on_frame_callback

        self.device: Optional[Device] = None
        self.adb_bin_path: Optional[str] = None
        self.is_running = False

        # 全域異常彈窗關鍵字 (項目 B: 突發異常彈窗全域攔截)
        self.popup_keywords = [
            "連線中斷", "重新連線", "網路異常", "網路連線",
            "伺服器維護", "伺服器", "請重新登入", "連線逾時", "連線失敗"
        ]
        self.popup_confirm_keywords = ["確認", "確定", "重試", "OK", "重新連接", "同意"]

        # 語言辨識與過濾設定 (預設繁體中文+英文開啟，簡體中文關閉以杜絕誤判)
        self.allowed_languages = {"tc": True, "sc": False, "en": True}

        # 預先快取多尺度特殊圖案 (打勾、叉叉) 模板
        self._init_symbol_templates()

        # 初始化 RapidOCR 辨識引擎
        self._log("初始化 RapidOCR 辨識引擎中...")
        self.ocr = RapidOCR()
        self._log("RapidOCR 初始化完成！")

        self.target_keywords = ["確認", "確定", "領取", "繼續", "下一步", "準備", "開始"]
        self.roi: Optional[Tuple[float, float, float, float]] = None

    def _log(self, message: str, level: str = "INFO"):
        """記錄日誌並推播至 GUI 回呼函式"""
        formatted = f"[{level}] {message}"
        if level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)

        if self.log_callback:
            try:
                self.log_callback(f"{time.strftime('%H:%M:%S')} {formatted}")
            except Exception:
                pass

    # =========================================================================
    # 語言過濾設定與判斷 (繁體中文 Big5、簡體中文 GB2312、英文/數字 ASCII)
    # =========================================================================
    def set_allowed_languages(self, allow_tc: bool = True, allow_sc: bool = False, allow_en: bool = True):
        """設定允許辨識的語言種類：繁體中文(tc)、簡體中文(sc)、英文與數字(en)"""
        self.allowed_languages = {
            "tc": bool(allow_tc),
            "sc": bool(allow_sc),
            "en": bool(allow_en)
        }
        tc_str = "開" if allow_tc else "關"
        sc_str = "開" if allow_sc else "關"
        en_str = "開" if allow_en else "關"
        self._log(f"🔤 辨識語言過濾更新: 繁體中文[{tc_str}] | 簡體中文[{sc_str}] | 英文與數字[{en_str}]")

    def is_text_allowed(self, text: str) -> bool:
        """
        檢查辨識文字是否符合使用者勾選的語言範圍。
        若文字內包含未允許的專用字元，則判定不通過 (有效杜絕背景雜訊產生的亂碼或簡體字)。
        """
        clean = text.strip()
        if not clean:
            return False
        # 特殊圖案與標籤永遠豁免
        if clean in ("[打勾]", "[叉叉]", "✓", "✔", "√", "✕", "✖", "×", "X", "x") or "[打勾]" in clean or "[叉叉]" in clean:
            return True

        allow_tc = self.allowed_languages.get("tc", True)
        allow_sc = self.allowed_languages.get("sc", False)
        allow_en = self.allowed_languages.get("en", True)

        # 逐字檢查主要字元
        for ch in clean:
            if ch in " \t\n\r，,。.！!？?-_:：()[]{}/*+·~`@#$%^&|\\<>=’'\"":
                continue
            c_type = classify_char(ch)
            if c_type == 'en' and not allow_en:
                return False
            if c_type == 'sc_only' and not allow_sc:
                return False
            if c_type == 'tc_only' and not allow_tc:
                return False
            if c_type in ('shared_cjk', 'rare_cjk') and (not allow_tc and not allow_sc):
                return False
        return True

    # =========================================================================
    # 特殊圖案模板快取與偵測 (打勾 ✓、叉叉/關閉 ✕/X)
    # =========================================================================
    def _init_symbol_templates(self):
        """預先快取多尺度打勾 (Checkmark) 與叉叉 (Cross) 模板"""
        self._symbol_templates: Dict[str, List[Tuple[int, np.ndarray, np.ndarray]]] = {
            "check": [],
            "cross": []
        }
        for sz in [20, 28, 36, 48]:
            # 1. 打勾 (Checkmark)
            t_c = np.zeros((sz, sz), dtype=np.uint8)
            th = max(2, sz // 8)
            p1 = (int(sz * 0.15), int(sz * 0.50))
            p2 = (int(sz * 0.40), int(sz * 0.82))
            p3 = (int(sz * 0.85), int(sz * 0.18))
            cv2.polylines(t_c, [np.array([p1, p2, p3])], False, 255, th)
            t_c_edges = cv2.Canny(t_c, 50, 150)
            self._symbol_templates["check"].append((sz, t_c, t_c_edges))

            # 2. 叉叉 (Cross / X / Close)
            t_x = np.zeros((sz, sz), dtype=np.uint8)
            m = int(sz * 0.15)
            cv2.line(t_x, (m, m), (sz - m, sz - m), 255, th)
            cv2.line(t_x, (m, sz - m), (sz - m, m), 255, th)
            t_x_edges = cv2.Canny(t_x, 50, 150)
            self._symbol_templates["cross"].append((sz, t_x, t_x_edges))

    def detect_symbols(
        self,
        screen_bgr: np.ndarray,
        target_type: str = "all",
        roi: Optional[Tuple[float, float, float, float]] = None,
        threshold: float = 0.50
    ) -> List[Dict[str, Any]]:
        """
        偵測畫面中的特殊圖案 (打勾 ✓、叉叉/關閉 ✕/X)。
        target_type: 'all' (兩者), 'check' (僅打勾), 'cross' (僅叉叉)
        回傳格式相容於 parsed_boxes:
        [{'text': '[打勾]', 'symbol': 'check', 'score': float, 'center': (cx, cy), 'size': (w, h), 'box': pts}, ...]
        """
        if screen_bgr is None:
            return []

        h, w = screen_bgr.shape[:2]
        offset_x, offset_y = 0, 0
        roi_img = screen_bgr

        # ROI 區域裁切加速
        if roi:
            ymin, xmin, ymax, xmax = roi
            rx1 = int(xmin * w) if xmin <= 1.0 else int(xmin)
            ry1 = int(ymin * h) if ymin <= 1.0 else int(ymin)
            rx2 = int(xmax * w) if xmax <= 1.0 else int(xmax)
            ry2 = int(ymax * h) if ymax <= 1.0 else int(ymax)
            rx1, ry1 = max(0, rx1), max(0, ry1)
            rx2, ry2 = min(w, rx2), min(h, ry2)
            if rx2 > rx1 and ry2 > ry1:
                roi_img = screen_bgr[ry1:ry2, rx1:rx2]
                offset_x, offset_y = rx1, ry1

        rh, rw = roi_img.shape[:2]
        if rw < 15 or rh < 15:
            return []

        gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        types_to_check = []
        target_type_str = str(target_type).lower()
        if "all" in target_type_str or "混合" in target_type or "文字或圖案" in target_type:
            types_to_check = ["check", "cross"]
        elif "check" in target_type_str or "打勾" in target_type or "✓" in target_type:
            types_to_check = ["check"]
        elif "cross" in target_type_str or "叉叉" in target_type or "✕" in target_type or "關閉" in target_type:
            types_to_check = ["cross"]
        else:
            types_to_check = ["check", "cross"]

        candidates = []

        # 1. 多尺度邊緣與灰階模板比對
        for sym in types_to_check:
            tpl_list = self._symbol_templates.get(sym, [])
            for sz, tpl_raw, t_edges in tpl_list:
                if rw < sz or rh < sz:
                    continue
                # 邊緣匹對 (不受底色影響)
                res_edge = cv2.matchTemplate(edges, t_edges, cv2.TM_CCOEFF_NORMED)
                locs_e = np.where(res_edge >= threshold)
                for pt in zip(*locs_e[::-1]):
                    val = float(res_edge[pt[1], pt[0]])
                    candidates.append((sym, val, pt[0], pt[1], pt[0] + sz, pt[1] + sz))

                # 灰階匹對備援 (高對比度實心圖示)
                res_gray = cv2.matchTemplate(gray, tpl_raw, cv2.TM_CCOEFF_NORMED)
                locs_g = np.where(res_gray >= max(0.68, threshold + 0.08))
                for pt in zip(*locs_g[::-1]):
                    val = float(res_gray[pt[1], pt[0]])
                    candidates.append((sym, val, pt[0], pt[1], pt[0] + sz, pt[1] + sz))

        # 2. 凸缺陷幾何拓撲分析
        try:
            bin_img = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 3)
            cnts, _ = cv2.findContours(bin_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in cnts:
                area = cv2.contourArea(cnt)
                if area < 30 or area > 3500:
                    continue
                cx_b, cy_b, cw_b, ch_b = cv2.boundingRect(cnt)
                aspect = cw_b / max(1, ch_b)
                if aspect < 0.6 or aspect > 1.8:
                    continue
                hull = cv2.convexHull(cnt, returnPoints=False)
                if hull is None or len(hull) < 4:
                    continue
                defects = cv2.convexityDefects(cnt, hull)
                if defects is None:
                    continue
                deep_defects = 0
                for i in range(defects.shape[0]):
                    d = defects[i, 0, 3] / 256.0
                    if d > 3.5:
                        deep_defects += 1

                if deep_defects == 4 and "cross" in types_to_check:
                    candidates.append(("cross", 0.78, cx_b, cy_b, cx_b + cw_b, cy_b + ch_b))
                elif deep_defects in (1, 2) and "check" in types_to_check:
                    if cw_b >= 12 and ch_b >= 10:
                        candidates.append(("check", 0.75, cx_b, cy_b, cx_b + cw_b, cy_b + ch_b))
        except Exception:
            pass

        if not candidates:
            return []

        # 3. NMS 非極大值抑制
        results = []
        for sym in types_to_check:
            sym_cands = [c for c in candidates if c[0] == sym]
            if not sym_cands:
                continue
            boxes_list = [[c[2], c[3], c[4] - c[2], c[5] - c[3]] for c in sym_cands]
            scores_list = [c[1] for c in sym_cands]
            indices = cv2.dnn.NMSBoxes(boxes_list, scores_list, score_threshold=threshold, nms_threshold=0.35)
            for idx in indices:
                i = int(idx)
                c = sym_cands[i]
                bx1, by1, bx2, by2 = c[2], c[3], c[4], c[5]
                score = c[1]

                real_x1 = bx1 + offset_x
                real_y1 = by1 + offset_y
                real_x2 = bx2 + offset_x
                real_y2 = by2 + offset_y

                box_w = real_x2 - real_x1
                box_h = real_y2 - real_y1
                center_x = real_x1 + box_w // 2
                center_y = real_y1 + box_h // 2

                pts = np.array([
                    [real_x1, real_y1],
                    [real_x2, real_y1],
                    [real_x2, real_y2],
                    [real_x1, real_y2]
                ], dtype=np.int32)

                sym_tag = "[打勾]" if sym == "check" else "[叉叉]"
                results.append({
                    "text": sym_tag,
                    "symbol": sym,
                    "score": round(float(score), 2),
                    "center": (center_x, center_y),
                    "size": (int(box_w), int(box_h)),
                    "box": pts
                })

        return results

    def send_telegram_notify(
        self,
        token: str,
        chat_id: str,
        custom_text: str,
        step_name: str = "",
        hit_text: str = "",
        screen_bgr: Optional[np.ndarray] = None
    ) -> bool:
        """
        發送 Telegram 通知 (非同步背景發送，不阻礙主線程點擊)
        支援自訂訊息內容與附帶截圖相片，並附帶當前時間戳記與命中資訊。
        """
        token = str(token).strip()
        chat_id = str(chat_id).strip()
        if not token or not chat_id:
            return False

        now_str = time.strftime('%Y-%m-%d %H:%M:%S')
        body_text = custom_text.strip() if custom_text else f"動作「{step_name}」執行完成！"
        
        # 組合包含時間戳記的通知文字
        lines = [
            f"⚾ 【9局職棒自動腳本通知】",
            f"📢 訊息: {body_text}",
        ]
        if step_name:
            lines.append(f"🎯 步驟: {step_name}")
        if hit_text:
            lines.append(f"🔍 命中: {hit_text}")
        lines.append(f"⏰ 時間: {now_str}")
        full_msg = "\n".join(lines)

        def _do_send():
            try:
                # 若有附帶螢幕截圖，優先發送照片
                if screen_bgr is not None:
                    try:
                        ok, buf = cv2.imencode('.jpg', screen_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                        if ok:
                            url = f"https://api.telegram.org/bot{token}/sendPhoto"
                            files = {'photo': ('screenshot.jpg', buf.tobytes(), 'image/jpeg')}
                            data = {'chat_id': chat_id, 'caption': full_msg}
                            resp = requests.post(url, data=data, files=files, timeout=12)
                            if resp.status_code == 200 and resp.json().get("ok"):
                                self._log(f"📱 [Telegram] 圖片通知發送成功:「{body_text}」")
                                return
                            else:
                                self._log(f"⚠️ [Telegram] 照片發送失敗，改發送純文字: {resp.text}", "WARNING")
                    except Exception as e_img:
                        self._log(f"⚠️ [Telegram] 照片編碼失敗: {e_img}", "WARNING")

                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": full_msg
                }
                resp = requests.post(url, json=payload, timeout=8)
                if resp.status_code == 200 and resp.json().get("ok"):
                    self._log(f"📱 [Telegram] 通知發送成功:「{body_text}」")
                else:
                    self._log(f"⚠️ [Telegram] 發送回應異常: {resp.text}", "WARNING")
            except Exception as e:
                self._log(f"⚠️ [Telegram] 通知發送失敗: {e}", "WARNING")

        threading.Thread(target=_do_send, daemon=True).start()
        return True

    def auto_detect_and_start_adb(self) -> Optional[str]:
        """
        全域掃描 macOS / Windows 系統中的模擬器（BlueStacks, MuMu, 夜神, 雷電）
        若本機 ADB Daemon 未啟動，自動使用模擬器內建的 adb 二進位檔啟動服務。
        """
        candidate_paths = [
            # Windows 模擬器路徑
            r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Program Files\BlueStacks\HD-Adb.exe",
            r"C:\Program Files (x86)\BlueStacks\HD-Adb.exe",
            r"D:\Program Files\BlueStacks_nxt\HD-Adb.exe",
            r"D:\Program Files\BlueStacks\HD-Adb.exe",
            r"C:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\LDPlayer\LDPlayer4\adb.exe",
            r"D:\LDPlayer\LDPlayer9\adb.exe",
            r"D:\LDPlayer\LDPlayer4\adb.exe",
            r"C:\leidian\LDPlayer9\adb.exe",
            r"C:\Program Files\LDPlayer\LDPlayer9\adb.exe",
            r"C:\Program Files\Nox\bin\adb.exe",
            r"C:\Program Files (x86)\Nox\bin\adb.exe",
            r"C:\Program Files\Nox\bin\nox_adb.exe",
            r"D:\Program Files\Nox\bin\adb.exe",
            r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe",
            r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
            r"D:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
            r"C:\Program Files (x86)\MuMu\emulator\nemu\vmonitor\bin\adb_server.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
            # macOS 模擬器
            "/Applications/BlueStacks.app/Contents/MacOS/hd-adb",
            "/Applications/BlueStacks Air multi-instance manager.app/Contents/MacOS/hd-adb",
            # MuMu 模擬器
            "/Applications/MuMuPlayer.app/Contents/MacOS/adb",
            "/Applications/Netease/MuMuPlayer/Contents/MacOS/adb",
            # 夜神模擬器 (Nox)
            "/Applications/NoxAppPlayer.app/Contents/MacOS/adb",
            # Android SDK 或 Homebrew 常用路徑
            "/usr/local/bin/adb",
            "/opt/homebrew/bin/adb",
            os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
        ]

        which_adb = shutil.which("adb.exe") or shutil.which("adb")
        if which_adb and which_adb not in candidate_paths:
            candidate_paths.insert(0, which_adb)

        found_adb = None
        for path in candidate_paths:
            if os.path.exists(path) and (sys.platform == "win32" or os.access(path, os.X_OK)):
                found_adb = path
                break

        if found_adb:
            self.adb_bin_path = found_adb
            self._log(f"找到模擬器 ADB 工具: {found_adb}")
            try:
                if sys.platform == "win32":
                    # Windows: 透過 cmd.exe /c 執行 devices 命令，自動拉起背景 daemon 且避免 PIPE 阻斷
                    p = subprocess.Popen(['cmd.exe', '/c', found_adb, 'devices'])
                    p.wait(timeout=15)
                else:
                    # 啟動 ADB server 並抓取設備
                    subprocess.run([found_adb, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                    # 嘗試常見端口連線 (BlueStacks / 雷電 5554/5555, 夜神 62001, MuMu 7555/16384)
                    for port in [5554, 5555, 62001, 7555, 16384]:
                        subprocess.run([found_adb, "connect", f"127.0.0.1:{port}"],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
            except Exception as e:
                self._log(f"啟動 ADB Server 時發生警告: {e}", "WARNING")
            return found_adb
        else:
            self._log("未在系統預設目錄找到獨立 ADB 工具，將嘗試直接連線本機 5037 埠。", "WARNING")
            return None

    def get_devices_list(self) -> List[str]:
        """獲取目前 ADB 連接的所有裝置序號（若未啟動則自動偵測啟動）"""
        try:
            client = AdbClient(host=self.adb_host, port=self.adb_port)
            devices = client.devices()
            if devices:
                return [d.serial for d in devices]
        except Exception:
            pass

        # 若未成功，進行全域掃描啟動 ADB 後再試
        self._log("正在全域搜尋已安裝的模擬器與 ADB 服務...")
        self.auto_detect_and_start_adb()

        try:
            client = AdbClient(host=self.adb_host, port=self.adb_port)
            devices = client.devices()
            return [d.serial for d in devices]
        except Exception as e:
            self._log(f"ADB 連線異常: {e}", "ERROR")
            return []

    def connect(self, target_serial: Optional[str] = None) -> bool:
        """連線至 ADB Server 並選定目標裝置"""
        try:
            client = AdbClient(host=self.adb_host, port=self.adb_port)
            devices = client.devices()

            if not devices:
                self.auto_detect_and_start_adb()
                devices = client.devices()

            if not devices:
                self._log("未檢測到任何已連線的模擬器！請確認 BlueStacks/MuMu 已開機。", "ERROR")
                return False

            if target_serial:
                matched = [d for d in devices if d.serial == target_serial]
                if not matched:
                    self._log(f"找不到序號為 {target_serial} 的裝置！", "ERROR")
                    return False
                self.device = matched[0]
            else:
                self.device = devices[0]

            self._log(f"✅ 成功連線至模擬器裝置: {self.device.serial}")
            return True
        except Exception as e:
            self._log(f"連線 ADB 異常: {e}", "ERROR")
            return False

    # =========================================================================
    # 【項目 D】ADB 通訊強韌化 (3 次重試、斷線自動重新取得連線)
    # 【項目 C】記憶體與效能保護 (明確刪除暫存 buffer 與顯式記憶體管理)
    # =========================================================================
    def capture_screen(self, max_retries: int = 3) -> Optional[np.ndarray]:
        """
        後台截圖並轉為 BGR OpenCV 矩陣。
        【項目 D - 強化】：內建 3 次重試與斷線自動重連機制。
        【項目 C - 強化】：主動釋放 raw_png 二進位緩衝區與臨時陣列，避免記憶體洩漏。
        """
        if not self.device:
            if not self.connect():
                return None

        current_serial = self.device.serial if self.device else None

        for attempt in range(1, max_retries + 1):
            raw_png = None

            # 管道 1: pure-python-adb 原生 screencap
            try:
                raw_png = self.device.screencap()
            except Exception as adb_err:
                raw_png = None

            # 管道 2: 備援 exec-out (針對 BlueStacks FAIL 0006closed 或 Socket 中斷)
            if not raw_png or len(raw_png) < 100:
                adb_bin = self.adb_bin_path or self.auto_detect_and_start_adb()
                if adb_bin and current_serial:
                    try:
                        cmd = [adb_bin, "-s", current_serial, "exec-out", "screencap", "-p"]
                        kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
                        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, **kwargs)
                        if proc.returncode == 0 and len(proc.stdout) > 100:
                            raw_png = proc.stdout
                    except Exception as sub_e:
                        raw_png = None

            # 若獲取到有效影像資料，解碼為 OpenCV BGR 並主動釋放暫存 buffer
            if raw_png and len(raw_png) >= 100:
                try:
                    img_array = np.frombuffer(raw_png, dtype=np.uint8)
                    raw_png = None  # 【用完即刪】：及時釋放原始二進位 bytes
                    img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    img_array = None  # 【用完即刪】：及時釋放中間 NumPy 陣列
                    if img_bgr is not None:
                        return img_bgr
                except Exception as dec_err:
                    self._log(f"影像解碼失敗: {dec_err}", "WARNING")
                finally:
                    raw_png = None
                    img_array = None

            # 若此輪失敗，進行重試並在需要時重新連線
            if attempt < max_retries:
                self._log(f"⚠️ 截圖通訊微斷線 (第 {attempt}/{max_retries} 次)，1 秒後重試並修復連線...", "WARNING")
                time.sleep(1.0)
                # 【項目 D】重新取得 device 物件連線
                self.connect(target_serial=current_serial)

        self._log("截圖失敗：連續 3 次重試後仍無法從裝置取得畫面緩衝區", "ERROR")
        return None

    # 別名相容
    get_screenshot = capture_screen

    def scan_text(self, screen_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """使用 RapidOCR 辨識畫面中的文字，支援 ROI 範圍裁切加速 (用完即刪、即時釋放臨時緩衝區)"""
        h, w = screen_bgr.shape[:2]
        offset_x, offset_y = 0, 0
        img_for_ocr = screen_bgr
        is_sub_slice = False

        if self.roi:
            ymin, xmin, ymax, xmax = self.roi
            x1 = int(xmin * w) if xmin <= 1.0 else int(xmin)
            y1 = int(ymin * h) if ymin <= 1.0 else int(ymin)
            x2 = int(xmax * w) if xmax <= 1.0 else int(xmax)
            y2 = int(ymax * h) if ymax <= 1.0 else int(ymax)

            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 > x1 and y2 > y1:
                img_for_ocr = screen_bgr[y1:y2, x1:x2]
                offset_x, offset_y = x1, y1
                is_sub_slice = True

        ocr_result, _ = self.ocr(img_for_ocr, box_thresh=0.3)
        parsed_boxes = []
        if ocr_result:
            for box, text, score in ocr_result:
                clean_t = text.strip()
                # 語言過濾：若不符合勾選語言則過濾 (杜絕雜訊與未選語言)
                if not self.is_text_allowed(clean_t):
                    continue

                pts = np.array(box, dtype=np.int32)
                pts[:, 0] += offset_x
                pts[:, 1] += offset_y

                cx = int(np.mean(pts[:, 0]))
                cy = int(np.mean(pts[:, 1]))
                box_w = int(np.max(pts[:, 0]) - np.min(pts[:, 0]))
                box_h = int(np.max(pts[:, 1]) - np.min(pts[:, 1]))

                # 若 OCR 恰好辨識到特殊符號，打上標記
                sym_tag = None
                if clean_t in ("✓", "✔", "√"):
                    sym_tag = "check"
                    clean_t = "[打勾]"
                elif clean_t in ("✕", "✖", "×", "X", "x") and box_w <= 90:
                    aspect = box_w / max(1, box_h)
                    if 0.65 <= aspect <= 1.5:
                        sym_tag = "cross"
                        clean_t = "[叉叉]"

                item = {
                    "text": clean_t,
                    "score": float(score),
                    "center": (cx, cy),
                    "size": (box_w, box_h),
                    "box": pts
                }
                if sym_tag:
                    item["symbol"] = sym_tag
                parsed_boxes.append(item)

        # 【特色增強】：藍底/深底白色按鈕專屬超對比度補檢
        # 遊戲中結算、確認按鈕常為深藍底白字，常規 OCR 容易因邊緣對比度不足或解析度微縮漏檢
        # 透過 R 通道天然高反差 (文字 R~250 vs 藍底 R~10) 進行局部超採樣與反相補檢
        try:
            b_chan = img_for_ocr[:, :, 0]
            r_chan = img_for_ocr[:, :, 2]
            blue_mask = (b_chan > 160) & (r_chan < 75)
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(blue_mask.astype(np.uint8))
            for i in range(1, num_labels):
                bw = stats[i, cv2.CC_STAT_WIDTH]
                bh = stats[i, cv2.CC_STAT_HEIGHT]
                b_area = stats[i, cv2.CC_STAT_AREA]
                # 篩選符合按鈕特徵的連通區域 (寬高比 > 1.8 且面積足夠)
                if bw >= 35 and bh >= 14 and (bw / max(1, bh)) >= 1.6 and b_area >= 350:
                    bx = stats[i, cv2.CC_STAT_LEFT]
                    by = stats[i, cv2.CC_STAT_TOP]
                    center_x = bx + bw // 2 + offset_x
                    center_y = by + bh // 2 + offset_y

                    # 檢查常規 OCR 是否已經檢測到該按鈕內的文字，避免重複添加
                    already_covered = False
                    for existing in parsed_boxes:
                        ecx, ecy = existing["center"]
                        if abs(ecx - center_x) < (bw // 2) and abs(ecy - center_y) < (bh // 2):
                            already_covered = True
                            break
                    if already_covered:
                        continue

                    btn_roi = img_for_ocr[by:by+bh, bx:bx+bw]
                    # R 通道反相：白色文字變為深黑，藍色背景變為純白 (白底黑字)
                    inv_gray = 255 - btn_roi[:, :, 2]
                    inv_bgr = cv2.cvtColor(inv_gray, cv2.COLOR_GRAY2BGR)
                    inv_scaled = cv2.resize(inv_bgr, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
                    inv_pad = cv2.copyMakeBorder(inv_scaled, 25, 25, 25, 25, cv2.BORDER_CONSTANT, value=[255, 255, 255])

                    btn_res, _ = self.ocr(inv_pad, box_thresh=0.2)
                    # 【用完即刪】：按鈕辨識完成立即釋放局部影像
                    del btn_roi, inv_gray, inv_bgr, inv_scaled, inv_pad

                    if btn_res:
                        for box, b_text, b_score in btn_res:
                            clean_t = b_text.strip()
                            if not clean_t or not self.is_text_allowed(clean_t):
                                continue
                            real_pts = np.array([
                                [bx + offset_x, by + offset_y],
                                [bx + bw + offset_x, by + offset_y],
                                [bx + bw + offset_x, by + bh + offset_y],
                                [bx + offset_x, by + bh + offset_y]
                            ], dtype=np.int32)
                            parsed_boxes.append({
                                "text": clean_t,
                                "score": float(b_score),
                                "center": (center_x, center_y),
                                "size": (int(bw), int(bh)),
                                "box": real_pts
                            })
            # 【用完即刪】：連通圖分析完成，立即釋放通道與遮罩矩陣
            del b_chan, r_chan, blue_mask, labels, stats
        except Exception:
            pass
        finally:
            if is_sub_slice:
                del img_for_ocr

        # 【特色增強】：特殊圖案 (打勾、叉叉/關閉) 視覺偵測與融合
        try:
            symbols = self.detect_symbols(screen_bgr, target_type="all")
            for sym_item in symbols:
                scx, scy = sym_item["center"]
                matched_exist = None
                for exist in parsed_boxes:
                    ecx, ecy = exist["center"]
                    if abs(ecx - scx) < 22 and abs(ecy - scy) < 22:
                        matched_exist = exist
                        break
                if matched_exist:
                    # 如果現有 OCR 框僅辨識出 V、X、x、r、1、7 等單一模糊字元，升級為明確符號
                    ex_t = matched_exist.get("text", "")
                    if ex_t in ("V", "v", "X", "x", "r", "1", "7", "+", "-") or not matched_exist.get("symbol"):
                        matched_exist["text"] = sym_item["text"]
                        matched_exist["symbol"] = sym_item["symbol"]
                        matched_exist["score"] = max(matched_exist["score"], sym_item["score"])
                else:
                    parsed_boxes.append(sym_item)
        except Exception:
            pass

        return parsed_boxes

    # =========================================================================
    # 【項目 A】文字識別容錯（模糊比對與空白標點放寬）
    # =========================================================================
    @staticmethod
    def _clean_str(s: str) -> str:
        """過濾文字中的所有空格與常見標點符號並轉大寫，並進行常用繁簡字正規化，使文字比對更寬鬆精確"""
        for ch in [" ", "\t", "\n", "\r", "　", "，", ",", "。", ".", "！", "!", "？", "?", "-", "_", ":", "："]:
            s = s.replace(ch, "")
        s = s.strip().upper()
        # 符號正規化 (打勾與叉叉)
        for sym in ["✔", "√"]:
            s = s.replace(sym, "✓")
        for sym in ["✖", "×"]:
            s = s.replace(sym, "✕")
        # 常見遊戲字詞繁簡歸一化 (使「確定」與「确定」、「下一頁」與「下一页」能雙向精確對應)
        s = s.translate(str.maketrans({
            "確": "确", "頁": "页", "認": "认", "點": "点", "開": "开",
            "關": "关", "閉": "闭", "結": "结", "賽": "赛", "聯": "联",
            "獲": "获", "獎": "奖", "勵": "励", "選": "选", "擇": "择",
            "進": "进", "國": "国", "畫": "画", "幾": "几", "續": "续"
        }))
        return s

    def _is_text_matched(self, target_kw: str, recognized_text: str, similarity_threshold: float = 0.70) -> Tuple[bool, float]:
        """
        多重文字比對機制（已放寬空白與標點干擾）：
        1. 原文精確比對：若 target_kw 在 recognized_text 中，直接判定為精確命中 (1.0)。
        2. 特殊圖案對齊：支援 [打勾]、✓、[叉叉]、✕、X 之直接對應。
        3. 去除空白/標點精確比對：處理 OCR 中間誤插入空格（如 "開 始" vs "開始"）。
        4. 滑動視窗模糊比對：使用 difflib.SequenceMatcher，相似度 >= 0.70 視為命中。
        """
        kw = target_kw.strip()
        rec = recognized_text.strip()
        if not kw or not rec:
            return False, 0.0

        # 特殊符號優先對齊
        if kw in ("[打勾]", "✓") and (rec in ("[打勾]", "✓", "✔", "√") or "[打勾]" in rec):
            return True, 1.0
        if kw in ("[叉叉]", "✕", "X", "x") and (rec in ("[叉叉]", "✕", "✖", "×", "X", "x") or "[叉叉]" in rec):
            return True, 1.0

        clean_kw = self._clean_str(kw)
        clean_rec = self._clean_str(rec)
        if not clean_kw or not clean_rec:
            return False, 0.0

        # 【寫死邏輯】：若目標關鍵字為 4 個字 (例如 AUTO)，嚴格限制辨識文字長度不可超過 4 個字
        # 避免因包含字串或高相似度將長字串 (如 AUTOPLAYING、AUTOXNG) 誤判為 AUTO
        if len(clean_kw) == 4 and len(clean_rec) > 4:
            return False, 0.0

        # 1. 優先原始字串精確子字串比對
        if kw in rec:
            return True, 1.0

        # 2. 去除所有空格與標點符號後比對 (放寬空格與符號干擾)
        # 只有當目標關鍵字存在於辨識文字中才算精確命中 (嚴禁反向 clean_rec in clean_kw，避免單字誤判)
        if clean_kw in clean_rec:
            return True, 1.0

        len_kw = len(clean_kw)
        len_rec = len(clean_rec)

        # 3. 模糊比對：若目標字數小於 2 字，不啟用模糊比對，避免誤觸
        if len_kw < 2:
            return False, 0.0

        # 若文字長度小於等於關鍵字長度，直接計算整體相似度
        if len_rec <= len_kw:
            ratio = difflib.SequenceMatcher(None, clean_kw, clean_rec).ratio()
            if ratio >= similarity_threshold:
                return True, ratio
            return False, ratio

        # 4. 滑動視窗模糊比對（長度相當的視窗滑動）
        best_ratio = 0.0
        for window_len in [len_kw, len_kw + 1]:
            for i in range(len_rec - window_len + 1):
                sub = clean_rec[i:i + window_len]
                ratio = difflib.SequenceMatcher(None, clean_kw, sub).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                if ratio >= similarity_threshold:
                    return True, ratio

        return False, best_ratio

    def _is_text_excluded(
        self,
        item: Dict[str, Any],
        exclude_keywords: List[str],
        detected_items: Optional[List[Dict[str, Any]]] = None,
        roi_box: Optional[Tuple[int, int, int, int]] = None
    ) -> Tuple[bool, str]:
        """
        檢查文字項目是否命中「排除字元 (Negative Keywords)」。
        1. 項目自身文字檢查：若辨識文字包含或高度符合任何排除關鍵字，則排除（不點擊）。
        2. 局部鄰近檢查：若同一按鈕/ROI範圍或鄰近位置（同一UI元件範圍）出現排除關鍵字，亦排除。
        回傳: (是否排除, 命中的排除字元)
        """
        if not exclude_keywords or not item:
            return False, ""

        raw_item_text = item.get("text", "")
        clean_item_text = self._clean_str(raw_item_text)

        for ex_kw in exclude_keywords:
            ex_kw_str = str(ex_kw).strip()
            if not ex_kw_str:
                continue

            clean_ex = self._clean_str(ex_kw_str)
            if not clean_ex:
                continue

            # 1. 自身文字精確包含排除詞（例如辨識到「AUTOPLAYING」包含了排除詞「AUTOPLAYING」或「PLAYING」）
            if clean_ex in clean_item_text:
                return True, ex_kw_str

            # 2. 自身文字模糊匹配排除詞（處理 OCR 辨識失誤如 AUT0PLAYING、AUTOXNG 等）
            # 注意：排除詞長度若大於辨識文字 (如 clean_ex='AUTOXNG'(7字) vs item='AUTO'(4字))，
            # 絕對不能把短的按鈕文字「AUTO」當成排除詞！只有文字長度足夠長時才做模糊匹配。
            if len(clean_item_text) >= len(clean_ex) - 1:
                matched, ratio = self._is_text_matched(clean_ex, clean_item_text, similarity_threshold=0.75)
                if matched and ratio >= 0.75:
                    return True, ex_kw_str

        # 3. 檢查水平緊密相鄰文字（僅處理同一按鈕被 OCR 橫向拆分為兩段的情況，例如「AUTO」與「PLAY」）
        if detected_items:
            icx, icy = item.get("center", (0, 0))
            bw, bh = item.get("size", (50, 30))

            for other in detected_items:
                if other is item:
                    continue
                ocx, ocy = other.get("center", (0, 0))
                obw, obh = other.get("size", (50, 30))

                # 垂直方向必須幾乎在同一水平線（字高範圍內），且水平相隔極近（同一行被切開）
                vert_overlap = abs(icy - ocy) <= max(bh, obh) * 0.6
                horiz_close = abs(icx - ocx) <= (bw // 2 + obw // 2 + 35)

                if vert_overlap and horiz_close:
                    raw_other = other.get("text", "")
                    clean_other = self._clean_str(raw_other)
                    for ex_kw in exclude_keywords:
                        ex_kw_str = str(ex_kw).strip()
                        if not ex_kw_str:
                            continue
                        clean_ex = self._clean_str(ex_kw_str)
                        if clean_ex and clean_ex in clean_other:
                            return True, ex_kw_str
                        if len(clean_other) >= len(clean_ex) - 1:
                            matched, ratio = self._is_text_matched(clean_ex, clean_other, similarity_threshold=0.75)
                            if matched and ratio >= 0.75:
                                return True, ex_kw_str

        return False, ""

    def find_target_button(
        self,
        detected_items: List[Dict[str, Any]],
        keywords: Optional[List[str]] = None
    ) -> Optional[Tuple[str, int, int, float]]:
        """依照優先順序檢索關鍵字（支援模糊比對），並計算隨機微偏移點擊座標"""
        search_words = keywords if keywords is not None else self.target_keywords

        for kw in search_words:
            for item in detected_items:
                if item["score"] < self.confidence_threshold:
                    continue

                matched, ratio = self._is_text_matched(kw, item["text"], similarity_threshold=0.75)
                if matched:
                    cx, cy = item["center"]
                    bw, bh = item["size"]

                    # 隨機偏移 ±3~5 像素防止固定點擊被偵測
                    off_x = min(max(3, bw // 8), 6)
                    off_y = min(max(3, bh // 8), 5)
                    rand_x = cx + random.randint(-off_x, off_x)
                    rand_y = cy + random.randint(-off_y, off_y)

                    return item["text"], rand_x, rand_y, item["score"]

        return None

    # =========================================================================
    # 【項目 D】點擊通訊強韌化 (3 次重試、斷線自動重連)
    # =========================================================================
    def tap(self, x: int, y: int, delay_range: Tuple[float, float] = (0.04, 0.08), max_retries: int = 3) -> bool:
        """
        後台發送點擊並加入微量動態隨機防抖延遲 (預設 40ms ~ 80ms)。
        注意：步驟的換頁冷卻時間由步驟邏輯負責，tap() 僅負責底層物理點擊，做到 0 毫秒極速反應。
        【項目 D - 強化】：遭遇 Socket 斷開時自動重試最多 3 次，並自動恢復 ADB 裝置連線。
        """
        if not self.device:
            if not self.connect():
                return False

        tap_success = False
        current_serial = self.device.serial if self.device else None

        for attempt in range(1, max_retries + 1):
            # 管道 1: pure-python-adb device.shell
            try:
                self.device.shell(f"input tap {x} {y}")
                tap_success = True
                break
            except Exception as e:
                # 管道 2: 備援 adb 二進位檔直接下指令
                adb_bin = self.adb_bin_path or self.auto_detect_and_start_adb()
                if adb_bin and current_serial:
                    try:
                        res = subprocess.run(
                            [adb_bin, "-s", current_serial, "shell", f"input tap {x} {y}"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=5
                        )
                        if res.returncode == 0:
                            tap_success = True
                            break
                    except Exception:
                        pass

            if attempt < max_retries:
                time.sleep(1.0)
                self.connect(target_serial=current_serial)

        if tap_success:
            sleep_time = random.uniform(delay_range[0], delay_range[1])
            time.sleep(sleep_time)
            return True
        else:
            self._log(f"點擊指令失敗 ({x}, {y}): 連續 {max_retries} 次重試皆超時或中斷", "ERROR")
            return False

    def stop(self) -> None:
        """請求停止自動循環"""
        self.is_running = False
        self._log("已發出停止信號...")

    # =========================================================================
    # 【最高層級】優先字元檢查 (Top-Priority Override)
    # =========================================================================
    def _calc_action_coord(
        self,
        action: str,
        item: Dict[str, Any],
        step: Dict[str, Any],
        screen_shape: Tuple[int, int]
    ) -> Tuple[int, int]:
        """
        根據步驟設定的動作模式計算最終點擊座標：
        - 點擊詞條 / 點擊字元 (預設)：點擊辨識文字中心 (含微隨機防作弊防抖)
        - 自訂座標 / 自訂特定區塊：點擊自訂的 (custom_x, custom_y)
        - 右下角區域：點擊螢幕 (86%, 86%)
        - 中央區域：點擊螢幕 (50%, 50%)
        - 右上角 (Skip)：點擊螢幕 (90%, 12%)
        - 右半側中央：點擊螢幕 (82%, 50%)
        """
        img_h, img_w = screen_shape
        act = str(action).strip() if action else "點擊詞條"
        custom_x = int(step.get("custom_x", step.get("repeat_custom_x", 0)))
        custom_y = int(step.get("custom_y", step.get("repeat_custom_y", 0)))

        if act in ("custom_coord", "自訂座標", "自訂特定區塊"):
            if custom_x > 0 and custom_y > 0:
                return custom_x + random.randint(-4, 4), custom_y + random.randint(-4, 4)
            return custom_x, custom_y
        elif act == "右下角區域":
            bx, by = int(img_w * 0.86), int(img_h * 0.86)
            return bx + random.randint(-6, 6), by + random.randint(-6, 6)
        elif act == "中央區域":
            bx, by = int(img_w * 0.50), int(img_h * 0.50)
            return bx + random.randint(-6, 6), by + random.randint(-6, 6)
        elif act == "右上角 (Skip)":
            bx, by = int(img_w * 0.90), int(img_h * 0.12)
            return bx + random.randint(-6, 6), by + random.randint(-6, 6)
        elif act == "右半側中央":
            bx, by = int(img_w * 0.82), int(img_h * 0.50)
            return bx + random.randint(-6, 6), by + random.randint(-6, 6)
        else:
            # 點擊詞條 / 點擊字元 (預設)
            cx, cy = item["center"]
            bw, bh = item.get("size", (40, 20))
            off_x = min(max(3, bw // 8), 6)
            off_y = min(max(3, bh // 8), 5)
            rx = cx + random.randint(-off_x, off_x)
            ry = cy + random.randint(-off_y, off_y)
            return rx, ry

    def match_priority_step(
        self,
        detected_items: List[Dict[str, Any]],
        step: Optional[Dict[str, Any]],
        screen_shape: Optional[Tuple[int, int]] = None
    ) -> Optional[Tuple[str, int, int, float, Any]]:
        """
        比對單一優先動作是否命中畫面上的文字。
        支援 ROI 區域過濾、精確匹配、模糊匹配、點擊詞條或自訂特定區塊/座標。
        若命中，回傳 (命中文字, 點擊X, 點擊Y, 信心度, 文字框, 相似度)
        """
        if not step or not step.get("enabled", True):
            return None

        raw_kws = step.get("keywords", [])
        if isinstance(raw_kws, str):
            keywords = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
        elif isinstance(raw_kws, (list, tuple)):
            keywords = [str(k).strip() for k in raw_kws if str(k).strip()]
        else:
            keywords = []

        raw_ex_kws = step.get("exclude_keywords", [])
        if isinstance(raw_ex_kws, str):
            exclude_keywords = [k.strip() for k in raw_ex_kws.replace("，", ",").split(",") if k.strip()]
        elif isinstance(raw_ex_kws, (list, tuple)):
            exclude_keywords = [str(k).strip() for k in raw_ex_kws if str(k).strip()]
        else:
            exclude_keywords = []

        target_type = str(step.get("target_type", "📝 僅文字"))
        is_check = ("打勾" in target_type or "check" in target_type.lower())
        is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)
        is_symbol_target = is_check or is_cross

        if not detected_items:
            return None
        if not keywords and not is_symbol_target:
            return None

        if screen_shape:
            img_h, img_w = screen_shape[0], screen_shape[1]
        else:
            img_h, img_w = 1080, 1920
        action = step.get("action", "click_text")

        step_roi = step.get("roi", None)
        if isinstance(step_roi, str):
            step_roi = {
                "右下角區域": (0.45, 0.45, 1.0, 1.0),
                "右半側螢幕": (0.0, 0.45, 1.0, 1.0),
                "下半部區域": (0.50, 0.0, 1.0, 1.0),
                "中央區域": (0.25, 0.25, 0.75, 0.75),
            }.get(step_roi, (0.0, 0.0, 1.0, 1.0))

        if step_roi and isinstance(step_roi, (list, tuple)) and len(step_roi) == 4:
            ymin, xmin, ymax, xmax = step_roi
            rx1 = int(xmin * img_w) if xmin <= 1.0 else int(xmin)
            ry1 = int(ymin * img_h) if ymin <= 1.0 else int(ymin)
            rx2 = int(xmax * img_w) if xmax <= 1.0 else int(xmax)
            ry2 = int(ymax * img_h) if ymax <= 1.0 else int(ymax)
        else:
            rx1, ry1, rx2, ry2 = 0, 0, img_w, img_h

        roi_box = (rx1, ry1, rx2, ry2)

        # 0. 特殊圖案比對 (打勾 ✓ / 叉叉 ✕)
        if is_check or is_cross:
            for item in detected_items:
                if item["score"] < max(0.50, self.confidence_threshold - 0.10):
                    continue
                cx, cy = item["center"]
                if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                    continue
                is_ex, _ = self._is_text_excluded(item, exclude_keywords, detected_items, roi_box)
                if is_ex:
                    continue
                sym = item.get("symbol")
                txt = item.get("text", "")
                if is_check and (sym == "check" or txt in ("[打勾]", "✓", "✔", "√") or (len(txt) == 1 and txt.upper() == "V")):
                    tx, ty = self._calc_action_coord(action, item, step, (img_h, img_w))
                    return item["text"], tx, ty, item["score"], item["box"], 1.0
                if is_cross and (sym == "cross" or txt in ("[叉叉]", "✕", "✖", "×", "X", "x")):
                    tx, ty = self._calc_action_coord(action, item, step, (img_h, img_w))
                    return item["text"], tx, ty, item["score"], item["box"], 1.0

        # 第一階段：精確關鍵字比對 (Exact Match)
        for kw in keywords:
            for item in detected_items:
                if item["score"] < self.confidence_threshold:
                    continue
                cx, cy = item["center"]
                if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                    continue

                # 排除字元檢查 (若命中排除詞則略過)
                is_ex, ex_match = self._is_text_excluded(item, exclude_keywords, detected_items, roi_box)
                if is_ex:
                    continue

                matched, ratio = self._is_text_matched(kw, item["text"], similarity_threshold=1.0)
                if matched and ratio >= 0.99:
                    tx, ty = self._calc_action_coord(action, item, step, (img_h, img_w))
                    return item["text"], tx, ty, item["score"], item["box"], float(ratio)

        # 第二階段：模糊容錯比對 (Fuzzy Match >= 0.70)
        for kw in keywords:
            for item in detected_items:
                if item["score"] < self.confidence_threshold:
                    continue
                cx, cy = item["center"]
                if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                    continue

                # 排除字元檢查 (若命中排除詞則略過)
                is_ex, ex_match = self._is_text_excluded(item, exclude_keywords, detected_items, roi_box)
                if is_ex:
                    continue

                matched, ratio = self._is_text_matched(kw, item["text"], similarity_threshold=0.70)
                if matched:
                    tx, ty = self._calc_action_coord(action, item, step, (img_h, img_w))
                    return item["text"], tx, ty, item["score"], item["box"], float(ratio)

        return None

    def match_all_priority_steps(
        self,
        detected_items: List[Dict[str, Any]],
        priority_steps: List[Dict[str, Any]],
        screen_shape: Optional[Tuple[int, int]] = None
    ) -> Optional[Tuple[Dict[str, Any], Tuple[str, int, int, float, Any]]]:
        """
        【所有優先步驟同級評判】：
        不再以 if/elif 順序固定先到先得，而是同時檢測所有啟用的優先步驟。
        若有多個優先動作同時出現在畫面中：
        1. 優先選取「精確命中 (ratio >= 0.99)」者。
        2. 若同為精確命中或同為模糊命中，優先選取文字辨識信心度 (score) 最高者。
        3. 若信心度相同，依照相似度 (ratio) 最高者排序。
        回傳: (命中之優先步驟字典, match_priority_step 回傳的 (text, x, y, score, box)) 或 None
        """
        if not priority_steps or not detected_items:
            return None

        candidates = []
        for p_step in priority_steps:
            if not p_step.get("enabled", True):
                continue
            res = self.match_priority_step(detected_items, p_step, screen_shape)
            if res:
                # res: (p_text, px, py, p_score, p_box, ratio)
                p_text, px, py, p_score, p_box, ratio = res
                candidates.append((p_step, (p_text, px, py, p_score, p_box), ratio, p_score))

        if not candidates:
            return None

        # 排序權重：
        # key: (是否精確命中 [1/0], 相似度 ratio, 信心度 score)
        candidates.sort(key=lambda c: (1 if c[2] >= 0.99 else 0, c[2], c[3]), reverse=True)
        best_p_step, best_match_tuple, _, _ = candidates[0]
        return best_p_step, best_match_tuple

    def match_priority(
        self,
        detected_items: List[Dict[str, Any]],
        priority_config: Optional[Dict[str, Any]],
        screen_shape: Optional[Tuple[int, int]] = None
    ) -> Optional[Tuple[str, int, int, float, Any]]:
        res = self.match_priority_step(detected_items, priority_config, screen_shape)
        if res:
            return res[0], res[1], res[2], res[3], res[4]
        return None

    # =========================================================================
    # 【核心底層】自訂步驟文字識別 (精確優先、區域限定、狀態優先順序)
    # =========================================================================
    def match_custom_steps(
        self,
        detected_items: List[Dict[str, Any]],
        steps: List[Dict[str, Any]],
        screen_shape: Optional[Tuple[int, int]] = None,
        expected_step_idx: Optional[int] = None
    ) -> Optional[Tuple[Dict[str, Any], str, int, int, float]]:
        """
        比對使用者自訂步驟列表。
        底層策略：
        1. 優先比對「當前期待的步驟」(expected_step_idx)，避免畫面上有殘留舊文字時發生步驟錯亂。
        2. 每個步驟嚴格限制在設定的「偵測範圍 (ROI)」內比對文字。
        3. 先進行「精確關鍵字比對」，全部步驟都沒精確命中才進行「模糊容錯比對」，避免錯按。
        4. 點擊座標取自命中文字方框中心點 (center)，並加上隨機防偵測微偏。
        回傳: (步驟字典, 命中文字, 點擊X, 點擊Y, 信心度)
        """
        if screen_shape:
            img_h, img_w = screen_shape[0], screen_shape[1]
        else:
            img_h, img_w = 1080, 1920
        if not steps or not detected_items:
            return None

        # 排序步驟：優先檢查當前期待步驟，若無則按清單順序
        ordered_steps = []
        if expected_step_idx is not None and 0 <= expected_step_idx < len(steps):
            exp_step = steps[expected_step_idx]
            if exp_step.get("enabled", True):
                ordered_steps.append(exp_step)
            for idx, s in enumerate(steps):
                if idx != expected_step_idx and s.get("enabled", True):
                    ordered_steps.append(s)
        else:
            ordered_steps = [s for s in steps if s.get("enabled", True)]

        # --- 第一階段：精確比對 (Exact Match) ---
        for step in ordered_steps:
            raw_kws = step.get("keywords", [])
            if isinstance(raw_kws, str):
                keywords = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
            elif isinstance(raw_kws, (list, tuple)):
                keywords = [str(k).strip() for k in raw_kws if str(k).strip()]
            else:
                keywords = []

            raw_ex = step.get("exclude_keywords", [])
            if isinstance(raw_ex, str):
                exclude_keywords = [k.strip() for k in raw_ex.replace("，", ",").split(",") if k.strip()]
            elif isinstance(raw_ex, (list, tuple)):
                exclude_keywords = [str(k).strip() for k in raw_ex if str(k).strip()]
            else:
                exclude_keywords = []

            step_roi = step.get("roi", None)
            if isinstance(step_roi, str):
                step_roi = {
                    "右下角區域": (0.45, 0.45, 1.0, 1.0),
                    "右半側螢幕": (0.0, 0.45, 1.0, 1.0),
                    "下半部區域": (0.50, 0.0, 1.0, 1.0),
                    "中央區域": (0.25, 0.25, 0.75, 0.75),
                }.get(step_roi, (0.0, 0.0, 1.0, 1.0))

            if step_roi and isinstance(step_roi, (list, tuple)) and len(step_roi) == 4:
                ymin, xmin, ymax, xmax = step_roi
                rx1 = int(xmin * img_w) if xmin <= 1.0 else int(xmin)
                ry1 = int(ymin * img_h) if ymin <= 1.0 else int(ymin)
                rx2 = int(xmax * img_w) if xmax <= 1.0 else int(xmax)
                ry2 = int(ymax * img_h) if ymax <= 1.0 else int(ymax)
            else:
                rx1, ry1, rx2, ry2 = 0, 0, img_w, img_h

            roi_box = (rx1, ry1, rx2, ry2)

            target_type = str(step.get("target_type", "📝 僅文字"))
            is_check = ("打勾" in target_type or "check" in target_type.lower())
            is_cross = ("叉叉" in target_type or "cross" in target_type.lower() or "關閉" in target_type)

            # 特殊圖案比對 (打勾 ✓ / 叉叉 ✕)
            if is_check or is_cross:
                for item in detected_items:
                    if item["score"] < max(0.50, self.confidence_threshold - 0.10):
                        continue
                    cx, cy = item["center"]
                    if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                        continue
                    is_ex, _ = self._is_text_excluded(item, exclude_keywords, detected_items, roi_box)
                    if is_ex:
                        continue
                    sym = item.get("symbol")
                    txt = item.get("text", "")
                    if is_check and (sym == "check" or txt in ("[打勾]", "✓", "✔", "√") or (len(txt) == 1 and txt.upper() == "V")):
                        action = step.get("action", "click_text")
                        tx, ty = self._calc_action_coord(action, item, step, (img_h, img_w))
                        return step, item["text"], tx, ty, item["score"]
                    if is_cross and (sym == "cross" or txt in ("[叉叉]", "✕", "✖", "×", "X", "x")):
                        action = step.get("action", "click_text")
                        tx, ty = self._calc_action_coord(action, item, step, (img_h, img_w))
                        return step, item["text"], tx, ty, item["score"]

            for kw in keywords:
                for item in detected_items:
                    if item["score"] < self.confidence_threshold:
                        continue

                    cx, cy = item["center"]
                    if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                        continue

                    # 排除字元檢查 (若命中排除詞則略過)
                    is_ex, ex_match = self._is_text_excluded(item, exclude_keywords, detected_items, roi_box)
                    if is_ex:
                        continue

                    matched, ratio = self._is_text_matched(kw, item["text"], similarity_threshold=1.0)
                    if matched and ratio >= 0.99:  # 精確命中
                        action = step.get("action", "click_text")
                        tx, ty = self._calc_action_coord(action, item, step, (img_h, img_w))
                        return step, item["text"], tx, ty, item["score"]

        # --- 第二階段：模糊容錯比對 (Fuzzy Match >= 0.70) ---
        for step in ordered_steps:
            raw_kws = step.get("keywords", [])
            if isinstance(raw_kws, str):
                keywords = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
            elif isinstance(raw_kws, (list, tuple)):
                keywords = [str(k).strip() for k in raw_kws if str(k).strip()]
            else:
                keywords = []

            raw_ex = step.get("exclude_keywords", [])
            if isinstance(raw_ex, str):
                exclude_keywords = [k.strip() for k in raw_ex.replace("，", ",").split(",") if k.strip()]
            elif isinstance(raw_ex, (list, tuple)):
                exclude_keywords = [str(k).strip() for k in raw_ex if str(k).strip()]
            else:
                exclude_keywords = []

            step_roi = step.get("roi", None)
            if isinstance(step_roi, str):
                step_roi = {
                    "右下角區域": (0.45, 0.45, 1.0, 1.0),
                    "右半側螢幕": (0.0, 0.45, 1.0, 1.0),
                    "下半部區域": (0.50, 0.0, 1.0, 1.0),
                    "中央區域": (0.25, 0.25, 0.75, 0.75),
                }.get(step_roi, (0.0, 0.0, 1.0, 1.0))

            if step_roi and isinstance(step_roi, (list, tuple)) and len(step_roi) == 4:
                ymin, xmin, ymax, xmax = step_roi
                rx1 = int(xmin * img_w) if xmin <= 1.0 else int(xmin)
                ry1 = int(ymin * img_h) if ymin <= 1.0 else int(ymin)
                rx2 = int(xmax * img_w) if xmax <= 1.0 else int(xmax)
                ry2 = int(ymax * img_h) if ymax <= 1.0 else int(ymax)
            else:
                rx1, ry1, rx2, ry2 = 0, 0, img_w, img_h

            roi_box = (rx1, ry1, rx2, ry2)

            for kw in keywords:
                for item in detected_items:
                    if item["score"] < self.confidence_threshold:
                        continue

                    cx, cy = item["center"]
                    if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                        continue

                    # 排除字元檢查 (若命中排除詞則略過)
                    is_ex, ex_match = self._is_text_excluded(item, exclude_keywords, detected_items, roi_box)
                    if is_ex:
                        continue

                    matched, ratio = self._is_text_matched(kw, item["text"], similarity_threshold=0.70)
                    if matched:
                        action = step.get("action", "click_text")
                        tx, ty = self._calc_action_coord(action, item, step, (img_h, img_w))
                        return step, item["text"], tx, ty, item["score"]

        return None

    # =========================================================================
    # 【項目 B】突發異常彈窗全域攔截（Global Interceptor）
    # =========================================================================
    def check_and_handle_global_popups(
        self,
        detected_items: List[Dict[str, Any]],
        screen_shape: Tuple[int, int]
    ) -> bool:
        """
        輕量掃描全域中斷關鍵字（連線中斷、網路異常、重新連線等）。
        若偵測到異常彈窗，優先點擊確定/重試按鈕排除干擾，不破壞原步驟狀態機。
        回傳: True 表示攔截並處理了異常彈窗，False 表示未發現異常彈窗
        """
        img_h, img_w = screen_shape[0], screen_shape[1]
        found_popup_keyword = None

        # 1. 檢查畫面中是否出現彈窗中斷關鍵字
        for item in detected_items:
            for kw in self.popup_keywords:
                matched, _ = self._is_text_matched(kw, item["text"], similarity_threshold=0.8)
                if matched:
                    found_popup_keyword = item["text"]
                    break
            if found_popup_keyword:
                break

        if not found_popup_keyword:
            return False

        self._log(f"🚨 [全域攔截器] 捕捉到突發異常彈窗:「{found_popup_keyword}」！嘗試自動復原...", "WARNING")

        # 2. 尋找彈窗上的「確認 / 確定 / 重試」等按鈕
        confirm_btn = None
        for kw in self.popup_confirm_keywords:
            for item in detected_items:
                matched, _ = self._is_text_matched(kw, item["text"], similarity_threshold=0.8)
                if matched:
                    confirm_btn = item
                    break
            if confirm_btn:
                break

        if confirm_btn:
            cx, cy = confirm_btn["center"]
            self._log(f"🛡️ [全域攔截器] 點擊彈窗排除按鈕:「{confirm_btn['text']}」({cx}, {cy})")
            self.tap(cx, cy, delay_range=(1.5, 2.5))
        else:
            # 備援：若未標註文字按鈕，點擊畫面正中央偏下方一般確認按鈕常見位置
            fallback_x, fallback_y = int(img_w * 0.5), int(img_h * 0.65)
            self._log(f"🛡️ [全域攔截器] 未辨識到文字按鈕，點擊常見確認區域 ({fallback_x}, {fallback_y})", "WARNING")
            self.tap(fallback_x, fallback_y, delay_range=(1.5, 2.5))

        time.sleep(1.0)
        return True

    # =========================================================================
    # 主迴圈邏輯 (整合模糊比對、全域攔截、記憶體釋放與退避延遲)
    # =========================================================================
    def run_loop(
        self,
        poll_interval: float = 2.5,
        max_idle_cycles: int = 12,
        custom_steps: Optional[List[Dict[str, Any]]] = None,
        idle_strategy: str = "wait",
        fallback_coord: Optional[Tuple[int, int]] = None,
        idle_tap_config: Optional[Dict[str, Any]] = None,
        priority_config: Optional[Dict[str, Any]] = None,
        priority_steps: Optional[List[Dict[str, Any]]] = None,
        watchdog_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        循環主邏輯，支援使用者完全自訂的動作步驟列表與未偵測到動作時的處理策略。
        priority_steps: 最高層級優先動作清單 (依序判斷 if 優先1 elif 優先2 ... else 平常動作)
        idle_tap_config: 等待時執行連續點擊特定區塊
        watchdog_config: 進階看門狗防卡死設定 {"enabled": True, "seconds": 60}
        """
        self.is_running = True
        self._watchdog_triggered = False
        self._log(f"【自訂步驟流程】自動刷關任務開始運行！(無動作策略: {idle_strategy})")

        # 看門狗防卡死守護設定
        wd_enabled = False
        wd_seconds = 60
        if watchdog_config and watchdog_config.get("enabled", False):
            wd_enabled = True
            wd_seconds = max(10, int(watchdog_config.get("seconds", 60)))
            self._log(f"🛡️ [防卡死守護] 已啟動！若連續 {wd_seconds} 秒無任何動作，將自動停止並重新開啟腳本。")

        last_active_time = time.time()

        # 整合優先動作清單 (支援多個優先條件 if / elif / ...)
        p_list = []
        if priority_steps:
            p_list.extend(priority_steps)
        elif priority_config:
            p_list.append(priority_config)
        active_priority_steps = [p for p in p_list if p.get("enabled", True)]

        # 若未傳入自訂步驟，則使用預設關鍵字清單
        default_steps = [
            {"name": "預設按鈕", "keywords": self.target_keywords, "delay_min": 2.0, "delay_max": 3.5, "enabled": True}
        ]
        active_steps = custom_steps if custom_steps is not None else default_steps

        # 當前進度指針：依序期待執行的步驟索引與進入等待的時間
        current_step_idx = 0
        step_wait_start_time = time.time()
        consecutive_idle = 0
        loop_counter = 0

        while self.is_running:
            loop_counter += 1

            # 【項目 C】記憶體防護：每 10 輪主動執行輕量垃圾回收，防止長時高頻運行記憶體增長
            if loop_counter % 10 == 0:
                gc.collect(1)

            screen = self.capture_screen()
            if screen is None:
                time.sleep(1.0)
                continue

            img_h, img_w = screen.shape[:2]
            detected = self.scan_text(screen)

            # 【項目 B】執行步驟前，優先呼叫全域攔截器排除突發彈窗
            if self.check_and_handle_global_popups(detected, (img_h, img_w)):
                last_active_time = time.time()
                del screen, detected  # 【用完即刪】：及時釋放影像與辨識陣列
                continue

            # =================================================================
            # 【最高層級】優先動作清單檢查 (所有優先步驟同等優先級同時評判)
            # =================================================================
            p_hit = None
            if active_priority_steps:
                p_hit = self.match_all_priority_steps(detected, active_priority_steps, screen_shape=(img_h, img_w))

            if p_hit:
                last_active_time = time.time()
                p_step, (p_text, px, py, p_score, p_box) = p_hit
                p_name = p_step.get("name", "優先動作")
                p_idx = (active_priority_steps.index(p_step) + 1) if p_step in active_priority_steps else 1
                p_tag = f"優先 {p_idx}: {p_name}"
                p_delay = float(p_step.get("delay", 1.0))
                d_min = max(0.2, p_delay - 0.2)
                d_max = p_delay + 0.3
                keep_while = p_step.get("while_condition", True)
                max_p_cycles = int(p_step.get("max_continuous", 25))

                p_count = 0
                while self.is_running and p_count < max_p_cycles:
                    p_count += 1
                    self._log(f"⭐ [{p_tag}] 命中「{p_text}」({p_score:.2f}) → 優先點擊 ({px}, {py})")

                    rep_enabled = p_step.get("repeat_enabled", False)
                    # 1. 【0ms 極速下發 ADB 指令】：偵測到優先字元第一時間秒按！
                    self.tap(px, py, delay_range=(0.04, 0.08))

                    # 2. 【0ms 立即同步呈現】：點擊下發瞬間，GUI 預覽視窗同步標記呈現
                    if self.on_frame_callback and self.is_running:
                        try:
                            self.on_frame_callback(screen, detected, (p_step, p_text, px, py, p_score))
                        except Exception:
                            pass

                    # 📱 若設定了 Telegram 通知，非同步發送通知
                    tg_cfg = p_step.get("telegram", {})
                    if tg_cfg and tg_cfg.get("enabled", False):
                        tg_tok = tg_cfg.get("token", "")
                        tg_cid = tg_cfg.get("chat_id", "")
                        tg_msg = tg_cfg.get("message", "")
                        self.send_telegram_notify(tg_tok, tg_cid, tg_msg, step_name=p_tag, hit_text=p_text)

                    # 命中後連點過渡動作 或 步驟自訂換頁延遲
                    if rep_enabled and self.is_running:
                        rep_mode = p_step.get("repeat_mode", "until_next")
                        rep_area = p_step.get("repeat_area", "右下角區域")
                        rep_count = int(p_step.get("repeat_count", 15))
                        rep_speed = float(p_step.get("repeat_speed", 0.3))
                        min_spd = max(0.08, rep_speed - 0.05)
                        max_spd = rep_speed + 0.05

                        if rep_area == "右下角區域":
                            bx, by = int(img_w * 0.86), int(img_h * 0.86)
                        elif rep_area == "中央區域":
                            bx, by = int(img_w * 0.50), int(img_h * 0.50)
                        elif rep_area == "右上角 (Skip)":
                            bx, by = int(img_w * 0.90), int(img_h * 0.12)
                        elif rep_area == "右半側中央":
                            bx, by = int(img_w * 0.82), int(img_h * 0.50)
                        elif "自訂" in rep_area:
                            cust_coord = p_step.get("repeat_custom_coord")
                            if cust_coord and isinstance(cust_coord, (list, tuple)) and len(cust_coord) == 2:
                                bx, by = int(cust_coord[0]), int(cust_coord[1])
                            else:
                                bx = int(p_step.get("repeat_custom_x", px))
                                by = int(p_step.get("repeat_custom_y", py))
                        else:
                            bx, by = px, py

                        if rep_mode == "until_next":
                            self._log(f"⚡ [{p_tag}] 正在連續點擊「{rep_area}」跳過過場 (直到下一步驟出現)...")
                            tap_count = 0
                            # 解除連點次數上限：棒球比賽整場進行時持續點擊，直到常規步驟或其它優先動作出現
                            while self.is_running:
                                rx = bx + random.randint(-12, 12)
                                ry = by + random.randint(-12, 12)
                                self.tap(rx, ry, delay_range=(min_spd, max_spd))
                                tap_count += 1

                                if tap_count % 4 == 0:
                                    chk_screen = self.capture_screen()
                                    if chk_screen is not None:
                                        chk_detected = self.scan_text(chk_screen)
                                        if self.check_and_handle_global_popups(chk_detected, (img_h, img_w)):
                                            del chk_screen, chk_detected
                                            break

                                        # 檢查是否有其他優先動作觸發 (例如優先 2 下一頁)
                                        other_p_hit = None
                                        if active_priority_steps:
                                            for other_p in active_priority_steps:
                                                if other_p is p_step:
                                                    continue
                                                chk_p = self.match_priority_step(chk_detected, other_p, screen_shape=(img_h, img_w))
                                                if chk_p:
                                                    other_p_hit = other_p
                                                    break
                                        if other_p_hit:
                                            self._log(f"⭐ [{p_tag}] 連點中途觸發其他優先動作「{other_p_hit.get('name')}」，結束連點切換！")
                                            del chk_screen, chk_detected
                                            break

                                        # 檢查是否有常規步驟出現 (例如結算畫面、下一步驟按鈕等)
                                        next_matched = self.match_custom_steps(chk_detected, active_steps, screen_shape=(img_h, img_w))

                                        # 🎥 即時推送連點中的遊戲畫面與當前連點座標至預覽視窗
                                        if self.on_frame_callback and self.is_running:
                                            try:
                                                p_rep_info = (dict(p_step, repeat_point=(bx, by), status="continuous_tap"), f"連點中 #{tap_count}", rx, ry, 1.0)
                                                self.on_frame_callback(chk_screen, chk_detected, next_matched or p_rep_info)
                                            except Exception:
                                                pass

                                        if next_matched:
                                            self._log(f"✨ [{p_tag}] 偵測到常規步驟 [{next_matched[0].get('name')}]，結束連點 (共連點 {tap_count} 次)")
                                            del chk_screen, chk_detected
                                            break
                                        del chk_screen, chk_detected
                        else:
                            self._log(f"⚡ [{p_tag}] 在「{rep_area}」連點 {rep_count} 次...")
                            for _ in range(rep_count):
                                if not self.is_running:
                                    break
                                rx = bx + random.randint(-12, 12)
                                ry = by + random.randint(-12, 12)
                                self.tap(rx, ry, delay_range=(min_spd, max_spd))
                            time.sleep(max(0.05, random.uniform(d_min, d_max)))
                    else:
                        # 單次點擊：依據優先動作設定的自訂換頁延遲進行冷卻等待
                        wait_time = max(0.05, random.uniform(d_min, d_max))
                        time.sleep(wait_time)

                    # 【用完即刪】：本輪點擊與回報完成，立即釋放當前 screen 與 detected
                    del screen, detected
                    if not self.is_running:
                        break

                    if not keep_while:
                        break

                    # while 條件：再次擷取畫面檢查優先條件是否依然存在
                    screen = self.capture_screen()
                    if screen is None:
                        break
                    img_h, img_w = screen.shape[:2]
                    detected = self.scan_text(screen)
                    rematch = self.match_priority_step(detected, p_step, screen_shape=(img_h, img_w))
                    if not rematch:
                        self._log(f"⭐ [{p_tag}] 優先字元已解除 (共執行 {p_count} 次)，恢復平常流程")
                        del screen, detected
                        break
                    p_text, px, py, p_score, p_box = rematch[:5]

                # 重置空閒計數與等待計時，釋放資源
                consecutive_idle = 0
                step_wait_start_time = time.time()
                if 'screen' in locals() and screen is not None:
                    del screen
                if 'detected' in locals() and detected is not None:
                    del detected
                continue

            # =================================================================
            # else: 平常動作 (一般自訂步驟狀態機流程)
            # =================================================================
            # 比對自訂步驟 (精確優先、區域限定，並優先比對當前期待步驟)
            matched = self.match_custom_steps(
                detected,
                active_steps,
                screen_shape=(img_h, img_w),
                expected_step_idx=current_step_idx
            )

            if matched and self.is_running:
                last_active_time = time.time()
                step, text, x, y, score = matched
                step_name = step.get("name", "自訂步驟")
                d_min = step.get("delay_min", 2.0)
                d_max = step.get("delay_max", 3.5)
                rep_enabled = step.get("repeat_enabled", False)
                rep_count = int(step.get("repeat_count", 3))
                rep_area = step.get("repeat_area", "右下角區域")

                step_idx = (active_steps.index(step) + 1) if step in active_steps else (current_step_idx + 1)
                step_tag = f"步驟 {step_idx}: {step_name}"

                # 更新當前執行到的步驟索引並重置等待計時
                if step in active_steps:
                    current_step_idx = (active_steps.index(step) + 1) % len(active_steps)
                    step_wait_start_time = time.time()

                self._log(f"🎯 [{step_tag}] 命中「{text}」({score:.2f}) → 點擊 ({x}, {y})")

                # 1. 【0ms 極速下發 ADB 指令】：第一時間下發點擊指令，確保反應動作零延遲
                self.tap(x, y, delay_range=(0.04, 0.08))

                # 2. 【0ms 立即同步呈現】：點擊下發瞬間，GUI 預覽視窗同步標記呈現
                if self.on_frame_callback and self.is_running:
                    try:
                        self.on_frame_callback(screen, detected, matched)
                    except Exception:
                        pass

                # 📱 若設定了 Telegram 通知，非同步發送通知
                tg_cfg = step.get("telegram", {})
                if tg_cfg and tg_cfg.get("enabled", False):
                    tg_tok = tg_cfg.get("token", "")
                    tg_cid = tg_cfg.get("chat_id", "")
                    tg_msg = tg_cfg.get("message", "")
                    self.send_telegram_notify(tg_tok, tg_cid, tg_msg, step_name=step_tag, hit_text=text)

                # 【步驟換頁冷卻 / 過渡連點】：點擊與預覽呈現皆完成後，才進行遊戲過場或換頁冷卻
                if rep_enabled and self.is_running:
                    rep_mode = step.get("repeat_mode", "until_next")
                    rep_speed = float(step.get("repeat_speed", 0.3))
                    min_spd = max(0.08, rep_speed - 0.05)
                    max_spd = rep_speed + 0.05

                    if rep_area == "右下角區域":
                        bx, by = int(img_w * 0.86), int(img_h * 0.86)
                    elif rep_area == "中央區域":
                        bx, by = int(img_w * 0.50), int(img_h * 0.50)
                    elif rep_area == "右上角 (Skip)":
                        bx, by = int(img_w * 0.90), int(img_h * 0.12)
                    elif rep_area == "右半側中央":
                        bx, by = int(img_w * 0.82), int(img_h * 0.50)
                    elif "自訂" in rep_area:
                        cust_coord = step.get("repeat_custom_coord")
                        if cust_coord and isinstance(cust_coord, (list, tuple)) and len(cust_coord) == 2:
                            bx, by = int(cust_coord[0]), int(cust_coord[1])
                        else:
                            bx, by = x, y
                    else:
                        bx, by = x, y

                    if rep_mode == "until_next":
                        self._log(f"⚡ [{step_tag}] 正在連續點擊「{rep_area}」跳過過場 (直到下一步驟出現)...")
                        tap_count = 0
                        # 解除連點次數上限：持續點擊直至下一步驟或優先動作出現
                        while self.is_running:
                            rx = bx + random.randint(-12, 12)
                            ry = by + random.randint(-12, 12)
                            self.tap(rx, ry, delay_range=(min_spd, max_spd))
                            tap_count += 1

                            # 每敲擊 4 下檢查一次畫面是否有下一個步驟出現
                            if tap_count % 4 == 0:
                                chk_screen = self.capture_screen()
                                if chk_screen is not None:
                                    chk_detected = self.scan_text(chk_screen)
                                    # 全域彈窗偵測
                                    if self.check_and_handle_global_popups(chk_detected, (img_h, img_w)):
                                        del chk_screen, chk_detected
                                        break
                                    # 優先動作偵測：若出現任何優先動作字元則立即中斷過渡連點
                                    if active_priority_steps:
                                        p_interrupted = False
                                        for p_step in active_priority_steps:
                                            chk_p = self.match_priority_step(chk_detected, p_step, screen_shape=(img_h, img_w))
                                            if chk_p:
                                                self._log(f"⭐ [{step_tag}] 連點中途觸發優先動作「{p_step.get('name')}」，立即切換！")
                                                p_interrupted = True
                                                break
                                        if p_interrupted:
                                            del chk_screen, chk_detected
                                            break
                                    next_matched = self.match_custom_steps(chk_detected, active_steps, screen_shape=(img_h, img_w))
                                    # 🎥 即時推送連點中的遊戲畫面與當前連點座標至預覽視窗
                                    if self.on_frame_callback and self.is_running:
                                        try:
                                            rep_info = (dict(step, repeat_point=(bx, by), status="continuous_tap"), f"連點中 #{tap_count}", rx, ry, 1.0)
                                            self.on_frame_callback(chk_screen, chk_detected, next_matched or rep_info)
                                        except Exception:
                                            pass
                                    if next_matched:
                                        n_step, n_text, _, _, _ = next_matched
                                        if n_step.get("name") != step_name or tap_count >= 8:
                                            self._log(f"✨ [{step_tag}] 偵測到 [{n_step.get('name')}]，結束連點 (共連點 {tap_count} 次)")
                                            del chk_screen, chk_detected
                                            break
                                    del chk_screen, chk_detected
                    else:
                        self._log(f"⚡ [{step_tag}] 在「{rep_area}」連點 {rep_count} 次...")
                        for _ in range(rep_count):
                            if not self.is_running:
                                break
                            rx = bx + random.randint(-12, 12)
                            ry = by + random.randint(-12, 12)
                            self.tap(rx, ry, delay_range=(min_spd, max_spd))
                        time.sleep(max(0.05, random.uniform(d_min, d_max)))
                else:
                    # 單次點擊：根據步驟自訂的延遲時間進行換頁冷卻 (遊戲讀取等待)
                    wait_time = max(0.05, random.uniform(d_min, d_max))
                    time.sleep(wait_time)

                consecutive_idle = 0
                step_wait_start_time = time.time()
                del screen, detected  # 【用完即刪】：步驟執行完畢，立即刪除當前畫面與辨識資料

                # 🚨【關鍵優化】：本步驟已完成使用者設定的自訂換頁延遲，絕不再疊加 poll_interval！
                # 換頁時間一結束，立刻進行下一輪截圖辨識！
                continue
            else:
                # 未命中任何步驟時，更新預覽畫面供使用者介面觀察當前無命中狀態
                if self.on_frame_callback and self.is_running:
                    try:
                        self.on_frame_callback(screen, detected, None)
                    except Exception:
                        pass

                consecutive_idle += 1
                del screen, detected  # 【用完即刪】：未命中任何步驟，回報後立即釋放畫面與資料

                # 🛡️【看門狗防卡死檢查】：超過設定時間未命中任何動作時自動停止並重新開啟
                if wd_enabled and self.is_running:
                    idle_duration = time.time() - last_active_time
                    if idle_duration >= wd_seconds:
                        self._log(f"🚨 [防卡死守護] 已連續 {int(idle_duration)} 秒無任何動作，觸發自動停止並重新開啟腳本！", "WARNING")
                        self.is_running = False
                        self._watchdog_triggered = True
                        break

                expected_step = active_steps[current_step_idx] if active_steps else None
                exp_idx = current_step_idx + 1 if active_steps else 1
                exp_name = expected_step.get("name", "下一步驟") if expected_step else "步驟"
                exp_tag = f"步驟 {exp_idx}: {exp_name}"

                # 檢查當前期待步驟是否開啟了【超時自動跳過】
                if expected_step and expected_step.get("timeout_enabled", False):
                    timeout_sec = expected_step.get("timeout_seconds", 15)
                    elapsed = time.time() - step_wait_start_time
                    if elapsed >= timeout_sec:
                        self._log(f"⏩ [{exp_tag}] 等待超過 {timeout_sec} 秒未出現，自動跳過此步驟！", "WARNING")
                        current_step_idx = (current_step_idx + 1) % len(active_steps)
                        step_wait_start_time = time.time()
                        consecutive_idle = 0
                        time.sleep(0.5)
                        continue

                # 簡潔有力顯示當前等待狀態（不洗版，不列出大量文字 dump）
                elapsed_wait = int(time.time() - step_wait_start_time)
                if consecutive_idle == 1:
                    self._log(f"⏳ 等待中：正在等待 [{exp_tag}]...")
                elif consecutive_idle in [5, 12] or (consecutive_idle > 12 and consecutive_idle % 10 == 0):
                    self._log(f"⏳ 等待中：卡在 [{exp_tag}] (已等待 {elapsed_wait} 秒)...")

                # 【等待時連續點擊策略】：如果開啟，在等待下一目標時持續點擊指定位置以跳過過場
                if idle_tap_config and idle_tap_config.get("enabled", False) and self.is_running:
                    it_area = idle_tap_config.get("area", "右下角區域")
                    it_times = int(idle_tap_config.get("times", 2))
                    it_interval = float(idle_tap_config.get("interval", 0.4))
                    if it_area == "右下角區域":
                        it_x, it_y = int(img_w * 0.86), int(img_h * 0.86)
                    elif it_area == "中央區域":
                        it_x, it_y = int(img_w * 0.50), int(img_h * 0.50)
                    elif it_area == "右上角 (Skip)":
                        it_x, it_y = int(img_w * 0.90), int(img_h * 0.12)
                    elif it_area == "右半側中央":
                        it_x, it_y = int(img_w * 0.82), int(img_h * 0.50)
                    elif "自訂" in it_area:
                        it_coord = idle_tap_config.get("custom_coord")
                        if it_coord and isinstance(it_coord, (list, tuple)) and len(it_coord) == 2:
                            it_x, it_y = int(it_coord[0]), int(it_coord[1])
                        else:
                            it_x = int(idle_tap_config.get("custom_x", int(img_w * 0.86)))
                            it_y = int(idle_tap_config.get("custom_y", int(img_h * 0.86)))
                    else:
                        it_x, it_y = int(img_w * 0.86), int(img_h * 0.86)

                    for _ in range(it_times):
                        if not self.is_running:
                            break
                        rix = it_x + random.randint(-12, 12)
                        riy = it_y + random.randint(-12, 12)
                        self.tap(rix, riy, delay_range=(max(0.1, it_interval - 0.05), it_interval + 0.05))

                # 動態退避延遲：避免空迴圈密集高頻截圖導致 CPU 飆高
                idle_sleep = poll_interval
                if consecutive_idle >= 6:
                    idle_sleep = min(poll_interval * 1.5, 4.0)

                if idle_strategy == "skip":
                    time.sleep(0.6)
                elif idle_strategy == "stop":
                    if consecutive_idle >= max_idle_cycles:
                        self._log(f"🛑 卡在 [{exp_tag}] 超時未辨識到目標，停止腳本！", "ERROR")
                        self.is_running = False
                        break
                    time.sleep(idle_sleep)
                else:
                    time.sleep(idle_sleep)

        self._log("腳本停止。")

