"""
================================================================================
📱 iPhone 鏡像輸出 (iPhone Mirroring) 自動化控制器與核心機器人引擎
================================================================================
專為 macOS 內建「iPhone 鏡像輸出 (iPhone Mirroring)」與各類 iPhone 投屏設計：
1. 視窗鎖定與動態追蹤：自動識別並鎖定 iPhone 鏡像 App 視窗，動態獲取螢幕位置與尺寸。
2. 高畫質螢幕截圖：透過 macOS 原生 screencapture 截取視窗區域，自動計算 Retina 2x 縮放比。
3. 原生 CoreGraphics 滑鼠模擬：透過 macOS 底層 CGEvent API 進行精確滑鼠單擊、連點、滑動拖曳。
4. 滑鼠游標智慧保護：點擊瞬間執行，點擊完畢立即將游標還原至使用者原本所在位置，不影響正常使用。
5. 完整繼承 BaseballBot：100% 複用 OCR 文字辨識、多尺度圖片模板比對、符號比對與 ROI 搜尋算法。
================================================================================
"""

import os
import sys
import time
import subprocess
import logging
import ctypes
from typing import Optional, Tuple, List, Dict, Any, Callable
import numpy as np
import cv2

# 匯入現有的機器人基礎類別
from bot_core import BaseballBot, logger

# ==============================================================================
# 🍎 macOS CoreGraphics 與 CoreFoundation 原生 C API 綁定 (Zero Dependency)
# ==============================================================================
_cg = None
_cf = None

try:
    if sys.platform == "darwin":
        _cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        _cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
except Exception as _ex:
    logger.warning(f"⚠️ 無法載入 macOS CoreGraphics 原生庫: {_ex}")


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


if _cg and _cf:
    # CGEvent 相關函式簽名定義
    _cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    _cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]

    _cg.CGEventPost.restype = None
    _cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]

    _cg.CGEventCreate.restype = ctypes.c_void_p
    _cg.CGEventCreate.argtypes = [ctypes.c_void_p]

    _cg.CGEventGetLocation.restype = CGPoint
    _cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]

    _cf.CFRelease.restype = None
    _cf.CFRelease.argtypes = [ctypes.c_void_p]

# CGEvent 事件類型常數
_kCGEventLeftMouseDown = 1
_kCGEventLeftMouseUp = 2
_kCGEventMouseMoved = 5
_kCGEventLeftMouseDragged = 6
_kCGMouseButtonLeft = 0
_kCGHIDEventTap = 0


# ==============================================================================
# 📱 iPhone 鏡像視窗控制器 (IPhoneWindowController)
# ==============================================================================
class IPhoneWindowController:
    """
    負責在 macOS 上偵測、鎖定「iPhone 鏡像輸出」視窗，截取畫面並發送原生滑鼠點擊。
    """

    KNOWN_IPHONE_APPS = [
        "iPhone Mirroring",
        "iPhone鏡像輸出",
        "iPhone 鏡像輸出",
        "QuickTime Player",
    ]

    def __init__(self, logger_func: Optional[Callable[[str], None]] = None):
        self.log_fn = logger_func or (lambda msg: logger.info(msg))
        self.locked_app_name: Optional[str] = None
        self.win_x: float = 0.0
        self.win_y: float = 0.0
        self.win_w: float = 0.0
        self.win_h: float = 0.0
        self.scale_x: float = 2.0  # Retina 預設為 2.0，截圖後動態校正
        self.scale_y: float = 2.0
        self.last_capture_bgr: Optional[np.ndarray] = None
        import tempfile
        self.temp_capture_path = os.path.join(
            tempfile.gettempdir(),
            f"iphone_screen_tmp_{os.getpid()}.png"
        )

    def log(self, msg: str):
        if self.log_fn:
            self.log_fn(msg)

    def get_running_windows(self) -> List[Dict[str, Any]]:
        """
        列出目前 macOS 上所有前台應用程式視窗資訊。
        回傳清單，每一項包含 {'owner': str, 'name': str, 'x': float, 'y': float, 'w': float, 'h': float}
        """
        if sys.platform != "darwin":
            return []

        cmd = '''osascript -e '
        tell application "System Events"
            set winInfoList to {}
            repeat with p in (every process whose background only is false)
                try
                    set pName to name of p
                    repeat with w in (every window of p)
                        try
                            set wName to name of w
                            set wPos to position of w
                            set wSize to size of w
                            set end of winInfoList to (pName & ":::" & wName & ":::" & (item 1 of wPos) & ":::" & (item 2 of wPos) & ":::" & (item 1 of wSize) & ":::" & (item 2 of wSize))
                        end try
                    end repeat
                end try
            end repeat
            return winInfoList
        end tell
        ' '''
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            lines = res.stdout.strip().split(", ")
            results = []
            for item in lines:
                parts = item.split(":::")
                if len(parts) >= 6:
                    owner, wname, sx, sy, sw, sh = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip(), parts[4].strip(), parts[5].strip()
                    try:
                        results.append({
                            "owner": owner,
                            "name": wname,
                            "x": float(sx),
                            "y": float(sy),
                            "w": float(sw),
                            "h": float(sh),
                        })
                    except Exception:
                        pass
            return results
        except Exception as ex:
            self.log(f"⚠️ 讀取視窗清單失敗: {ex}")
            return []

    def lock_window(self, target_owner: Optional[str] = None) -> bool:
        """
        鎖定指定的視窗。若未指定，自動優先搜尋 iPhone 鏡像輸出。
        """
        if sys.platform != "darwin":
            self.log("❌ iPhone 鏡像功能僅支援 macOS 系統。")
            return False

        # 若使用者指定了特定 App 名稱
        candidates = [target_owner] if target_owner else self.KNOWN_IPHONE_APPS

        for app_name in candidates:
            if not app_name:
                continue
            bounds = self._query_app_window_bounds(app_name)
            if bounds:
                self.win_x, self.win_y, self.win_w, self.win_h = bounds
                self.locked_app_name = app_name
                self.log(f"✅ 成功鎖定 iPhone 視窗「{app_name}」 (座標: {int(self.win_x)}, {int(self.win_y)} | 尺寸: {int(self.win_w)}×{int(self.win_h)})")
                return True

        # 若上方預設名稱找不到，遍歷現有視窗搜尋包含 iPhone 關鍵字之視窗
        all_wins = self.get_running_windows()
        for w in all_wins:
            owner = w.get("owner", "")
            wname = w.get("name", "")
            if "iphone" in owner.lower() or "iphone" in wname.lower():
                self.win_x, self.win_y, self.win_w, self.win_h = w["x"], w["y"], w["w"], w["h"]
                self.locked_app_name = owner
                self.log(f"✅ 成功模糊比對鎖定 iPhone 視窗「{owner}」 (尺寸: {int(self.win_w)}×{int(self.win_h)})")
                return True

        self.log("⚠️ 未在 Mac 上找到「iPhone 鏡像輸出」視窗！請確認是否已開啟 iPhone 鏡像輸出 App。")
        return False

    def _query_app_window_bounds(self, app_name: str) -> Optional[Tuple[float, float, float, float]]:
        """透過 AppleScript 查詢指定應用程式的主視窗座標與大小"""
        cmd = f'''osascript -e '
        tell application "System Events"
            try
                if exists process "{app_name}" then
                    tell process "{app_name}"
                        set pos to position of window 1
                        set sz to size of window 1
                        return (item 1 of pos as string) & "," & (item 2 of pos as string) & "," & (item 1 of sz as string) & "," & (item 2 of sz as string)
                    end tell
                end if
            end try
            return ""
        end tell
        ' '''
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
            out = res.stdout.strip()
            if out and "," in out:
                parts = [float(p.strip()) for p in out.split(",")]
                if len(parts) == 4 and parts[2] > 20 and parts[3] > 20:
                    return parts[0], parts[1], parts[2], parts[3]
        except Exception:
            pass
        return None

    def refresh_bounds(self) -> bool:
        """動態追蹤目前鎖定視窗的最新位置與尺寸（若使用者拖曳移動了視窗）"""
        if not self.locked_app_name:
            return False
        bounds = self._query_app_window_bounds(self.locked_app_name)
        if bounds:
            self.win_x, self.win_y, self.win_w, self.win_h = bounds
            return True
        return False

    def activate_window(self):
        """將目標 iPhone 鏡像視窗移至最前景 (Activate)"""
        if not self.locked_app_name or sys.platform != "darwin":
            return
        try:
            subprocess.run(
                ["osascript", "-e", f'tell application "{self.locked_app_name}" to activate'],
                capture_output=True,
                timeout=2
            )
        except Exception:
            pass

    def capture_screen(self) -> Optional[np.ndarray]:
        """
        截取目前鎖定 iPhone 視窗區域的畫面，並傳回 OpenCV BGR 格式圖片矩陣。
        自動根據 Retina 解析度校正 scale_x / scale_y 縮放比。
        """
        if not self.locked_app_name:
            if not self.lock_window():
                return None

        # 動態追蹤視窗位置 (每秒或每次截圖自動跟隨視窗拖曳)
        self.refresh_bounds()

        rx, ry, rw, rh = int(self.win_x), int(self.win_y), int(self.win_w), int(self.win_h)
        if rw < 10 or rh < 10:
            return None

        try:
            # 呼叫 macOS 原生截圖工具 (超高速靜音截取指定矩形區域)
            cmd = ["screencapture", f"-R{rx},{ry},{rw},{rh}", "-x", self.temp_capture_path]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
            if res.returncode == 0 and os.path.exists(self.temp_capture_path):
                # 跨平台讀取中文與一般圖片
                img = cv2.imread(self.temp_capture_path)
                if img is not None:
                    ih, iw = img.shape[:2]
                    # 動態校正 Retina 縮放比例 (例如 1410/705 = 2.0)
                    self.scale_x = iw / rw if rw > 0 else 2.0
                    self.scale_y = ih / rh if rh > 0 else 2.0
                    self.last_capture_bgr = img
                    return img
        except Exception as ex:
            self.log(f"⚠️ 截取 iPhone 鏡像畫面失敗: {ex}")
        finally:
            if os.path.exists(self.temp_capture_path):
                try:
                    os.remove(self.temp_capture_path)
                except Exception:
                    pass

        return None

    def get_current_mouse_pos(self) -> Tuple[float, float]:
        """取得目前 macOS 滑鼠游標位置"""
        if not _cg or not _cf:
            return 0.0, 0.0
        try:
            ev = _cg.CGEventCreate(None)
            loc = _cg.CGEventGetLocation(ev)
            _cf.CFRelease(ev)
            return loc.x, loc.y
        except Exception:
            return 0.0, 0.0

    def click(
        self,
        img_x: int,
        img_y: int,
        restore_cursor: bool = True,
        auto_activate: bool = True
    ) -> bool:
        """
        在 iPhone 視窗對應圖片內部座標 (img_x, img_y) 發送原生 CoreGraphics 滑鼠點擊。
        :param img_x: 截圖像素座標 X
        :param img_y: 截圖像素座標 Y
        :param restore_cursor: 點擊完成後是否將滑鼠指標復位回原處 (貼心保護使用者日常工作)
        :param auto_activate: 點擊前是否自動將 iPhone 視窗帶至最前
        """
        if not _cg or not _cf or sys.platform != "darwin":
            self.log("❌ 系統非 macOS 或缺乏 CoreGraphics，無法執行滑鼠事件。")
            return False

        # 更新最新視窗座標
        self.refresh_bounds()

        # 映射圖片像素座標至 Mac 邏輯螢幕座標
        target_screen_x = self.win_x + (img_x / self.scale_x)
        target_screen_y = self.win_y + (img_y / self.scale_y)

        # 越界防護
        target_screen_x = max(self.win_x, min(self.win_x + self.win_w - 2, target_screen_x))
        target_screen_y = max(self.win_y, min(self.win_y + self.win_h - 2, target_screen_y))

        orig_mouse_x, orig_mouse_y = (0.0, 0.0)
        if restore_cursor:
            orig_mouse_x, orig_mouse_y = self.get_current_mouse_pos()

        if auto_activate:
            self.activate_window()

        pt = CGPoint(float(target_screen_x), float(target_screen_y))

        try:
            # 1. 移動至目標位置
            ev_move = _cg.CGEventCreateMouseEvent(None, _kCGEventMouseMoved, pt, _kCGMouseButtonLeft)
            _cg.CGEventPost(_kCGHIDEventTap, ev_move)
            _cf.CFRelease(ev_move)

            # 2. 按下滑鼠左鍵
            ev_down = _cg.CGEventCreateMouseEvent(None, _kCGEventLeftMouseDown, pt, _kCGMouseButtonLeft)
            _cg.CGEventPost(_kCGHIDEventTap, ev_down)
            _cf.CFRelease(ev_down)

            # 微量防抖延遲 (手遊需約 40ms 響應點擊)
            time.sleep(0.045)

            # 3. 釋放滑鼠左鍵
            ev_up = _cg.CGEventCreateMouseEvent(None, _kCGEventLeftMouseUp, pt, _kCGMouseButtonLeft)
            _cg.CGEventPost(_kCGHIDEventTap, ev_up)
            _cf.CFRelease(ev_up)

            # 4. 游標復位保護 (若啟用)
            if restore_cursor and (orig_mouse_x > 0 or orig_mouse_y > 0):
                time.sleep(0.015)
                orig_pt = CGPoint(float(orig_mouse_x), float(orig_mouse_y))
                ev_restore = _cg.CGEventCreateMouseEvent(None, _kCGEventMouseMoved, orig_pt, _kCGMouseButtonLeft)
                _cg.CGEventPost(_kCGHIDEventTap, ev_restore)
                _cf.CFRelease(ev_restore)

            return True
        except Exception as ex:
            self.log(f"❌ CoreGraphics 滑鼠點擊異常: {ex}")
            return False

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.25,
        steps: int = 15
    ) -> bool:
        """在 iPhone 視窗內模擬平滑滑動/拖曳 (Swipe/Drag)"""
        if not _cg or not _cf:
            return False

        self.refresh_bounds()
        sx1 = self.win_x + (x1 / self.scale_x)
        sy1 = self.win_y + (y1 / self.scale_y)
        sx2 = self.win_x + (x2 / self.scale_x)
        sy2 = self.win_y + (y2 / self.scale_y)

        self.activate_window()
        p1 = CGPoint(float(sx1), float(sy1))

        try:
            # 1. 移至起點並按下
            ev_down = _cg.CGEventCreateMouseEvent(None, _kCGEventLeftMouseDown, p1, _kCGMouseButtonLeft)
            _cg.CGEventPost(_kCGHIDEventTap, ev_down)
            _cf.CFRelease(ev_down)
            time.sleep(0.03)

            # 2. 插值拖曳移動
            sleep_step = max(0.005, duration / max(1, steps))
            for i in range(1, steps + 1):
                t = i / steps
                cx = sx1 + (sx2 - sx1) * t
                cy = sy1 + (sy2 - sy1) * t
                c_pt = CGPoint(float(cx), float(cy))
                ev_drag = _cg.CGEventCreateMouseEvent(None, _kCGEventLeftMouseDragged, c_pt, _kCGMouseButtonLeft)
                _cg.CGEventPost(_kCGHIDEventTap, ev_drag)
                _cf.CFRelease(ev_drag)
                time.sleep(sleep_step)

            # 3. 終點釋放
            p2 = CGPoint(float(sx2), float(sy2))
            ev_up = _cg.CGEventCreateMouseEvent(None, _kCGEventLeftMouseUp, p2, _kCGMouseButtonLeft)
            _cg.CGEventPost(_kCGHIDEventTap, ev_up)
            _cf.CFRelease(ev_up)
            return True
        except Exception as ex:
            self.log(f"❌ 模擬滑動異常: {ex}")
            return False


class DummyIPhoneDevice:
    """提供模擬 device 物件，使共用邏輯與裝置檢查無縫相容"""
    def __init__(self, serial: str = "iPhone-Mirroring"):
        self.serial = serial

    def shell(self, *args, **kwargs):
        return ""


# ==============================================================================
# 🤖 iPhone 鏡像核心機器人引擎 (IPhoneMirrorBot)
# ==============================================================================
class IPhoneMirrorBot(BaseballBot):
    """
    繼承自標準 BaseballBot，底層通訊與輸入全面改為 macOS「iPhone 鏡像輸出」專屬滑鼠控制。
    保有完整 OCR、模板特徵匹配、符號匹配、ROI 計算與安全保護。
    """

    def __init__(
        self,
        templates_dir: Optional[str] = None,
        logger_func: Optional[Callable[[str], None]] = None,
        confidence_threshold: float = 0.65,
        on_frame_callback: Optional[Callable] = None
    ):
        super().__init__(
            confidence_threshold=confidence_threshold,
            log_callback=logger_func,
            on_frame_callback=on_frame_callback
        )
        if templates_dir:
            self.set_templates_dir(templates_dir)
        self.window_ctrl = IPhoneWindowController(logger_func=logger_func)
        self.restore_cursor: bool = True  # 點擊完畢游標自動移回原位
        self.auto_activate: bool = True   # 點擊前自動將 iPhone 視窗移至最前景

    def log(self, msg: str):
        self._log(msg)

    def connect(self, target_serial: Optional[str] = None) -> bool:
        """
        覆寫連線方法：嘗試鎖定 iPhone 鏡像輸出視窗。
        :param target_serial: 在此模式下充當 target_window_name。
        """
        self.log(f"📱 正在搜尋並鎖定 iPhone 鏡像輸出視窗...")
        success = self.window_ctrl.lock_window(target_owner=target_serial)
        if success:
            self.device = DummyIPhoneDevice(self.window_ctrl.locked_app_name or "iPhone-Mirroring")
            self.log("✅ iPhone 鏡像視窗連線鎖定成功！")
            return True
        else:
            self.device = None
            self.log("❌ 無法鎖定 iPhone 鏡像視窗，請先啟動 iPhone Mirroring App。")
            return False

    def is_connected(self) -> bool:
        """檢查 iPhone 鏡像視窗是否存在且有效"""
        return self.window_ctrl.refresh_bounds()

    def capture_screen(self, max_retries: int = 3) -> Optional[np.ndarray]:
        """
        覆寫螢幕截圖：改為截取 iPhone 鏡像視窗畫面。
        """
        for _ in range(max_retries):
            img = self.window_ctrl.capture_screen()
            if img is not None and img.shape[0] > 10 and img.shape[1] > 10:
                return img
            time.sleep(0.1)
        return None

    def tap(
        self,
        x: int,
        y: int,
        delay_range: Tuple[float, float] = (0.04, 0.08),
        max_retries: int = 3
    ) -> bool:
        """
        覆寫點擊動作：改為使用 macOS 原生滑鼠點擊 iPhone 鏡像視窗中對應座標。
        """
        for attempt in range(max_retries):
            ok = self.window_ctrl.click(
                img_x=x,
                img_y=y,
                restore_cursor=self.restore_cursor,
                auto_activate=self.auto_activate
            )
            if ok:
                # 附加動態微量防抖延遲
                time.sleep(np.random.uniform(delay_range[0], delay_range[1]))
                return True
            time.sleep(0.05)
        return False

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300
    ) -> bool:
        """
        覆寫滑動動作：改為在 iPhone 鏡像視窗內模擬滑鼠拖曳滑動。
        """
        return self.window_ctrl.swipe(
            x1=x1, y1=y1, x2=x2, y2=y2,
            duration=duration_ms / 1000.0
        )
