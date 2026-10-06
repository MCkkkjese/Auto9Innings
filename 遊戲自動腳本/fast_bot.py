"""
棒球手遊自動刷關腳本 - 極簡高反應速度版 (Reactive Tap & Keyword Trigger)
基於 pure-python-adb 與 rapidocr-onnxruntime
架構：雙執行緒非同步設計 (常態高頻背景連點 + 高速 OCR 事件中斷)
"""
import os
import sys
import time
import random
import difflib
import threading
import subprocess
from typing import Optional, Tuple, List, Dict, Any

import cv2
import numpy as np
from ppadb.client import Client as AdbClient
from ppadb.device import Device
from rapidocr_onnxruntime import RapidOCR


# ==============================================================================
# 🛠️ 使用者設定集中區 (Config) - 隨時依手機/模擬器解析度微調
# ==============================================================================
ADB_HOST: str = "127.0.0.1"
ADB_PORT: int = 5037
DEVICE_SERIAL: Optional[str] = None  # None 代表自動偵測並選定第一個連線的裝置

# 常態連點設定 (平時無事件時持續點擊的預設位置，例如 AUTO、右側空白處或結算跳過區)
DEFAULT_TAP_X: int = 1650            # 連點 X 座標 (以 1920x1080 為參考)
DEFAULT_TAP_Y: int = 850             # 連點 Y 座標
TAP_INTERVAL_MIN: float = 0.20       # 連點最短間隔 (秒) -> 每秒約 3~5 次
TAP_INTERVAL_MAX: float = 0.40       # 連點最長間隔 (秒)
TAP_RANDOM_OFFSET: int = 8           # 連點防偵測微小像素偏移量 (±像素)

# 關鍵字中斷清單 (依優先順序排列，支援大小寫不拘與模糊比對)
# 當畫面上偵測到這些字時，立即中斷常態連點，優先點擊該文字
TRIGGER_KEYWORDS: List[str] = [
    "PLAY BALL",
    "PLAYBALL",
    "下一頁",
    "下一步",
    "NEXT",
    "確定",
    "確認",
    "OK",
    "NEXT SCHEDULE",
    "SCHEDULE",
    "AUTO",
    "領取",
    "繼續",
    "開始"
]

OCR_CONFIDENCE_THRESHOLD: float = 0.60   # OCR 最低信心度門檻
FUZZY_SIMILARITY_THRESHOLD: float = 0.70 # 模糊比對門檻 (容許 1 個錯別字)
OCR_CHECK_INTERVAL: float = 0.15         # OCR 迴圈各輪之間的最短間隔 (秒)
EVENT_PAUSE_DURATION: float = 0.8        # 觸發關鍵字點擊後，短暫讓畫面切換的冷卻時間 (秒)
# ==============================================================================


class FastReactiveBot:
    """極簡高效能反應式刷關機器人"""

    def __init__(self):
        self.client: Optional[AdbClient] = None
        self.device: Optional[Device] = None
        self.adb_bin: Optional[str] = None
        self.ocr = RapidOCR()
        self.is_running = False

        # 執行緒同步控制
        self.pause_tapping_event = threading.Event()  # 關鍵字事件觸發時暫停常態連點
        self.pause_tapping_event.set()                # set 代表允許連點，clear 代表暫停

    def log(self, msg: str):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def auto_detect_adb_bin(self) -> Optional[str]:
        """尋找系統或模擬器中的 ADB 二進位工具 (macOS / Linux / Windows 常用路徑)"""
        candidates = [
            "/Applications/BlueStacks.app/Contents/MacOS/hd-adb",
            "/Applications/MuMuPlayer.app/Contents/MacOS/adb",
            "/Applications/NoxAppPlayer.app/Contents/MacOS/adb",
            "/usr/local/bin/adb",
            "/opt/homebrew/bin/adb",
            os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
        ]
        for path in candidates:
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path
        return None

    def connect_device(self) -> bool:
        """連接 ADB Server 並取得 Device 物件"""
        self.adb_bin = self.auto_detect_adb_bin()

        # 嘗試直接連線
        try:
            self.client = AdbClient(host=ADB_HOST, port=ADB_PORT)
            devices = self.client.devices()
        except Exception:
            devices = []

        # 若未啟動，使用 adb start-server
        if not devices and self.adb_bin:
            self.log("啟動 ADB Server 並搜尋模擬器連線...")
            try:
                subprocess.run([self.adb_bin, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                for port in [5554, 5555, 16384, 7555, 62001]:
                    subprocess.run([self.adb_bin, "connect", f"127.0.0.1:{port}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1)
                self.client = AdbClient(host=ADB_HOST, port=ADB_PORT)
                devices = self.client.devices()
            except Exception as e:
                self.log(f"ADB 工具喚醒異常: {e}")

        if not devices:
            self.log("❌ 找不到任何 ADB 裝置！請確認模擬器 (BlueStacks / MuMu) 已開機。")
            return False

        if DEVICE_SERIAL:
            matched = [d for d in devices if d.serial == DEVICE_SERIAL]
            self.device = matched[0] if matched else devices[0]
        else:
            self.device = devices[0]

        self.log(f"✅ 成功連線裝置: {self.device.serial}")
        return True

    def fast_tap(self, x: int, y: int):
        """低延遲背景點擊指令"""
        if not self.device:
            return
        try:
            self.device.shell(f"input tap {x} {y}")
        except Exception:
            # 備援 adb 二進位檔直接點擊
            if self.adb_bin:
                try:
                    subprocess.run(
                        [self.adb_bin, "-s", self.device.serial, "shell", f"input tap {x} {y}"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2
                    )
                except Exception:
                    pass

    def fast_screencap(self) -> Optional[np.ndarray]:
        """後台高效率截圖並解碼為 OpenCV 影像陣列"""
        if not self.device:
            return None

        raw = None
        try:
            raw = self.device.screencap()
        except Exception:
            pass

        # 備援 exec-out (處理 BlueStacks FAIL 0006closed)
        if not raw or len(raw) < 100:
            if self.adb_bin:
                try:
                    res = subprocess.run(
                        [self.adb_bin, "-s", self.device.serial, "exec-out", "screencap", "-p"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3
                    )
                    if res.returncode == 0 and len(res.stdout) > 100:
                        raw = res.stdout
                except Exception:
                    pass

        if not raw or len(raw) < 100:
            return None

        try:
            buf = np.frombuffer(raw, dtype=np.uint8)
            del raw
            img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            del buf
            return img
        except Exception:
            return None

    @staticmethod
    def clean_text(s: str) -> str:
        """去除空格與特殊標點，轉大寫統一格式"""
        for ch in [" ", "\t", "\n", "\r", "　", "，", ",", "。", ".", "！", "!", "-", "_", ":", "："]:
            s = s.replace(ch, "")
        return s.strip().upper()

    def is_keyword_matched(self, target_kw: str, text: str) -> bool:
        """文字匹配：支援完全包含與 1 字元容錯模糊比對"""
        c_kw = self.clean_text(target_kw)
        c_text = self.clean_text(text)
        if not c_kw or not c_text:
            return False

        # 1. 直接包含命中 (最快)
        if c_kw in c_text:
            return True

        # 2. 模糊滑動視窗比對 (字數 >= 2 才啟用)
        len_kw = len(c_kw)
        len_text = len(c_text)
        if len_kw < 2:
            return False

        if len_text <= len_kw:
            return difflib.SequenceMatcher(None, c_kw, c_text).ratio() >= FUZZY_SIMILARITY_THRESHOLD

        for w_len in [len_kw, len_kw + 1]:
            for i in range(len_text - w_len + 1):
                sub = c_text[i:i + w_len]
                if difflib.SequenceMatcher(None, c_kw, sub).ratio() >= FUZZY_SIMILARITY_THRESHOLD:
                    return True
        return False

    # ==========================================================================
    # 執行緒 1: 常態連續點擊 (Default Background Clicker)
    # ==========================================================================
    def tapping_worker(self):
        """專注維持常態連點跳過動畫；當事件觸發時會被暫停"""
        self.log(f"⚡ [常態連點] 啟動！目標座標: ({DEFAULT_TAP_X}, {DEFAULT_TAP_Y})")
        while self.is_running:
            # 等待事件許可 (若被 OCR 事件 clear 則阻塞在此)
            self.pause_tapping_event.wait()
            if not self.is_running:
                break

            # 加上隨機微小位移，防固定座標偵測
            rx = DEFAULT_TAP_X + random.randint(-TAP_RANDOM_OFFSET, TAP_RANDOM_OFFSET)
            ry = DEFAULT_TAP_Y + random.randint(-TAP_RANDOM_OFFSET, TAP_RANDOM_OFFSET)
            self.fast_tap(rx, ry)

            # 隨機延遲 0.2 ~ 0.4 秒
            sleep_sec = random.uniform(TAP_INTERVAL_MIN, TAP_INTERVAL_MAX)
            time.sleep(sleep_sec)

    # ==========================================================================
    # 執行緒 2: 文字掃描與事件中斷 (OCR & Event Interrupt)
    # ==========================================================================
    def ocr_worker(self):
        """專注週期性截圖辨識畫面，一旦出現關鍵字立即搶先點擊"""
        self.log("👀 [事件偵測] 啟動！正在持續監視觸發關鍵字...")
        while self.is_running:
            start_t = time.time()
            screen = self.fast_screencap()
            if screen is None:
                time.sleep(0.5)
                continue

            # RapidOCR 推論
            ocr_results, _ = self.ocr(screen)
            del screen

            hit_keyword = None
            hit_text = None
            hit_center = None

            if ocr_results:
                # 取得畫面上偵測到的全部文字
                all_detected_texts = [text.strip() for _, text, score in ocr_results if float(score) >= OCR_CONFIDENCE_THRESHOLD and text.strip()]
                if all_detected_texts:
                    self.log(f"📋 [畫面文字] 共 {len(all_detected_texts)} 個: {all_detected_texts}")

                # 依 TRIGGER_KEYWORDS 優先級順序核對
                for kw in TRIGGER_KEYWORDS:
                    for box, text, score in ocr_results:
                        if float(score) < OCR_CONFIDENCE_THRESHOLD:
                            continue
                        if self.is_keyword_matched(kw, text):
                            pts = np.array(box, dtype=np.int32)
                            cx = int(np.mean(pts[:, 0]))
                            cy = int(np.mean(pts[:, 1]))
                            hit_keyword = kw
                            hit_text = text.strip()
                            hit_center = (cx, cy)
                            break
                    if hit_keyword:
                        break

            # 🎯 命中事件處理
            if hit_keyword and hit_center and self.is_running:
                cx, cy = hit_center
                self.log(f"🎯 [事件觸發] 偵測到「{hit_text}」(匹配: {hit_keyword}) -> 立即點擊 ({cx}, {cy})")

                # 1. 暫停常態連點
                self.pause_tapping_event.clear()

                # 2. 精準點擊文字目標 (加微偏)
                tx = cx + random.randint(-4, 4)
                ty = cy + random.randint(-3, 3)
                self.fast_tap(tx, ty)

                # 3. 稍作等待以讓畫面轉場
                time.sleep(EVENT_PAUSE_DURATION)

                # 4. 恢復常態連點
                self.pause_tapping_event.set()

            # 保持合適的偵測週期，避免 CPU 滿載
            elapsed = time.time() - start_t
            wait_time = max(0.05, OCR_CHECK_INTERVAL - elapsed)
            time.sleep(wait_time)

    # ==========================================================================
    # 主程式進入點
    # ==========================================================================
    def run(self):
        self.log("=" * 60)
        self.log("⚾ 棒球手遊自動刷關 (反應式連點 + 關鍵字事件中斷版)")
        self.log("=" * 60)

        if not self.connect_device():
            return

        self.is_running = True
        self.pause_tapping_event.set()

        # 啟動雙執行緒
        t_tap = threading.Thread(target=self.tapping_worker, daemon=True)
        t_ocr = threading.Thread(target=self.ocr_worker, daemon=True)

        t_tap.start()
        t_ocr.start()

        self.log("🚀 腳本已全速運行！(按下 Ctrl + C 可隨時停止)\n")
        try:
            while self.is_running:
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.log("\n🛑 收到停止信號，正在退出腳本...")
        finally:
            self.is_running = False
            self.pause_tapping_event.set()
            t_tap.join(timeout=1.0)
            t_ocr.join(timeout=1.0)
            self.log("👋 腳本已安全停止。")


if __name__ == "__main__":
    bot = FastReactiveBot()
    bot.run()
