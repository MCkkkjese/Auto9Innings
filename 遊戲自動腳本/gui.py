"""
棒球手遊自動化腳本 - 現代化 CustomTkinter 圖形化介面 (Modern GUI)
完全重構特色：
1. 全域 macOS 深色控制面板風格 (ctk.set_appearance_mode("dark"))，採用低飽和度配色 (#1E1E2E 背景，#252538 卡片)。
2. 大字體狀態指示燈：彩色呼吸指示燈 (綠：運作中 / 橘：未連線/暫停 / 紅：已停止) 與大字體狀態文字。
3. 主控制大按鈕：圓角 corner_radius=8 大按鈕 (啟動刷關 / 停止刷關 / 連線 / 搜尋)。
4. 參數設定格 (Settings Grid)：以卡片式 CTkFrame 封裝，內部對齊輸入框與間距留白充足。
5. 等寬即時日誌終端 (Log Console)：等寬字體 (Menlo/Consolas) 唯讀 CTkTextbox，附帶時間戳記與自動滾動。
6. 保留所有使用邏輯：聯賽刷關、OCR步驟比對、優先動作、自訂座標、即時預覽ROI、Scratch積木任務、打擊輔助 100% 完整相容！
"""
import os
import sys
import time
import threading
import json
import queue
import datetime
import subprocess
import shutil
from typing import Optional, Dict, Any, List, Tuple, Callable

import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk

import cv2
import numpy as np
from PIL import Image, ImageTk

from bot_core import BaseballBot
# [AI協作註記] 即時打擊輔助功能已全面關閉（停用狀態），協作與維護聯賽/任務時可直接跳過此模組。
from batting_tab import BattingAssistTab
from task_flow import TaskFlowTab


# ==============================================================================
# 🎨 現代化深色主題調色盤 (Low-Saturation Modern Dark Palette)
# ==============================================================================
COLOR_BG = "#1E1E2E"           # 主視窗背景 (Catppuccin Mocha Base)
COLOR_CARD = "#252538"         # 卡片/容器底色
COLOR_CARD_BORDER = "#313244"  # 卡片邊框
COLOR_CARD_ITEM = "#20222e"    # 步驟卡片內部底色
COLOR_INPUT_BG = "#181825"     # 輸入框/終端文字底色
COLOR_INPUT_BORDER = "#45475A" # 輸入框邊框

# 狀態指示色彩 (Status Indicator Lights)
COLOR_RUNNING = "#22C55E"      # 綠色：運作中 (Running)
COLOR_PAUSED = "#F59E0B"       # 橙黃色：暫停/未連線
COLOR_STOPPED = "#EF4444"      # 紅色：已停止 (Stopped)

# 按鈕色彩配置 (圓角 corner_radius=8)
COLOR_BTN_START = "#10B981"    # 啟動大按鈕 (Emerald Green)
COLOR_BTN_START_HOVER = "#059669"
COLOR_BTN_STOP = "#EF4444"     # 停止大按鈕 (Rose Red)
COLOR_BTN_STOP_HOVER = "#DC2626"
COLOR_BTN_PRIMARY = "#3B82F6"  # 主要操作按鈕 (Blue)
COLOR_BTN_PRIMARY_HOVER = "#2563EB"
COLOR_BTN_DARK = "#313244"     # 次要灰底按鈕
COLOR_BTN_DARK_HOVER = "#45475A"

# 文字排版色彩
COLOR_TEXT_PRIMARY = "#CDD6F4" # 主要文字亮白
COLOR_TEXT_MUTED = "#A6ADC8"   # 次要說明文字淺灰
COLOR_TEXT_DIM = "#6C7086"     # 邊緣提示資訊


# ==============================================================================
# 📋 步驟與辨識選項常數
# ==============================================================================
ROI_OPTIONS = ["右下角區域", "右半側螢幕", "下半部區域", "中央區域", "全畫面比對", "自訂特定區塊"]
REPEAT_MODES = ["持續連點", "指定次數"]
REPEAT_AREAS = ["右下角區域", "中央區域", "右上角 (Skip)", "右半側中央", "跟隨命中目標", "自訂座標"]

# 動作模式常數 (圖片特徵模式 vs 文字辨識模式)
ACTION_TARGET_IMAGE = "🎯 點擊目標圖片 (按鈕中心)"
ACTION_TARGET_TEXT = "🎯 點擊目標文字 (詞條中心)"
ACTION_CUSTOM_COORD = "📍 點擊指定座標 (自訂)"
ACTION_CUSTOM_BLOCK = "自訂特定區塊"
ACTION_REPEAT = "持續連點"
ACTION_WAIT = "無動作(僅等待)"
ACTION_TASK_FLOW = "📋 執行任務清單"

ACTION_OPTIONS_IMAGE = [
    ACTION_TARGET_IMAGE,
    ACTION_CUSTOM_COORD,
    ACTION_CUSTOM_BLOCK,
    ACTION_REPEAT,
    ACTION_WAIT,
    ACTION_TASK_FLOW,
]

ACTION_OPTIONS_TEXT = [
    ACTION_TARGET_TEXT,
    ACTION_CUSTOM_COORD,
    ACTION_CUSTOM_BLOCK,
    ACTION_REPEAT,
    ACTION_WAIT,
    ACTION_TASK_FLOW,
]

ACTION_OPTIONS = [
    ACTION_TARGET_IMAGE,
    ACTION_TARGET_TEXT,
    ACTION_CUSTOM_COORD,
    "點擊目標中心 / 詞條",
    "自訂座標",
    ACTION_CUSTOM_BLOCK,
    ACTION_REPEAT,
    ACTION_WAIT,
    ACTION_TASK_FLOW,
]
IDLE_STRATEGIES = ["常規等待", "快速跳過", "自動停止"]
TARGET_TYPES = ["📝 文字辨識 (OCR)", "🖼️ 圖片特徵 (模板比對)", "✅ 勾選方塊 (打勾)", "❌ 關閉按鈕 (叉叉)"]
RECOGNITION_MODES = ["🖼️ 圖片特徵比對模式", "📝 文字辨識模式"]

# 步驟卡片專屬邊框色 (拖曳時色彩跟隨)
STEP_COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4"]

# 預覽畫布固定尺寸 (16:9 高畫質大尺寸鎖死，杜絕排版位移與框選跳動)
PREVIEW_CANVAS_W = 800
PREVIEW_CANVAS_H = 450

# 預設 Telegram 設定
DEFAULT_TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DEFAULT_TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 獨立於 Git 倉庫之使用者存檔目錄持久化檔案路徑 (存放在使用者家目錄)
USER_STORAGE_CONFIG_FILE = os.path.expanduser("~/.auto9innings_storage_path.json")


def get_persisted_storage_dir() -> str:
    """從使用者個人目錄讀取持久化存檔路徑 (完全不受 git pull/push 影響)"""
    try:
        if os.path.exists(USER_STORAGE_CONFIG_FILE):
            with open(USER_STORAGE_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            path = data.get("storage_dir", "").strip()
            if path:
                if os.path.isdir(path):
                    return os.path.abspath(path)
                elif os.path.isdir(os.path.dirname(path)):
                    return os.path.abspath(os.path.dirname(path))
    except Exception:
        pass

    # 預設路徑：以目前專案腳本所在目錄為預設，絕不自動建立額外資料夾
    return os.path.abspath(os.path.dirname(__file__))


def persist_storage_dir(path: str):
    """將存檔路徑寫入使用者個人目錄 (~/.auto9innings_storage_path.json)"""
    try:
        data = {"storage_dir": os.path.abspath(path)}
        with open(USER_STORAGE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass



def _num(var, default, cast=float):
    """安全讀取數值變數 (輸入框暫時為空或格式錯誤時回傳預設值)"""
    try:
        val = var.get() if hasattr(var, "get") else var
        return cast(val)
    except Exception:
        return default


def _normalize_target_type(t: str) -> str:
    """正規化步驟辨識類型"""
    if not t:
        return "📝 文字辨識 (OCR)"
    t = str(t)
    if "圖片" in t or "image" in t.lower() or "模板" in t:
        return "🖼️ 圖片特徵 (模板比對)"
    if "打勾" in t or "check" in t.lower():
        return "✅ 勾選方塊 (打勾)"
    if "叉叉" in t or "cross" in t.lower() or "關閉" in t:
        return "❌ 關閉按鈕 (叉叉)"
    return "📝 文字辨識 (OCR)"


def is_custom_coord_action(a: str) -> bool:
    """判斷動作是否為點擊指定座標/自訂座標"""
    if not a:
        return False
    s = str(a).strip()
    return (
        s in (
            "自訂座標", "點擊指定座標", "自訂特定區塊", "custom_coord",
            ACTION_CUSTOM_COORD, ACTION_CUSTOM_BLOCK
        )
        or "指定座標" in s
        or "自訂" in s
        or "custom" in s.lower()
    )


def is_target_center_action(a: str) -> bool:
    """判斷動作是否為點擊辨識目標中心 (圖片或文字)"""
    if not a:
        return True
    if is_custom_coord_action(a):
        return False
    s = str(a).strip()
    if s in (ACTION_REPEAT, ACTION_WAIT, ACTION_TASK_FLOW) or "任務清單" in s or "連點" in s or "等待" in s:
        return False
    return True


def _normalize_action(a: str, is_image: bool = True) -> str:
    """正規化動作選項，依當前辨識模式區分圖片或文字標籤，並維持高度向下相容性"""
    if not a:
        return ACTION_TARGET_IMAGE if is_image else ACTION_TARGET_TEXT
    a = str(a).strip()
    if is_custom_coord_action(a):
        if a == ACTION_CUSTOM_BLOCK or "區塊" in a:
            return ACTION_CUSTOM_BLOCK
        return ACTION_CUSTOM_COORD
    if a in (ACTION_REPEAT, "持續連點"):
        return ACTION_REPEAT
    if a in (ACTION_WAIT, "無動作(僅等待)", "僅等待", "無動作"):
        return ACTION_WAIT
    if a == ACTION_TASK_FLOW or "任務清單" in a or "jump_task" in a:
        return ACTION_TASK_FLOW
    # 預設為點擊辨識到的目標中心 (圖片按鈕或文字詞條)
    return ACTION_TARGET_IMAGE if is_image else ACTION_TARGET_TEXT


def imread_unicode(path: str, flags: int = cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
    """跨平台安全讀取包含中文檔名的圖片"""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, flags)
    except Exception:
        return None


def imwrite_unicode(path: str, img: np.ndarray) -> bool:
    """跨平台安全寫入包含中文檔名與路徑的圖片"""
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
            encoded.tofile(p)
            return os.path.exists(p) and os.path.getsize(p) > 0
        return False
    except Exception:
        return False


# ==============================================================================
# ✂️ 模板截圖選取視窗 (Template Snipping Tool)
# ==============================================================================
class TemplateSnipperDialog(ctk.CTkToplevel):
    """
    從當前遊戲畫面中拖曳框選局部按鈕/圖示，直接裁切儲存為圖片模板。
    """
    def __init__(
        self,
        parent,
        screen_bgr: np.ndarray,
        initial_name: str,
        templates_dir: str,
        on_save_callback: Callable[[str], None]
    ):
        super().__init__(parent)
        self.title("✂️ 從畫面框選按鈕模板")
        self.geometry("980x700")
        self.minsize(860, 620)
        self.configure(fg_color=COLOR_BG)
        self.grab_set()
        self.transient(parent)

        self.screen_bgr = screen_bgr
        self.save_dir = templates_dir if (templates_dir and os.path.exists(templates_dir)) else os.path.dirname(os.path.abspath(__file__))
        self.templates_dir = self.save_dir
        self.on_save_callback = on_save_callback
        self.crop_bgr = None

        h, w = screen_bgr.shape[:2]
        self.orig_w, self.orig_h = w, h

        # 頂部提示列
        top_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=8)
        top_frame.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(
            top_frame,
            text="✂️ 在下方畫面上「按住滑鼠左鍵並拖曳」框選目標按鈕，放開後即可預覽並儲存為模板圖片。",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FBBF24"
        ).pack(side="left", padx=12, pady=8)

        # 畫布容器
        canvas_container = ctk.CTkFrame(self, fg_color="#11111B", corner_radius=8)
        canvas_container.pack(fill="both", expand=True, padx=12, pady=4)

        self.canvas_w = 940
        self.canvas_h = 490
        self.canvas = tk.Canvas(
            canvas_container,
            bg="#11111B",
            highlightthickness=0,
            cursor="crosshair"
        )
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)

        # 縮放原圖至適合視窗
        scale = min(self.canvas_w / w, self.canvas_h / h)
        self.scale = scale
        self.disp_w = int(w * scale)
        self.disp_h = int(h * scale)

        disp_resized = cv2.resize(screen_bgr, (self.disp_w, self.disp_h), interpolation=cv2.INTER_AREA)
        disp_rgb = cv2.cvtColor(disp_resized, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(disp_rgb))

        self.img_on_canvas = self.canvas.create_image(
            self.canvas_w // 2, self.canvas_h // 2,
            image=self.photo, anchor="center"
        )

        self.offset_x = (self.canvas_w - self.disp_w) // 2
        self.offset_y = (self.canvas_h - self.disp_h) // 2

        self.rect_id = None
        self.start_x = 0
        self.start_y = 0

        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # 底部控制與預覽列
        bot_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=8)
        bot_frame.pack(fill="x", padx=12, pady=(4, 10))

        # 縮圖預覽
        self.lbl_crop_thumb = ctk.CTkLabel(bot_frame, text="[請框選按鈕]", width=80, height=60, fg_color=COLOR_INPUT_BG, corner_radius=6)
        self.lbl_crop_thumb.pack(side="left", padx=10, pady=8)

        # 資訊與命名
        info_box = ctk.CTkFrame(bot_frame, fg_color="transparent")
        info_box.pack(side="left", fill="x", expand=True, padx=6)

        self.lbl_crop_info = ctk.CTkLabel(info_box, text="選取尺寸: 尚未框選", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_crop_info.pack(anchor="w")

        row_dir = ctk.CTkFrame(info_box, fg_color="transparent")
        row_dir.pack(fill="x", pady=(2, 2))
        ctk.CTkLabel(row_dir, text="儲存目錄:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        self.lbl_save_dir = ctk.CTkLabel(row_dir, text=self.save_dir, font=ctk.CTkFont(family="Menlo", size=10), text_color=COLOR_TEXT_MUTED, anchor="w")
        self.lbl_save_dir.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(row_dir, text="📁 變更目錄", width=76, height=24, font=ctk.CTkFont(size=10), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, command=self._choose_save_dir).pack(side="left")

        row_name = ctk.CTkFrame(info_box, fg_color="transparent")
        row_name.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(row_name, text="儲存檔名:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        clean_init = "".join(c for c in initial_name if c.isalnum() or c in ("_", "-")).strip() or "btn_template"
        self.var_filename = tk.StringVar(value=f"{clean_init}.png")
        self.entry_filename = ctk.CTkEntry(row_name, textvariable=self.var_filename, width=180, height=26, corner_radius=6, fg_color=COLOR_INPUT_BG)
        self.entry_filename.pack(side="left", padx=(0, 6))
        ctk.CTkButton(row_name, text="另存為...", width=64, height=26, font=ctk.CTkFont(size=10), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, command=self._choose_save_as).pack(side="left")

        # 按鈕列
        btn_box = ctk.CTkFrame(bot_frame, fg_color="transparent")
        btn_box.pack(side="right", padx=10)

        self.btn_save = ctk.CTkButton(
            btn_box,
            text="💾 儲存並套用",
            width=100,
            height=32,
            corner_radius=6,
            fg_color="#22C55E",
            hover_color="#16A34A",
            font=ctk.CTkFont(weight="bold"),
            state="disabled",
            command=self._do_save
        )
        self.btn_save.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_box,
            text="取消",
            width=68,
            height=32,
            corner_radius=6,
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.destroy
        ).pack(side="left")

    def _choose_save_dir(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.save_dir, title="選擇模板圖片儲存目錄")
        if d:
            self.save_dir = os.path.abspath(d)
            self.templates_dir = self.save_dir
            self.lbl_save_dir.configure(text=self.save_dir)

    def _choose_save_as(self):
        fn = self.var_filename.get().strip() or "template.png"
        f = filedialog.asksaveasfilename(
            parent=self,
            title="選擇模板儲存位置與檔名",
            initialdir=self.save_dir,
            initialfile=fn,
            defaultextension=".png",
            filetypes=[("PNG 圖片", "*.png"), ("所有檔案", "*.*")]
        )
        if f:
            self.save_dir = os.path.dirname(os.path.abspath(f))
            self.templates_dir = self.save_dir
            self.var_filename.set(os.path.basename(f))
            self.lbl_save_dir.configure(text=self.save_dir)

    def _on_mouse_down(self, e):
        self.start_x = e.x
        self.start_y = e.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None

    def _on_mouse_drag(self, e):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, e.x, e.y)
        else:
            self.rect_id = self.canvas.create_rectangle(
                self.start_x, self.start_y, e.x, e.y,
                outline="#22C55E", width=2, dash=(4, 2)
            )

    def _on_mouse_up(self, e):
        x1 = min(self.start_x, e.x) - self.offset_x
        y1 = min(self.start_y, e.y) - self.offset_y
        x2 = max(self.start_x, e.x) - self.offset_x
        y2 = max(self.start_y, e.y) - self.offset_y

        rx1 = max(0, min(self.orig_w, int(x1 / self.scale)))
        ry1 = max(0, min(self.orig_h, int(y1 / self.scale)))
        rx2 = max(0, min(self.orig_w, int(x2 / self.scale)))
        ry2 = max(0, min(self.orig_h, int(y2 / self.scale)))

        w = rx2 - rx1
        h = ry2 - ry1

        if w < 8 or h < 8:
            self.lbl_crop_info.configure(text="選取範圍過小，請重新框選")
            self.btn_save.configure(state="disabled")
            self.crop_bgr = None
            return

        self.crop_bgr = self.screen_bgr[ry1:ry2, rx1:rx2].copy()
        self.lbl_crop_info.configure(text=f"選取尺寸: {w} × {h} 像素 (範圍: X {rx1}~{rx2}, Y {ry1}~{ry2})")

        # 產生預覽縮圖
        rgb = cv2.cvtColor(self.crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        pil_img.thumbnail((76, 56))
        self.crop_photo = ImageTk.PhotoImage(pil_img)
        self.lbl_crop_thumb.configure(image=self.crop_photo, text="")
        self.btn_save.configure(state="normal")

    def _do_save(self):
        if self.crop_bgr is None:
            messagebox.showwarning("提示", "尚未框選按鈕範圍！請在畫面上拖曳框選。", parent=self)
            return
        fname = self.var_filename.get().strip()
        if not fname:
            fname = "template.png"
        if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
            fname += ".png"

        target_path = os.path.join(self.save_dir, fname)
        try:
            success = imwrite_unicode(target_path, self.crop_bgr)
            if success:
                self.on_save_callback(target_path)
                messagebox.showinfo("截圖成功", f"✅ 模板圖片已成功儲存至：\n{target_path}\n\n已自動套用至步驟！", parent=self)
                self.destroy()
            else:
                messagebox.showerror("錯誤", f"無法儲存模板檔案至: {target_path}\n請檢查是否有寫入權限或磁碟空間。", parent=self)
        except Exception as ex:
            messagebox.showerror("錯誤", f"儲存模板發生異常: {ex}", parent=self)


# ==============================================================================
# 🏆 核心 GUI 類別：BaseballBotGUI
# ==============================================================================
class BaseballBotGUI:
    """現代化 CustomTkinter 遊戲自動化控制面板與進階步驟編輯器"""

    def __init__(self, root: ctk.CTk, instance_id: int = 1):
        self.root = root
        self.instance_id = instance_id

        # 1. 外觀主題初始化
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        title_suffix = f" (視窗 #{instance_id})" if instance_id > 1 else ""
        self.root.title(f"⚾ Auto9Innings 自動刷關控制中心{title_suffix}")
        self.root.geometry("1440x920")
        self.root.minsize(1260, 780)
        self.root.configure(fg_color=COLOR_BG)

        self.config_dir = os.path.dirname(os.path.abspath(__file__))

        # 2. 自動化核心與工作執行緒
        self.bot = BaseballBot(log_callback=self.log_message, on_frame_callback=self.on_bot_frame_update)
        self.worker_thread = None
        self.is_running = False

        # 獨立存檔與圖片資料夾初始化 (持久化讀取，預設 ~/Documents/Auto9Innings_Data，完全獨立於 git 倉庫)
        self.league_presets: Dict[str, Dict[str, Any]] = {}
        self.var_storage_display = tk.StringVar(value="")
        self.set_storage_dir(get_persisted_storage_dir(), seed=False)

        # 最新框選裁切模板檔名快取
        self.last_snipped_template = ""
        try:
            if hasattr(self, "templates_dir") and os.path.exists(self.templates_dir):
                _f_list = [f for f in os.listdir(self.templates_dir) if f.lower().endswith((".png", ".jpg"))]
                if _f_list:
                    _f_list.sort(key=lambda x: os.path.getmtime(os.path.join(self.templates_dir, x)), reverse=True)
                    self.last_snipped_template = _f_list[0]
        except Exception:
            pass

        # 統計指標
        self.start_time: Optional[float] = None
        self.total_uptime_seconds = 0
        self.loop_count = 0
        self.hit_count = 0

        # 非同步日誌佇列
        self.log_queue = queue.Queue()
        self.auto_scroll_logs = True

        # 預覽畫面狀態
        self.current_screen_bgr = None
        self._last_detected = None
        self._display_full = None
        self.preview_image_tk = None
        self.preview_scale = 1.0
        self.preview_img_w = 0
        self.preview_img_h = 0
        self.canvas_w = PREVIEW_CANVAS_W
        self.canvas_h = PREVIEW_CANVAS_H
        self.raw_screen_w = 0
        self.raw_screen_h = 0
        self._capturing = False
        self._resize_job = None
        self._preview_update_pending = False
        self._last_preview_time = 0.0
        self._preview_frame_count = 0
        self.auto_refresh_job = None

        # 預覽畫面框選與裁切狀態
        self.preview_crop_coords: Optional[Tuple[int, int, int, int]] = None
        self.is_dragging = False
        self.preview_canvas_img_id = None

        # 3. 綁定變數
        self.var_device = tk.StringVar()
        self.var_status_text = tk.StringVar(value="未連線 (DISCONNECTED)")
        self.var_interval = tk.DoubleVar(value=2.5)
        self.var_confidence = tk.DoubleVar(value=0.65)
        self.var_idle_strategy = tk.StringVar(value=IDLE_STRATEGIES[0])
        self.var_auto_refresh = tk.BooleanVar(value=True)
        self.var_preview_interval = tk.StringVar(value="1.5秒")
        self.var_preview_coords = tk.StringVar(value="")
        self.var_recognition_mode = tk.StringVar(value="🖼️ 圖片特徵比對模式")

        # 語言辨識與過濾 (預設繁中+英文開啟，簡中關閉杜絕誤判)
        self.var_lang_tc = tk.BooleanVar(value=True)
        self.var_lang_sc = tk.BooleanVar(value=False)
        self.var_lang_en = tk.BooleanVar(value=True)

        def _on_lang_changed(*_):
            self.bot.set_allowed_languages(
                self.var_lang_tc.get(),
                self.var_lang_sc.get(),
                self.var_lang_en.get()
            )
            self.auto_save_current_config()

        self.var_lang_tc.trace_add("write", _on_lang_changed)
        self.var_lang_sc.trace_add("write", _on_lang_changed)
        self.var_lang_en.trace_add("write", _on_lang_changed)
        self.bot.set_allowed_languages(True, False, True)

        # 看門狗防卡死守護參數
        self.var_watchdog_enabled = tk.BooleanVar(value=False)
        self.var_watchdog_seconds = tk.IntVar(value=60)
        self._watchdog_restart_job = None

        # 等待時連點參數
        self.var_idle_tap_enabled = tk.BooleanVar(value=False)
        self.var_idle_tap_area = tk.StringVar(value="右下角區域")
        self.var_idle_tap_times = tk.IntVar(value=3)
        self.var_idle_tap_interval = tk.DoubleVar(value=0.4)
        self.var_idle_tap_custom_x = tk.IntVar(value=983)
        self.var_idle_tap_custom_y = tk.IntVar(value=1023)

        # Telegram Bot 通知全域設定
        self.var_tg_token = tk.StringVar(value=DEFAULT_TG_TOKEN)
        self.var_tg_chat_id = tk.StringVar(value=DEFAULT_TG_CHAT_ID)

        # 進階設定變更即刻自動儲存監聽
        self._is_loading_config = False

        def _on_adv_var_changed(*_):
            if getattr(self, "_is_loading_config", False):
                return
            self.auto_save_current_config()

        self.var_interval.trace_add("write", _on_adv_var_changed)
        self.var_confidence.trace_add("write", _on_adv_var_changed)
        self.var_idle_strategy.trace_add("write", _on_adv_var_changed)
        self.var_watchdog_enabled.trace_add("write", _on_adv_var_changed)
        self.var_watchdog_seconds.trace_add("write", _on_adv_var_changed)
        self.var_idle_tap_enabled.trace_add("write", _on_adv_var_changed)
        self.var_idle_tap_area.trace_add("write", _on_adv_var_changed)
        self.var_idle_tap_times.trace_add("write", _on_adv_var_changed)
        self.var_idle_tap_interval.trace_add("write", _on_adv_var_changed)
        self.var_idle_tap_custom_x.trace_add("write", _on_adv_var_changed)
        self.var_idle_tap_custom_y.trace_add("write", _on_adv_var_changed)
        self.var_tg_token.trace_add("write", _on_adv_var_changed)
        self.var_tg_chat_id.trace_add("write", _on_adv_var_changed)

        # 步驟清單
        self.priority_steps_list = []  # 最高優先動作 (if/elif 條件中斷)
        self.steps_list = []           # 一般循序步驟
        self._adv_open = False

        # 4. 建立現代化介面排版
        self._build_ui()
        self._init_default_steps()
        self.on_refresh_devices()

        # 5. 計時排程與視窗事件
        self.root.after(50, self._process_log_queue)
        self.root.after(1000, self._update_uptime_timer)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

        # 啟動初始日誌
        self.log_message("✨ 現代化控制面板初始化完成！")

    # ==========================================================================
    # 📐 介面排版建構 (Layout Structure)
    # ==========================================================================
    def _build_ui(self):
        """建構主容器：頂部狀態導覽卡片 + 主內容 Tabview 分頁"""
        # 主外層容器 (Padding 14)
        main_box = ctk.CTkFrame(self.root, fg_color="transparent")
        main_box.pack(fill="both", expand=True, padx=14, pady=12)

        # 1. 頂部狀態與控制卡片
        self._build_topbar(main_box)

        # 2. 分頁標籤管理器 (CTkTabview)
        self.tabview = ctk.CTkTabview(
            main_box,
            corner_radius=10,
            fg_color=COLOR_BG,
            segmented_button_fg_color=COLOR_CARD,
            segmented_button_selected_color=COLOR_BTN_PRIMARY,
            segmented_button_selected_hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self._on_tab_changed
        )
        self.tabview.pack(fill="both", expand=True, pady=(10, 0))

        # 頁籤 1: 🏆 聯賽自動刷
        tab_league = self.tabview.add("🏆 聯賽自動刷")
        self._build_league_tab(tab_league)

        # 頁籤 2: 📋 任務清單 (Scratch 積木)
        tab_tasks = self.tabview.add("📋 任務清單 (Scratch 積木)")
        self.task_tab = TaskFlowTab(
            tab_tasks,
            bot_instance=self.bot,
            gui_parent=self,
            log_callback=self.log_message,
            instance_id=self.instance_id
        )
        self.bot.set_task_flow_handler(self._execute_task_flow_for_event)

        # 頁籤 3: ⚡ 即時打擊輔助 (放到最後，點擊跳出警告並覆蓋灰色遮罩完全停用)
        tab_batting = self.tabview.add("⚡ 即時打擊輔助")
        self._build_disabled_batting_tab(tab_batting)

    def _on_tab_changed(self):
        """切換頁籤事件回呼：當點擊進入打擊輔助時先跳出警告"""
        selected_tab = self.tabview.get()
        if "即時打擊輔助" in selected_tab:
            messagebox.showwarning("警告", "正在開發，功能不完全")

    def _build_disabled_batting_tab(self, parent: ctk.CTkFrame):
        """
        建構打擊輔助頁面：
        1. 保留底層原始 BattingAssistTab 介面與程式碼結構。
        2. 以灰色半透明/實心遮罩完整覆蓋全畫面，攔截所有點擊與操作。
        3. 遮罩點擊時即時彈出警告提示。
        """
        try:
            self.batting_tab = BattingAssistTab(
                parent,
                bot_instance=self.bot,
                gui_parent=self,
                log_callback=self.log_message
            )
        except Exception:
            self.batting_tab = None

        # 灰色半透明鎖定遮罩 (覆蓋整個頁面，無法點開底層任何元件)
        overlay = ctk.CTkFrame(
            parent,
            fg_color="#181825",
            corner_radius=12,
            border_width=2,
            border_color="#45475A"
        )
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        overlay.lift()

        def _warn_disabled(event=None):
            messagebox.showwarning("警告", "正在開發，功能不完全")

        overlay.bind("<Button-1>", _warn_disabled)

        # 遮罩內部居中警告卡片
        center_card = ctk.CTkFrame(
            overlay,
            fg_color="#252538",
            corner_radius=16,
            border_width=1,
            border_color="#313244",
            width=540,
            height=280
        )
        center_card.place(relx=0.5, rely=0.5, anchor="center")
        center_card.pack_propagate(False)
        center_card.bind("<Button-1>", _warn_disabled)

        lbl_icon = ctk.CTkLabel(center_card, text="⚠️", font=ctk.CTkFont(size=46))
        lbl_icon.pack(pady=(26, 6))
        lbl_icon.bind("<Button-1>", _warn_disabled)

        lbl_title = ctk.CTkLabel(
            center_card,
            text="正在開發，功能不完全",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#F59E0B"
        )
        lbl_title.pack(pady=4)
        lbl_title.bind("<Button-1>", _warn_disabled)

        lbl_desc = ctk.CTkLabel(
            center_card,
            text="即時打擊輔助功能目前暫停使用，畫面已鎖定。\n背景計算、視窗截圖與按鍵模擬已全面關閉。\n請使用「🏆 聯賽自動刷」或「📋 任務清單」進行自動化操作。",
            font=ctk.CTkFont(size=13),
            text_color="#A6ADC8",
            justify="center"
        )
        lbl_desc.pack(pady=(8, 14))
        lbl_desc.bind("<Button-1>", _warn_disabled)

        badge = ctk.CTkLabel(
            center_card,
            text="🔒 [ 功能已停用 (Feature Disabled) ]",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#6C7086"
        )
        badge.pack()
        badge.bind("<Button-1>", _warn_disabled)

    # --------------------------------------------------------------------------
    # 💾 專案存檔設定對話框 (按下存檔後跳出的視窗，自訂存檔目錄與確認儲存)
    # --------------------------------------------------------------------------
    def on_open_save_dialog(self):
        """開啟專案存檔視窗：詢問使用者要存到哪裡，可直接自訂路徑與檔名儲存，不生成任何多餘資料夾"""
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("💾 儲存設定")
        dlg.geometry("580x300")
        dlg.minsize(520, 260)
        dlg.resizable(False, False)
        dlg.configure(fg_color=COLOR_BG)
        dlg.grab_set()
        dlg.transient(self.root)

        card = ctk.CTkFrame(dlg, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # 頂部標題列
        header_box = ctk.CTkFrame(card, fg_color="transparent")
        header_box.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            header_box,
            text="💾 儲存設定 (Save Settings)",
            font=ctk.CTkFont(family="Arial", size=16, weight="bold"),
            text_color="#FBBF24"
        ).pack(anchor="w")

        ctk.CTkLabel(
            header_box,
            text="請選擇或輸入設定檔要儲存到哪裡（.json 檔案）：",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_PRIMARY
        ).pack(anchor="w", pady=(4, 0))

        # 路徑輸入與選擇區塊
        sec_path = ctk.CTkFrame(card, fg_color=COLOR_INPUT_BG, corner_radius=8, border_width=1, border_color=COLOR_CARD_BORDER)
        sec_path.pack(fill="x", padx=16, pady=(8, 12))

        sec_path_inner = ctk.CTkFrame(sec_path, fg_color="transparent")
        sec_path_inner.pack(fill="x", padx=12, pady=12)

        default_save_path = getattr(self, "auto_save_file", None)
        if not default_save_path:
            default_save_path = os.path.join(self.storage_dir, "baseball_last_config.json")

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
            init_d = os.path.dirname(curr) if curr and os.path.isdir(os.path.dirname(curr)) else self.storage_dir
            init_f = os.path.basename(curr) if curr else "baseball_config.json"
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

        # 狀態訊息
        lbl_msg = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color="#10B981")
        lbl_msg.pack(fill="x", padx=16, pady=(0, 8))

        def _do_save_file():
            p = var_save_file.get().strip()
            if not p:
                messagebox.showwarning("提示", "請輸入或選擇儲存路徑！", parent=dlg)
                return
            if not p.lower().endswith(".json"):
                p += ".json"
                var_save_file.set(p)

            target_path = os.path.abspath(p)
            try:
                parent_dir = os.path.dirname(target_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)

                cfg = self.serialize_current_config()
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)

                self.auto_save_file = target_path
                self.storage_dir = os.path.dirname(target_path)
                self.templates_dir = self.storage_dir
                persist_storage_dir(self.storage_dir)
                if hasattr(self, "bot") and self.bot:
                    self.bot.set_templates_dir(self.templates_dir)

                lbl_msg.configure(text=f"✅ 已成功儲存至：{os.path.basename(target_path)}")
                self.log_message(f"💾 設定已成功儲存至: {target_path}")
                messagebox.showinfo("儲存成功", f"✅ 設定已成功儲存至：\n{target_path}", parent=dlg)
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("儲存失敗", f"無法寫入檔案: {ex}", parent=dlg)

        # 底部按鈕
        btn_box = ctk.CTkFrame(card, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(0, 14), side="bottom")

        ctk.CTkButton(
            btn_box,
            text="💾 確認儲存",
            width=120,
            height=34,
            corner_radius=6,
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=_do_save_file
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_box,
            text="取消",
            width=70,
            height=34,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=dlg.destroy
        ).pack(side="right")

    # --------------------------------------------------------------------------
    # 頂部狀態列 (大字體指示燈、統計數據、裝置連線與主控制大按鈕)
    # --------------------------------------------------------------------------
    def _build_topbar(self, parent: ctk.CTkFrame):
        bar = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        bar.pack(fill="x", ipady=4)

        # 左側：狀態指示燈與大字體狀態
        left_box = ctk.CTkFrame(bar, fg_color="transparent")
        left_box.pack(side="left", padx=16, pady=8)

        self.indicator_light = ctk.CTkLabel(
            left_box,
            text="●",
            font=ctk.CTkFont(family="Arial", size=24, weight="bold"),
            text_color=COLOR_STOPPED,
            width=24
        )
        self.indicator_light.pack(side="left", padx=(0, 8))

        status_text_box = ctk.CTkFrame(left_box, fg_color="transparent")
        status_text_box.pack(side="left")

        self.lbl_status = ctk.CTkLabel(
            status_text_box,
            textvariable=self.var_status_text,
            font=ctk.CTkFont(family="Arial", size=17, weight="bold"),
            text_color=COLOR_STOPPED
        )
        self.lbl_status.pack(anchor="w")

        self.lbl_metrics_inline = ctk.CTkLabel(
            status_text_box,
            text="⏱ 運行: 00:00:00   |   🔄 輪次: 0 次   |   🎯 命中: 0 次",
            font=ctk.CTkFont(family="Menlo", size=11),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_metrics_inline.pack(anchor="w")

        # 右側：裝置選取、連線與主操作大按鈕
        right_box = ctk.CTkFrame(bar, fg_color="transparent")
        right_box.pack(side="right", padx=14, pady=8)

        # 裝置選取 Combobox
        self.combo_devices = ctk.CTkComboBox(
            right_box,
            variable=self.var_device,
            width=175,
            height=34,
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            state="readonly"
        )
        self.combo_devices.pack(side="left", padx=(0, 6))

        self.btn_refresh = ctk.CTkButton(
            right_box,
            text="🔍 搜尋",
            width=68,
            height=34,
            corner_radius=8,
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_refresh_devices
        )
        self.btn_refresh.pack(side="left", padx=(0, 6))

        self.btn_connect = ctk.CTkButton(
            right_box,
            text="⚡ 連線",
            width=68,
            height=34,
            corner_radius=8,
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self.on_connect_device
        )
        self.btn_connect.pack(side="left", padx=(0, 10))

        # 開新視窗
        self.btn_new_win = ctk.CTkButton(
            right_box,
            text="＋ 開新視窗",
            width=85,
            height=34,
            corner_radius=8,
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_open_new_window
        )
        self.btn_new_win.pack(side="left", padx=(0, 6))

        # 儲存設定與自訂存檔位置
        self.btn_top_save = ctk.CTkButton(
            right_box,
            text="💾 儲存設定",
            width=85,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            command=self.on_open_save_dialog
        )
        self.btn_top_save.pack(side="left", padx=(0, 10))

        # 主控制大按鈕：啟動 (Start)
        self.btn_start = ctk.CTkButton(
            right_box,
            text="▶ 啟動刷關",
            width=100,
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            fg_color=COLOR_BTN_START,
            hover_color=COLOR_BTN_START_HOVER,
            state="disabled",
            command=self.on_start_bot
        )
        self.btn_start.pack(side="left", padx=(0, 6))

        # 主控制大按鈕：停止 (Stop)
        self.btn_stop = ctk.CTkButton(
            right_box,
            text="⏹ 停止刷關",
            width=100,
            height=38,
            corner_radius=8,
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            fg_color=COLOR_BTN_STOP,
            hover_color=COLOR_BTN_STOP_HOVER,
            state="disabled",
            command=self.on_stop_bot
        )
        self.btn_stop.pack(side="left")

    # --------------------------------------------------------------------------
    # 聯賽自動刷頁籤 (左右雙欄佈局)
    # --------------------------------------------------------------------------
    def _build_league_tab(self, parent: ctk.CTkFrame):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=4, pady=4)
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=0)
        container.grid_rowconfigure(0, weight=1)

        # 左欄：步驟與優先動作卡片列表 + 進階參數格 (寬度隨視窗彈性展開)
        left_pane = ctk.CTkFrame(container, fg_color="transparent")
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        self._build_steps_panel(left_pane)
        self._build_advanced_panel(left_pane)

        # 右欄：即時截圖預覽卡片 + 等寬日誌終端 (鎖死固定寬度 824px，高度日誌彈性)
        right_pane = ctk.CTkFrame(container, fg_color="transparent", width=824)
        right_pane.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        right_pane.grid_rowconfigure(0, weight=0)
        right_pane.grid_rowconfigure(1, weight=1)
        right_pane.grid_columnconfigure(0, weight=1)

        self._build_preview_panel(right_pane)
        self._build_log_panel(right_pane)

    # --------------------------------------------------------------------------
    # 步驟與優先動作清單卡片 (左側上半部，支援滾動)
    # --------------------------------------------------------------------------
    def _build_steps_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="both", expand=True, pady=(0, 8))

        # 頂部工具列 (彈性雙行佈局，徹底解決按鈕擠壓遮蔽)
        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=12, pady=(10, 8))

        # 第一行：標題 + 全域辨識模式切換開關 (圖片特徵 vs 文字OCR)
        tools_row1 = ctk.CTkFrame(tools, fg_color="transparent")
        tools_row1.pack(fill="x", pady=(0, 6))

        lbl_title = ctk.CTkLabel(
            tools_row1,
            text="📋 步驟與優先動作",
            font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        lbl_title.pack(side="left")

        self.seg_mode = ctk.CTkSegmentedButton(
            tools_row1,
            values=RECOGNITION_MODES,
            variable=self.var_recognition_mode,
            command=self._on_recognition_mode_changed,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            selected_color=COLOR_BTN_PRIMARY,
            selected_hover_color=COLOR_BTN_PRIMARY_HOVER
        )
        self.seg_mode.pack(side="right")

        # 第二行：步驟增刪與設定存檔按鈕群 (整齊平鋪排開)
        tools_row2 = ctk.CTkFrame(tools, fg_color="transparent")
        tools_row2.pack(fill="x")

        ctk.CTkButton(tools_row2, text="＋ 優先動作", width=80, height=28, corner_radius=6, command=self.on_add_priority_step, fg_color="#F59E0B", hover_color="#D97706", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        ctk.CTkButton(tools_row2, text="⚡ 事件跳轉", width=80, height=28, corner_radius=6, command=self.on_add_task_trigger_step, fg_color="#8B5CF6", hover_color="#7C3AED", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=3)
        ctk.CTkButton(tools_row2, text="＋ 一般步驟", width=80, height=28, corner_radius=6, command=self.on_add_empty_step, fg_color=COLOR_BTN_PRIMARY, hover_color=COLOR_BTN_PRIMARY_HOVER, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=3)
        ctk.CTkButton(tools_row2, text="💾 儲存設定", width=84, height=28, corner_radius=6, command=self.on_open_save_dialog, fg_color="#10B981", hover_color="#059669", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=4)
        ctk.CTkButton(tools_row2, text="📂 載入設定", width=84, height=28, corner_radius=6, command=self.on_load_config_manual, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=3)

        # 滾動步驟區域 (CTkScrollableFrame)
        self.step_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", corner_radius=8)
        self.step_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 1. 優先動作區塊
        self.frame_priority_section = ctk.CTkFrame(self.step_scroll, fg_color="transparent")
        self.frame_priority_section.pack(fill="x", pady=(0, 6))

        hdr_p = ctk.CTkFrame(self.frame_priority_section, fg_color="transparent")
        hdr_p.pack(fill="x", pady=(2, 4))
        self.lbl_hdr_p = ctk.CTkLabel(hdr_p, text="⚡ 優先動作（由上而下比對，符合即中斷並執行）", font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color="#FBBF24")
        self.lbl_hdr_p.pack(side="left")
        self.lbl_p_count = ctk.CTkLabel(hdr_p, text="(0)", font=ctk.CTkFont(family="Arial", size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_p_count.pack(side="left", padx=4)

        self.frame_priority_cards = ctk.CTkFrame(self.frame_priority_section, fg_color="transparent")
        self.frame_priority_cards.pack(fill="x")

        self.lbl_no_priority = ctk.CTkLabel(
            self.frame_priority_section,
            text="（尚無優先動作，點擊上方「＋ 優先動作」或「⚡ 事件跳轉」新增）",
            font=ctk.CTkFont(family="Arial", size=11),
            text_color=COLOR_TEXT_DIM
        )
        self.lbl_no_priority.pack(pady=4)

        # 2. 一般步驟區塊
        self.frame_normal_section = ctk.CTkFrame(self.step_scroll, fg_color="transparent")
        self.frame_normal_section.pack(fill="x", pady=(6, 0))

        hdr_n = ctk.CTkFrame(self.frame_normal_section, fg_color="transparent")
        hdr_n.pack(fill="x", pady=(2, 4))
        self.lbl_hdr_n = ctk.CTkLabel(hdr_n, text="🔄 一般步驟（依序循環執行）", font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color="#60A5FA")
        self.lbl_hdr_n.pack(side="left")
        self.lbl_n_count = ctk.CTkLabel(hdr_n, text="(0)", font=ctk.CTkFont(family="Arial", size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_n_count.pack(side="left", padx=4)

        self.frame_normal_cards = ctk.CTkFrame(self.frame_normal_section, fg_color="transparent")
        self.frame_normal_cards.pack(fill="x")

    # --------------------------------------------------------------------------
    # 參數設定格 (Settings Grid / Advanced Panel，可展開收合)
    # --------------------------------------------------------------------------
    def _build_advanced_panel(self, parent: ctk.CTkFrame):
        self.adv_card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        self.adv_card.pack(fill="x", pady=(0, 0))

        # 展開/收合開關按鈕列
        toggle_bar = ctk.CTkFrame(self.adv_card, fg_color="transparent")
        toggle_bar.pack(fill="x", padx=12, pady=8)

        self.btn_adv = ctk.CTkButton(
            toggle_bar,
            text="⚙️ 進階參數設定 ▸",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            corner_radius=6,
            height=30,
            command=self._toggle_advanced
        )
        self.btn_adv.pack(side="left")

        # 內部設定網格 (預設隱藏)
        self.adv_content = ctk.CTkFrame(self.adv_card, fg_color="transparent")

        grid = ctk.CTkFrame(self.adv_content, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=(0, 10))
        grid.grid_columnconfigure((0, 2), weight=0, minsize=100)
        grid.grid_columnconfigure((1, 3), weight=1)

        # 1. 掃描間隔秒數
        ctk.CTkLabel(grid, text="⏱ 掃描間隔 (秒):", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=0, column=0, sticky="w", pady=4)
        row_speed = ctk.CTkFrame(grid, fg_color="transparent")
        row_speed.grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=4)
        self.lbl_sp_val = ctk.CTkLabel(row_speed, text=f"{self.var_interval.get():.1f}s", width=42, font=ctk.CTkFont(family="Menlo", size=11))
        slider_sp = ctk.CTkSlider(row_speed, from_=0.5, to=8.0, number_of_steps=75, variable=self.var_interval, height=16)
        slider_sp.pack(side="left", fill="x", expand=True)
        self.lbl_sp_val.pack(side="left", padx=4)
        slider_sp.configure(command=lambda v: [self.lbl_sp_val.configure(text=f"{v:.1f}s"), self.auto_save_current_config()])

        # 2. 文字辨識信心門檻 (專屬 OCR，不影響圖片)
        ctk.CTkLabel(grid, text="🎯 文字門檻 (OCR):", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=0, column=2, sticky="w", pady=4)
        row_conf = ctk.CTkFrame(grid, fg_color="transparent")
        row_conf.grid(row=0, column=3, sticky="ew", padx=(6, 0), pady=4)
        self.lbl_cf_val = ctk.CTkLabel(row_conf, text=f"{self.var_confidence.get():.2f}", width=40, font=ctk.CTkFont(family="Menlo", size=11))
        slider_cf = ctk.CTkSlider(row_conf, from_=0.4, to=0.95, number_of_steps=55, variable=self.var_confidence, height=16)
        slider_cf.pack(side="left", fill="x", expand=True)
        self.lbl_cf_val.pack(side="left", padx=4)
        slider_cf.configure(command=lambda v: [self.lbl_cf_val.configure(text=f"{v:.2f}"), setattr(self.bot, "confidence_threshold", float(v)), self.auto_save_current_config()])

        # 3. 語言辨識過濾 Checkboxes
        ctk.CTkLabel(grid, text="🔤 語言過濾:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=1, column=0, sticky="w", pady=4)
        lang_box = ctk.CTkFrame(grid, fg_color="transparent")
        lang_box.grid(row=1, column=1, sticky="w", padx=(6, 12), pady=4)
        ctk.CTkCheckBox(lang_box, text="繁中", variable=self.var_lang_tc, corner_radius=4, height=18, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(lang_box, text="英文", variable=self.var_lang_en, corner_radius=4, height=18, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(lang_box, text="簡中 (過濾)", variable=self.var_lang_sc, corner_radius=4, height=18, font=ctk.CTkFont(size=11)).pack(side="left")

        # 4. 看門狗防卡死
        ctk.CTkLabel(grid, text="🐕 看門狗守護:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=1, column=2, sticky="w", pady=4)
        wd_box = ctk.CTkFrame(grid, fg_color="transparent")
        wd_box.grid(row=1, column=3, sticky="w", padx=(6, 0), pady=4)
        ctk.CTkCheckBox(wd_box, text="超時重啟", variable=self.var_watchdog_enabled, corner_radius=4, height=18, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        ctk.CTkEntry(wd_box, textvariable=self.var_watchdog_seconds, width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=11)).pack(side="left")
        ctk.CTkLabel(wd_box, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=2)

        # 5. 找不到目標時策略
        ctk.CTkLabel(grid, text="💤 找不到目標時:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=2, column=0, sticky="w", pady=4)
        row_idle = ctk.CTkFrame(grid, fg_color="transparent")
        row_idle.grid(row=2, column=1, sticky="w", padx=(6, 12), pady=4)
        ctk.CTkOptionMenu(
            row_idle,
            variable=self.var_idle_strategy,
            values=IDLE_STRATEGIES,
            width=120,
            height=24,
            corner_radius=4,
            font=ctk.CTkFont(size=11)
        ).pack(side="left")

        # 6. 等待時背景連點
        ctk.CTkLabel(grid, text="⚡ 等待時連點:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).grid(row=2, column=2, sticky="w", pady=4)
        tap_box = ctk.CTkFrame(grid, fg_color="transparent")
        tap_box.grid(row=2, column=3, sticky="w", padx=(6, 0), pady=4)
        ctk.CTkCheckBox(tap_box, text="連點", variable=self.var_idle_tap_enabled, corner_radius=4, height=18, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(
            tap_box,
            variable=self.var_idle_tap_area,
            values=["右下角區域", "中央區域", "右上角 (Skip)", "右半側中央"],
            width=100,
            height=24,
            corner_radius=4,
            font=ctk.CTkFont(size=10)
        ).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(tap_box, textvariable=self.var_idle_tap_times, width=32, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left")
        ctk.CTkLabel(tap_box, text="次", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=2)

        # 7. Telegram 通知設定
        ctk.CTkLabel(grid, text="📱 Telegram:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#38BDF8").grid(row=3, column=0, sticky="w", pady=4)
        tg_box = ctk.CTkFrame(grid, fg_color="transparent")
        tg_box.grid(row=3, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=4)
        ctk.CTkLabel(tg_box, text="Token:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(tg_box, textvariable=self.var_tg_token, width=150, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(tg_box, text="Chat ID:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(tg_box, textvariable=self.var_tg_chat_id, width=110, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(tg_box, text="測試發送", width=68, height=24, corner_radius=4, command=self.on_test_telegram_message, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=10)).pack(side="left")

    def _toggle_advanced(self):
        """展開或收合進階參數設定"""
        self._adv_open = not self._adv_open
        if self._adv_open:
            self.adv_content.pack(fill="x")
            self.btn_adv.configure(text="⚙️ 進階參數設定 ▾")
        else:
            self.adv_content.pack_forget()
            self.btn_adv.configure(text="⚙️ 進階參數設定 ▸")

    # --------------------------------------------------------------------------
    # 即時截圖預覽卡片 (右側上半部)
    # --------------------------------------------------------------------------
    def _build_preview_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER, width=824)
        card.grid(row=0, column=0, sticky="nsew", pady=(0, 6))

        # 頂部控制列
        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=12, pady=(10, 6))

        self.btn_capture = ctk.CTkButton(
            tools,
            text="📸 立即截取",
            width=84,
            height=28,
            corner_radius=6,
            command=self.on_preview_and_detect,
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.btn_capture.pack(side="left")

        # 自動刷新頻率選單 (連線後自動開始循環刷新，開關預設常駐開啟並移除多餘切換鈕)
        ctk.CTkLabel(
            tools,
            text="⏱ 刷新:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_TEXT_MUTED
        ).pack(side="left", padx=(8, 3))

        self.combo_preview_interval = ctk.CTkOptionMenu(
            tools,
            values=["0.5秒", "1.0秒", "1.5秒", "2.0秒", "3.0秒", "5.0秒"],
            variable=self.var_preview_interval,
            width=76,
            height=28,
            dynamic_resizing=False,
            command=self._on_preview_interval_change
        )
        self.combo_preview_interval.pack(side="left", padx=(0, 8))

        # 框選直接裁切截圖按鈕 (在畫面上滑鼠拖曳框選後亮起)
        self.btn_crop_selection = ctk.CTkButton(
            tools,
            text="✂️ 裁切截圖",
            width=92,
            height=28,
            corner_radius=6,
            state="disabled",
            fg_color=COLOR_BTN_DARK,
            hover_color="#D97706",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.on_crop_preview_selection
        )
        self.btn_crop_selection.pack(side="left")

        # 即時座標顯示 (Menlo 11 等寬藍字)
        self.lbl_preview_coords = ctk.CTkLabel(
            tools,
            textvariable=self.var_preview_coords,
            font=ctk.CTkFont(family="Menlo", size=12, weight="bold"),
            text_color="#60A5FA",
            anchor="e"
        )
        self.lbl_preview_coords.pack(side="right", padx=(4, 0))

        # 嵌入式畫布容器 (固定 PREVIEW_CANVAS_W × PREVIEW_CANVAS_H，絕對鎖死尺寸)
        holder = ctk.CTkFrame(
            card,
            fg_color=COLOR_INPUT_BG,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
            width=PREVIEW_CANVAS_W,
            height=PREVIEW_CANVAS_H
        )
        holder.pack(padx=12, pady=(0, 10))
        holder.pack_propagate(False)
        self.preview_holder = holder

        # 互動式預覽畫布 (鎖定 PREVIEW_CANVAS_W × PREVIEW_CANVAS_H)
        self.preview_canvas = tk.Canvas(
            holder,
            width=PREVIEW_CANVAS_W,
            height=PREVIEW_CANVAS_H,
            bg=COLOR_INPUT_BG,
            highlightthickness=0,
            cursor="crosshair"
        )
        self.preview_canvas.pack(fill="none", expand=False)
        self.lbl_canvas = self.preview_canvas  # 向下相容

        # 初始未連線引導文字
        self.preview_canvas.create_text(
            PREVIEW_CANVAS_W // 2, PREVIEW_CANVAS_H // 2,
            text="模擬器連線後將自動即時刷新畫面\n可直接在畫面上「按住滑鼠左鍵拖曳框選」按鈕並點擊【✂️ 裁切截圖】",
            fill=COLOR_TEXT_MUTED,
            font=("Arial", 13),
            justify="center",
            tags="placeholder"
        )

        # 畫布滑鼠互動事件
        self.preview_canvas.bind("<Motion>", self._on_preview_mouse_move)
        self.preview_canvas.bind("<Leave>", self._on_preview_mouse_leave)
        self.preview_canvas.bind("<ButtonPress-1>", self._on_preview_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_preview_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_preview_release)

    # --------------------------------------------------------------------------
    # 等寬即時日誌終端卡片 (右側下半部)
    # --------------------------------------------------------------------------
    def _build_log_panel(self, parent: ctk.CTkFrame):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        # 頂部控制列
        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(fill="x", padx=12, pady=(10, 6))

        lbl_log = ctk.CTkLabel(
            tools,
            text="📜 即時執行日誌 (Log Console)",
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        lbl_log.pack(side="left")

        # 自動捲動 Switch
        self.sw_log_scroll = ctk.CTkSwitch(
            tools,
            text="自動捲動",
            font=ctk.CTkFont(size=11),
            command=self._toggle_auto_scroll
        )
        self.sw_log_scroll.select()
        self.sw_log_scroll.pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            tools, text="儲存", width=54, height=24, corner_radius=4,
            command=self._export_logs, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=10)
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            tools, text="清除", width=54, height=24, corner_radius=4,
            command=self.on_clear_log, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=10)
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            tools, text="診斷", width=54, height=24, corner_radius=4,
            command=self.on_run_diagnostics, fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=10)
        ).pack(side="right", padx=2)

        # 等寬字體唯讀 CTkTextbox (Menlo / Consolas)
        mono_family = "Menlo" if sys.platform == "darwin" else "Consolas"
        self.txt_log = ctk.CTkTextbox(
            card,
            font=ctk.CTkFont(family=mono_family, size=11),
            fg_color=COLOR_INPUT_BG,
            text_color=COLOR_TEXT_PRIMARY,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
            corner_radius=8,
            wrap="char"
        )
        self.txt_log.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    # ==========================================================================
    # 🧩 步驟卡片生成與事件綁定 (Priority & Normal Steps)
    # ==========================================================================
    def _on_recognition_mode_changed(self, mode=None):
        mode_val = self.var_recognition_mode.get()
        is_img = ("圖片" in mode_val)
        for p in self.priority_steps_list:
            if "_refresh_target_ui" in p and callable(p["_refresh_target_ui"]):
                p["_refresh_target_ui"]()
        for s in self.steps_list:
            if "_refresh_target_ui" in s and callable(s["_refresh_target_ui"]):
                s["_refresh_target_ui"]()
        self.log_message(f"🔄 辨識模式已切換為：{'🖼️ 圖片特徵比對模式 (0-OCR / 極致節能)' if is_img else '📝 文字辨識模式 (RapidOCR)'}")
        self.auto_save_current_config()

    def on_add_priority_step(self):
        n = len(self.priority_steps_list) + 1
        is_img = ("圖片" in self.var_recognition_mode.get())
        self._create_priority_step_widget(
            name=f"優先 {n}",
            target_type="🖼️ 圖片特徵 (模板比對)" if is_img else "📝 文字辨識 (OCR)",
            action=ACTION_TARGET_IMAGE if is_img else ACTION_TARGET_TEXT,
            expanded=True
        )

    def on_add_task_trigger_step(self):
        n = len(self.priority_steps_list) + 1
        self._create_priority_step_widget(
            name=f"任務跳轉 {n}",
            keywords="",
            action="📋 執行任務清單",
            task_target_mode="📋 完整任務清單",
            task_cooldown=60.0,
            expanded=True
        )

    def on_delete_priority_step(self, p_step):
        if p_step in self.priority_steps_list:
            self.priority_steps_list.remove(p_step)
            p_step["frame"].destroy()
            self._renumber_priority_steps()
            self.auto_save_current_config()

    def _clear_all_priority_steps(self):
        for p in self.priority_steps_list:
            p["frame"].destroy()
        self.priority_steps_list.clear()
        self.lbl_p_count.configure(text="(0)")
        self.lbl_no_priority.pack(pady=4)

    def _renumber_priority_steps(self):
        for i, p in enumerate(self.priority_steps_list, start=1):
            if "lbl_num" in p:
                p["lbl_num"].configure(text=f"P{i}")
        self.lbl_p_count.configure(text=f"({len(self.priority_steps_list)})")
        if self.priority_steps_list:
            self.lbl_no_priority.pack_forget()
        else:
            self.lbl_no_priority.pack(pady=4)

    def _create_priority_step_widget(
        self,
        name: str = "",
        keywords: str = "",
        target_type: str = "📝 文字辨識 (OCR)",
        template_image: str = "",
        image_threshold: float = 0.80,
        image_multiscale: bool = False,
        exclude_keywords: str = "",
        action: str = ACTION_TARGET_IMAGE,
        custom_x: int = 960,
        custom_y: int = 540,
        delay: float = 2.0,
        roi_name: str = "全畫面比對",
        while_condition: bool = False,
        repeat_enabled: bool = False,
        repeat_mode: str = "持續連點",
        repeat_count: int = 5,
        repeat_speed: float = 0.25,
        repeat_area: str = "右下角區域",
        repeat_custom_x: int = 960,
        repeat_custom_y: int = 540,
        tg_enabled: bool = False,
        tg_message: str = "",
        task_target_mode: str = "📋 完整任務清單",
        task_target_item: str = "",
        task_cooldown: float = 60.0,
        enabled: bool = True,
        expanded: bool = False
    ):
        color = "#F59E0B"
        card = ctk.CTkFrame(self.frame_priority_cards, fg_color=COLOR_CARD_ITEM, corner_radius=8, border_width=1, border_color=color)
        card.pack(fill="x", pady=4, padx=2)

        target_type = _normalize_target_type(target_type)
        if target_type not in TARGET_TYPES:
            target_type = TARGET_TYPES[0]
        is_init_img = ("圖片" in self.var_recognition_mode.get()) or ("圖片" in target_type)
        action = _normalize_action(action, is_image=is_init_img)

        p = {
            "type": "priority",
            "enabled": tk.BooleanVar(value=enabled),
            "name": tk.StringVar(value=name),
            "target_type": tk.StringVar(value=target_type),
            "template_image": tk.StringVar(value=template_image),
            "image_threshold": tk.DoubleVar(value=image_threshold),
            "image_multiscale": tk.BooleanVar(value=image_multiscale),
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
            "task_target_mode": tk.StringVar(value=task_target_mode),
            "task_target_item": tk.StringVar(value=task_target_item),
            "task_cooldown": tk.DoubleVar(value=task_cooldown),
            "expanded": tk.BooleanVar(value=expanded),
            "frame": card,
        }
        self.priority_steps_list.append(p)

        def _on_p_var_changed(*_):
            if getattr(self, "_is_loading_config", False):
                return
            self.auto_save_current_config()

        for _v in [
            p["enabled"], p["name"], p["target_type"], p["template_image"],
            p["image_threshold"], p["image_multiscale"], p["keywords"],
            p["exclude_keywords"], p["action"], p["custom_x"], p["custom_y"],
            p["delay"], p["roi"], p["while_condition"], p["repeat_enabled"],
            p["repeat_mode"], p["repeat_count"], p["repeat_speed"],
            p["repeat_area"], p["repeat_custom_x"], p["repeat_custom_y"],
            p["tg_enabled"], p["tg_message"], p["task_target_mode"],
            p["task_target_item"], p["task_cooldown"]
        ]:
            _v.trace_add("write", _on_p_var_changed)

        # 標題列
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=6)

        handle = ctk.CTkLabel(head, text="☰", font=ctk.CTkFont(family="Arial", size=13, weight="bold"), text_color=color, width=16)
        handle.pack(side="left", padx=(0, 4))
        self._bind_drag_priority_events(handle, p)

        ctk.CTkCheckBox(head, text="", variable=p["enabled"], width=18, height=18, corner_radius=4).pack(side="left", padx=(0, 4))
        lbl_num = ctk.CTkLabel(head, text=f"P{len(self.priority_steps_list)}", font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color=color, width=28)
        lbl_num.pack(side="left")
        p["lbl_num"] = lbl_num

        ctk.CTkEntry(head, textvariable=p["name"], width=80, height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))

        btn_toggle = ctk.CTkButton(head, text="▸", width=26, height=26, corner_radius=4, command=lambda: p["expanded"].set(not p["expanded"].get()), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER)
        btn_toggle.pack(side="right", padx=2)

        ctk.CTkButton(head, text="✕", width=26, height=26, corner_radius=4, command=lambda: self.on_delete_priority_step(p), fg_color=COLOR_STOPPED, hover_color="#DC2626").pack(side="right", padx=2)

        # 文字模式輸入容器 (關鍵字 + ✓ + ✕)
        box_text_target = ctk.CTkFrame(head, fg_color="transparent")
        def _add_p_sym(tag):
            k = p["keywords"].get().strip()
            p["keywords"].set(f"{k}, {tag}" if k else tag)
        ctk.CTkButton(box_text_target, text="✕", width=26, height=26, corner_radius=4, command=lambda: _add_p_sym("[叉叉]"), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER).pack(side="right", padx=1)
        ctk.CTkButton(box_text_target, text="✓", width=26, height=26, corner_radius=4, command=lambda: _add_p_sym("[打勾]"), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER).pack(side="right", padx=1)
        ctk.CTkEntry(box_text_target, textvariable=p["keywords"], placeholder_text="關鍵字 (以逗號分隔)", height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", fill="x", expand=True)

        # 圖片模板模式容器 (檔名 + 帶入截圖 + 截圖 + 選擇)
        box_image_target = ctk.CTkFrame(head, fg_color="transparent")
        ctk.CTkButton(box_image_target, text="📥 帶入", width=54, height=26, corner_radius=5, command=lambda: self.on_apply_last_snippet(p), fg_color="#F59E0B", hover_color="#D97706", font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=1)
        ctk.CTkButton(box_image_target, text="✂️ 截圖", width=48, height=26, corner_radius=5, command=lambda: self.on_snip_template_dialog(p), fg_color="#0284C7", hover_color="#0369A1", font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=1)
        ctk.CTkButton(box_image_target, text="📂 瀏覽", width=48, height=26, corner_radius=5, command=lambda: self.on_browse_template_dialog(p), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=11)).pack(side="right", padx=1)
        ctk.CTkEntry(box_image_target, textvariable=p["template_image"], placeholder_text="模板圖檔 (如: 開始比賽.png)", height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", fill="x", expand=True, padx=(0, 2))

        # 展開設定內容
        lbl_sum = ctk.CTkLabel(card, text="", font=ctk.CTkFont(family="Arial", size=11), text_color=COLOR_TEXT_MUTED, anchor="w", wraplength=480, justify="left")
        detail = ctk.CTkFrame(card, fg_color="transparent")

        def summary() -> str:
            is_img = ("圖片" in self.var_recognition_mode.get())
            act = p["action"].get()
            if is_custom_coord_action(act):
                act_str = f"📍 自訂座標 ({p['custom_x'].get()}, {p['custom_y'].get()})"
            elif act == ACTION_TASK_FLOW or "任務清單" in act:
                t_m = p["task_target_mode"].get()
                t_i = p["task_target_item"].get()
                act_str = f"📋 跳轉: {t_i if t_m != '📋 完整任務清單' and t_i else t_m}"
            elif is_img:
                act_str = "↳ 🎯 點擊目標圖片"
            else:
                act_str = "↳ 🎯 點擊目標文字"

            if is_img:
                tpl_val = p["template_image"].get().strip()
                tpl_name = os.path.basename(tpl_val) if tpl_val else "(未選圖)"
                th = _num(p["image_threshold"], 0.80)
                parts = [f"🖼️ 模板: {tpl_name} ({th:.2f})", act_str, p["roi"].get(), f"延遲 {_num(p['delay'], 1.0):g}s"]
                if p["image_multiscale"].get():
                    parts.append("多尺度")
            else:
                parts = [act_str, p["roi"].get(), f"延遲 {_num(p['delay'], 1.0):g}s"]

            if p["while_condition"].get():
                parts.append("while重複")
            if p["repeat_enabled"].get():
                rep = "連點"
                if p["repeat_mode"].get() == "指定次數":
                    rep += f"×{_num(p['repeat_count'], 15, int)}"
                area = p["repeat_area"].get()
                if "自訂" in area:
                    area = f"({_num(p['repeat_custom_x'], 0, int)}, {_num(p['repeat_custom_y'], 0, int)})"
                parts.append(f"{rep}@{area}")
            if not is_img:
                ex = p["exclude_keywords"].get().strip()
                if ex:
                    parts.append(f"排除: {ex}")
            if p["tg_enabled"].get():
                parts.append("📱TG")
            return "  ·  ".join(parts)

        # 動作與比對列 (彈性雙行分組佈局，徹底消除遮蔽)
        # 行 1: 執行動作選單 + 自訂座標輸入
        ra1 = ctk.CTkFrame(detail, fg_color="transparent")
        ra1.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(ra1, text="動作:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        menu_p_act = ctk.CTkOptionMenu(
            ra1,
            variable=p["action"],
            values=ACTION_OPTIONS_IMAGE if is_init_img else ACTION_OPTIONS_TEXT,
            width=165,
            height=24,
            corner_radius=6,
            font=ctk.CTkFont(size=11)
        )
        menu_p_act.pack(side="left", padx=(0, 6))
        p["menu_action"] = menu_p_act

        box_act_xy = ctk.CTkFrame(ra1, fg_color="transparent")
        ctk.CTkLabel(box_act_xy, text="X:", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkEntry(box_act_xy, textvariable=p["custom_x"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
        ctk.CTkLabel(box_act_xy, text="Y:", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkEntry(box_act_xy, textvariable=p["custom_y"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
        ctk.CTkLabel(box_act_xy, text="(點右側預覽取點)", font=ctk.CTkFont(size=9), text_color="#F59E0B").pack(side="left", padx=(0, 4))

        # 行 2: 比對範圍 + 操作延遲
        ra2 = ctk.CTkFrame(detail, fg_color="transparent")
        ra2.pack(fill="x", pady=(2, 2))
        ctk.CTkLabel(ra2, text="比對範圍:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(ra2, variable=p["roi"], values=ROI_OPTIONS, width=120, height=24, corner_radius=6, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(ra2, text="延遲:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(ra2, textvariable=p["delay"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left")
        ctk.CTkLabel(ra2, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(2, 0))

        # 任務清單跳轉面板 (動作為 📋 執行任務清單 時顯示)
        box_task_flow = ctk.CTkFrame(detail, fg_color="#1E1B4B", corner_radius=6, border_width=1, border_color="#8B5CF6")
        row_tf1 = ctk.CTkFrame(box_task_flow, fg_color="transparent")
        row_tf1.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(row_tf1, text="跳轉目標:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#A78BFA").pack(side="left", padx=(0, 4))
        combo_task_mode = ctk.CTkOptionMenu(
            row_tf1,
            variable=p["task_target_mode"],
            values=["📋 完整任務清單", "🧩 指定積木步驟", "📂 已儲存任務檔"],
            width=120,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10)
        )
        combo_task_mode.pack(side="left", padx=(0, 4))
        combo_task_item = ctk.CTkOptionMenu(row_tf1, variable=p["task_target_item"], values=["(無)"], width=160, height=22, corner_radius=4, font=ctk.CTkFont(size=10))

        def _update_p_task_items(*_):
            m = p["task_target_mode"].get()
            if m == "🧩 指定積木步驟":
                choices = self.task_tab.get_block_choices() if hasattr(self, "task_tab") else []
                combo_task_item.configure(values=choices if choices else ["(無步驟)"])
                if choices and p["task_target_item"].get() not in choices:
                    p["task_target_item"].set(choices[0])
                combo_task_item.pack(side="left", padx=(2, 4))
            elif "任務檔" in m or "範本" in m:
                choices = self.task_tab.get_preset_choices() if hasattr(self, "task_tab") else []
                combo_task_item.configure(values=choices if choices else ["(無存檔)"])
                if choices and p["task_target_item"].get() not in choices:
                    p["task_target_item"].set(choices[0])
                combo_task_item.pack(side="left", padx=(2, 4))
            else:
                combo_task_item.pack_forget()

        p["task_target_mode"].trace_add("write", _update_p_task_items)

        row_tf2 = ctk.CTkFrame(box_task_flow, fg_color="transparent")
        row_tf2.pack(fill="x", padx=8, pady=(2, 4))
        ctk.CTkLabel(row_tf2, text="冷卻時間:", font=ctk.CTkFont(size=11), text_color="#A78BFA").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(row_tf2, textvariable=p["task_cooldown"], width=46, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 2))
        ctk.CTkLabel(row_tf2, text="秒 (避免短時間重複觸發)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkButton(row_tf2, text="🔄 刷新", width=50, height=20, corner_radius=4, command=_update_p_task_items, font=ctk.CTkFont(size=10), fg_color="#4C1D95", hover_color="#5B21B6").pack(side="right")

        def _refresh_act_ui(*_):
            if is_custom_coord_action(p["action"].get()):
                box_act_xy.pack(side="left", padx=(0, 6))
            else:
                box_act_xy.pack_forget()
            if p["action"].get() == ACTION_TASK_FLOW or "任務清單" in p["action"].get():
                box_task_flow.pack(fill="x", pady=(4, 0))
                _update_p_task_items()
            else:
                box_task_flow.pack_forget()

        p["action"].trace_add("write", _refresh_act_ui)
        _refresh_act_ui()

        # 排除字詞列 (僅文字辨識模式顯示)
        re = ctk.CTkFrame(detail, fg_color="transparent")
        ctk.CTkLabel(re, text="排除字詞:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#F87171").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(re, textvariable=p["exclude_keywords"], height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=10)).pack(side="left", fill="x", expand=True)

        # 圖片模板細項面板 (僅圖片模式顯示，彈性雙行結構)
        box_image_detail = ctk.CTkFrame(detail, fg_color="#181825", corner_radius=6, border_width=1, border_color="#334155")

        # 圖片行 1: 縮圖 + 比對門檻滑桿 + 多尺度容錯
        row_id1 = ctk.CTkFrame(box_image_detail, fg_color="transparent")
        row_id1.pack(fill="x", padx=8, pady=(4, 2))

        lbl_thumb = tk.Label(row_id1, bg="#11111B", fg=COLOR_TEXT_DIM, font=("Arial", 10), text="（未選圖）", width=8, height=2)
        lbl_thumb.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row_id1, text="門檻:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 2))
        lbl_thresh_val = ctk.CTkLabel(row_id1, text=f"{p['image_threshold'].get():.2f}", width=34, font=ctk.CTkFont(family="Menlo", size=11))
        slider_thresh = ctk.CTkSlider(row_id1, from_=0.50, to=0.98, number_of_steps=48, variable=p["image_threshold"], width=110, height=16)
        slider_thresh.pack(side="left", padx=(2, 2))
        lbl_thresh_val.pack(side="left", padx=(0, 6))
        slider_thresh.configure(command=lambda v: [lbl_thresh_val.configure(text=f"{float(v):.2f}"), self.auto_save_current_config()])

        ctk.CTkCheckBox(
            row_id1,
            text="多尺度容錯 (0.95x~1.05x)",
            variable=p["image_multiscale"],
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_PRIMARY,
            width=18,
            height=18,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4
        ).pack(side="left", padx=(4, 0))

        # 圖片行 2: 模板快捷動作按鈕列 (平鋪排開，絕不互相覆蓋)
        row_id2 = ctk.CTkFrame(box_image_detail, fg_color="transparent")
        row_id2.pack(fill="x", padx=8, pady=(2, 5))

        ctk.CTkLabel(row_id2, text="📷 模板操作:", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            row_id2,
            text="✂️ 截圖",
            width=54,
            height=24,
            corner_radius=4,
            command=lambda: self.on_snip_template_dialog(p),
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1"
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            row_id2,
            text="📂 瀏覽",
            width=54,
            height=24,
            corner_radius=4,
            command=lambda: self.on_browse_template_dialog(p),
            font=ctk.CTkFont(size=10),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            row_id2,
            text="📥 帶入最新截圖",
            width=96,
            height=24,
            corner_radius=4,
            command=lambda: self.on_apply_last_snippet(p),
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#F59E0B",
            hover_color="#D97706"
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            row_id2,
            text="📁 開啟資料夾",
            width=76,
            height=24,
            corner_radius=4,
            command=self.on_open_templates_folder,
            font=ctk.CTkFont(size=10),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER
        ).pack(side="left", padx=2)

        def _update_p_thumb(*_):
            img_name = p["template_image"].get().strip()
            if not img_name:
                lbl_thumb.configure(image="", text="（未選圖）", fg=COLOR_TEXT_DIM, width=8, height=2)
                p["_thumb_img"] = None
                return
            full_path = self.resolve_image_path(img_name)
            if full_path and os.path.exists(full_path):
                try:
                    bgr = imread_unicode(full_path)
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
                        p["_thumb_img"] = tk_img
                        return
                except Exception:
                    pass
            lbl_thumb.configure(image="", text="⚠️ 缺檔", fg="#EF4444", width=8, height=2)
            p["_thumb_img"] = None

        p["template_image"].trace_add("write", _update_p_thumb)

        def _refresh_p_target_ui(*_):
            is_img = ("圖片" in self.var_recognition_mode.get())
            p["target_type"].set("🖼️ 圖片特徵 (模板比對)" if is_img else "📝 文字辨識 (OCR)")
            if "menu_action" in p and hasattr(p["menu_action"], "configure"):
                p["menu_action"].configure(values=ACTION_OPTIONS_IMAGE if is_img else ACTION_OPTIONS_TEXT)
            curr_act = p["action"].get()
            if is_target_center_action(curr_act):
                p["action"].set(ACTION_TARGET_IMAGE if is_img else ACTION_TARGET_TEXT)
            elif is_custom_coord_action(curr_act):
                p["action"].set(ACTION_CUSTOM_COORD)

            if is_img:
                box_text_target.pack_forget()
                box_image_target.pack(side="left", fill="x", expand=True, padx=(0, 4))
                re.pack_forget()
                box_image_detail.pack(fill="x", pady=(4, 0))
                _update_p_thumb()
            else:
                box_image_target.pack_forget()
                box_text_target.pack(side="left", fill="x", expand=True, padx=(0, 4))
                box_image_detail.pack_forget()
                re.pack(fill="x", pady=(4, 0))
            if not p["expanded"].get():
                lbl_sum.configure(text=summary())

        p["_refresh_target_ui"] = _refresh_p_target_ui
        _refresh_p_target_ui()

        # 條件存在時重複執行（until消失）
        row_while = ctk.CTkFrame(detail, fg_color="transparent")
        row_while.pack(fill="x", pady=(4, 0))
        ctk.CTkCheckBox(
            row_while,
            text="條件存在時重複執行（直到消失）",
            variable=p["while_condition"],
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_PRIMARY,
            width=18,
            height=18,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4
        ).pack(side="left")

        # ⚡ 命中後連點區塊
        row_rep = ctk.CTkFrame(detail, fg_color="transparent")
        row_rep.pack(fill="x", pady=(4, 0))
        ctk.CTkCheckBox(
            row_rep,
            text="⚡ 命中後連點（過場跳過）",
            variable=p["repeat_enabled"],
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F59E0B",
            width=18,
            height=18,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4
        ).pack(side="left", padx=(0, 8))

        # 連點細項面板
        box_rep_detail = ctk.CTkFrame(detail, fg_color="#1E1E2E", corner_radius=6, border_width=1, border_color="#3B4252")

        row_rep_opts = ctk.CTkFrame(box_rep_detail, fg_color="transparent")
        row_rep_opts.pack(fill="x", padx=8, pady=(4, 2))

        ctk.CTkLabel(row_rep_opts, text="模式:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(
            row_rep_opts,
            variable=p["repeat_mode"],
            values=REPEAT_MODES,
            width=90,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10)
        ).pack(side="left", padx=(0, 8))

        box_rep_cnt = ctk.CTkFrame(row_rep_opts, fg_color="transparent")
        ctk.CTkLabel(box_rep_cnt, text="次數:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(box_rep_cnt, textvariable=p["repeat_count"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 2))
        ctk.CTkLabel(box_rep_cnt, text="次", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row_rep_opts, text="間隔:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(row_rep_opts, textvariable=p["repeat_speed"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 2))
        ctk.CTkLabel(row_rep_opts, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 8))

        row_rep_loc = ctk.CTkFrame(box_rep_detail, fg_color="transparent")
        row_rep_loc.pack(fill="x", padx=8, pady=(2, 4))

        ctk.CTkLabel(row_rep_loc, text="位置:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(
            row_rep_loc,
            variable=p["repeat_area"],
            values=REPEAT_AREAS,
            width=110,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10)
        ).pack(side="left", padx=(0, 6))

        box_rep_xy = ctk.CTkFrame(row_rep_loc, fg_color="transparent")
        ctk.CTkLabel(box_rep_xy, text="X:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkEntry(box_rep_xy, textvariable=p["repeat_custom_x"], width=46, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
        ctk.CTkLabel(box_rep_xy, text="Y:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkEntry(box_rep_xy, textvariable=p["repeat_custom_y"], width=46, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 0))

        def _refresh_p_repeat_ui(*_):
            if p["repeat_enabled"].get():
                box_rep_detail.pack(fill="x", pady=(2, 0))
                if p["repeat_mode"].get() == "指定次數":
                    box_rep_cnt.pack(side="left", padx=(0, 8))
                else:
                    box_rep_cnt.pack_forget()
                if "自訂" in p["repeat_area"].get():
                    box_rep_xy.pack(side="left", padx=(4, 0))
                else:
                    box_rep_xy.pack_forget()
            else:
                box_rep_detail.pack_forget()

        p["repeat_enabled"].trace_add("write", _refresh_p_repeat_ui)
        p["repeat_mode"].trace_add("write", _refresh_p_repeat_ui)
        p["repeat_area"].trace_add("write", _refresh_p_repeat_ui)
        _refresh_p_repeat_ui()

        # Telegram 通知列
        row_tg = ctk.CTkFrame(detail, fg_color="transparent")
        row_tg.pack(fill="x", pady=(4, 0))
        ctk.CTkCheckBox(
            row_tg,
            text="📱 成功後發送 Telegram 通知",
            variable=p["tg_enabled"],
            font=ctk.CTkFont(size=11),
            text_color="#38BDF8",
            width=18,
            height=18,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4
        ).pack(side="left", padx=(0, 6))

        box_tg_msg = ctk.CTkFrame(detail, fg_color="transparent")
        ctk.CTkLabel(box_tg_msg, text="訊息內容:", font=ctk.CTkFont(size=10), text_color="#38BDF8").pack(side="left", padx=(22, 4))
        ctk.CTkEntry(box_tg_msg, textvariable=p["tg_message"], height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=10)).pack(side="left", fill="x", expand=True)

        def _refresh_p_tg_ui(*_):
            if p["tg_enabled"].get():
                box_tg_msg.pack(fill="x", pady=(2, 0))
            else:
                box_tg_msg.pack_forget()
        p["tg_enabled"].trace_add("write", _refresh_p_tg_ui)
        _refresh_p_tg_ui()

        # 展開/收合切換邏輯
        def refresh(*_):
            if p["expanded"].get():
                btn_toggle.configure(text="▾")
                lbl_sum.pack_forget()
                detail.pack(fill="x", padx=10, pady=(0, 8))
            else:
                btn_toggle.configure(text="▸")
                detail.pack_forget()
                lbl_sum.configure(text=summary())
                lbl_sum.pack(fill="x", padx=12, pady=(0, 4))

        p["expanded"].trace_add("write", refresh)
        refresh()
        self._renumber_priority_steps()

    # --------------------------------------------------------------------------
    # 一般步驟卡片建立 (Normal Steps)
    # --------------------------------------------------------------------------
    def on_add_empty_step(self):
        n = len(self.steps_list) + 1
        is_img = ("圖片" in self.var_recognition_mode.get())
        self._create_step_widget(
            name=f"步驟 {n}",
            target_type="🖼️ 圖片特徵 (模板比對)" if is_img else "📝 文字辨識 (OCR)",
            action=ACTION_TARGET_IMAGE if is_img else ACTION_TARGET_TEXT,
            expanded=True
        )

    def on_add_image_step(self):
        self.on_add_empty_step()

    def on_browse_template_dialog(self, step_or_p: dict):
        curr_dir = self.storage_dir if os.path.exists(self.storage_dir) else self.config_dir
        fpath = filedialog.askopenfilename(
            parent=self.root,
            title="選擇圖片模板",
            initialdir=curr_dir,
            filetypes=[("圖片檔案", "*.png;*.jpg;*.jpeg;*.bmp"), ("PNG 圖片", "*.png"), ("所有檔案", "*.*")]
        )
        if fpath:
            fname = os.path.basename(fpath)
            # 若在目前存檔目錄下，記錄檔名；否則記錄絕對路徑
            if self.storage_dir and os.path.commonpath([os.path.abspath(fpath), os.path.abspath(self.storage_dir)]) == os.path.abspath(self.storage_dir):
                step_or_p["template_image"].set(fname)
            else:
                step_or_p["template_image"].set(os.path.abspath(fpath))
            self.auto_save_current_config()
            self._refresh_all_step_thumbs()
            self.log_message(f"已指定圖片模板: {fpath}")

    def on_open_templates_folder(self):
        target = self.storage_dir if os.path.exists(self.storage_dir) else self.config_dir
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", target])
            elif sys.platform == "win32":
                os.startfile(target)
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as ex:
            messagebox.showerror("錯誤", f"無法打開資料夾: {ex}", parent=self.root)

    def on_delete_step(self, step):
        if step in self.steps_list:
            self.steps_list.remove(step)
            step["frame"].destroy()
            self._renumber_steps()
            self.auto_save_current_config()

    def _clear_all_steps(self):
        for s in self.steps_list:
            s["frame"].destroy()
        self.steps_list.clear()
        self.lbl_n_count.configure(text="(0)")

    def _renumber_steps(self):
        for i, s in enumerate(self.steps_list, start=1):
            if "lbl_num" in s:
                s["lbl_num"].configure(text=str(i))
        self.lbl_n_count.configure(text=f"({len(self.steps_list)})")

    def _create_step_widget(
        self,
        name: str = "",
        keywords: str = "",
        target_type: str = "📝 文字辨識 (OCR)",
        template_image: str = "",
        image_threshold: float = 0.80,
        image_multiscale: bool = False,
        exclude_keywords: str = "",
        action: str = ACTION_TARGET_IMAGE,
        custom_x: int = 960,
        custom_y: int = 540,
        delay: float = 2.5,
        roi_name: str = "右下角區域",
        repeat_enabled: bool = False,
        repeat_mode: str = "持續連點",
        repeat_count: int = 5,
        repeat_speed: float = 0.25,
        repeat_area: str = "右下角區域",
        repeat_custom_x: int = 960,
        repeat_custom_y: int = 540,
        timeout_enabled: bool = False,
        timeout_seconds: int = 20,
        tg_enabled: bool = False,
        tg_message: str = "",
        task_target_mode: str = "📋 完整任務清單",
        task_target_item: str = "",
        task_cooldown: float = 60.0,
        enabled: bool = True,
        expanded: bool = False
    ):
        color = STEP_COLORS[len(self.steps_list) % len(STEP_COLORS)]
        card = ctk.CTkFrame(self.frame_normal_cards, fg_color=COLOR_CARD_ITEM, corner_radius=8, border_width=1, border_color=color)
        card.pack(fill="x", pady=4, padx=2)

        target_type = _normalize_target_type(target_type)
        if target_type not in TARGET_TYPES:
            target_type = TARGET_TYPES[0]
        is_init_img = ("圖片" in self.var_recognition_mode.get()) or ("圖片" in target_type)
        action = _normalize_action(action, is_image=is_init_img)

        s = {
            "type": "normal",
            "enabled": tk.BooleanVar(value=enabled),
            "name": tk.StringVar(value=name),
            "target_type": tk.StringVar(value=target_type),
            "template_image": tk.StringVar(value=template_image),
            "image_threshold": tk.DoubleVar(value=image_threshold),
            "image_multiscale": tk.BooleanVar(value=image_multiscale),
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
            "task_target_mode": tk.StringVar(value=task_target_mode),
            "task_target_item": tk.StringVar(value=task_target_item),
            "task_cooldown": tk.DoubleVar(value=task_cooldown),
            "expanded": tk.BooleanVar(value=expanded),
            "frame": card,
            "border_color": color,
        }
        self.steps_list.append(s)

        def _on_s_var_changed(*_):
            if getattr(self, "_is_loading_config", False):
                return
            self.auto_save_current_config()

        for _v in [
            s["enabled"], s["name"], s["target_type"], s["template_image"],
            s["image_threshold"], s["image_multiscale"], s["keywords"],
            s["exclude_keywords"], s["action"], s["custom_x"], s["custom_y"],
            s["delay"], s["roi"], s["repeat_enabled"], s["repeat_mode"],
            s["repeat_count"], s["repeat_speed"], s["repeat_area"],
            s["repeat_custom_x"], s["repeat_custom_y"], s["timeout_enabled"],
            s["timeout_seconds"], s["tg_enabled"], s["tg_message"],
            s["task_target_mode"], s["task_target_item"], s["task_cooldown"]
        ]:
            _v.trace_add("write", _on_s_var_changed)

        # 標題列
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=6)

        handle = ctk.CTkLabel(head, text="☰", font=ctk.CTkFont(family="Arial", size=13, weight="bold"), text_color=color, width=16)
        handle.pack(side="left", padx=(0, 4))
        self._bind_drag_events(handle, s)

        ctk.CTkCheckBox(head, text="", variable=s["enabled"], width=18, height=18, corner_radius=4).pack(side="left", padx=(0, 4))
        lbl_num = ctk.CTkLabel(head, text=str(len(self.steps_list)), font=ctk.CTkFont(family="Arial", size=12, weight="bold"), text_color=color, width=24)
        lbl_num.pack(side="left")
        s["lbl_num"] = lbl_num

        ctk.CTkEntry(head, textvariable=s["name"], width=80, height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))

        btn_toggle = ctk.CTkButton(head, text="▸", width=26, height=26, corner_radius=4, command=lambda: s["expanded"].set(not s["expanded"].get()), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER)
        btn_toggle.pack(side="right", padx=2)

        ctk.CTkButton(head, text="✕", width=26, height=26, corner_radius=4, command=lambda: self.on_delete_step(s), fg_color=COLOR_STOPPED, hover_color="#DC2626").pack(side="right", padx=2)

        # 文字模式輸入容器 (關鍵字 + ✓ + ✕)
        box_text_target = ctk.CTkFrame(head, fg_color="transparent")
        def _add_s_sym(tag):
            k = s["keywords"].get().strip()
            s["keywords"].set(f"{k}, {tag}" if k else tag)
        ctk.CTkButton(box_text_target, text="✕", width=26, height=26, corner_radius=4, command=lambda: _add_s_sym("[叉叉]"), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER).pack(side="right", padx=1)
        ctk.CTkButton(box_text_target, text="✓", width=26, height=26, corner_radius=4, command=lambda: _add_s_sym("[打勾]"), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER).pack(side="right", padx=1)
        ctk.CTkEntry(box_text_target, textvariable=s["keywords"], placeholder_text="關鍵字 (以逗號分隔)", height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", fill="x", expand=True)

        # 圖片模板模式容器 (檔名 + 帶入截圖 + 截圖 + 選擇)
        box_image_target = ctk.CTkFrame(head, fg_color="transparent")
        ctk.CTkButton(box_image_target, text="📥 帶入", width=54, height=26, corner_radius=5, command=lambda: self.on_apply_last_snippet(s), fg_color="#F59E0B", hover_color="#D97706", font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=1)
        ctk.CTkButton(box_image_target, text="✂️ 截圖", width=48, height=26, corner_radius=5, command=lambda: self.on_snip_template_dialog(s), fg_color="#0284C7", hover_color="#0369A1", font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=1)
        ctk.CTkButton(box_image_target, text="📂 瀏覽", width=48, height=26, corner_radius=5, command=lambda: self.on_browse_template_dialog(s), fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER, font=ctk.CTkFont(size=11)).pack(side="right", padx=1)
        ctk.CTkEntry(box_image_target, textvariable=s["template_image"], placeholder_text="模板圖檔 (如: 開始比賽.png)", height=26, corner_radius=6, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=11)).pack(side="left", fill="x", expand=True, padx=(0, 2))

        # 展開設定內容
        lbl_sum = ctk.CTkLabel(card, text="", font=ctk.CTkFont(family="Arial", size=11), text_color=COLOR_TEXT_MUTED, anchor="w", wraplength=480, justify="left")
        detail = ctk.CTkFrame(card, fg_color="transparent")

        def summary() -> str:
            is_img = ("圖片" in self.var_recognition_mode.get())
            act = s["action"].get()
            if is_custom_coord_action(act):
                act_str = f"📍 自訂座標 ({s['custom_x'].get()}, {s['custom_y'].get()})"
            elif act == ACTION_TASK_FLOW or "任務清單" in act:
                t_m = s["task_target_mode"].get()
                t_i = s["task_target_item"].get()
                act_str = f"📋 跳轉: {t_i if t_m != '📋 完整任務清單' and t_i else t_m}"
            elif is_img:
                act_str = "↳ 🎯 點擊目標圖片"
            else:
                act_str = "↳ 🎯 點擊目標文字"

            if is_img:
                tpl_val = s["template_image"].get().strip()
                tpl_name = os.path.basename(tpl_val) if tpl_val else "(未選圖)"
                th = _num(s["image_threshold"], 0.80)
                parts = [f"🖼️ 模板: {tpl_name} ({th:.2f})", act_str, s["roi"].get(), f"延遲 {_num(s['delay'], 2.5):g}s"]
                if s["image_multiscale"].get():
                    parts.append("多尺度")
            else:
                parts = [act_str, s["roi"].get(), f"延遲 {_num(s['delay'], 2.5):g}s"]

            if s["repeat_enabled"].get():
                rep = "連點"
                if s["repeat_mode"].get() == "指定次數":
                    rep += f"×{_num(s['repeat_count'], 15, int)}"
                area = s["repeat_area"].get()
                if "自訂" in area:
                    area = f"({_num(s['repeat_custom_x'], 0, int)}, {_num(s['repeat_custom_y'], 0, int)})"
                parts.append(f"{rep}@{area}")
            if s["timeout_enabled"].get():
                parts.append(f"{_num(s['timeout_seconds'], 20, int)}s超時跳過")
            if not is_img:
                ex = s["exclude_keywords"].get().strip()
                if ex:
                    parts.append(f"排除: {ex}")
            if s["tg_enabled"].get():
                parts.append("📱TG")
            return "  ·  ".join(parts)

        # 動作與比對列 (彈性雙行分組佈局，徹底消除遮蔽)
        # 行 1: 執行動作選單 + 自訂座標輸入
        ra1 = ctk.CTkFrame(detail, fg_color="transparent")
        ra1.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(ra1, text="動作:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        menu_s_act = ctk.CTkOptionMenu(
            ra1,
            variable=s["action"],
            values=ACTION_OPTIONS_IMAGE if is_init_img else ACTION_OPTIONS_TEXT,
            width=165,
            height=24,
            corner_radius=6,
            font=ctk.CTkFont(size=11)
        )
        menu_s_act.pack(side="left", padx=(0, 6))
        s["menu_action"] = menu_s_act

        box_act_xy = ctk.CTkFrame(ra1, fg_color="transparent")
        ctk.CTkLabel(box_act_xy, text="X:", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkEntry(box_act_xy, textvariable=s["custom_x"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
        ctk.CTkLabel(box_act_xy, text="Y:", font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkEntry(box_act_xy, textvariable=s["custom_y"], width=46, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
        ctk.CTkLabel(box_act_xy, text="(點右側預覽取點)", font=ctk.CTkFont(size=9), text_color="#F59E0B").pack(side="left", padx=(0, 4))

        # 行 2: 比對範圍 + 操作延遲
        ra2 = ctk.CTkFrame(detail, fg_color="transparent")
        ra2.pack(fill="x", pady=(2, 2))
        ctk.CTkLabel(ra2, text="比對範圍:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(ra2, variable=s["roi"], values=ROI_OPTIONS, width=120, height=24, corner_radius=6, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(ra2, text="延遲:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(ra2, textvariable=s["delay"], width=44, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left")
        ctk.CTkLabel(ra2, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(2, 0))

        # 任務清單跳轉面板 (動作為 📋 執行任務清單 時顯示)
        box_task_flow = ctk.CTkFrame(detail, fg_color="#1E1B4B", corner_radius=6, border_width=1, border_color="#8B5CF6")
        row_tf1 = ctk.CTkFrame(box_task_flow, fg_color="transparent")
        row_tf1.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(row_tf1, text="跳轉目標:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#A78BFA").pack(side="left", padx=(0, 4))
        combo_task_mode = ctk.CTkOptionMenu(
            row_tf1,
            variable=s["task_target_mode"],
            values=["📋 完整任務清單", "🧩 指定積木步驟", "📂 已儲存任務檔"],
            width=120,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10)
        )
        combo_task_mode.pack(side="left", padx=(0, 4))
        combo_task_item = ctk.CTkOptionMenu(row_tf1, variable=s["task_target_item"], values=["(無)"], width=160, height=22, corner_radius=4, font=ctk.CTkFont(size=10))

        def _update_s_task_items(*_):
            m = s["task_target_mode"].get()
            if m == "🧩 指定積木步驟":
                choices = self.task_tab.get_block_choices() if hasattr(self, "task_tab") else []
                combo_task_item.configure(values=choices if choices else ["(無步驟)"])
                if choices and s["task_target_item"].get() not in choices:
                    s["task_target_item"].set(choices[0])
                combo_task_item.pack(side="left", padx=(2, 4))
            elif "任務檔" in m or "範本" in m:
                choices = self.task_tab.get_preset_choices() if hasattr(self, "task_tab") else []
                combo_task_item.configure(values=choices if choices else ["(無存檔)"])
                if choices and s["task_target_item"].get() not in choices:
                    s["task_target_item"].set(choices[0])
                combo_task_item.pack(side="left", padx=(2, 4))
            else:
                combo_task_item.pack_forget()

        s["task_target_mode"].trace_add("write", _update_s_task_items)

        row_tf2 = ctk.CTkFrame(box_task_flow, fg_color="transparent")
        row_tf2.pack(fill="x", padx=8, pady=(2, 4))
        ctk.CTkLabel(row_tf2, text="冷卻時間:", font=ctk.CTkFont(size=11), text_color="#A78BFA").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(row_tf2, textvariable=s["task_cooldown"], width=46, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 2))
        ctk.CTkLabel(row_tf2, text="秒 (避免短時間重複觸發)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkButton(row_tf2, text="🔄 刷新", width=50, height=20, corner_radius=4, command=_update_s_task_items, font=ctk.CTkFont(size=10), fg_color="#4C1D95", hover_color="#5B21B6").pack(side="right")

        def _refresh_s_act_ui(*_):
            if is_custom_coord_action(s["action"].get()):
                box_act_xy.pack(side="left", padx=(0, 6))
            else:
                box_act_xy.pack_forget()
            if s["action"].get() == ACTION_TASK_FLOW or "任務清單" in s["action"].get():
                box_task_flow.pack(fill="x", pady=(4, 0))
                _update_s_task_items()
            else:
                box_task_flow.pack_forget()

        s["action"].trace_add("write", _refresh_s_act_ui)
        _refresh_s_act_ui()

        # 排除字詞列 (僅文字辨識模式顯示)
        re = ctk.CTkFrame(detail, fg_color="transparent")
        ctk.CTkLabel(re, text="排除字詞:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#F87171").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(re, textvariable=s["exclude_keywords"], height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=10)).pack(side="left", fill="x", expand=True)

        # 圖片模板細項面板 (僅圖片模式顯示，彈性雙行結構)
        box_image_detail = ctk.CTkFrame(detail, fg_color="#181825", corner_radius=6, border_width=1, border_color="#334155")

        # 圖片行 1: 縮圖 + 比對門檻滑桿 + 多尺度容錯
        row_id1 = ctk.CTkFrame(box_image_detail, fg_color="transparent")
        row_id1.pack(fill="x", padx=8, pady=(4, 2))

        lbl_thumb = tk.Label(row_id1, bg="#11111B", fg=COLOR_TEXT_DIM, font=("Arial", 10), text="（未選圖）", width=8, height=2)
        lbl_thumb.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row_id1, text="門檻:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0, 2))
        lbl_thresh_val = ctk.CTkLabel(row_id1, text=f"{s['image_threshold'].get():.2f}", width=34, font=ctk.CTkFont(family="Menlo", size=11))
        slider_thresh = ctk.CTkSlider(row_id1, from_=0.50, to=0.98, number_of_steps=48, variable=s["image_threshold"], width=110, height=16)
        slider_thresh.pack(side="left", padx=(2, 2))
        lbl_thresh_val.pack(side="left", padx=(0, 6))
        slider_thresh.configure(command=lambda v: [lbl_thresh_val.configure(text=f"{float(v):.2f}"), self.auto_save_current_config()])

        ctk.CTkCheckBox(
            row_id1,
            text="多尺度容錯 (0.95x~1.05x)",
            variable=s["image_multiscale"],
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_PRIMARY,
            width=18,
            height=18,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4
        ).pack(side="left", padx=(4, 0))

        # 圖片行 2: 模板快捷動作按鈕列 (平鋪排開，絕不互相覆蓋)
        row_id2 = ctk.CTkFrame(box_image_detail, fg_color="transparent")
        row_id2.pack(fill="x", padx=8, pady=(2, 5))

        ctk.CTkLabel(row_id2, text="📷 模板操作:", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            row_id2,
            text="✂️ 截圖",
            width=54,
            height=24,
            corner_radius=4,
            command=lambda: self.on_snip_template_dialog(s),
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1"
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            row_id2,
            text="📂 瀏覽",
            width=54,
            height=24,
            corner_radius=4,
            command=lambda: self.on_browse_template_dialog(s),
            font=ctk.CTkFont(size=10),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            row_id2,
            text="📥 帶入最新截圖",
            width=96,
            height=24,
            corner_radius=4,
            command=lambda: self.on_apply_last_snippet(s),
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#F59E0B",
            hover_color="#D97706"
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            row_id2,
            text="📁 開啟資料夾",
            width=76,
            height=24,
            corner_radius=4,
            command=self.on_open_templates_folder,
            font=ctk.CTkFont(size=10),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER
        ).pack(side="left", padx=2)

        def _update_s_thumb(*_):
            img_name = s["template_image"].get().strip()
            if not img_name:
                lbl_thumb.configure(image="", text="（未選圖）", fg=COLOR_TEXT_DIM, width=8, height=2)
                s["_thumb_img"] = None
                return
            full_path = self.resolve_image_path(img_name)
            if full_path and os.path.exists(full_path):
                try:
                    bgr = imread_unicode(full_path)
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
                        s["_thumb_img"] = tk_img
                        return
                except Exception:
                    pass
            lbl_thumb.configure(image="", text="⚠️ 缺檔", fg="#EF4444", width=8, height=2)
            s["_thumb_img"] = None

        s["template_image"].trace_add("write", _update_s_thumb)

        def _refresh_s_target_ui(*_):
            is_img = ("圖片" in self.var_recognition_mode.get())
            s["target_type"].set("🖼️ 圖片特徵 (模板比對)" if is_img else "📝 文字辨識 (OCR)")
            if "menu_action" in s and hasattr(s["menu_action"], "configure"):
                s["menu_action"].configure(values=ACTION_OPTIONS_IMAGE if is_img else ACTION_OPTIONS_TEXT)
            curr_act = s["action"].get()
            if is_target_center_action(curr_act):
                s["action"].set(ACTION_TARGET_IMAGE if is_img else ACTION_TARGET_TEXT)
            elif is_custom_coord_action(curr_act):
                s["action"].set(ACTION_CUSTOM_COORD)

            if is_img:
                box_text_target.pack_forget()
                box_image_target.pack(side="left", fill="x", expand=True, padx=(0, 4))
                re.pack_forget()
                box_image_detail.pack(fill="x", pady=(4, 0))
                _update_s_thumb()
            else:
                box_image_target.pack_forget()
                box_text_target.pack(side="left", fill="x", expand=True, padx=(0, 4))
                box_image_detail.pack_forget()
                re.pack(fill="x", pady=(4, 0))
            if not s["expanded"].get():
                lbl_sum.configure(text=summary())

        s["_refresh_target_ui"] = _refresh_s_target_ui
        _refresh_s_target_ui()

        # ⚡ 命中後連點區塊
        row_rep = ctk.CTkFrame(detail, fg_color="transparent")
        row_rep.pack(fill="x", pady=(4, 0))
        ctk.CTkCheckBox(
            row_rep,
            text="⚡ 命中後連點（過場跳過）",
            variable=s["repeat_enabled"],
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F59E0B",
            width=18,
            height=18,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4
        ).pack(side="left", padx=(0, 8))

        # 連點細項面板
        box_rep_detail = ctk.CTkFrame(detail, fg_color="#1E1E2E", corner_radius=6, border_width=1, border_color="#3B4252")

        row_rep_opts = ctk.CTkFrame(box_rep_detail, fg_color="transparent")
        row_rep_opts.pack(fill="x", padx=8, pady=(4, 2))

        ctk.CTkLabel(row_rep_opts, text="模式:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(
            row_rep_opts,
            variable=s["repeat_mode"],
            values=REPEAT_MODES,
            width=90,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10)
        ).pack(side="left", padx=(0, 8))

        box_rep_cnt = ctk.CTkFrame(row_rep_opts, fg_color="transparent")
        ctk.CTkLabel(box_rep_cnt, text="次數:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(box_rep_cnt, textvariable=s["repeat_count"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 2))
        ctk.CTkLabel(box_rep_cnt, text="次", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row_rep_opts, text="間隔:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(row_rep_opts, textvariable=s["repeat_speed"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 2))
        ctk.CTkLabel(row_rep_opts, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 8))

        row_rep_loc = ctk.CTkFrame(box_rep_detail, fg_color="transparent")
        row_rep_loc.pack(fill="x", padx=8, pady=(2, 4))

        ctk.CTkLabel(row_rep_loc, text="位置:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(
            row_rep_loc,
            variable=s["repeat_area"],
            values=REPEAT_AREAS,
            width=110,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10)
        ).pack(side="left", padx=(0, 6))

        box_rep_xy = ctk.CTkFrame(row_rep_loc, fg_color="transparent")
        ctk.CTkLabel(box_rep_xy, text="X:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkEntry(box_rep_xy, textvariable=s["repeat_custom_x"], width=46, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 4))
        ctk.CTkLabel(box_rep_xy, text="Y:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkEntry(box_rep_xy, textvariable=s["repeat_custom_y"], width=46, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(2, 0))

        def _refresh_s_repeat_ui(*_):
            if s["repeat_enabled"].get():
                box_rep_detail.pack(fill="x", pady=(2, 0))
                if s["repeat_mode"].get() == "指定次數":
                    box_rep_cnt.pack(side="left", padx=(0, 8))
                else:
                    box_rep_cnt.pack_forget()
                if "自訂" in s["repeat_area"].get():
                    box_rep_xy.pack(side="left", padx=(4, 0))
                else:
                    box_rep_xy.pack_forget()
            else:
                box_rep_detail.pack_forget()

        s["repeat_enabled"].trace_add("write", _refresh_s_repeat_ui)
        s["repeat_mode"].trace_add("write", _refresh_s_repeat_ui)
        s["repeat_area"].trace_add("write", _refresh_s_repeat_ui)
        _refresh_s_repeat_ui()

        # 超時未命中跳過
        row_timeout = ctk.CTkFrame(detail, fg_color="transparent")
        row_timeout.pack(fill="x", pady=(4, 0))
        ctk.CTkCheckBox(
            row_timeout,
            text="⏱ 超時未命中跳過",
            variable=s["timeout_enabled"],
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_PRIMARY,
            width=18,
            height=18,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4
        ).pack(side="left", padx=(0, 6))

        box_timeout = ctk.CTkFrame(row_timeout, fg_color="transparent")
        ctk.CTkLabel(box_timeout, text="等候上限:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(box_timeout, textvariable=s["timeout_seconds"], width=42, height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(family="Menlo", size=10)).pack(side="left", padx=(0, 2))
        ctk.CTkLabel(box_timeout, text="秒", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).pack(side="left")

        def _refresh_s_timeout_ui(*_):
            if s["timeout_enabled"].get():
                box_timeout.pack(side="left")
            else:
                box_timeout.pack_forget()
        s["timeout_enabled"].trace_add("write", _refresh_s_timeout_ui)
        _refresh_s_timeout_ui()

        # Telegram 通知列
        row_tg = ctk.CTkFrame(detail, fg_color="transparent")
        row_tg.pack(fill="x", pady=(4, 0))
        ctk.CTkCheckBox(
            row_tg,
            text="📱 成功後發送 Telegram 通知",
            variable=s["tg_enabled"],
            font=ctk.CTkFont(size=11),
            text_color="#38BDF8",
            width=18,
            height=18,
            checkbox_width=16,
            checkbox_height=16,
            corner_radius=4
        ).pack(side="left", padx=(0, 6))

        box_tg_msg = ctk.CTkFrame(detail, fg_color="transparent")
        ctk.CTkLabel(box_tg_msg, text="訊息內容:", font=ctk.CTkFont(size=10), text_color="#38BDF8").pack(side="left", padx=(22, 4))
        ctk.CTkEntry(box_tg_msg, textvariable=s["tg_message"], height=22, corner_radius=4, fg_color=COLOR_INPUT_BG, font=ctk.CTkFont(size=10)).pack(side="left", fill="x", expand=True)

        def _refresh_s_tg_ui(*_):
            if s["tg_enabled"].get():
                box_tg_msg.pack(fill="x", pady=(2, 0))
            else:
                box_tg_msg.pack_forget()
        s["tg_enabled"].trace_add("write", _refresh_s_tg_ui)
        _refresh_s_tg_ui()

        # 展開/收合切換邏輯
        def refresh(*_):
            if s["expanded"].get():
                btn_toggle.configure(text="▾")
                lbl_sum.pack_forget()
                detail.pack(fill="x", padx=10, pady=(0, 8))
            else:
                btn_toggle.configure(text="▸")
                detail.pack_forget()
                lbl_sum.configure(text=summary())
                lbl_sum.pack(fill="x", padx=12, pady=(0, 4))

        s["expanded"].trace_add("write", refresh)
        refresh()
        self._renumber_steps()

    # --------------------------------------------------------------------------
    # 拖曳排序實作 (Drag & Drop Reordering)
    # --------------------------------------------------------------------------
    def _bind_drag_priority_events(self, handle, step):
        def on_start(e):
            step["_drag_start_y"] = e.y_root
            step["_orig_idx"] = self.priority_steps_list.index(step)
        def on_motion(e):
            dy = e.y_root - step.get("_drag_start_y", e.y_root)
            step_height = 40
            steps_moved = int(dy // step_height)
            orig = step.get("_orig_idx", 0)
            new_idx = max(0, min(len(self.priority_steps_list) - 1, orig + steps_moved))
            cur = self.priority_steps_list.index(step)
            if new_idx != cur:
                self.priority_steps_list.remove(step)
                self.priority_steps_list.insert(new_idx, step)
                self._repack_all_priority_steps()
        def on_end(e):
            self.auto_save_current_config()
        handle.bind("<Button-1>", on_start)
        handle.bind("<B1-Motion>", on_motion)
        handle.bind("<ButtonRelease-1>", on_end)

    def _repack_all_priority_steps(self):
        for p in self.priority_steps_list:
            p["frame"].pack_forget()
        for p in self.priority_steps_list:
            p["frame"].pack(fill="x", pady=4, padx=2)
        self._renumber_priority_steps()

    def _bind_drag_events(self, handle, step):
        def on_start(e):
            step["_drag_start_y"] = e.y_root
            step["_orig_idx"] = self.steps_list.index(step)
        def on_motion(e):
            dy = e.y_root - step.get("_drag_start_y", e.y_root)
            step_height = 40
            steps_moved = int(dy // step_height)
            orig = step.get("_orig_idx", 0)
            new_idx = max(0, min(len(self.steps_list) - 1, orig + steps_moved))
            cur = self.steps_list.index(step)
            if new_idx != cur:
                self.steps_list.remove(step)
                self.steps_list.insert(new_idx, step)
                self._repack_all_steps()
        def on_end(e):
            self.auto_save_current_config()
        handle.bind("<Button-1>", on_start)
        handle.bind("<B1-Motion>", on_motion)
        handle.bind("<ButtonRelease-1>", on_end)

    def _repack_all_steps(self):
        for s in self.steps_list:
            s["frame"].pack_forget()
        for s in self.steps_list:
            s["frame"].pack(fill="x", pady=4, padx=2)
        self._renumber_steps()

    # ==========================================================================
    # ⚙️ 設定檔序列化、自動儲存與載入 (100% 相容 JSON)
    # ==========================================================================
    def serialize_current_config(self) -> dict:
        cfg_data = {
            "version": "1.0",
            "recognition_mode": self.var_recognition_mode.get(),
            "device": self.var_device.get(),
            "interval": self.var_interval.get(),
            "confidence": self.var_confidence.get(),
            "idle_strategy": self.var_idle_strategy.get(),
            "auto_refresh": self.var_auto_refresh.get(),
            "preview_interval": self.var_preview_interval.get(),
            "lang_tc": self.var_lang_tc.get(),
            "lang_sc": self.var_lang_sc.get(),
            "lang_en": self.var_lang_en.get(),
            "ocr_languages": {
                "tc": self.var_lang_tc.get(),
                "sc": self.var_lang_sc.get(),
                "en": self.var_lang_en.get(),
            },
            "watchdog_enabled": self.var_watchdog_enabled.get(),
            "watchdog_seconds": self.var_watchdog_seconds.get(),
            "watchdog": {
                "enabled": self.var_watchdog_enabled.get(),
                "seconds": self.var_watchdog_seconds.get(),
            },
            "idle_tap": {
                "enabled": self.var_idle_tap_enabled.get(),
                "area": self.var_idle_tap_area.get(),
                "times": self.var_idle_tap_times.get(),
                "interval": self.var_idle_tap_interval.get(),
                "custom_x": self.var_idle_tap_custom_x.get(),
                "custom_y": self.var_idle_tap_custom_y.get(),
            },
            "tg_token": self.var_tg_token.get(),
            "tg_chat_id": self.var_tg_chat_id.get(),
            "telegram_global": {
                "token": self.var_tg_token.get(),
                "chat_id": self.var_tg_chat_id.get(),
            },
            "priority_steps": [
                {
                    "name": p["name"].get(),
                    "keywords": p["keywords"].get(),
                    "target_type": _normalize_target_type(p["target_type"].get() if "target_type" in p else ""),
                    "template_image": self._ensure_template_in_storage(p["template_image"].get()) if "template_image" in p else "",
                    "image_threshold": _num(p.get("image_threshold", 0.80), 0.80),
                    "image_multiscale": bool(p["image_multiscale"].get()) if "image_multiscale" in p else False,
                    "exclude_keywords": p["exclude_keywords"].get() if "exclude_keywords" in p else "",
                    "action": p["action"].get(),
                    "custom_x": p["custom_x"].get(),
                    "custom_y": p["custom_y"].get(),
                    "delay": p["delay"].get(),
                    "roi": p["roi"].get(),
                    "while_condition": p["while_condition"].get() if "while_condition" in p else True,
                    "repeat_enabled": p["repeat_enabled"].get() if "repeat_enabled" in p else False,
                    "repeat_mode": p["repeat_mode"].get() if "repeat_mode" in p else "持續連點",
                    "repeat_count": p["repeat_count"].get() if "repeat_count" in p else 5,
                    "repeat_speed": p["repeat_speed"].get() if "repeat_speed" in p else 0.25,
                    "repeat_area": p["repeat_area"].get() if "repeat_area" in p else "右下角區域",
                    "repeat_custom_x": p["repeat_custom_x"].get() if "repeat_custom_x" in p else 960,
                    "repeat_custom_y": p["repeat_custom_y"].get() if "repeat_custom_y" in p else 540,
                    "enabled": p["enabled"].get(),
                    "tg_enabled": p["tg_enabled"].get() if "tg_enabled" in p else False,
                    "tg_message": p["tg_message"].get() if "tg_message" in p else "",
                    "task_target_mode": p["task_target_mode"].get() if "task_target_mode" in p else "📋 完整任務清單",
                    "task_target_item": p["task_target_item"].get() if "task_target_item" in p else "",
                    "task_cooldown": p["task_cooldown"].get() if "task_cooldown" in p else 60.0,
                } for p in self.priority_steps_list
            ],
            "steps": [
                {
                    "name": s["name"].get(),
                    "keywords": s["keywords"].get(),
                    "target_type": _normalize_target_type(s["target_type"].get() if "target_type" in s else ""),
                    "template_image": self._ensure_template_in_storage(s["template_image"].get()) if "template_image" in s else "",
                    "image_threshold": _num(s.get("image_threshold", 0.80), 0.80),
                    "image_multiscale": bool(s["image_multiscale"].get()) if "image_multiscale" in s else False,
                    "exclude_keywords": s["exclude_keywords"].get() if "exclude_keywords" in s else "",
                    "action": s["action"].get(),
                    "custom_x": s["custom_x"].get(),
                    "custom_y": s["custom_y"].get(),
                    "delay": s["delay"].get(),
                    "roi": s["roi"].get(),
                    "enabled": s["enabled"].get(),
                    "repeat_enabled": s["repeat_enabled"].get() if "repeat_enabled" in s else False,
                    "repeat_mode": s["repeat_mode"].get() if "repeat_mode" in s else "持續連點",
                    "repeat_count": s["repeat_count"].get() if "repeat_count" in s else 5,
                    "repeat_speed": s["repeat_speed"].get() if "repeat_speed" in s else 0.25,
                    "repeat_area": s["repeat_area"].get() if "repeat_area" in s else "右下角區域",
                    "repeat_custom_x": s["repeat_custom_x"].get() if "repeat_custom_x" in s else 960,
                    "repeat_custom_y": s["repeat_custom_y"].get() if "repeat_custom_y" in s else 540,
                    "timeout_enabled": s["timeout_enabled"].get() if "timeout_enabled" in s else False,
                    "timeout_seconds": s["timeout_seconds"].get() if "timeout_seconds" in s else 20,
                    "tg_enabled": s["tg_enabled"].get() if "tg_enabled" in s else False,
                    "tg_message": s["tg_message"].get() if "tg_message" in s else "",
                    "task_target_mode": s["task_target_mode"].get() if "task_target_mode" in s else "📋 完整任務清單",
                    "task_target_item": s["task_target_item"].get() if "task_target_item" in s else "",
                    "task_cooldown": s["task_cooldown"].get() if "task_cooldown" in s else 60.0,
                } for s in self.steps_list
            ]
        }
        if hasattr(self, "task_tab") and self.task_tab:
            try:
                cfg_data["task_flow"] = self.task_tab._serialize_all_blocks()
                cfg_data["task_loop_count"] = self.task_tab.var_loop_count.get()
            except Exception:
                pass
        return cfg_data

    def apply_config_dict(self, cfg: dict):
        if not isinstance(cfg, dict):
            return
        self._is_loading_config = True
        if "recognition_mode" in cfg:
            self.var_recognition_mode.set(str(cfg["recognition_mode"]))
        else:
            has_img = any(
                (s.get("template_image") or "圖片" in str(s.get("target_type", "")))
                for s in (cfg.get("steps", []) + cfg.get("priority_steps", []))
            )
            self.var_recognition_mode.set("🖼️ 圖片特徵比對模式" if has_img else "📝 文字辨識模式")
        if "device" in cfg and cfg["device"]:
            self.var_device.set(cfg["device"])
        if "interval" in cfg:
            try:
                self.var_interval.set(float(cfg["interval"]))
            except Exception:
                pass
        if "confidence" in cfg:
            try:
                self.var_confidence.set(float(cfg["confidence"]))
            except Exception:
                pass
        if "idle_strategy" in cfg:
            self.var_idle_strategy.set(str(cfg["idle_strategy"]))
        if "auto_refresh" in cfg:
            self.var_auto_refresh.set(bool(cfg["auto_refresh"]))
        if "preview_interval" in cfg:
            self.var_preview_interval.set(str(cfg["preview_interval"]))

        # 語言設定
        if "ocr_languages" in cfg and isinstance(cfg["ocr_languages"], dict):
            langs = cfg["ocr_languages"]
            self.var_lang_tc.set(bool(langs.get("tc", True)))
            self.var_lang_sc.set(bool(langs.get("sc", False)))
            self.var_lang_en.set(bool(langs.get("en", True)))
        else:
            if "lang_tc" in cfg: self.var_lang_tc.set(bool(cfg["lang_tc"]))
            if "lang_sc" in cfg: self.var_lang_sc.set(bool(cfg["lang_sc"]))
            if "lang_en" in cfg: self.var_lang_en.set(bool(cfg["lang_en"]))

        if hasattr(self, "bot"):
            self.bot.set_allowed_languages(
                self.var_lang_tc.get(),
                self.var_lang_sc.get(),
                self.var_lang_en.get()
            )
            try:
                self.bot.confidence_threshold = float(self.var_confidence.get())
            except Exception:
                pass

        if hasattr(self, "lbl_sp_val") and self.lbl_sp_val:
            self.lbl_sp_val.configure(text=f"{self.var_interval.get():.1f}s")
        if hasattr(self, "lbl_cf_val") and self.lbl_cf_val:
            self.lbl_cf_val.configure(text=f"{self.var_confidence.get():.2f}")

        # 看門狗防卡死
        if "watchdog" in cfg and isinstance(cfg["watchdog"], dict):
            wd = cfg["watchdog"]
            self.var_watchdog_enabled.set(bool(wd.get("enabled", False)))
            self.var_watchdog_seconds.set(int(wd.get("seconds", 60)))
        else:
            if "watchdog_enabled" in cfg: self.var_watchdog_enabled.set(bool(cfg["watchdog_enabled"]))
            if "watchdog_seconds" in cfg: self.var_watchdog_seconds.set(int(cfg["watchdog_seconds"]))

        # 連點區塊
        if "idle_tap" in cfg and isinstance(cfg["idle_tap"], dict):
            it = cfg["idle_tap"]
            self.var_idle_tap_enabled.set(bool(it.get("enabled", False)))
            self.var_idle_tap_area.set(str(it.get("area", "右下角區域")))
            self.var_idle_tap_times.set(int(it.get("times", 3)))
            self.var_idle_tap_interval.set(float(it.get("interval", 0.4)))
            self.var_idle_tap_custom_x.set(int(it.get("custom_x", 983)))
            self.var_idle_tap_custom_y.set(int(it.get("custom_y", 1023)))

        # Telegram
        if "telegram_global" in cfg and isinstance(cfg["telegram_global"], dict):
            tg_g = cfg["telegram_global"]
            self.var_tg_token.set(str(tg_g.get("token", DEFAULT_TG_TOKEN)))
            self.var_tg_chat_id.set(str(tg_g.get("chat_id", DEFAULT_TG_CHAT_ID)))
        else:
            if "tg_token" in cfg: self.var_tg_token.set(str(cfg["tg_token"]))
            if "tg_chat_id" in cfg: self.var_tg_chat_id.set(str(cfg["tg_chat_id"]))

        # 優先動作
        p_list = cfg.get("priority_steps")
        if p_list is None and "priority" in cfg and isinstance(cfg["priority"], dict):
            p_old = cfg["priority"]
            if p_old.get("keywords") or p_old.get("enabled") or p_old.get("template_image"):
                p_list = [p_old]

        if isinstance(p_list, list):
            self._clear_all_priority_steps()
            for p_data in p_list:
                kw = p_data.get("keywords", "")
                if isinstance(kw, list):
                    kw = ", ".join(str(k) for k in kw)
                ex_kw = p_data.get("exclude_keywords", "")
                if isinstance(ex_kw, list):
                    ex_kw = ", ".join(str(k) for k in ex_kw)

                tg_on = p_data.get("tg_enabled", False)
                tg_msg = p_data.get("tg_message", "")
                if isinstance(p_data.get("telegram"), dict):
                    tg_on = p_data["telegram"].get("enabled", tg_on)
                    tg_msg = p_data["telegram"].get("message", tg_msg)

                self._create_priority_step_widget(
                    name=str(p_data.get("name", "優先動作")),
                    keywords=str(kw),
                    target_type=str(p_data.get("target_type", "📝 文字辨識 (OCR)")),
                    template_image=str(p_data.get("template_image", "")),
                    image_threshold=float(p_data.get("image_threshold", 0.80)),
                    image_multiscale=bool(p_data.get("image_multiscale", False)),
                    exclude_keywords=str(ex_kw),
                    action=str(p_data.get("action", "點擊目標中心 / 詞條")),
                    custom_x=int(p_data.get("custom_x", 960)),
                    custom_y=int(p_data.get("custom_y", 540)),
                    delay=float(p_data.get("delay", 2.0)),
                    roi_name=str(p_data.get("roi", "全畫面比對")),
                    while_condition=bool(p_data.get("while_condition", True)),
                    repeat_enabled=bool(p_data.get("repeat_enabled", False)),
                    repeat_mode=str(p_data.get("repeat_mode", "持續連點")),
                    repeat_count=int(p_data.get("repeat_count", 5)),
                    repeat_speed=float(p_data.get("repeat_speed", 0.25)),
                    repeat_area=str(p_data.get("repeat_area", "右下角區域")),
                    repeat_custom_x=int(p_data.get("repeat_custom_x", 960)),
                    repeat_custom_y=int(p_data.get("repeat_custom_y", 540)),
                    enabled=bool(p_data.get("enabled", True)),
                    tg_enabled=bool(tg_on),
                    tg_message=str(tg_msg),
                    task_target_mode=str(p_data.get("task_target_mode", "📋 完整任務清單")),
                    task_target_item=str(p_data.get("task_target_item", "")),
                    task_cooldown=float(p_data.get("task_cooldown", 60.0)),
                    expanded=False
                )

        # 一般步驟
        if isinstance(cfg.get("steps"), list):
            self._clear_all_steps()
            for s_data in cfg["steps"]:
                kw = s_data.get("keywords", "")
                if isinstance(kw, list):
                    kw = ", ".join(str(k) for k in kw)
                ex_kw = s_data.get("exclude_keywords", "")
                if isinstance(ex_kw, list):
                    ex_kw = ", ".join(str(k) for k in ex_kw)

                tg_on = s_data.get("tg_enabled", False)
                tg_msg = s_data.get("tg_message", "")
                if isinstance(s_data.get("telegram"), dict):
                    tg_on = s_data["telegram"].get("enabled", tg_on)
                    tg_msg = s_data["telegram"].get("message", tg_msg)

                self._create_step_widget(
                    name=str(s_data.get("name", "步驟")),
                    keywords=str(kw),
                    target_type=str(s_data.get("target_type", "📝 文字辨識 (OCR)")),
                    template_image=str(s_data.get("template_image", "")),
                    image_threshold=float(s_data.get("image_threshold", 0.80)),
                    image_multiscale=bool(s_data.get("image_multiscale", False)),
                    exclude_keywords=str(ex_kw),
                    action=str(s_data.get("action", "點擊目標中心 / 詞條")),
                    custom_x=int(s_data.get("custom_x", 960)),
                    custom_y=int(s_data.get("custom_y", 540)),
                    delay=float(s_data.get("delay", 2.5)),
                    roi_name=str(s_data.get("roi", "右下角區域")),
                    enabled=bool(s_data.get("enabled", True)),
                    repeat_enabled=bool(s_data.get("repeat_enabled", False)),
                    repeat_mode=str(s_data.get("repeat_mode", "持續連點")),
                    repeat_count=int(s_data.get("repeat_count", 5)),
                    repeat_speed=float(s_data.get("repeat_speed", 0.25)),
                    repeat_area=str(s_data.get("repeat_area", "右下角區域")),
                    repeat_custom_x=int(s_data.get("repeat_custom_x", 960)),
                    repeat_custom_y=int(s_data.get("repeat_custom_y", 540)),
                    timeout_enabled=bool(s_data.get("timeout_enabled", False)),
                    timeout_seconds=int(s_data.get("timeout_seconds", 20)),
                    tg_enabled=bool(tg_on),
                    tg_message=str(tg_msg),
                    task_target_mode=str(s_data.get("task_target_mode", "📋 完整任務清單")),
                    task_target_item=str(s_data.get("task_target_item", "")),
                    task_cooldown=float(s_data.get("task_cooldown", 60.0)),
                    expanded=False
                )

        # 任務清單積木載入
        if hasattr(self, "task_tab") and self.task_tab:
            tf_blocks = cfg.get("task_flow") or (cfg.get("blocks") if "priority_steps" not in cfg else None)
            if isinstance(tf_blocks, list):
                try:
                    if "task_loop_count" in cfg:
                        self.task_tab.var_loop_count.set(int(cfg["task_loop_count"]))
                    elif "loop_count" in cfg:
                        self.task_tab.var_loop_count.set(int(cfg["loop_count"]))
                    for b in self.task_tab.blocks_list:
                        for cb in b.get("inner_blocks_list", []):
                            if cb.get("frame"):
                                cb["frame"].destroy()
                        if b.get("frame"):
                            b["frame"].destroy()
                    self.task_tab.blocks_list.clear()
                    self.task_tab.selected_block_target = None
                    for bd in tf_blocks:
                        self.task_tab.add_block(
                            b_type=bd["type"],
                            params=bd.get("params", {}),
                            name=bd.get("name", ""),
                            enabled=bd.get("enabled", True)
                        )
                    self.task_tab.auto_save_config()
                except Exception:
                    pass

        self._is_loading_config = False
        # 刷新所有卡片外觀與辨識模式
        self._on_recognition_mode_changed()

    def auto_save_current_config(self):
        """防抖 (Debounced) 自動存檔，避免連續編輯時重複頻繁寫入硬碟"""
        if getattr(self, "_is_loading_config", False):
            return
        if hasattr(self, "_auto_save_timer") and self._auto_save_timer:
            try:
                self.root.after_cancel(self._auto_save_timer)
            except Exception:
                pass
        self._auto_save_timer = self.root.after(300, self._do_auto_save_write)

    def _do_auto_save_write(self):
        self._auto_save_timer = None
        if getattr(self, "_is_loading_config", False):
            return
        try:
            cfg = self.serialize_current_config()
            with open(self.auto_save_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_all_settings(self, show_msg: bool = True):
        """立即將所有聯賽設定與任務清單儲存至自訂存檔目錄中"""
        try:
            self._do_auto_save_write()
            if hasattr(self, "task_tab") and self.task_tab:
                self.task_tab.auto_save_config()
            self.log_message(f"💾 所有設定已成功儲存至存檔目錄: {self.storage_dir}")
            if show_msg:
                messagebox.showinfo(
                    "儲存成功",
                    f"✅ 所有設定已成功儲存至自訂資料夾：\n{self.storage_dir}\n\n"
                    f"• 聯賽設定：{os.path.basename(self.auto_save_file)}\n"
                    f"• 任務清單：{os.path.basename(self.task_save_file)}",
                    parent=self.root
                )
        except Exception as ex:
            self.log_message(f"❌ 儲存所有設定失敗: {ex}")
            if show_msg:
                messagebox.showerror("儲存失敗", f"無法儲存設定: {ex}", parent=self.root)

    def auto_load_last_config(self) -> bool:
        if os.path.exists(self.auto_save_file):
            try:
                with open(self.auto_save_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.apply_config_dict(cfg)
                self.log_message(f"自動載入歷史設定: {os.path.basename(self.auto_save_file)}")
                return True
            except Exception:
                pass
        return False

    def on_save_config_manual(self):
        path = filedialog.asksaveasfilename(
            parent=self.root,
            initialdir=self.storage_dir if os.path.exists(self.storage_dir) else self.config_dir,
            title="另存設定檔 (JSON)",
            defaultextension=".json",
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
        )
        if path:
            try:
                cfg = self.serialize_current_config()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                self.log_message(f"設定已儲存至: {os.path.basename(path)}")
                messagebox.showinfo("成功", f"設定已成功另存至:\n{path}", parent=self.root)
            except Exception as e:
                messagebox.showerror("錯誤", f"儲存失敗: {e}", parent=self.root)

    def on_load_config_manual(self):
        path = filedialog.askopenfilename(
            title="載入設定檔",
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.apply_config_dict(cfg)
                self.log_message(f"已成功載入設定: {os.path.basename(path)}")
                messagebox.showinfo("成功", f"已成功載入設定:\n{path}")
            except Exception as e:
                messagebox.showerror("錯誤", f"載入失敗: {e}")

    # ==========================================================================
    # 📁 獨立存檔與圖片資料夾管理 (完全脫離 Git 倉庫，永久記憶)
    # ==========================================================================
    def set_storage_dir(self, new_dir: str, seed: bool = False):
        """動態切換自訂存檔目錄，不生成任何多餘資料夾"""
        if not new_dir:
            new_dir = os.path.dirname(os.path.abspath(__file__))
        self.storage_dir = os.path.abspath(os.path.expanduser(new_dir))
        self.templates_dir = self.storage_dir
        self.league_presets_dir = self.storage_dir
        self.task_presets_dir = self.storage_dir
        self.auto_save_file = os.path.join(self.storage_dir, f"baseball_last_config{'' if self.instance_id == 1 else f'_{self.instance_id}'}.json")
        self.task_save_file = os.path.join(self.storage_dir, f"task_flow_save{'' if self.instance_id == 1 else f'_{self.instance_id}'}.json")

        persist_storage_dir(self.storage_dir)

        if hasattr(self, "var_storage_display"):
            self.var_storage_display.set(self.storage_dir)

        if hasattr(self, "bot") and self.bot:
            self.bot.set_templates_dir(self.templates_dir)

        if hasattr(self, "task_tab") and self.task_tab:
            self.task_tab.presets_dir = self.task_presets_dir
            self.task_tab.save_file = self.task_save_file

        self._refresh_all_step_thumbs()

    def _seed_default_assets(self):
        """不主動在使用者電腦生成多餘資料夾或拷貝檔案"""
        pass

    def resolve_image_path(self, img_name: str) -> Optional[str]:
        """跨目錄解析步驟設定的圖片模板，確保縮圖與辨識 100% 讀取得到"""
        if not img_name or not str(img_name).strip():
            return None
        p = str(img_name).strip()
        if os.path.isabs(p) and os.path.isfile(p):
            return os.path.abspath(p)
        candidates = [
            p,
            os.path.join(self.storage_dir, p),
            os.path.join(self.storage_dir, os.path.basename(p)),
            os.path.join(self.config_dir, "templates", os.path.basename(p)),
            os.path.join(self.config_dir, "templates", p),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", os.path.basename(p)),
            os.path.join(os.getcwd(), p),
            os.path.join(os.getcwd(), os.path.basename(p)),
        ]
        if hasattr(self, "auto_save_file") and self.auto_save_file:
            save_p_dir = os.path.dirname(self.auto_save_file)
            candidates.append(os.path.join(save_p_dir, os.path.basename(p)))
            candidates.append(os.path.join(save_p_dir, p))
        if hasattr(self, "bot") and self.bot:
            bot_res = self.bot.resolve_template_path(p)
            if bot_res and os.path.isfile(bot_res):
                return bot_res
        for c in candidates:
            if c and os.path.isfile(c):
                return os.path.abspath(c)
        return None

    def _refresh_all_step_thumbs(self):
        """重新觸發所有步驟卡片的縮圖載入"""
        for p in getattr(self, "priority_steps_list", []):
            if "template_image" in p:
                try:
                    p["template_image"].set(p["template_image"].get())
                except Exception:
                    pass
        for s in getattr(self, "steps_list", []):
            if "template_image" in s:
                try:
                    s["template_image"].set(s["template_image"].get())
                except Exception:
                    pass

    def _ensure_template_in_storage(self, img_name: str) -> str:
        """回傳圖檔路徑或檔名，不額外建立資料夾或強制拷貝"""
        return str(img_name).strip() if img_name else ""

    def on_change_storage_dir(self):
        """開啟目錄選擇器變更存檔資料夾"""
        d = filedialog.askdirectory(
            parent=self.root,
            initialdir=self.storage_dir if os.path.exists(self.storage_dir) else self.config_dir,
            title="📁 選擇存檔資料夾"
        )
        if d:
            self.set_storage_dir(d, seed=False)
            self.log_message(f"📁 存檔資料夾已切換至: {d}")
            messagebox.showinfo(
                "存檔路徑已更新",
                f"存檔資料夾已成功切換至：\n{d}",
                parent=self.root
            )

    def on_open_storage_dir(self):
        """開啟存檔資料夾"""
        target = self.storage_dir if os.path.exists(self.storage_dir) else self.config_dir
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", target])
            elif sys.platform == "win32":
                os.startfile(target)
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as ex:
            messagebox.showerror("錯誤", f"無法開啟存檔資料夾: {ex}", parent=self.root)

    def on_snip_template_dialog(self, step_or_p: dict):
        """從當前畫面或即時截圖進行局部框選裁切，儲存為圖片模板"""
        screen_bgr = self.current_screen_bgr
        if screen_bgr is None:
            if hasattr(self, "bot") and self.bot and self.bot.device:
                self.log_message("正在即時截取最新遊戲畫面以供框選...")
                screen_bgr = self.bot.capture_screen()
                if screen_bgr is not None:
                    self.current_screen_bgr = screen_bgr
                    self._render_preview(screen_bgr)
        if screen_bgr is None:
            messagebox.showwarning(
                "提示",
                "目前尚無遊戲畫面可用於框選！\n請先確認模擬器已連線，並點擊右側「📸 截圖」獲取最新畫面。",
                parent=self.root
            )
            return

        initial_name = step_or_p.get("name", tk.StringVar()).get().strip() or "btn_template"

        def on_saved(saved_path: str):
            fname = os.path.basename(saved_path)
            self.last_snipped_template = saved_path
            # 若位於目前存檔目錄下，儲存檔名；否則儲存絕對路徑
            if self.storage_dir and os.path.commonpath([os.path.abspath(saved_path), os.path.abspath(self.storage_dir)]) == os.path.abspath(self.storage_dir):
                step_or_p["template_image"].set(fname)
            else:
                step_or_p["template_image"].set(os.path.abspath(saved_path))
            self.auto_save_current_config()
            self._refresh_all_step_thumbs()
            self.log_message(f"✂️ 已框選並儲存模板圖片: {saved_path}")

        TemplateSnipperDialog(
            parent=self.root,
            screen_bgr=screen_bgr,
            initial_name=initial_name,
            templates_dir=self.storage_dir,
            on_save_callback=on_saved
        )

    def _init_default_steps(self):
        if self.auto_load_last_config():
            return
        self.on_reset_baseball_template()

    def reload_league_presets(self):
        """相容保留：不載入額外範本庫"""
        self.league_presets = {}

    def load_league_preset(self, preset_key: str, confirm: bool = True):
        """相容保留：轉調載入設定檔"""
        self.on_load_config_manual()

    def delete_league_preset(self, preset_key: str, parent_dlg=None):
        pass

    def on_open_league_presets_dialog(self):
        """開啟載入設定檔對話框（直接選擇電腦上的設定檔）"""
        self.on_load_config_manual()

    def on_save_league_preset_dialog(self, default_mode: str = "new"):
        """開啟儲存設定對話框（直接詢問使用者要存到哪裡）"""
        self.on_open_save_dialog()

    def on_reset_baseball_template(self):
        """建立經典棒球聯賽刷關預設步驟"""
        self._clear_all_priority_steps()
        self._clear_all_steps()
        self._create_priority_step_widget(
            name="異常連線中斷",
            keywords="連線中斷, 重新連線, 網路異常, 伺服器維護, 請重新登入",
            action="點擊詞條",
            delay=3.0,
            roi_name="中央區域",
            expanded=False
        )
        default_steps = [
            ("結算確認", "確認, 確定, 領取, 結算, 結束", 3.0, "右下角區域"),
            ("繼續下一場", "繼續, 下一步, 再來一場, 返回", 2.5, "右下角區域"),
            ("準備比賽", "準備, 挑戰, 出戰, 進入", 2.5, "右半側螢幕"),
            ("開始比賽", "開始, 確定開始, 比賽開始, 開打", 4.0, "右下角區域"),
        ]
        for name, kw, d, r in default_steps:
            self._create_step_widget(name=name, keywords=kw, delay=d, roi_name=r, expanded=False)
        self.log_message("已重設為經典棒球聯賽自動刷關預設步驟。")

    # ==========================================================================
    # 🔌 裝置連線與 ADB 控制
    # ==========================================================================
    def on_refresh_devices(self):
        self.log_message("正在搜尋 ADB 裝置與模擬器...")
        devices = self.bot.get_devices_list()
        self.combo_devices.configure(values=devices if devices else ["未偵測到裝置"])
        if devices:
            self.combo_devices.set(devices[0])
            self.log_message(f"發現裝置: {', '.join(devices)}")
        else:
            self.combo_devices.set("未偵測到裝置")
            self.log_message("未找到已連線的 ADB 裝置。請確認模擬器已啟動。")

    def on_connect_device(self):
        target = self.var_device.get()
        if not target or target == "未偵測到裝置":
            target = None
        self.log_message(f"連線至裝置: {target or '預設第一台'}")
        if self.bot.connect(target_serial=target):
            self._set_status("已連線 (CONNECTED)", COLOR_RUNNING)
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.log_message("ADB 裝置連線成功！已自動啟動即時畫面連續刷新。")
            self.on_preview_and_detect()
            if self.var_auto_refresh.get():
                self._schedule_next_refresh(self._get_preview_interval_ms())
        else:
            self._set_status("連線失敗 (FAILED)", COLOR_STOPPED)
            messagebox.showerror("錯誤", "無法連線至指定的 ADB 裝置。請檢查連接埠或重啟模擬器。")

    def _set_status(self, text: str, color: str):
        self.var_status_text.set(text)
        self.lbl_status.configure(text_color=color)
        self.indicator_light.configure(text_color=color)

    # ==========================================================================
    # 🧵 執行緒運作與背景巡檢 (Worker Loop)
    # ==========================================================================
    def _map_roi_name_to_tuple(self, roi_name: str):
        """範圍名稱 -> (ymin, xmin, ymax, xmax) 比例"""
        return {
            "右下角區域": (0.45, 0.45, 1.0, 1.0),
            "右半側螢幕": (0.0, 0.45, 1.0, 1.0),
            "下半部區域": (0.50, 0.0, 1.0, 1.0),
            "中央區域": (0.25, 0.25, 0.75, 0.75),
            "全畫面比對": (0.0, 0.0, 1.0, 1.0),
        }.get(roi_name, (0.0, 0.0, 1.0, 1.0))

    def _sync_bot_roi(self):
        self.bot.confidence_threshold = _num(self.var_confidence, 0.65)
        self.bot.roi = None

    def on_start_bot(self):
        if self.is_running:
            return
        if not self.bot.device:
            messagebox.showwarning("警告", "尚未連線至 ADB 裝置，請先點擊「連線」。")
            return
        if hasattr(self, "task_tab") and self.task_tab and self.task_tab.engine.is_running:
            messagebox.showwarning("提示", "【任務清單】正在執行中，請先停止任務清單再啟動聯賽自動刷關。")
            return

        steps = self._get_active_steps_config()
        priority_steps = self._get_active_priority_steps_config()
        if not any(s["enabled"] for s in steps) and not any(p["enabled"] for p in priority_steps):
            messagebox.showwarning("提示", "請至少啟用一個步驟或優先動作")
            return

        self.auto_save_current_config()
        self._sync_bot_roi()
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

        self.is_running = True
        self.bot.is_running = True
        self.start_time = time.time()

        self._set_status("運作中 (RUNNING)", COLOR_RUNNING)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.log_message("🚀 自動刷關執行緒已啟動！")

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(interval, steps, idle, idle_tap_cfg, priority_steps, watchdog_cfg),
            daemon=True
        )
        self.worker_thread.start()

    def on_stop_bot(self):
        if getattr(self, "_watchdog_restart_job", None):
            self.root.after_cancel(self._watchdog_restart_job)
            self._watchdog_restart_job = None
        self.log_message("🛑 正在停止自動刷關...")
        self.bot.stop()
        if hasattr(self, "task_tab") and self.task_tab:
            self.task_tab.engine.stop()
        self.is_running = False
        self._set_status("已停止 (STOPPED)", COLOR_STOPPED)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _run_worker(self, interval: float, steps: list, idle: str, idle_tap_cfg: dict, priority_steps: list, watchdog_cfg: dict = None):
        """背景執行緒迴圈：委託 bot_core.run_loop 運行完整比對與動作引擎"""
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
        self.current_screen_bgr = None
        self._last_detected = None
        import gc
        gc.collect()

        was_watchdog = getattr(self.bot, "_watchdog_triggered", False)
        self.bot._watchdog_triggered = False

        if was_watchdog:
            self.log_message("🔄 [防卡死守護] 腳本已由守護程式停止，將於 1.5 秒後自動重新開啟...")
            self._set_status("● 防卡死重新啟動中...", COLOR_WARN)
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self._watchdog_restart_job = self.root.after(1500, self._restart_worker_after_watchdog)
            return

        self.is_running = False
        self.bot.is_running = False
        self._set_status("已停止 (STOPPED)", COLOR_STOPPED)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.log_message("⏹ 背景工作執行緒已安全終止。")

        if self.var_auto_refresh.get() and not self.auto_refresh_job:
            self._schedule_next_refresh(500)

    def _restart_worker_after_watchdog(self):
        self._watchdog_restart_job = None
        if not self.bot.device:
            self.log_message("⚠️ 模擬器連線已中斷，無法自動重啟")
            self._on_worker_stopped()
            return
        self.log_message("🚀 [防卡死守護] 自動重新開啟腳本！")
        self.on_start_bot()

    def _get_active_steps_config(self) -> list:
        cfg = []
        is_img_mode = ("圖片" in self.var_recognition_mode.get())
        for s in self.steps_list:
            raw_kws = s["keywords"].get()
            kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
            raw_ex = s["exclude_keywords"].get() if "exclude_keywords" in s else ""
            ex_kws = [k.strip() for k in raw_ex.replace("，", ",").split(",") if k.strip()]
            delay = _num(s["delay"], 2.5)
            rep_on = s["repeat_enabled"].get() if "repeat_enabled" in s else False
            tt = "🖼️ 圖片特徵 (模板比對)" if is_img_mode else "📝 文字辨識 (OCR)"
            is_img = is_img_mode
            is_sym = ("打勾" in tt or "叉叉" in tt)
            tpl_img = s["template_image"].get().strip() if "template_image" in s else ""
            img_th = _num(s.get("image_threshold", 0.80), 0.80)
            img_ms = bool(s["image_multiscale"].get()) if "image_multiscale" in s else False

            is_valid_target = (is_img and bool(tpl_img)) or (not is_img and (bool(kws) or is_sym))

            cfg.append({
                "name": s["name"].get().strip() or "步驟",
                "target_type": tt,
                "template_image": tpl_img,
                "image_threshold": img_th,
                "image_multiscale": img_ms,
                "keywords": kws,
                "exclude_keywords": ex_kws,
                "action": "custom_coord" if is_custom_coord_action(s["action"].get()) else s["action"].get(),
                "custom_x": _num(s["custom_x"], 0, int),
                "custom_y": _num(s["custom_y"], 0, int),
                "delay": delay,
                "delay_min": max(0.05, delay - 0.15),
                "delay_max": delay + 0.15,
                "enabled": s["enabled"].get() and is_valid_target,
                "roi": self._map_roi_name_to_tuple(s["roi"].get()),
                "roi_name": s["roi"].get(),
                "repeat_enabled": rep_on,
                "repeat_mode": "count" if (s.get("repeat_mode") and s["repeat_mode"].get() == "指定次數") else "until_next",
                "repeat_count": _num(s["repeat_count"], 15, int) if rep_on and "repeat_count" in s else 1,
                "repeat_speed": _num(s["repeat_speed"], 0.3) if "repeat_speed" in s else 0.3,
                "repeat_area": s["repeat_area"].get() if "repeat_area" in s else "右下角區域",
                "repeat_custom_x": _num(s.get("repeat_custom_x", 0), 0, int),
                "repeat_custom_y": _num(s.get("repeat_custom_y", 0), 0, int),
                "repeat_custom_coord": (_num(s.get("repeat_custom_x", 0), 0, int), _num(s.get("repeat_custom_y", 0), 0, int)),
                "timeout_enabled": s["timeout_enabled"].get() if "timeout_enabled" in s else False,
                "timeout_seconds": _num(s["timeout_seconds"], 15, int) if "timeout_seconds" in s else 15,
                "telegram": {
                    "enabled": s["tg_enabled"].get() if "tg_enabled" in s else False,
                    "message": s["tg_message"].get().strip() if "tg_message" in s else "",
                    "token": self.var_tg_token.get().strip(),
                    "chat_id": self.var_tg_chat_id.get().strip(),
                },
                "task_target_mode": s["task_target_mode"].get() if "task_target_mode" in s else "📋 完整任務清單",
                "task_target_item": s["task_target_item"].get() if "task_target_item" in s else "",
                "task_cooldown": _num(s["task_cooldown"], 60.0) if "task_cooldown" in s else 60.0,
            })
        return cfg

    def _get_active_priority_steps_config(self) -> list:
        cfg = []
        is_img_mode = ("圖片" in self.var_recognition_mode.get())
        for p in self.priority_steps_list:
            raw_kws = p["keywords"].get()
            kws = [k.strip() for k in raw_kws.replace("，", ",").split(",") if k.strip()]
            raw_ex = p["exclude_keywords"].get() if "exclude_keywords" in p else ""
            ex_kws = [k.strip() for k in raw_ex.replace("，", ",").split(",") if k.strip()]
            rep_on = p["repeat_enabled"].get() if "repeat_enabled" in p else False
            tt = "🖼️ 圖片特徵 (模板比對)" if is_img_mode else "📝 文字辨識 (OCR)"
            is_img = is_img_mode
            is_sym = ("打勾" in tt or "叉叉" in tt)
            tpl_img = p["template_image"].get().strip() if "template_image" in p else ""
            img_th = _num(p.get("image_threshold", 0.80), 0.80)
            img_ms = bool(p["image_multiscale"].get()) if "image_multiscale" in p else False

            is_valid_target = (is_img and bool(tpl_img)) or (not is_img and (bool(kws) or is_sym))
            delay = _num(p["delay"], 1.0)
            cfg.append({
                "type": "priority",
                "name": p["name"].get().strip() or "優先動作",
                "target_type": tt,
                "template_image": tpl_img,
                "image_threshold": img_th,
                "image_multiscale": img_ms,
                "keywords": kws,
                "exclude_keywords": ex_kws,
                "action": "custom_coord" if is_custom_coord_action(p["action"].get()) else p["action"].get(),
                "custom_x": _num(p["custom_x"], 0, int),
                "custom_y": _num(p["custom_y"], 0, int),
                "delay": delay,
                "delay_min": max(0.05, delay - 0.15),
                "delay_max": delay + 0.15,
                "roi": self._map_roi_name_to_tuple(p["roi"].get()),
                "roi_name": p["roi"].get(),
                "while_condition": p["while_condition"].get() if "while_condition" in p else True,
                "repeat_enabled": rep_on,
                "repeat_mode": "count" if (p.get("repeat_mode") and p["repeat_mode"].get() == "指定次數") else "until_next",
                "repeat_count": _num(p["repeat_count"], 15, int) if rep_on and "repeat_count" in p else 1,
                "repeat_speed": _num(p["repeat_speed"], 0.3) if "repeat_speed" in p else 0.3,
                "repeat_area": p["repeat_area"].get() if "repeat_area" in p else "右下角區域",
                "repeat_custom_x": _num(p.get("repeat_custom_x", 0), 0, int),
                "repeat_custom_y": _num(p.get("repeat_custom_y", 0), 0, int),
                "repeat_custom_coord": (_num(p.get("repeat_custom_x", 0), 0, int), _num(p.get("repeat_custom_y", 0), 0, int)),
                "telegram": {
                    "enabled": p["tg_enabled"].get() if "tg_enabled" in p else False,
                    "message": p["tg_message"].get().strip() if "tg_message" in p else "",
                    "token": self.var_tg_token.get().strip(),
                    "chat_id": self.var_tg_chat_id.get().strip(),
                },
                "task_target_mode": p["task_target_mode"].get() if "task_target_mode" in p else "📋 完整任務清單",
                "task_target_item": p["task_target_item"].get() if "task_target_item" in p else "",
                "task_cooldown": _num(p["task_cooldown"], 60.0) if "task_cooldown" in p else 60.0,
                "enabled": p["enabled"].get() and is_valid_target,
                "max_continuous": 25,
            })
        return cfg

    def _execute_task_flow_for_event(self, step_cfg: dict) -> bool:
        """
        當聯賽自動刷偵測到指定事件/文字時，暫停聯賽循環，跳轉至任務清單執行特定功能，完成後無縫恢復聯賽。
        本方法由工作執行緒直接呼叫，會同步執行直到任務完成或被停止。
        """
        if not hasattr(self, "task_tab") or not self.task_tab:
            self.log_message("⚠️ 尚未初始化任務清單元件，跳過執行。")
            return False

        mode = step_cfg.get("task_target_mode", "📋 完整任務清單")
        target_item = step_cfg.get("task_target_item", "")
        step_name = step_cfg.get("name", "事件步驟")

        blocks_to_run = []
        if ("任務檔" in mode or "範本" in mode) and target_item:
            preset_key = target_item.split(":")[0].strip()
            preset = self.task_tab.get_preset_data(preset_key) if hasattr(self.task_tab, "get_preset_data") else None
            if not preset:
                from task_flow import DAILY_PRESETS
                preset = DAILY_PRESETS.get(preset_key)
            if preset:
                blocks_to_run = [dict(b) for b in preset.get("blocks", [])]
                self.log_message(f"📋 [任務跳轉] 載入任務設定「{preset.get('title', preset_key)}」(共 {len(blocks_to_run)} 個步驟)")
            else:
                self.log_message(f"⚠️ [任務跳轉] 找不到任務設定「{target_item}」，執行完整任務清單備援")
                blocks_to_run = self.task_tab._serialize_all_blocks()
        elif mode == "🧩 指定積木步驟" and target_item:
            single_block = self.task_tab.get_block_data_by_choice(target_item)
            if single_block:
                blocks_to_run = [single_block]
                self.log_message(f"📋 [任務跳轉] 執行指定積木「{single_block.get('name', target_item)}」")
            else:
                self.log_message(f"⚠️ [任務跳轉] 找不到指定積木「{target_item}」，執行完整任務清單備援")
                blocks_to_run = self.task_tab._serialize_all_blocks()
        else:
            blocks_to_run = self.task_tab._serialize_all_blocks()
            self.log_message(f"📋 [任務跳轉] 執行完整任務清單 (共 {len(blocks_to_run)} 個步驟)")

        if not blocks_to_run:
            self.log_message("⚠️ [任務跳轉] 任務清單中無可執行的步驟，結束跳轉並恢復聯賽。")
            return False

        self.root.after(0, lambda: self._set_status(f"● 執行任務: {step_name}", "#8b5cf6"))

        def _on_step_change(idx, cycle, total):
            if idx >= 0:
                self.root.after(0, lambda: self.task_tab.highlight_active_step(idx))
            else:
                self.root.after(0, lambda: self.task_tab.highlight_active_step(-1))

        ok = self.task_tab.engine.run_sync(
            blocks_data=blocks_to_run,
            loop_count=1,
            on_step_change=_on_step_change,
            global_settings=self.task_tab.get_global_settings()
        )

        self.root.after(0, lambda: self.task_tab.highlight_active_step(-1))
        if self.bot.is_running:
            self.root.after(0, lambda: self._set_status("運作中 (RUNNING)", COLOR_RUNNING))

        return ok

    # ==========================================================================
    # 📸 即時截圖與畫面預覽 (Canvas Preview & Mouse Picking)
    # ==========================================================================
    def on_preview_and_detect(self):
        if self._capturing:
            return
        self._capturing = True
        self.btn_capture.configure(state="disabled")

        def work():
            screen = self.bot.capture_screen()
            def done():
                self._capturing = False
                self.btn_capture.configure(state="normal")
                if screen is not None:
                    self.current_screen_bgr = screen
                    self._render_preview(screen)
                if self.var_auto_refresh.get() and self.bot.device and not (self.bot.is_running or self.is_running):
                    if not self.auto_refresh_job:
                        self._schedule_next_refresh(self._get_preview_interval_ms())
            self.root.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def on_bot_frame_update(self, screen_bgr: np.ndarray, detected_items: list, matched=None):
        """當背景 bot 截取到新畫面時，由回呼推播至預覽與統計"""
        self.loop_count += 1
        if matched is not None:
            self.hit_count += 1
        if screen_bgr is not None:
            self.current_screen_bgr = screen_bgr
            self._render_preview(screen_bgr, matched=matched)

    def _render_preview(self, screen_bgr: np.ndarray, matched=None):
        if screen_bgr is None:
            return
        if getattr(self, "is_dragging", False):
            # 使用者正在畫面上拖曳框選中，不打斷目前畫布與座標
            return
        try:
            display_bgr = screen_bgr
            if matched is not None and isinstance(matched, (list, tuple)) and len(matched) >= 4:
                display_bgr = screen_bgr.copy()
                try:
                    tx, ty = int(matched[2]), int(matched[3])
                    cv2.circle(display_bgr, (tx, ty), 16, (0, 255, 0), 2)
                    cv2.drawMarker(display_bgr, (tx, ty), (0, 255, 0), cv2.MARKER_CROSS, 24, 2)
                except Exception:
                    pass

            h, w = display_bgr.shape[:2]
            self.raw_screen_w, self.raw_screen_h = w, h

            c_w = PREVIEW_CANVAS_W
            c_h = PREVIEW_CANVAS_H
            self.canvas_w = c_w
            self.canvas_h = c_h

            avail_w = PREVIEW_CANVAS_W
            avail_h = PREVIEW_CANVAS_H

            scale = min(avail_w / w, avail_h / h)
            self.preview_scale = scale
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            self.preview_img_w, self.preview_img_h = new_w, new_h

            resized = cv2.resize(display_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            self.preview_image_tk = ImageTk.PhotoImage(pil_img)

            cx = c_w // 2
            cy = c_h // 2
            if hasattr(self, "preview_canvas"):
                self.preview_canvas.delete("placeholder")
                if getattr(self, "preview_canvas_img_id", None) is None or not self.preview_canvas.find_withtag("bg_image"):
                    self.preview_canvas_img_id = self.preview_canvas.create_image(
                        cx, cy, image=self.preview_image_tk, anchor="center", tags="bg_image"
                    )
                else:
                    self.preview_canvas.coords("bg_image", cx, cy)
                    self.preview_canvas.itemconfig("bg_image", image=self.preview_image_tk)

                # 若使用者已框選，更新框線與標籤位置確保對齊
                if self.preview_crop_coords and not getattr(self, "is_dragging", False):
                    rx1, ry1, rx2, ry2 = self.preview_crop_coords
                    w_offset = max(0, (c_w - new_w) // 2)
                    h_offset = max(0, (c_h - new_h) // 2)
                    bx1 = int(rx1 * scale) + w_offset
                    by1 = int(ry1 * scale) + h_offset
                    bx2 = int(rx2 * scale) + w_offset
                    by2 = int(ry2 * scale) + h_offset
                    if self.preview_canvas.find_withtag("selection_box"):
                        self.preview_canvas.coords("selection_box", bx1, by1, bx2, by2)
                    else:
                        self.preview_canvas.create_rectangle(
                            bx1, by1, bx2, by2, outline="#F59E0B", width=2, dash=(4, 2), tags="selection_box"
                        )
                    if self.preview_canvas.find_withtag("selection_text"):
                        self.preview_canvas.coords("selection_text", bx1 + 4, max(14, by1 - 10))
                    else:
                        self.preview_canvas.create_text(
                            bx1 + 4, max(14, by1 - 10),
                            text=f"{rx2 - rx1}×{ry2 - ry1}",
                            fill="#FBBF24",
                            font=("Arial", 11, "bold"),
                            anchor="w",
                            tags="selection_text"
                        )

                self.preview_canvas.tag_raise("selection_box")
                self.preview_canvas.tag_raise("selection_text")
        except Exception:
            pass

    def _on_preview_resize(self, e=None):
        # 畫布尺寸已完全鎖定為 PREVIEW_CANVAS_W × PREVIEW_CANVAS_H，不隨視窗變更縮放
        pass

    def _on_preview_press(self, e):
        self.drag_start_x = max(0, min(PREVIEW_CANVAS_W, e.x))
        self.drag_start_y = max(0, min(PREVIEW_CANVAS_H, e.y))
        self.is_dragging = False
        self.preview_canvas.delete("selection_box")
        self.preview_canvas.delete("selection_text")
        self.preview_crop_coords = None
        if hasattr(self, "btn_crop_selection"):
            self.btn_crop_selection.configure(state="disabled", text="✂️ 裁切截圖", fg_color=COLOR_BTN_DARK)

    def _on_preview_drag(self, e):
        if not hasattr(self, "drag_start_x"):
            return
        cur_x = max(0, min(PREVIEW_CANVAS_W, e.x))
        cur_y = max(0, min(PREVIEW_CANVAS_H, e.y))
        dx = abs(cur_x - self.drag_start_x)
        dy = abs(cur_y - self.drag_start_y)
        if dx > 4 or dy > 4:
            self.is_dragging = True
            x1 = min(self.drag_start_x, cur_x)
            y1 = min(self.drag_start_y, cur_y)
            x2 = max(self.drag_start_x, cur_x)
            y2 = max(self.drag_start_y, cur_y)

            if self.preview_canvas.find_withtag("selection_box"):
                self.preview_canvas.coords("selection_box", x1, y1, x2, y2)
            else:
                self.preview_canvas.create_rectangle(
                    x1, y1, x2, y2,
                    outline="#F59E0B", width=2, dash=(4, 2), tags="selection_box"
                )

            rx1, ry1 = self._preview_to_real_clamped(x1, y1)
            rx2, ry2 = self._preview_to_real_clamped(x2, y2)
            rw = max(0, rx2 - rx1)
            rh = max(0, ry2 - ry1)

            tx = x1 + 4
            ty = max(14, y1 - 10)
            if self.preview_canvas.find_withtag("selection_text"):
                self.preview_canvas.coords("selection_text", tx, ty)
                self.preview_canvas.itemconfig("selection_text", text=f"{rw}×{rh}")
            else:
                self.preview_canvas.create_text(
                    tx, ty, text=f"{rw}×{rh}", fill="#FBBF24",
                    font=("Arial", 11, "bold"), anchor="w", tags="selection_text"
                )

            self.preview_canvas.tag_raise("selection_box")
            self.preview_canvas.tag_raise("selection_text")
            self.var_preview_coords.set(f"框選範圍: {rw}×{rh} (X:{rx1}~{rx2}, Y:{ry1}~{ry2})")

    def _on_preview_release(self, e):
        if getattr(self, "is_dragging", False):
            self.is_dragging = False
            cur_x = max(0, min(PREVIEW_CANVAS_W, e.x))
            cur_y = max(0, min(PREVIEW_CANVAS_H, e.y))
            x1 = min(self.drag_start_x, cur_x)
            y1 = min(self.drag_start_y, cur_y)
            x2 = max(self.drag_start_x, cur_x)
            y2 = max(self.drag_start_y, cur_y)
            rx1, ry1 = self._preview_to_real_clamped(x1, y1)
            rx2, ry2 = self._preview_to_real_clamped(x2, y2)
            rw = rx2 - rx1
            rh = ry2 - ry1
            if rw >= 8 and rh >= 8 and self.current_screen_bgr is not None:
                self.preview_crop_coords = (rx1, ry1, rx2, ry2)
                if hasattr(self, "btn_crop_selection"):
                    self.btn_crop_selection.configure(
                        state="normal",
                        text=f"✂️ 裁切截圖 ({rw}×{rh})",
                        fg_color="#10B981",
                        hover_color="#059669"
                    )
                self.var_preview_coords.set(f"已選取範圍: {rw}×{rh} (X:{rx1}~{rx2}, Y:{ry1}~{ry2})，請按【✂️ 裁切截圖】")
            else:
                self.preview_canvas.delete("selection_box")
                self.preview_canvas.delete("selection_text")
                self.preview_crop_coords = None
                if hasattr(self, "btn_crop_selection"):
                    self.btn_crop_selection.configure(state="disabled", text="✂️ 裁切截圖", fg_color=COLOR_BTN_DARK)
        else:
            # 單純點擊（無拖曳）：清空選取框並執行單點自訂座標填入
            self.preview_canvas.delete("selection_box")
            self.preview_canvas.delete("selection_text")
            self.preview_crop_coords = None
            if hasattr(self, "btn_crop_selection"):
                self.btn_crop_selection.configure(state="disabled", text="✂️ 裁切截圖", fg_color=COLOR_BTN_DARK)
            self._on_preview_click(e)

    def _on_preview_mouse_move(self, e):
        if not getattr(self, "is_dragging", False):
            rx, ry = self._preview_to_real(e.x, e.y)
            if rx is not None:
                if self.preview_crop_coords:
                    r1, r2, r3, r4 = self.preview_crop_coords
                    self.var_preview_coords.set(f"選取: {r3-r1}×{r4-r2} | 游標: ({rx}, {ry})")
                else:
                    self.var_preview_coords.set(f"X: {rx}, Y: {ry}")

    def _on_preview_mouse_leave(self, e):
        if not getattr(self, "is_dragging", False) and not self.preview_crop_coords:
            self.var_preview_coords.set("")

    def _on_preview_click(self, e):
        rx, ry = self._preview_to_real(e.x, e.y)
        if rx is not None:
            self.log_message(f"🎯 選取座標: ({rx}, {ry})")
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(f"{rx}, {ry}")
            except Exception:
                pass

            # 1. 檢查優先動作中展開的卡片
            for p in self.priority_steps_list:
                if p.get("expanded") and p["expanded"].get():
                    if p.get("repeat_enabled") and p["repeat_enabled"].get() and "自訂" in p.get("repeat_area", tk.StringVar()).get():
                        p["repeat_custom_x"].set(rx)
                        p["repeat_custom_y"].set(ry)
                        self.log_message(f"已填入優先動作 [{p['name'].get()}] 連點自訂座標: ({rx}, {ry})")
                        return
                    else:
                        p["custom_x"].set(rx)
                        p["custom_y"].set(ry)
                        p["action"].set(ACTION_CUSTOM_COORD)
                        self.log_message(f"已填入優先動作 [{p['name'].get()}] 點擊指定座標: ({rx}, {ry})")
                        return

            # 2. 檢查一般步驟中展開的卡片
            for s in self.steps_list:
                if s.get("expanded") and s["expanded"].get():
                    if s.get("repeat_enabled") and s["repeat_enabled"].get() and "自訂" in s.get("repeat_area", tk.StringVar()).get():
                        s["repeat_custom_x"].set(rx)
                        s["repeat_custom_y"].set(ry)
                        self.log_message(f"已填入步驟 [{s['name'].get()}] 連點自訂座標: ({rx}, {ry})")
                        return
                    else:
                        s["custom_x"].set(rx)
                        s["custom_y"].set(ry)
                        s["action"].set(ACTION_CUSTOM_COORD)
                        self.log_message(f"已填入步驟 [{s['name'].get()}] 點擊指定座標: ({rx}, {ry})")
                        return

            # 3. 若無任何卡片展開，預設填入最後一個一般步驟或優先動作
            if self.steps_list:
                last_s = self.steps_list[-1]
                last_s["custom_x"].set(rx)
                last_s["custom_y"].set(ry)
                last_s["action"].set(ACTION_CUSTOM_COORD)
                self.log_message(f"已填入步驟 [{last_s['name'].get()}] 點擊指定座標: ({rx}, {ry})")
            elif self.priority_steps_list:
                last_p = self.priority_steps_list[-1]
                last_p["custom_x"].set(rx)
                last_p["custom_y"].set(ry)
                last_p["action"].set(ACTION_CUSTOM_COORD)
                self.log_message(f"已填入優先動作 [{last_p['name'].get()}] 點擊指定座標: ({rx}, {ry})")

    def _preview_to_real(self, ex: int, ey: int) -> Tuple[Optional[int], Optional[int]]:
        if not self.raw_screen_w or not self.preview_scale:
            return None, None
        c_w = PREVIEW_CANVAS_W
        c_h = PREVIEW_CANVAS_H
        w_offset = max(0, (c_w - self.preview_img_w) // 2)
        h_offset = max(0, (c_h - self.preview_img_h) // 2)
        img_x = ex - w_offset
        img_y = ey - h_offset
        if 0 <= img_x <= self.preview_img_w and 0 <= img_y <= self.preview_img_h:
            rx = int(img_x / self.preview_scale)
            ry = int(img_y / self.preview_scale)
            return min(self.raw_screen_w, max(0, rx)), min(self.raw_screen_h, max(0, ry))
        return None, None

    def _preview_to_real_clamped(self, ex: int, ey: int) -> Tuple[int, int]:
        if not self.raw_screen_w or not self.preview_scale:
            return 0, 0
        c_w = PREVIEW_CANVAS_W
        c_h = PREVIEW_CANVAS_H
        w_offset = max(0, (c_w - self.preview_img_w) // 2)
        h_offset = max(0, (c_h - self.preview_img_h) // 2)
        img_x = ex - w_offset
        img_y = ey - h_offset
        rx = int(img_x / self.preview_scale)
        ry = int(img_y / self.preview_scale)
        return min(self.raw_screen_w, max(0, rx)), min(self.raw_screen_h, max(0, ry))

    def on_crop_preview_selection(self):
        """將在預覽畫布上框選的區域裁切儲存為模板圖片，詢問使用者儲存位置，並自動套用至當前步驟"""
        if self.current_screen_bgr is None or not self.preview_crop_coords:
            messagebox.showwarning("提示", "尚未在預覽畫面上框選任何區域！\n請先用滑鼠在遊戲畫面上按住並拖曳出框選矩形。", parent=self.root)
            return

        rx1, ry1, rx2, ry2 = self.preview_crop_coords
        crop_bgr = self.current_screen_bgr[ry1:ry2, rx1:rx2].copy()
        ch, cw = crop_bgr.shape[:2]
        if cw < 4 or ch < 4:
            messagebox.showwarning("提示", "框選範圍過小，請重新框選！", parent=self.root)
            return

        # 找出當前展開之步驟 (優先使用)
        active_step = None
        for p in getattr(self, "priority_steps_list", []):
            if p.get("expanded") and p["expanded"].get():
                active_step = p
                break
        if not active_step:
            for s in getattr(self, "steps_list", []):
                if s.get("expanded") and s["expanded"].get():
                    active_step = s
                    break

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if active_step:
            step_name = active_step["name"].get().strip()
            clean_name = "".join(c for c in step_name if c.isalnum() or c in ("_", "-")).strip()
            init_fname = f"{clean_name}.png" if clean_name else f"snip_{ts}.png"
        else:
            init_fname = f"template_{ts}.png"

        init_dir = self.storage_dir if (self.storage_dir and os.path.isdir(self.storage_dir)) else self.config_dir
        save_path = filedialog.asksaveasfilename(
            parent=self.root,
            title="✂️ 儲存圖片模板 (請選擇儲存位置與檔名)",
            initialdir=init_dir,
            initialfile=init_fname,
            defaultextension=".png",
            filetypes=[("PNG 圖片", "*.png"), ("所有檔案", "*.*")]
        )
        if not save_path:
            return

        try:
            success = imwrite_unicode(save_path, crop_bgr)
            if not success:
                messagebox.showerror("錯誤", f"無法寫入圖檔至:\n{save_path}\n請檢查是否有寫入權限或磁碟空間。", parent=self.root)
                return

            self.last_snipped_template = save_path
            fname = os.path.basename(save_path)

            # 若位於目前存檔目錄下，儲存檔名；否則儲存絕對路徑
            if self.storage_dir and os.path.commonpath([os.path.abspath(save_path), os.path.abspath(self.storage_dir)]) == os.path.abspath(self.storage_dir):
                tpl_ref = fname
            else:
                tpl_ref = os.path.abspath(save_path)

            applied_msg = ""
            target_step = active_step
            if not target_step and getattr(self, "steps_list", []):
                target_step = self.steps_list[0]

            if target_step:
                target_step["template_image"].set(tpl_ref)
                if "target_type" in target_step:
                    target_step["target_type"].set("🖼️ 圖片特徵 (模板比對)")
                applied_msg = f"\n\n已自動套用至步驟：「{target_step['name'].get()}」！"

            self.auto_save_current_config()
            self._refresh_all_step_thumbs()
            self.log_message(f"✂️ 截圖儲存成功: {save_path} ({cw}×{ch}){applied_msg.replace(chr(10), ' ')}")

            # 清除畫布選取標記與重置裁切按鈕
            self.preview_canvas.delete("selection_box")
            self.preview_canvas.delete("selection_text")
            self.preview_crop_coords = None
            if hasattr(self, "btn_crop_selection"):
                self.btn_crop_selection.configure(state="disabled", text="✂️ 裁切截圖", fg_color=COLOR_BTN_DARK)

            self.var_preview_coords.set(f"✅ 已成功截圖: {fname} ({cw}×{ch})")
            messagebox.showinfo("截圖成功", f"✅ 圖片模板已成功儲存至：\n{save_path}{applied_msg}", parent=self.root)
        except Exception as ex:
            self.log_message(f"❌ 截圖儲存失敗: {ex}")
            messagebox.showerror("截圖失敗", f"無法儲存截圖: {ex}", parent=self.root)

    def on_apply_last_snippet(self, step_or_p: dict):
        """將最近一次在預覽畫面上裁切的模板圖片直接載入至指定的步驟"""
        if not getattr(self, "last_snipped_template", None):
            messagebox.showinfo(
                "提示",
                "尚未在預覽畫面上裁切過任何圖片模板！\n\n使用方式：\n1. 在右側預覽畫面按住滑鼠左鍵拖曳框選目標按鈕\n2. 點擊【✂️ 裁切截圖】儲存模板\n3. 再點擊步驟上的【📥 帶入截圖】即可直接套用！",
                parent=self.root
            )
            return

        target_tpl = self.last_snipped_template
        step_or_p["template_image"].set(target_tpl)
        self.auto_save_current_config()
        self.log_message(f"📥 已成功將最新截圖「{target_tpl}」帶入至步驟「{step_or_p['name'].get()}」")

    def _get_preview_interval_ms(self) -> int:
        try:
            val_str = self.var_preview_interval.get().replace("秒", "").replace("s", "").strip()
            return max(300, int(float(val_str) * 1000))
        except Exception:
            return 1500

    def _on_preview_interval_change(self, val: str = None):
        interval_ms = self._get_preview_interval_ms()
        self.log_message(f"⏱ 預覽畫面自動刷新間隔已設定為: {self.var_preview_interval.get()}")
        if self.var_auto_refresh.get() and self.bot.device and not (self.bot.is_running or self.is_running):
            self._schedule_next_refresh(interval_ms)

    def on_toggle_auto_refresh(self):
        if self.var_auto_refresh.get():
            self._schedule_next_refresh(self._get_preview_interval_ms())
        else:
            if self.auto_refresh_job:
                self.root.after_cancel(self.auto_refresh_job)
                self.auto_refresh_job = None

    def _schedule_next_refresh(self, delay_ms: int = None):
        if delay_ms is None:
            delay_ms = self._get_preview_interval_ms()
        if self.auto_refresh_job:
            self.root.after_cancel(self.auto_refresh_job)
        self.auto_refresh_job = self.root.after(delay_ms, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        self.auto_refresh_job = None
        if self.bot.is_running or self.is_running:
            return
        if getattr(self, "is_dragging", False):
            # 使用者正在畫面上拖曳框選截圖，暫緩刷新避免畫面閃爍打斷操作
            self._schedule_next_refresh(600)
            return
        if self.var_auto_refresh.get() and self.bot.device:
            self.on_preview_and_detect()
            interval_ms = self._get_preview_interval_ms()
            self._schedule_next_refresh(interval_ms)

    # ==========================================================================
    # 📜 日誌終端輸出與跨執行緒佇列渲染
    # ==========================================================================
    def log_message(self, text: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{now}] {text}\n"
        self.log_queue.put(entry)

    def _process_log_queue(self):
        batch = []
        while not self.log_queue.empty():
            try:
                batch.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if batch and hasattr(self, "txt_log"):
            self.txt_log.configure(state="normal")
            for item in batch:
                self.txt_log.insert("end", item)
            if self.auto_scroll_logs:
                self.txt_log.see("end")
            self.txt_log.configure(state="disabled")
        self.root.after(50, self._process_log_queue)

    def on_clear_log(self):
        if hasattr(self, "txt_log"):
            self.txt_log.configure(state="normal")
            self.txt_log.delete("1.0", "end")
            self.txt_log.configure(state="disabled")

    def _toggle_auto_scroll(self):
        self.auto_scroll_logs = bool(self.sw_log_scroll.get())

    def _export_logs(self):
        content = self.txt_log.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("提示", "目前沒有任何日誌可匯出。")
            return
        path = filedialog.asksaveasfilename(
            title="儲存執行日誌",
            defaultextension=".log",
            filetypes=[("Log 檔案", "*.log"), ("文字檔案", "*.txt"), ("所有檔案", "*.*")]
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.log_message(f"💾 日誌成功儲存至: {os.path.basename(path)}")
                messagebox.showinfo("成功", f"日誌已成功儲存至:\n{path}")
            except Exception as e:
                messagebox.showerror("錯誤", f"無法儲存日誌檔案: {e}")

    # ==========================================================================
    # ⏱ 計時器與輔助功能
    # ==========================================================================
    def _update_uptime_timer(self):
        if self.is_running and self.start_time:
            self.total_uptime_seconds += 1
            hrs = self.total_uptime_seconds // 3600
            mins = (self.total_uptime_seconds % 3600) // 60
            secs = self.total_uptime_seconds % 60
            uptime_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
            if hasattr(self, "lbl_metrics_inline"):
                self.lbl_metrics_inline.configure(
                    text=f"⏱ 運行: {uptime_str}   |   🔄 輪次: {self.loop_count} 次   |   🎯 命中: {self.hit_count} 次"
                )
        self.root.after(1000, self._update_uptime_timer)

    def on_test_telegram_message(self):
        token = self.var_tg_token.get().strip()
        chat_id = self.var_tg_chat_id.get().strip()
        if not token or not chat_id:
            messagebox.showwarning("警告", "請先輸入 Telegram Token 與 Chat ID。")
            return
        self.log_message("正在發送 Telegram 測試通知...")
        threading.Thread(target=self._send_tg_worker, args=(token, chat_id), daemon=True).start()

    def _send_tg_worker(self, token, chat_id):
        import requests
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            resp = requests.post(url, json={"chat_id": chat_id, "text": "⚾ Auto9Innings 測試通知已成功送達！"}, timeout=10)
            if resp.status_code == 200:
                self.log_message("✅ Telegram 測試訊息發送成功！")
            else:
                self.log_message(f"❌ Telegram 發送失敗: {resp.text}")
        except Exception as e:
            self.log_message(f"❌ 發送 Telegram 異常: {e}")

    def on_run_diagnostics(self):
        self.log_message("正在執行診斷程式...")
        try:
            from diagnostics import run_diagnostics
            threading.Thread(target=run_diagnostics, args=(self.log_message,), daemon=True).start()
        except Exception as e:
            self.log_message(f"無法執行診斷: {e}")

    def on_open_new_window(self):
        new_win = ctk.CTkToplevel(self.root)
        BaseballBotGUI(new_win, instance_id=self.instance_id + 1)

    def on_close_window(self):
        self._do_auto_save_write()
        if hasattr(self, "task_tab") and self.task_tab:
            try:
                self.task_tab.auto_save_config()
            except Exception:
                pass
        if hasattr(self, "batting_tab") and self.batting_tab:
            try:
                self.batting_tab.on_close()
            except Exception:
                pass
        if hasattr(self, "task_tab") and self.task_tab:
            try:
                self.task_tab.engine.stop()
            except Exception:
                pass
        if self.is_running or self.bot.is_running:
            self.on_stop_bot()
        self.root.destroy()


# ==============================================================================
# 🚀 程式入口函式 (Main Entry Point)
# ==============================================================================
def main():
    root = ctk.CTk()
    app = BaseballBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
