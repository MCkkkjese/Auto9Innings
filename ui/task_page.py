"""
任務流程頁面 (TaskFlowPage)。

以積木組成任務流程：左側是積木工具庫與任務存檔，中間是程式區（優先辨識步驟
與一般流程步驟），右側是畫面預覽、座標選取與執行日誌。執行由
core.task_engine.TaskEngine 負責。
"""
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Optional, Dict, Any, List, Callable, Tuple

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk

from core import storage
from core.imaging import IMAGE_EXTENSIONS, imread_unicode
from core.task_engine import (
    BLOCK_TYPES, DAILY_PRESETS, TaskEngine,
    COLOR_BLOCK_ACTIVE, COLOR_BLOCK_BG, COLOR_BLOCK_BODY, COLOR_BLOCK_FG, COLOR_BLOCK_MUTED,
)
from core.textutil import safe_float as _safe_float, safe_int as _safe_int
from ui import widgets as W
from ui.dialogs import TemplateSnipperDialog, ask_insert_position, ask_save_config
from ui.theme import (
    COLOR_BG, COLOR_CARD, COLOR_CARD_BORDER, COLOR_CARD_ITEM, COLOR_INPUT_BG, COLOR_INPUT_BORDER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    COLOR_BTN_PRIMARY, COLOR_BTN_PRIMARY_HOVER, COLOR_BTN_START, COLOR_BTN_START_HOVER,
    COLOR_BTN_STOP, COLOR_BTN_STOP_HOVER, COLOR_BTN_DARK, COLOR_BTN_DARK_HOVER,
)
from ui import theme as T
import version

# 三欄的最小寬度：在視窗最小尺寸下，工具庫、程式區與預覽都能完整顯示
PALETTE_WIDTH = 236
PROGRAM_MIN_WIDTH = 560
PICKER_MIN_WIDTH = 300

# 積木工具庫按鈕上的簡短名稱（完整說明見 BLOCK_TYPES 的 title）
PALETTE_NAMES = {
    "tap_coord": "點擊座標",
    "multi_tap": "連續點擊",
    "detect_click": "偵測並點擊",
    "branch_if": "條件分支",
    "loop": "迴圈",
    "wait_condition": "等待條件",
    "wait_sec": "等待秒數",
    "swipe": "滑動",
    "back_key": "返回鍵",
    "comment": "備註",
    "send_telegram": "Telegram 通知",
}


class TaskFlowPage:
    """積木式任務流程的編輯與執行頁面。"""

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

        # 全域文字辨識停用開關 (純圖片 0-OCR 模式)
        init_disable_ocr = True
        if self.gui and hasattr(self.gui, "var_recognition_mode"):
            init_disable_ocr = ("圖片" in self.gui.var_recognition_mode.get())
        self.var_disable_ocr = tk.BooleanVar(value=init_disable_ocr)

        self._adv_open = False
        self.engine = TaskEngine(bot_instance=self.bot, log_callback=self._log, global_settings=self.get_global_settings())
        self.blocks_list: List[Dict[str, Any]] = []
        self.priority_blocks_list: List[Dict[str, Any]] = []
        self.selected_block_idx: int = -1
        self.selected_block_target: Optional[Dict[str, Any]] = None
        self._all_folded: bool = False
        self._priority_folded: bool = False
        self.frame_priority_section: Optional[ctk.CTkFrame] = None
        self.frame_priority_container: Optional[ctk.CTkFrame] = None
        self.frame_normal_section: Optional[ctk.CTkFrame] = None
        self.frame_normal_container: Optional[ctk.CTkFrame] = None
        self.lbl_prio_count = None
        self.lbl_prio_empty = None
        self.lbl_normal_count = None
        self.btn_prio_fold = None
        self.btn_all_fold = None

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

        def _on_disable_ocr_changed(*_):
            is_dis = bool(self.var_disable_ocr.get())
            if hasattr(self, "engine") and self.engine:
                self.engine.global_settings["disable_ocr"] = is_dis
                self.engine.global_settings["recognition_mode"] = "image" if is_dis else "ocr"
            if self.gui and hasattr(self.gui, "var_recognition_mode"):
                mode_target = "圖片特徵比對模式" if is_dis else "文字辨識模式"
                if self.gui.var_recognition_mode.get() != mode_target:
                    self.gui.var_recognition_mode.set(mode_target)
            self._update_ocr_mode_ui()
            self.auto_save_config()

        self.var_disable_ocr.trace_add("write", _on_disable_ocr_changed)

        if self.gui and hasattr(self.gui, "var_recognition_mode"):
            def _on_gui_rec_mode_changed(*_):
                is_img = ("圖片" in self.gui.var_recognition_mode.get())
                if self.var_disable_ocr.get() != is_img:
                    self.var_disable_ocr.set(is_img)
            self.gui.var_recognition_mode.trace_add("write", _on_gui_rec_mode_changed)

        self.var_loop_count = tk.IntVar(value=1)
        self.var_status_text = tk.StringVar(value="閒置中")
        self.var_auto_preview = tk.BooleanVar(value=True)
        self.var_preview_coords = tk.StringVar(value="")
        self.var_picked_coord = tk.StringVar(value="尚未選取座標")

        self.current_screen_bgr: Optional[np.ndarray] = None
        self.preview: Optional[W.PreviewPanel] = None
        self.log_panel: Optional[W.LogPanel] = None
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
        """解析圖片模板路徑（絕對路徑，或相對於存檔資料夾／專案資料夾）。"""
        if not p or not str(p).strip():
            return None
        dirs = [self.presets_dir, self.config_dir]
        if self.gui and getattr(self.gui, "storage_dir", ""):
            dirs.append(self.gui.storage_dir)
        return storage.resolve_image_path(str(p).strip(), dirs)

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
                "目前尚無畫面可用於截圖！\n請先確認模擬器已連線，並點擊右側「截圖」取得畫面。",
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
                existing = target_vp["template_image"].get().strip() if hasattr(target_vp["template_image"], "get") else ""
                if existing:
                    should_append = messagebox.askyesno(
                        "追加或替換",
                        f"目前已設定模板圖片：\n{existing}\n\n是否將新裁切截圖【追加】為多圖複選？\n\n點擊「是」：追加為多圖複選\n點擊「否」：替換現有圖片",
                        parent=self.parent
                    )
                    if should_append:
                        ex_list = TaskEngine.parse_template_images_list(existing)
                        if saved_path not in ex_list:
                            ex_list.append(saved_path)
                        target_vp["template_image"].set(", ".join(ex_list))
                    else:
                        target_vp["template_image"].set(saved_path)
                else:
                    target_vp["template_image"].set(saved_path)
            self.auto_save_config()
            self._log(f"已框選並儲存模板圖片: {saved_path}")

        try:
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
        """開啟檔案選擇器選擇本機圖片 (支援單選與多圖複選)"""
        init_dir = self.presets_dir
        if self.gui and hasattr(self.gui, "storage_dir") and self.gui.storage_dir:
            init_dir = self.gui.storage_dir
        selected = filedialog.askopenfilenames(
            parent=self.parent,
            title="選擇圖片模板 (可按住 Cmd/Shift 複選多張圖片)",
            initialdir=init_dir,
            filetypes=[("圖片檔案", "*.png *.jpg *.jpeg *.bmp"), ("所有檔案", "*.*")]
        )
        if not selected:
            return

        abs_files = [os.path.abspath(f) for f in selected]
        if not abs_files:
            return

        self.last_snipped_template = abs_files[-1]
        if self.gui and hasattr(self.gui, "last_snipped_template"):
            self.gui.last_snipped_template = abs_files[-1]

        if "template_image" in target_vp:
            existing = target_vp["template_image"].get().strip() if hasattr(target_vp["template_image"], "get") else ""
            if existing:
                should_append = messagebox.askyesno(
                    "選擇模式",
                    f"目前已設定模板圖片：\n{existing}\n\n是否將新選取的 {len(abs_files)} 張圖片【追加】為多圖複選？\n\n點擊「是」：追加為多圖複選\n點擊「否」：替換現有圖片",
                    parent=self.parent
                )
                if should_append:
                    ex_list = TaskEngine.parse_template_images_list(existing)
                    for f in abs_files:
                        if f not in ex_list:
                            ex_list.append(f)
                    target_vp["template_image"].set(", ".join(ex_list))
                else:
                    target_vp["template_image"].set(", ".join(abs_files))
            else:
                target_vp["template_image"].set(", ".join(abs_files))

        self.auto_save_config()
        self._log(f"已選取圖片模板: {', '.join([os.path.basename(f) for f in abs_files])}")

    def on_apply_last_snippet(self, target_vp: Dict[str, Any]):
        """帶入最新裁切的截圖 (支援追加複選)"""
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
            messagebox.showinfo("提示", "目前尚無任何截圖歷史記錄！\n請先點擊「截圖」框選畫面。", parent=self.parent)
            return

        self.last_snipped_template = target
        if "template_image" in target_vp:
            existing = target_vp["template_image"].get().strip() if hasattr(target_vp["template_image"], "get") else ""
            if existing:
                ex_list = TaskEngine.parse_template_images_list(existing)
                if target not in ex_list:
                    should_append = messagebox.askyesno(
                        "追加或替換",
                        f"目前已設定模板圖片：\n{existing}\n\n是否將最新截圖【追加】為多圖複選？\n\n點擊「是」：追加為多圖複選\n點擊「否」：替換現有圖片",
                        parent=self.parent
                    )
                    if should_append:
                        ex_list.append(target)
                        target_vp["template_image"].set(", ".join(ex_list))
                    else:
                        target_vp["template_image"].set(target)
                else:
                    pass
            else:
                target_vp["template_image"].set(target)
        self.auto_save_config()
        self._log(f"已成功帶入最新截圖: {target}")

    def _build_image_template_row(self, parent_frame, vp: Dict[str, Any], block_dict: Optional[Dict[str, Any]] = None) -> ctk.CTkFrame:
        """建立圖片特徵比對專用控制面板 (縮圖、路徑、截圖、瀏覽、帶入、門檻、多尺度)"""
        box = ctk.CTkFrame(parent_frame, fg_color="#181825", corner_radius=6, border_width=1, border_color="#334155")

        # 行 1: 縮圖 + 多圖計數標籤 + 門檻值滑桿 + 多尺度容錯
        row1 = ctk.CTkFrame(box, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=(4, 2))

        lbl_thumb = tk.Label(row1, bg="#11111B", fg=COLOR_TEXT_DIM, font=("Arial", 10), text="（未選圖）", width=8, height=2)
        lbl_thumb.pack(side="left", padx=(0, 4))

        lbl_count = ctk.CTkLabel(row1, text="", font=ctk.CTkFont(family="Arial", size=10, weight="bold"), text_color="#38BDF8")
        lbl_count.pack(side="left", padx=(0, 6))

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

        # 行 2: 圖片檔名/路徑輸入框 + 動作按鈕 (截圖 / 瀏覽 / 帶入最新截圖)
        row2 = ctk.CTkFrame(box, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=(2, 5))

        ctk.CTkLabel(row2, text="圖檔 (支援複選):", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))
        ent_img = ctk.CTkEntry(
            row2,
            textvariable=vp["template_image"],
            placeholder_text="可複選多張，以逗號分隔",
            height=24,
            corner_radius=4,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            font=ctk.CTkFont(size=10)
        )
        ent_img.pack(side="left", fill="x", expand=True, padx=(0, 6))

        init_name = block_dict["name"].get() if (block_dict and "name" in block_dict and hasattr(block_dict["name"], "get")) else "btn_task"

        btn_snip = ctk.CTkButton(
            row2,
            text="截圖",
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
            text="瀏覽",
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
            text="帶入最新截圖",
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
            try:
                img_val = vp["template_image"].get().strip() if "template_image" in vp and hasattr(vp["template_image"], "get") else ""
                if not img_val:
                    lbl_thumb.configure(image="", text="（未選圖）", fg=COLOR_TEXT_DIM, width=8, height=2)
                    lbl_thumb.image = None
                    lbl_count.configure(text="")
                    vp.pop("_thumb_img", None)
                    return

                img_list = TaskEngine.parse_template_images_list(img_val)
                if len(img_list) > 1:
                    lbl_count.configure(text=f"[{len(img_list)}張複選]")
                else:
                    lbl_count.configure(text="")

                first_p = self.resolve_image_path(img_list[0]) if img_list else None
                if first_p and os.path.exists(first_p):
                    try:
                        bgr = imread_unicode(first_p)
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
                lbl_thumb.configure(image="", text=f"{len(img_list)}張" if len(img_list) > 1 else "缺檔", fg="#EF4444", width=8, height=2)
                lbl_thumb.image = None
                vp.pop("_thumb_img", None)
            except Exception:
                pass

        vp["template_image"].trace_add("write", _update_thumb)
        vp["template_image"].trace_add("write", lambda *_: self.auto_save_config())
        self.parent.after(100, _update_thumb)

        return box

    def get_global_settings(self) -> Dict[str, Any]:
        dis_ocr = bool(self.var_disable_ocr.get()) if hasattr(self, "var_disable_ocr") else True
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
            "disable_ocr": dis_ocr,
            "recognition_mode": "image" if dis_ocr else "ocr",
        }

    def toggle_ocr_mode(self):
        new_val = not self.var_disable_ocr.get()
        self.var_disable_ocr.set(new_val)
        mode_str = "純圖片模式 (0-OCR / 極致節能 / 杜絕文字誤判)" if new_val else "文字 OCR 辨識模式"
        self._log(f"辨識模式已切換為：{mode_str}")

    def _update_ocr_mode_ui(self):
        is_dis = bool(self.var_disable_ocr.get()) if hasattr(self, "var_disable_ocr") else True
        if hasattr(self, "btn_ocr_mode") and self.btn_ocr_mode:
            if is_dis:
                self.btn_ocr_mode.configure(
                    text="純圖片 (0-OCR)",
                    fg_color="#059669",
                    hover_color="#047857"
                )
            else:
                self.btn_ocr_mode.configure(
                    text="文字 OCR",
                    fg_color="#3B82F6",
                    hover_color="#2563EB"
                )
        if hasattr(self, "lbl_lang_warning") and self.lbl_lang_warning:
            if is_dis:
                self.lbl_lang_warning.configure(text="（已啟用純圖片 0-OCR 模式，完全跳過文字辨識與語言掃描）", text_color="#10B981")
            else:
                self.lbl_lang_warning.configure(text="", text_color=COLOR_TEXT_DIM)

    def _log(self, msg: str):
        """寫入本頁的執行日誌，並同步到主日誌。可從任何執行緒呼叫。"""
        if self.log_panel is not None:
            self.log_panel.log(msg)
        if self.log_callback:
            try:
                self.log_callback(msg)
            except Exception:
                pass

    def _build_ui(self):
        container = ctk.CTkFrame(self.parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=4, pady=4)
        # 三欄：工具庫（固定寬度）／程式區／預覽與日誌。後兩欄隨視窗縮放並各有最小寬度。
        container.grid_columnconfigure(0, weight=0, minsize=PALETTE_WIDTH)
        container.grid_columnconfigure(1, weight=5, minsize=PROGRAM_MIN_WIDTH)
        container.grid_columnconfigure(2, weight=3, minsize=PICKER_MIN_WIDTH)
        container.grid_rowconfigure(0, weight=1)

        frame_palette = ctk.CTkFrame(container, fg_color="transparent", width=PALETTE_WIDTH)
        frame_palette.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)
        frame_palette.pack_propagate(False)

        frame_program = ctk.CTkFrame(container, fg_color="transparent")
        frame_program.grid(row=0, column=1, sticky="nsew", padx=(0, 6), pady=0)

        frame_picker = ctk.CTkFrame(container, fg_color="transparent")
        frame_picker.grid(row=0, column=2, sticky="nsew", padx=0, pady=0)

        self._build_palette_panel(frame_palette)
        self._build_program_panel(frame_program)
        self._build_picker_panel(frame_picker)

    def _build_palette_panel(self, parent):
        card_palette = W.card(parent)
        card_palette.pack(fill="x", pady=(0, 8))

        hdr_box = W.row(card_palette)
        hdr_box.pack(fill="x", padx=12, pady=(10, 4))
        W.label(hdr_box, "積木工具庫", size=13, bold=True).pack(side="left")
        W.label(hdr_box, "點擊加入程式區", size=10, color=COLOR_TEXT_DIM).pack(side="left", padx=6)

        # 雙欄排列，12 種積木一次完整顯示，不需捲動
        box_blocks = W.row(card_palette)
        box_blocks.pack(fill="x", padx=8, pady=(0, 10))
        box_blocks.grid_columnconfigure(0, weight=1, uniform="palette")
        box_blocks.grid_columnconfigure(1, weight=1, uniform="palette")
        self._palette_open = True

        def _toggle_palette():
            self._palette_open = not self._palette_open
            if self._palette_open:
                box_blocks.pack(fill="x", padx=8, pady=(0, 10))
                btn_fold.configure(text="▾")
            else:
                box_blocks.pack_forget()
                btn_fold.configure(text="▸")

        btn_fold = W.button(hdr_box, "▾", _toggle_palette, width=26, height=20, size=10)
        btn_fold.pack(side="right")

        items = [("優先辨識", "#D97706", "#B45309", self.on_add_priority_block)]
        for b_type, info in BLOCK_TYPES.items():
            items.append((PALETTE_NAMES.get(b_type, info["title"]), info["color"], info["color"],
                          lambda bt=b_type: self.on_add_block_interactive(bt)))
        for i, (text, color, hover, cmd) in enumerate(items):
            ctk.CTkButton(
                box_blocks, text=text, font=T.font(11, True), fg_color=color, hover_color=hover,
                height=30, width=60, corner_radius=6, command=cmd,
            ).grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)

        card_presets = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        card_presets.pack(fill="both", expand=True)

        tool_pre = ctk.CTkFrame(card_presets, fg_color="transparent")
        tool_pre.pack(fill="x", padx=12, pady=(10, 6))

        lbl_pre = ctk.CTkLabel(
            tool_pre,
            text="任務存檔",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY
        )
        lbl_pre.pack(side="left")

        btn_new_pre = ctk.CTkButton(
            tool_pre,
            text="存檔",
            width=48,
            height=24,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self.on_save_config_dialog
        )
        btn_new_pre.pack(side="right", padx=(3, 0))

        btn_load = ctk.CTkButton(
            tool_pre,
            text="載入",
            width=48,
            height=24,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_BTN_DARK,
            hover_color=COLOR_BTN_DARK_HOVER,
            command=self.on_load_config_dialog
        )
        btn_load.pack(side="right")
        W.button(tool_pre, "範本", self.on_load_preset_dialog, width=44, height=24, bold=False).pack(side="right", padx=(0, 3))

        self.frame_preset_buttons = ctk.CTkScrollableFrame(card_presets, fg_color="transparent", corner_radius=8)
        self.frame_preset_buttons.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def reload_presets(self):
        """掃描存檔資料夾，列出其中的任務存檔。"""
        DAILY_PRESETS.clear()
        self.presets = {}
        try:
            entries = sorted(os.listdir(self.presets_dir)) if os.path.exists(self.presets_dir) else []
        except Exception:
            entries = []
        for fname in entries:
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self.presets_dir, fname)
            key = os.path.splitext(fname)[0]
            try:
                data = storage.load_config(fpath)
                if not isinstance(data, dict):
                    continue
                if "blocks" not in data and "version" not in data and "loop_count" not in data:
                    continue
                # 循序腳本頁的自動存檔不含積木，不列為任務存檔
                if storage.is_autosave_file(fname) and "blocks" not in data:
                    continue
                preset_obj = {
                    "key": key,
                    "title": data.get("title") or data.get("name") or key,
                    "desc": data.get("desc", ""),
                    "blocks": data.get("blocks", []),
                    "priority_blocks": data.get("priority_blocks", []),
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
                text="尚無任務存檔\n點擊「存檔」或「載入」\n即可管理任務設定。",
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
        tb.pack(fill="x", padx=10, pady=(8, 4))
        self.bar_tb = tb

        # 兩列工具列都會自動換行，視窗變窄時按鈕不會被裁切
        row1 = W.FlowFrame(tb)
        row1.pack(fill="x", pady=(0, 4))
        self.btn_run = row1.add(W.button(row1, "啟動任務", self.on_run_tasks, kind="success", width=84))
        self.btn_step = row1.add(W.button(row1, "單步", self.on_step_task, kind="primary", width=56))
        self.btn_stop = row1.add(W.button(row1, "停止", self.on_stop_tasks, kind="danger", width=56, state="disabled"))
        loop_box = W.row(row1)
        W.label(loop_box, "循環").pack(side="left", padx=(6, 4))
        W.entry(loop_box, self.var_loop_count, width=40, height=26, font=T.mono(11)).pack(side="left")
        W.label(loop_box, "次", size=10, color=COLOR_TEXT_DIM).pack(side="left", padx=(3, 4))
        row1.add(loop_box)
        self.btn_adv = row1.add(W.button(row1, "進階設定 ▸", self._toggle_advanced, width=88, bold=False))
        self.btn_ocr_mode = row1.add(W.button(row1, "純圖片 (0-OCR)", self.toggle_ocr_mode, width=104), right=True)

        row2 = W.FlowFrame(tb)
        row2.pack(fill="x")
        self.btn_add_prio = row2.add(W.button(row2, "＋ 優先辨識", self.on_add_priority_block, kind="warning", width=88))
        self.btn_all_fold = row2.add(W.button(row2, "全部收合", self.toggle_all_fold, width=76, bold=False))
        row2.add(W.button(row2, "存檔", self.on_save_config_dialog, width=52, bold=False), right=True)
        row2.add(W.button(row2, "載入", self.on_load_config_dialog, width=52, bold=False), right=True)
        row2.add(W.button(row2, "清空", self.on_clear_blocks, kind="danger", width=52, bold=False), right=True)

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

        # 極速滑順滾動優化 (Mac/Windows 滾輪加速與 O(1) 座標檢測，杜絕卡頓)
        def _fast_check_if_valid_scroll(widget):
            try:
                if widget in (self.scroll_blocks, getattr(self.scroll_blocks, "_parent_canvas", None), getattr(self.scroll_blocks, "_parent_frame", None)):
                    return True
                rx = self.scroll_blocks.winfo_rootx()
                ry = self.scroll_blocks.winfo_rooty()
                rw = self.scroll_blocks.winfo_width()
                rh = self.scroll_blocks.winfo_height()
                px = self.scroll_blocks.winfo_pointerx()
                py = self.scroll_blocks.winfo_pointery()
                return (rx <= px <= rx + rw) and (ry <= py <= ry + rh)
            except Exception:
                return True

        def _fast_mouse_wheel_all(event):
            if not _fast_check_if_valid_scroll(event.widget):
                return
            canvas = getattr(self.scroll_blocks, "_parent_canvas", None)
            if not canvas:
                return
            try:
                if sys.platform.startswith("darwin"):
                    delta = event.delta
                    raw_step = -delta * 4.5
                    step = int(raw_step)
                    if step == 0 and delta != 0:
                        step = -1 if delta > 0 else 1
                    if step != 0:
                        canvas.yview_scroll(step, "units")
                elif sys.platform.startswith("win"):
                    step = -int(event.delta / 120 * 4)
                    canvas.yview_scroll(step, "units")
                else:
                    if event.num == 4:
                        canvas.yview_scroll(-3, "units")
                    elif event.num == 5:
                        canvas.yview_scroll(3, "units")
            except Exception:
                pass

        self.scroll_blocks._check_if_valid_scroll = _fast_check_if_valid_scroll
        self.scroll_blocks._mouse_wheel_all = _fast_mouse_wheel_all

        # --- 1. 優先辨識區塊 (Priority Section) ---
        self.frame_priority_section = ctk.CTkFrame(
            self.scroll_blocks,
            fg_color="#211d13",
            corner_radius=8,
            border_width=1,
            border_color="#F59E0B"
        )
        self.frame_priority_section.pack(fill="x", padx=4, pady=(2, 6))

        hdr_prio = ctk.CTkFrame(self.frame_priority_section, fg_color="#382907", corner_radius=6, height=32)
        hdr_prio.pack(fill="x", padx=4, pady=4)

        ctk.CTkLabel(
            hdr_prio,
            text="優先辨識區塊 (優先級大於下方所有步驟)",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            text_color="#FBBF24"
        ).pack(side="left", padx=(8, 4))

        self.lbl_prio_count = ctk.CTkLabel(
            hdr_prio,
            text="(0 個優先步驟)",
            font=ctk.CTkFont(family="Arial", size=11),
            text_color="#FDE68A"
        )
        self.lbl_prio_count.pack(side="left", padx=2)

        self.btn_prio_fold = ctk.CTkButton(
            hdr_prio,
            text="▾",
            width=24,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10),
            fg_color="#D97706",
            hover_color="#B45309",
            command=self.toggle_priority_section_fold
        )
        self.btn_prio_fold.pack(side="right", padx=(2, 4))

        btn_add_prio_inner = ctk.CTkButton(
            hdr_prio,
            text="＋新增優先步驟",
            width=100,
            height=22,
            corner_radius=4,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#F59E0B",
            hover_color="#D97706",
            text_color="#000000",
            command=self.on_add_priority_block
        )
        btn_add_prio_inner.pack(side="right", padx=(2, 4))

        self.frame_priority_container = ctk.CTkFrame(self.frame_priority_section, fg_color="transparent")
        self.frame_priority_container.pack(fill="x", padx=4, pady=(0, 4))

        self.lbl_prio_empty = ctk.CTkLabel(
            self.frame_priority_container,
            text="尚無優先辨識步驟。\n點擊上方「＋新增優先步驟」或將下方積木「設為優先」，\n在此區塊中的步驟將在每一步驟執行前、連點跳過中途及等待期間優先辨識並執行！",
            font=ctk.CTkFont(size=11),
            text_color="#A6ADC8",
            justify="center"
        )
        self.lbl_prio_empty.pack(fill="x", padx=12, pady=8)

        # --- 2. 一般流程步驟區塊 (Normal Section) ---
        self.frame_normal_section = ctk.CTkFrame(self.scroll_blocks, fg_color="transparent")
        self.frame_normal_section.pack(fill="both", expand=True, padx=0, pady=(2, 4))

        hdr_norm = ctk.CTkFrame(self.frame_normal_section, fg_color="#181825", corner_radius=6, height=28)
        hdr_norm.pack(fill="x", padx=4, pady=(2, 4))

        ctk.CTkLabel(
            hdr_norm,
            text="一般流程步驟 (依序循環執行)",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            text_color="#93C5FD"
        ).pack(side="left", padx=(8, 4))

        self.lbl_normal_count = ctk.CTkLabel(
            hdr_norm,
            text="(0 個步驟)",
            font=ctk.CTkFont(family="Arial", size=11),
            text_color="#94A3B8"
        )
        self.lbl_normal_count.pack(side="left", padx=2)

        self.frame_normal_container = ctk.CTkFrame(self.frame_normal_section, fg_color="transparent")
        self.frame_normal_container.pack(fill="both", expand=True, padx=0, pady=0)

        self.inner_blocks = self.frame_normal_container
        self.canvas_blocks = getattr(self.scroll_blocks, "_parent_canvas", self.scroll_blocks)

    def _build_advanced_panel(self, parent):
        f = ctk.CTkFrame(parent, fg_color=COLOR_CARD_ITEM, corner_radius=8, border_width=1, border_color=COLOR_CARD_BORDER)
        self.adv_frame = f

        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        lbl_title = ctk.CTkLabel(
            inner,
            text="進階設定（與模擬器腳本共用）",
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

        ctk.CTkLabel(inner, text="辨識模式:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).grid(row=4, column=0, sticky="w", pady=3)
        row_ocr_mode = ctk.CTkFrame(inner, fg_color="transparent")
        row_ocr_mode.grid(row=4, column=1, sticky="w", padx=6, pady=3)
        ctk.CTkCheckBox(
            row_ocr_mode,
            text="純圖片 0-OCR 模式 (關閉文字辨識 / 杜絕誤判)",
            variable=self.var_disable_ocr,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10B981",
            checkbox_width=16,
            checkbox_height=16
        ).pack(side="left")

        ctk.CTkLabel(inner, text="語言辨識:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).grid(row=5, column=0, sticky="w", pady=3)
        row_lang = ctk.CTkFrame(inner, fg_color="transparent")
        row_lang.grid(row=5, column=1, sticky="w", padx=6, pady=3)
        ctk.CTkCheckBox(row_lang, text="繁中", variable=self.var_lang_tc, font=ctk.CTkFont(size=11), width=56, checkbox_width=16, checkbox_height=16).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(row_lang, text="簡中", variable=self.var_lang_sc, font=ctk.CTkFont(size=11), width=56, checkbox_width=16, checkbox_height=16).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(row_lang, text="英文/數字", variable=self.var_lang_en, font=ctk.CTkFont(size=11), width=80, checkbox_width=16, checkbox_height=16).pack(side="left")

        self.lbl_lang_warning = ctk.CTkLabel(inner, text="", font=ctk.CTkFont(size=10), text_color="#10B981",
                                             anchor="w", justify="left")
        self.lbl_lang_warning.grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self._update_ocr_mode_ui()

        ctk.CTkLabel(inner, text="Telegram:", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED).grid(row=6, column=0, sticky="w", pady=3)
        row_tg = ctk.CTkFrame(inner, fg_color="transparent")
        row_tg.grid(row=6, column=1, sticky="w", padx=6, pady=3)

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
        self._log("正在發送 Telegram 測試通知...")
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
                custom_text="任務清單 Telegram 連線測試成功！",
                step_name="手動測試",
                screen_bgr=screen
            )
        else:
            success = self.engine._send_telegram_direct(tok, cid, "任務清單 Telegram 連線測試成功！", screen)

        if success:
            self._log("測試請求已送出，請檢查 Telegram 聊天室！")

    def _build_picker_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=3)
        parent.grid_rowconfigure(1, weight=0)
        parent.grid_rowconfigure(2, weight=2, minsize=120)

        def _on_fold(is_open: bool):
            parent.grid_rowconfigure(0, weight=3 if is_open else 0)

        self.preview = W.PreviewPanel(
            parent,
            placeholder="連線後按「截圖」，\n再點擊畫面即可選取座標",
            on_capture=self.on_capture_screen,
            on_click=self._on_preview_pick,
            coords_var=self.var_preview_coords,
            auto_var=self.var_auto_preview,
            on_auto_toggle=self.on_toggle_auto_refresh,
            coord_formatter=lambda x, y: f"{x}, {y}",
            enable_selection=False,
            on_fold=_on_fold,
            capture_text="截圖",
            min_canvas=(200, 112),
        )
        self.preview.grid(row=0, column=0, sticky="nsew", pady=(0, 4))
        self.btn_capture = self.preview.btn_capture

        coord_card = W.card(parent)
        coord_card.grid(row=1, column=0, sticky="ew", pady=4)
        ctk.CTkLabel(coord_card, textvariable=self.var_picked_coord, font=T.mono(11, True),
                     text_color="#38BDF8").pack(anchor="w", padx=12, pady=(8, 2))
        row_fill = W.row(coord_card)
        row_fill.pack(fill="x", padx=10, pady=(0, 8))
        W.button(row_fill, "複製", self.on_copy_picked_coord, width=50, height=26, bold=False).pack(side="right")
        W.button(row_fill, "填入選取的積木", self.on_fill_selected_block, kind="primary", height=26
                 ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.log_panel = W.LogPanel(parent, title="執行日誌", font_size=10)
        self.log_panel.grid(row=2, column=0, sticky="nsew", pady=(4, 0))

        if self.var_auto_preview.get():
            self._schedule_auto_refresh(delay_ms=800)

    def ask_block_insert_position(
        self,
        current_blocks: list,
        block_type_label: str = "任務積木",
        title: str = "新增積木 - 選擇插入位置"
    ) -> Optional[int]:
        """詢問新積木要插入清單的哪個位置（清單為空時直接回傳 0，取消回傳 None）。"""
        return ask_insert_position(self.parent, current_blocks, block_type_label, title)

    def add_block(
        self,
        b_type: str,
        params: Optional[Dict[str, Any]] = None,
        name: str = "",
        enabled: bool = True,
        parent_loop: Optional[Dict[str, Any]] = None,
        is_priority: bool = False,
        expanded: Optional[bool] = None,
        insert_index: Optional[int] = None
    ) -> Dict[str, Any]:
        info = BLOCK_TYPES.get(b_type, BLOCK_TYPES["tap_coord"])
        if params is None:
            params = dict(info["default_params"])
        if not name:
            pos_num = (insert_index + 1) if insert_index is not None else (
                (len(self.priority_blocks_list) + 1) if is_priority else
                (len(parent_loop.get('inner_blocks_list', [])) + 1 if parent_loop else len(self.blocks_list) + 1)
            )
            if is_priority:
                name = f"優先{info['default_name']} #{pos_num}"
            elif parent_loop:
                name = f"{info['default_name']} #{pos_num}"
            else:
                name = f"{info['default_name']} #{pos_num}"

        init_exp = True
        if expanded is not None:
            init_exp = bool(expanded)
        elif isinstance(params, dict) and "expanded" in params:
            init_exp = bool(params.get("expanded"))

        block_item = {
            "type": b_type,
            "name": tk.StringVar(value=name),
            "enabled": tk.BooleanVar(value=enabled),
            "params": params,
            "var_params": {},
            "frame": None,
            "expanded": tk.BooleanVar(value=init_exp),
            "parent_loop": parent_loop,
            "inner_blocks_list": [],
            "is_priority": is_priority
        }

        self._render_block_widget(block_item, parent_loop=parent_loop, is_priority=is_priority)

        if is_priority:
            if insert_index is not None and 0 <= insert_index <= len(self.priority_blocks_list):
                self.priority_blocks_list.insert(insert_index, block_item)
            else:
                self.priority_blocks_list.append(block_item)
        elif parent_loop:
            inner_list = parent_loop.setdefault("inner_blocks_list", [])
            if insert_index is not None and 0 <= insert_index <= len(inner_list):
                inner_list.insert(insert_index, block_item)
            else:
                inner_list.append(block_item)
        else:
            if insert_index is not None and 0 <= insert_index <= len(self.blocks_list):
                self.blocks_list.insert(insert_index, block_item)
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

        if parent_loop is None and not is_priority:
            if insert_index is None or insert_index >= len(self.blocks_list) - 1:
                self.parent.after(50, lambda: getattr(self.canvas_blocks, "yview_moveto", lambda *_: None)(1.0))

        return block_item

    def on_add_priority_block(self):
        """快捷加入優先辨識步驟"""
        insert_idx = self.ask_block_insert_position(
            current_blocks=self.priority_blocks_list,
            block_type_label="優先辨識步驟",
            title="新增優先步驟 - 選擇插入位置"
        )
        if insert_idx is None:
            return None
        return self.add_block(
            b_type="detect_click",
            name=f"優先辨識 #{insert_idx + 1}",
            is_priority=True,
            insert_index=insert_idx
        )

    def on_add_block_interactive(self, b_type: str):
        """從工具箱按鈕互動式加入積木（詢問插入位置）"""
        insert_idx = self.ask_block_insert_position(
            current_blocks=self.blocks_list,
            block_type_label="任務積木",
            title="新增積木 - 選擇插入位置"
        )
        if insert_idx is None:
            return None
        return self.add_block(b_type=b_type, insert_index=insert_idx)

    def promote_to_priority(self, block_item: Dict[str, Any]):
        """將一般步驟提升為優先辨識步驟"""
        if block_item not in self.blocks_list:
            return
        self.blocks_list.remove(block_item)
        self.priority_blocks_list.append(block_item)
        block_item["is_priority"] = True
        if block_item.get("frame"):
            block_item["frame"].destroy()
        self._render_block_widget(block_item, is_priority=True)
        self._renumber_blocks()
        self.auto_save_config()
        self._log(f"已將步驟 [{block_item['name'].get()}] 升級為【優先辨識】步驟！")

    def demote_to_normal(self, block_item: Dict[str, Any]):
        """將優先辨識步驟降級為一般流程步驟"""
        if block_item not in self.priority_blocks_list:
            return
        self.priority_blocks_list.remove(block_item)
        self.blocks_list.append(block_item)
        block_item["is_priority"] = False
        if block_item.get("frame"):
            block_item["frame"].destroy()
        self._render_block_widget(block_item, is_priority=False)
        self._renumber_blocks()
        self.auto_save_config()
        self._log(f"已將步驟 [{block_item['name'].get()}] 移回【一般流程步驟】。")

    def toggle_block_fold(self, block_item: Dict[str, Any]):
        """單一積木收合/展開切換"""
        body = block_item.get("body_frame")
        btn_fold = block_item.get("btn_fold")
        if not body:
            return
        is_now_expanded = bool(block_item["expanded"].get())
        new_expanded = not is_now_expanded
        block_item["expanded"].set(new_expanded)
        if new_expanded:
            body.pack(fill="x", padx=6, pady=(2, 6))
            if btn_fold:
                btn_fold.configure(text="▾")
        else:
            body.pack_forget()
            if btn_fold:
                btn_fold.configure(text="▸")

    def _set_block_fold(self, block_item: Dict[str, Any], is_expanded: bool):
        block_item["expanded"].set(is_expanded)
        body = block_item.get("body_frame")
        btn_fold = block_item.get("btn_fold")
        if body:
            if is_expanded:
                body.pack(fill="x", padx=6, pady=(2, 6))
                if btn_fold:
                    btn_fold.configure(text="▾")
            else:
                body.pack_forget()
                if btn_fold:
                    btn_fold.configure(text="▸")

    def toggle_all_fold(self):
        """全部積木收合/展開切換，解決多積木時滑動卡頓"""
        self._all_folded = not getattr(self, "_all_folded", False)
        new_state = not self._all_folded
        if hasattr(self, "btn_all_fold") and self.btn_all_fold:
            self.btn_all_fold.configure(text="全部展開" if self._all_folded else "全部收合")
        for b in self.priority_blocks_list:
            self._set_block_fold(b, new_state)
        for b in self.blocks_list:
            self._set_block_fold(b, new_state)
            for cb in b.get("inner_blocks_list", []):
                self._set_block_fold(cb, new_state)

    def toggle_priority_section_fold(self):
        """收合/展開優先辨識區塊"""
        self._priority_folded = not getattr(self, "_priority_folded", False)
        if self._priority_folded:
            self.frame_priority_container.pack_forget()
            if self.btn_prio_fold:
                self.btn_prio_fold.configure(text="▸")
        else:
            self.frame_priority_container.pack(fill="x", padx=4, pady=(0, 4))
            if self.btn_prio_fold:
                self.btn_prio_fold.configure(text="▾")

    def add_inner_block(self, loop_item: Dict[str, Any], b_type: str, params: Optional[Dict[str, Any]] = None, name: str = ""):
        in_list = loop_item.get("inner_blocks_list", [])
        insert_idx = self.ask_block_insert_position(
            current_blocks=in_list,
            block_type_label="迴圈內部積木",
            title="新增迴圈積木 - 選擇插入位置"
        )
        if insert_idx is None:
            return None
        return self.add_block(b_type=b_type, params=params, name=name, parent_loop=loop_item, insert_index=insert_idx)

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

    def _render_block_widget(
        self,
        block_item: Dict[str, Any],
        parent_loop: Optional[Dict[str, Any]] = None,
        is_priority: bool = False
    ):
        b_type = block_item["type"]
        info = BLOCK_TYPES.get(b_type, BLOCK_TYPES["tap_coord"])

        if is_priority:
            target_parent = self.frame_priority_container
            card_border_color = "#F59E0B"
            hdr_bg_color = "#D97706"
            badge_text = f"[優先·{info['badge']}]"
        elif parent_loop and "inner_container" in parent_loop:
            target_parent = parent_loop["inner_container"]
            card_border_color = info["color"]
            hdr_bg_color = info["color"]
            badge_text = f"[{info['badge']}]"
        else:
            target_parent = self.frame_normal_container
            card_border_color = info["color"]
            hdr_bg_color = info["color"]
            badge_text = f"[{info['badge']}]"

        card = ctk.CTkFrame(
            target_parent,
            fg_color=COLOR_CARD_ITEM,
            corner_radius=8,
            border_width=1,
            border_color=card_border_color
        )
        card.pack(fill="x", padx=4, pady=2 if is_priority else 3)
        block_item["frame"] = card

        hdr = ctk.CTkFrame(card, fg_color=hdr_bg_color, corner_radius=6, height=32)
        hdr.pack(fill="x", padx=2, pady=2)
        block_item["hdr_frame"] = hdr

        lbl_drag = ctk.CTkLabel(
            hdr,
            text=" ☰ ",
            font=ctk.CTkFont(family="Arial", size=12, weight="bold"),
            text_color="#FFFFFF",
            cursor="fleur"
        )
        lbl_drag.pack(side="left", padx=(2, 0))
        self._bind_drag(lbl_drag, block_item)

        btn_fold = ctk.CTkButton(
            hdr,
            text="▾" if block_item.get("expanded", tk.BooleanVar(value=True)).get() else "▸",
            width=20,
            height=20,
            corner_radius=3,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent",
            hover_color="#181825",
            text_color="#FFFFFF",
            command=lambda: self.toggle_block_fold(block_item)
        )
        btn_fold.pack(side="left", padx=(0, 2))
        block_item["btn_fold"] = btn_fold

        chk_en = ctk.CTkCheckBox(
            hdr,
            text="",
            variable=block_item["enabled"],
            width=20,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=4,
            fg_color="#10B981",
            hover_color="#059669",
            command=self.auto_save_config
        )
        chk_en.pack(side="left", padx=(0, 2))

        lbl_num = ctk.CTkLabel(
            hdr,
            text="#0" if is_priority else "#0",
            font=ctk.CTkFont(family="Arial", size=11, weight="bold"),
            text_color="#FFFFFF"
        )
        lbl_num.pack(side="left", padx=2)
        block_item["lbl_num"] = lbl_num

        ent_name = ctk.CTkEntry(
            hdr,
            textvariable=block_item["name"],
            width=100,
            height=24,
            corner_radius=4,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11)
        )
        ent_name.pack(side="left", padx=3)

        lbl_type = ctk.CTkLabel(
            hdr,
            text=badge_text,
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

        if is_priority:
            btn_prio_tog = ctk.CTkButton(
                hdr,
                text="移至一般",
                width=68,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#3B82F6",
                hover_color="#2563EB",
                text_color="#FFFFFF",
                command=lambda: self.demote_to_normal(block_item)
            )
            btn_prio_tog.pack(side="right", padx=1)
        elif not parent_loop:
            btn_prio_tog = ctk.CTkButton(
                hdr,
                text="設為優先",
                width=68,
                height=22,
                corner_radius=4,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#D97706",
                hover_color="#B45309",
                text_color="#FFFFFF",
                command=lambda: self.promote_to_priority(block_item)
            )
            btn_prio_tog.pack(side="right", padx=1)
        else:
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
            fg_color="#F59E0B" if not is_priority else "#10B981",
            hover_color="#D97706" if not is_priority else "#059669",
            text_color="#000000",
            command=lambda: self.select_block(block_item)
        )
        btn_pick.pack(side="right", padx=(1, 4))

        body = ctk.CTkFrame(card, fg_color="transparent")
        if block_item.get("expanded", tk.BooleanVar(value=True)).get():
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
            vp["target_type"] = tk.StringVar(value=p.get("target_type", "僅文字"))
            vp["keywords"] = tk.StringVar(value=p.get("keywords", "確認, 確定"))
            vp["template_image"] = tk.StringVar(value=p.get("template_image", ""))
            vp["image_threshold"] = tk.DoubleVar(value=_safe_float(p.get("image_threshold", 0.80), 0.80))
            vp["image_multiscale"] = tk.BooleanVar(value=bool(p.get("image_multiscale", False)))
            vp["timeout"] = tk.IntVar(value=_safe_int(p.get("timeout", 10)))

            raw_mode = p.get("click_mode", "點擊目標中心")
            if raw_mode in ("click_text", "click_target", "點擊目標中心", "點擊目標圖片 (按鈕中心)", "點擊目標文字 (詞條中心)"):
                init_act = "點擊目標中心"
            elif raw_mode in ("custom_coord", "自訂座標", "點擊指定座標 (自訂)"):
                init_act = "點擊自訂座標"
            elif raw_mode in ("custom_block", "自訂特定區塊", "自訂特定區塊"):
                init_act = "自訂特定區塊"
            elif raw_mode in ("wait_only", "無動作", "無動作(僅等待)", "無動作(僅等待)"):
                init_act = "無動作(僅等待)"
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
                values=["僅文字", "圖片特徵 (模板比對)", "✓ 打勾圖案", "✕ 叉叉/關閉", "文字或圖案"],
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
            ctk.CTkLabel(row2, text="秒 (0=無限)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(row2, text="動作:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left")
            ACTION_MODES = ["點擊目標中心", "點擊自訂座標", "自訂特定區塊", "無動作(僅等待)"]
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

            # 行 3: 命中後連點（過場跳過）勾選框
            row_rep = ctk.CTkFrame(body, fg_color="transparent")
            row_rep.pack(fill="x", pady=(3, 1))
            ctk.CTkCheckBox(
                row_rep,
                text="命中後連點（過場跳過）",
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

            vp["timeout"] = tk.IntVar(value=_safe_int(p.get("timeout", 8), 8))
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
            ctk.CTkLabel(row_ctrl, text="s(0=∞) 延遲:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(2, 0))
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
                        row, text="截", width=24, height=22, corner_radius=4, font=ctk.CTkFont(size=10),
                        fg_color="#0284C7", hover_color="#0369A1",
                        command=lambda b_ref=br: self.on_snip_template_dialog(b_ref, initial_name=f"branch_{b_ref['name']}")
                    )
                    btn_br_snip.pack(side="left", padx=1)

                    btn_br_browse = ctk.CTkButton(
                        row, text="選", width=24, height=22, corner_radius=4, font=ctk.CTkFont(size=10),
                        fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER,
                        command=lambda b_ref=br: self.on_browse_template_dialog(b_ref)
                    )
                    btn_br_browse.pack(side="left", padx=1)

                    btn_br_apply = ctk.CTkButton(
                        row, text="入", width=24, height=22, corner_radius=4, font=ctk.CTkFont(size=10),
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

            # 複數停止條件清單
            raw_stop_conds = p.get("stop_conditions", [])
            vp["stop_conditions"] = []
            for sc_idx, sc_data in enumerate(raw_stop_conds):
                m_var = tk.StringVar(value=sc_data.get("mode", sc_data.get("stop_mode", "偵測到圖片出現")))
                k_var = tk.StringVar(value=sc_data.get("keywords", sc_data.get("stop_keywords", "")))
                t_var = tk.StringVar(value=sc_data.get("template_image", ""))
                th_var = tk.DoubleVar(value=_safe_float(sc_data.get("threshold", sc_data.get("image_threshold", 0.80)), 0.80))
                ms_var = tk.BooleanVar(value=bool(sc_data.get("multiscale", sc_data.get("image_multiscale", False))))
                en_var = tk.BooleanVar(value=bool(sc_data.get("enabled", True)))
                for v in (m_var, k_var, t_var, th_var, ms_var, en_var):
                    v.trace_add("write", lambda *_: self.auto_save_config())
                vp["stop_conditions"].append({
                    "name": sc_data.get("name", f"條件 #{sc_idx + 1}"),
                    "mode": m_var,
                    "keywords": k_var,
                    "template_image": t_var,
                    "threshold": th_var,
                    "multiscale": ms_var,
                    "enabled": en_var
                })

            for k in ("stop_mode", "count", "keywords", "template_image", "image_threshold", "image_multiscale", "check_timing", "delay_after"):
                vp[k].trace_add("write", lambda *_: self.auto_save_config())

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
                "偵測到叉叉圖案",
                "文字或圖案 (任一出現)",
                "文字或圖案 (任一消失)",
                "複數條件 (多條件任一達成)"
            ]
            cbo_mode = ctk.CTkComboBox(row_loop_ctrl, variable=vp["stop_mode"], values=LOOP_MODES, width=170, height=26, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly")
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

            # 檢查時機控制列 (獨立顯示，支援所有條件模式，絕不被圖片模式隱藏)
            row_timing = ctk.CTkFrame(box_loop_header, fg_color="transparent")
            ctk.CTkLabel(row_timing, text="檢查時機:", font=ctk.CTkFont(size=10, weight="bold"), text_color="#A5B4FC").pack(side="left")
            TIMINGS = [
                "每輪開始與結束",
                "每輪開始前 (While)",
                "每輪結束後 (Do-While)",
                "每個子步驟後"
            ]
            cbo_timing = ctk.CTkComboBox(row_timing, variable=vp["check_timing"], values=TIMINGS, width=145, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER, state="readonly")
            cbo_timing.pack(side="left", padx=4)
            lbl_timing_hint = ctk.CTkLabel(row_timing, text="(每輪開始前/結束後檢測，或每執行一個子步驟立即判斷停止)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM)
            lbl_timing_hint.pack(side="left", padx=4)

            # 單一條件關鍵字列
            row_kw = ctk.CTkFrame(box_loop_header, fg_color="transparent")
            lbl_kw_title = ctk.CTkLabel(row_kw, text="停止關鍵字:", font=ctk.CTkFont(size=10, weight="bold"), text_color="#C4B5FD")
            lbl_kw_title.pack(side="left")
            ent_kw = ctk.CTkEntry(row_kw, textvariable=vp["keywords"], placeholder_text="多詞以逗號分隔", width=180, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)
            ent_kw.pack(side="left", padx=(4, 6))

            # 單一條件圖片列
            box_loop_img = self._build_image_template_row(box_loop_header, vp, block_dict=block)

            # 複數條件控制區塊
            box_multi_cond = ctk.CTkFrame(box_loop_header, fg_color="transparent")

            row_multi_hdr = ctk.CTkFrame(box_multi_cond, fg_color="transparent")
            row_multi_hdr.pack(fill="x", pady=(2, 2))

            ctk.CTkLabel(row_multi_hdr, text="複數停止條件 (任一條件達成即停止迴圈):", font=ctk.CTkFont(size=11, weight="bold"), text_color="#A78BFA").pack(side="left")

            btn_add_cond = ctk.CTkButton(
                row_multi_hdr,
                text="＋ 新增停止條件",
                width=110,
                height=24,
                corner_radius=4,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#6366F1",
                hover_color="#4F46E5",
                command=lambda: _add_stop_cond()
            )
            btn_add_cond.pack(side="left", padx=(8, 4))

            box_cond_rows = ctk.CTkFrame(box_multi_cond, fg_color="transparent")
            box_cond_rows.pack(fill="x")

            def _render_stop_cond_rows():
                for widget in box_cond_rows.winfo_children():
                    widget.destroy()

                COND_ROW_MODES = [
                    "偵測到文字出現",
                    "偵測到文字消失",
                    "偵測到圖片出現",
                    "偵測到圖片消失",
                    "偵測到打勾圖案",
                    "偵測到叉叉圖案",
                    "文字或圖案 (任一出現)",
                    "文字或圖案 (任一消失)"
                ]

                for idx, cond in enumerate(vp["stop_conditions"]):
                    c_num = idx + 1
                    cond["name"] = f"條件 #{c_num}"

                    row = ctk.CTkFrame(box_cond_rows, fg_color=COLOR_CARD_ITEM, corner_radius=6, border_width=1, border_color="#313244")
                    row.pack(fill="x", pady=2, ipady=1)

                    lbl_badge = ctk.CTkLabel(
                        row,
                        text=f" 條件 #{c_num} ",
                        fg_color="#6366F1",
                        corner_radius=4,
                        text_color="#FFFFFF",
                        font=ctk.CTkFont(size=10, weight="bold"),
                        width=60
                    )
                    lbl_badge.pack(side="left", padx=(4, 4), pady=2)

                    cbo_c_mode = ctk.CTkComboBox(
                        row,
                        variable=cond["mode"],
                        values=COND_ROW_MODES,
                        width=120,
                        height=24,
                        corner_radius=4,
                        fg_color=COLOR_INPUT_BG,
                        border_color=COLOR_INPUT_BORDER,
                        state="readonly"
                    )
                    cbo_c_mode.pack(side="left", padx=2)

                    sub_f = ctk.CTkFrame(row, fg_color="transparent")
                    sub_f.pack(side="left", fill="x", expand=True, padx=2)

                    lbl_c_kw = ctk.CTkLabel(sub_f, text="文字:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED)
                    ent_c_kw = ctk.CTkEntry(sub_f, textvariable=cond["keywords"], width=85, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)

                    lbl_c_img = ctk.CTkLabel(sub_f, text="圖檔:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED)
                    ent_c_img = ctk.CTkEntry(sub_f, textvariable=cond["template_image"], placeholder_text="可複選多圖", width=90, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)

                    btn_c_snip = ctk.CTkButton(
                        sub_f, text="截", width=24, height=22, corner_radius=4, font=ctk.CTkFont(size=10),
                        fg_color="#0284C7", hover_color="#0369A1",
                        command=lambda c_ref=cond: self.on_snip_template_dialog(c_ref, initial_name=f"loop_cond_{c_ref['name']}")
                    )
                    btn_c_browse = ctk.CTkButton(
                        sub_f, text="選", width=24, height=22, corner_radius=4, font=ctk.CTkFont(size=10),
                        fg_color=COLOR_BTN_DARK, hover_color=COLOR_BTN_DARK_HOVER,
                        command=lambda c_ref=cond: self.on_browse_template_dialog(c_ref)
                    )
                    btn_c_apply = ctk.CTkButton(
                        sub_f, text="入", width=24, height=22, corner_radius=4, font=ctk.CTkFont(size=10),
                        fg_color="#F59E0B", hover_color="#D97706",
                        command=lambda c_ref=cond: self.on_apply_last_snippet(c_ref)
                    )

                    lbl_c_th = ctk.CTkLabel(row, text="門檻:", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED)
                    ent_c_th = ctk.CTkEntry(row, textvariable=cond["threshold"], width=38, height=24, corner_radius=4, fg_color=COLOR_INPUT_BG, border_color=COLOR_INPUT_BORDER)

                    def _update_row_fields(*_, m_var=cond["mode"], sf=sub_f, l_kw=lbl_c_kw, e_kw=ent_c_kw, l_im=lbl_c_img, e_im=ent_c_img, b_sn=btn_c_snip, b_br=btn_c_browse, b_ap=btn_c_apply, l_th=lbl_c_th, e_th=ent_c_th):
                        cur_m = m_var.get()
                        for w in sf.winfo_children():
                            w.pack_forget()
                        if "文字或圖案" in cur_m or "文字或圖片" in cur_m:
                            l_kw.pack(side="left", padx=1)
                            e_kw.pack(side="left", padx=1)
                            l_im.pack(side="left", padx=(2, 1))
                            e_im.pack(side="left", padx=1, fill="x", expand=True)
                            b_sn.pack(side="left", padx=1)
                            b_br.pack(side="left", padx=1)
                            b_ap.pack(side="left", padx=1)
                            l_th.pack(side="left", padx=1)
                            e_th.pack(side="left", padx=1)
                        elif "圖片" in cur_m:
                            l_im.pack(side="left", padx=1)
                            e_im.pack(side="left", padx=1, fill="x", expand=True)
                            b_sn.pack(side="left", padx=1)
                            b_br.pack(side="left", padx=1)
                            b_ap.pack(side="left", padx=1)
                            l_th.pack(side="left", padx=1)
                            e_th.pack(side="left", padx=1)
                        elif "打勾" in cur_m or "叉叉" in cur_m:
                            l_th.pack_forget()
                            e_th.pack_forget()
                        else:  # 文字
                            l_kw.pack(side="left", padx=1)
                            e_kw.pack(side="left", padx=1, fill="x", expand=True)
                            l_th.pack_forget()
                            e_th.pack_forget()

                    cond["mode"].trace_add("write", _update_row_fields)
                    _update_row_fields()

                    btn_del_c = ctk.CTkButton(
                        row, text="✕", width=22, height=22, corner_radius=4,
                        font=ctk.CTkFont(size=10, weight="bold"),
                        fg_color="#EF4444", hover_color="#DC2626",
                        command=lambda target_idx=idx: _remove_stop_cond(target_idx)
                    )
                    btn_del_c.pack(side="right", padx=(2, 4))

            def _add_stop_cond(init_dict=None):
                c_num = len(vp["stop_conditions"]) + 1
                c_data = init_dict or {}
                m_var = tk.StringVar(value=c_data.get("mode", "偵測到圖片出現"))
                k_var = tk.StringVar(value=c_data.get("keywords", ""))
                t_var = tk.StringVar(value=c_data.get("template_image", ""))
                th_var = tk.DoubleVar(value=_safe_float(c_data.get("threshold", 0.80), 0.80))
                ms_var = tk.BooleanVar(value=bool(c_data.get("multiscale", False)))
                en_var = tk.BooleanVar(value=bool(c_data.get("enabled", True)))
                for v in (m_var, k_var, t_var, th_var, ms_var, en_var):
                    v.trace_add("write", lambda *_: self.auto_save_config())
                vp["stop_conditions"].append({
                    "name": f"條件 #{c_num}",
                    "mode": m_var,
                    "keywords": k_var,
                    "template_image": t_var,
                    "threshold": th_var,
                    "multiscale": ms_var,
                    "enabled": en_var
                })
                _render_stop_cond_rows()
                self.auto_save_config()

            def _remove_stop_cond(target_idx):
                if 0 <= target_idx < len(vp["stop_conditions"]):
                    vp["stop_conditions"].pop(target_idx)
                    _render_stop_cond_rows()
                    self.auto_save_config()

            def _on_loop_mode_change(*_):
                mode = vp["stop_mode"].get()
                if mode == "依指定次數":
                    row_timing.pack_forget()
                    row_kw.pack_forget()
                    box_loop_img.pack_forget()
                    box_multi_cond.pack_forget()
                    lbl_cnt_title.configure(text="重複次數:")
                    lbl_cnt_hint.configure(text="次(0=無限)")
                elif "複數條件" in mode or "多條件" in mode:
                    row_timing.pack(fill="x", pady=(2, 2))
                    row_kw.pack_forget()
                    box_loop_img.pack_forget()
                    box_multi_cond.pack(fill="x", pady=(3, 2))
                    lbl_cnt_title.configure(text="上限次數:")
                    lbl_cnt_hint.configure(text="次(0=不限)")
                    if not vp["stop_conditions"]:
                        _add_stop_cond()
                    else:
                        _render_stop_cond_rows()
                elif "文字或圖案" in mode or "文字或圖片" in mode:
                    row_timing.pack(fill="x", pady=(2, 2))
                    box_multi_cond.pack_forget()
                    row_kw.pack(fill="x", pady=(2, 2))
                    box_loop_img.pack(fill="x", pady=(2, 2))
                    ent_kw.configure(state="normal")
                    lbl_cnt_title.configure(text="上限次數:")
                    lbl_cnt_hint.configure(text="次(0=不限)")
                elif "圖片" in mode:
                    row_timing.pack(fill="x", pady=(2, 2))
                    box_multi_cond.pack_forget()
                    row_kw.pack_forget()
                    box_loop_img.pack(fill="x", pady=(2, 2))
                    lbl_cnt_title.configure(text="上限次數:")
                    lbl_cnt_hint.configure(text="次(0=不限)")
                elif "打勾" in mode or "叉叉" in mode:
                    row_timing.pack(fill="x", pady=(2, 2))
                    box_multi_cond.pack_forget()
                    box_loop_img.pack_forget()
                    row_kw.pack_forget()
                    lbl_cnt_title.configure(text="上限次數:")
                    lbl_cnt_hint.configure(text="次(0=不限)")
                else:  # 文字出現 / 文字消失
                    row_timing.pack(fill="x", pady=(2, 2))
                    box_multi_cond.pack_forget()
                    box_loop_img.pack_forget()
                    row_kw.pack(fill="x", pady=(2, 2))
                    ent_kw.configure(state="normal")
                    lbl_cnt_title.configure(text="上限次數:")
                    lbl_cnt_hint.configure(text="次(0=不限)")

            vp["stop_mode"].trace_add("write", _on_loop_mode_change)
            _on_loop_mode_change()

            tb_inner = ctk.CTkFrame(body, fg_color=COLOR_CARD_ITEM, corner_radius=6, border_width=1, border_color="#313244")
            tb_inner.pack(fill="x", pady=(2, 4))

            ctk.CTkLabel(tb_inner, text="加入積木:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left", padx=(6, 4), pady=2)

            TYPE_LABELS = {
                "tap_coord": "點擊座標",
                "multi_tap": "連續點擊",
                "detect_click": "偵測點擊",
                "branch_if": "條件分支",
                "wait_condition": "等待條件",
                "wait_sec": "等待延遲",
                "swipe": "↔ 滑動手勢",
                "back_key": "返回鍵",
                "send_telegram": "Telegram 通知",
                "comment": "備註說明",
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
            vp["target_type"] = tk.StringVar(value=p.get("target_type", "僅文字"))
            vp["keywords"] = tk.StringVar(value=p.get("keywords", "確認, 確定"))
            vp["template_image"] = tk.StringVar(value=p.get("template_image", ""))
            vp["image_threshold"] = tk.DoubleVar(value=_safe_float(p.get("image_threshold", 0.80), 0.80))
            vp["image_multiscale"] = tk.BooleanVar(value=bool(p.get("image_multiscale", False)))
            vp["interval"] = tk.DoubleVar(value=_safe_float(p.get("interval", 1.0)))
            vp["timeout"] = tk.IntVar(value=_safe_int(p.get("timeout", 30)))
            vp["delay_after"] = tk.DoubleVar(value=_safe_float(p.get("delay_after", 0.5)))
            vp["delay"] = tk.DoubleVar(value=_safe_float(p.get("delay", p.get("delay_after", 0.5))))
            vp["on_timeout"] = tk.StringVar(value=p.get("on_timeout", "continue"))

            vp["click_mode"] = tk.StringVar(value=p.get("click_mode", "點擊目標中心"))
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
                values=["僅文字", "圖片特徵 (模板比對)", "✓ 打勾圖案", "✕ 叉叉/關閉", "文字或圖案"],
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
            ctk.CTkLabel(row2, text="s (0=無限)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(row2, text="動作:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_PRIMARY).pack(side="left")
            ACTION_MODES = ["點擊目標中心", "點擊自訂座標", "自訂特定區塊", "無動作(僅等待)"]
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

            # 行 3: 命中後連點（過場跳過）勾選框
            row_rep = ctk.CTkFrame(body, fg_color="transparent")
            row_rep.pack(fill="x", pady=(3, 1))
            ctk.CTkCheckBox(
                row_rep,
                text="命中後連點（過場跳過）",
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
            self._drag_data = {"block": block_item, "y": e.y_root, "last_swap": 0.0}

        def on_motion(e):
            d = getattr(self, "_drag_data", None)
            if not d:
                return
            curr_b = d["block"]
            is_prio = curr_b in self.priority_blocks_list
            target_list = self.priority_blocks_list if is_prio else self.blocks_list
            if curr_b not in target_list:
                return

            now = time.time()
            if now - d.get("last_swap", 0.0) < 0.06:
                return

            idx = target_list.index(curr_b)
            dy = e.y_root - d["y"]
            h = curr_b["frame"].winfo_height() or 36
            if dy > h * 0.7 and idx < len(target_list) - 1:
                target_list[idx], target_list[idx + 1] = target_list[idx + 1], target_list[idx]
                d["y"] = e.y_root
                d["last_swap"] = now
                self._repack_all_blocks(fast_update=True)
            elif dy < -h * 0.7 and idx > 0:
                target_list[idx], target_list[idx - 1] = target_list[idx - 1], target_list[idx]
                d["y"] = e.y_root
                d["last_swap"] = now
                self._repack_all_blocks(fast_update=True)

        def on_end(e):
            self._drag_data = None
            self._repack_all_blocks(fast_update=False)
            self.auto_save_config()

        handle.bind("<Button-1>", on_start)
        handle.bind("<B1-Motion>", on_motion)
        handle.bind("<ButtonRelease-1>", on_end)

    def _update_section_badges(self):
        p_cnt = len(self.priority_blocks_list)
        if hasattr(self, "lbl_prio_count") and self.lbl_prio_count:
            self.lbl_prio_count.configure(text=f"({p_cnt} 個優先步驟)")
        if hasattr(self, "lbl_prio_empty") and self.lbl_prio_empty:
            if p_cnt == 0:
                self.lbl_prio_empty.pack(fill="x", padx=12, pady=8)
            else:
                self.lbl_prio_empty.pack_forget()

        n_cnt = len(self.blocks_list)
        if hasattr(self, "lbl_normal_count") and self.lbl_normal_count:
            self.lbl_normal_count.configure(text=f"({n_cnt} 個步驟)")

    def _repack_all_blocks(self, fast_update: bool = False):
        # 1. 重新排序優先步驟
        for b in self.priority_blocks_list:
            b["frame"].pack_forget()
        for i, b in enumerate(self.priority_blocks_list, start=1):
            b["frame"].pack(fill="x", padx=4, pady=2)
            if b.get("lbl_num"):
                b["lbl_num"].configure(text=f"#{i}")

        # 2. 重新排序一般步驟
        for b in self.blocks_list:
            b["frame"].pack_forget()
        for i, b in enumerate(self.blocks_list, start=1):
            b["frame"].pack(fill="x", padx=4, pady=3)
            if b.get("lbl_num"):
                b["lbl_num"].configure(text=f"#{i}")
            if b["type"] == "loop":
                in_list = b.get("inner_blocks_list", [])
                for j, cb in enumerate(in_list, start=1):
                    cb["frame"].pack_forget()
                    cb["frame"].pack(fill="x", padx=2, pady=2)
                    if cb.get("lbl_num"):
                        cb["lbl_num"].configure(text=f"#{i}.{j}")

        self._update_section_badges()
        if not fast_update and hasattr(self, "scroll_blocks") and self.scroll_blocks:
            try:
                self.scroll_blocks.update_idletasks()
            except Exception:
                pass

    def _renumber_blocks(self):
        self._repack_all_blocks(fast_update=False)

    def move_block(self, block_item: Dict[str, Any], direction: int):
        if block_item in self.priority_blocks_list:
            idx = self.priority_blocks_list.index(block_item)
            target = idx + direction
            if 0 <= target < len(self.priority_blocks_list):
                self.priority_blocks_list[idx], self.priority_blocks_list[target] = self.priority_blocks_list[target], self.priority_blocks_list[idx]
                self._repack_all_blocks()
                self.auto_save_config()
        elif block_item in self.blocks_list:
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
        is_prio = block_item in self.priority_blocks_list
        p_loop = block_item.get("parent_loop")
        insert_idx = None
        if is_prio and block_item in self.priority_blocks_list:
            insert_idx = self.priority_blocks_list.index(block_item) + 1
        elif p_loop and block_item in p_loop.get("inner_blocks_list", []):
            insert_idx = p_loop["inner_blocks_list"].index(block_item) + 1
        elif block_item in self.blocks_list:
            insert_idx = self.blocks_list.index(block_item) + 1
        self.add_block(
            b_type=serialized["type"],
            params=dict(serialized["params"]),
            name=f"{serialized['name']} (複製)",
            enabled=serialized["enabled"],
            parent_loop=p_loop,
            is_priority=is_prio,
            insert_index=insert_idx
        )

    def delete_block(self, block_item: Dict[str, Any]):
        if block_item in self.priority_blocks_list:
            if block_item.get("frame"):
                block_item["frame"].destroy()
            self.priority_blocks_list.remove(block_item)
            if self.selected_block_target is block_item:
                self.selected_block_target = None
            self._renumber_blocks()
            self.auto_save_config()
        elif block_item in self.blocks_list:
            if block_item.get("frame"):
                block_item["frame"].destroy()
            self.blocks_list.remove(block_item)
            if self.selected_block_target is block_item:
                self.selected_block_target = None
            self._renumber_blocks()
            self.auto_save_config()
        elif block_item.get("parent_loop"):
            parent = block_item["parent_loop"]
            in_list = parent.get("inner_blocks_list", [])
            if block_item in in_list:
                if block_item.get("frame"):
                    block_item["frame"].destroy()
                in_list.remove(block_item)
                if self.selected_block_target is block_item:
                    self.selected_block_target = None
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

        self._log(f"正在測試發送積木 Telegram 通知:「{msg}」...")
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
            self._log("積木 Telegram 測試通知已送出！")

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
        is_prio = block_item in self.priority_blocks_list
        self._log(f"已選取{'【優先辨識】' if is_prio else ''}目標積木 [{b_name}]")

    def _update_all_selection_highlights(self):
        target = getattr(self, "selected_block_target", None)
        for b in self.priority_blocks_list:
            if b.get("frame"):
                if b is target:
                    b["frame"].configure(border_width=2, border_color="#10B981")
                else:
                    b["frame"].configure(border_width=1, border_color="#F59E0B")
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

    def highlight_active_step(self, active_idx: int, is_priority: bool = False):
        def _ui_update():
            # 優先步驟高亮
            for i, b in enumerate(self.priority_blocks_list):
                if not b.get("frame"):
                    continue
                if is_priority and i == active_idx:
                    b["frame"].configure(border_width=2, border_color="#10B981")
                else:
                    is_target = (b is getattr(self, "selected_block_target", None))
                    b["frame"].configure(border_width=2 if is_target else 1, border_color="#10B981" if is_target else "#F59E0B")

            # 一般步驟高亮
            for i, b in enumerate(self.blocks_list):
                if not b.get("frame"):
                    continue
                info = BLOCK_TYPES.get(b["type"], BLOCK_TYPES["tap_coord"])
                if not is_priority and i == active_idx:
                    b["frame"].configure(border_width=2, border_color="#10B981")
                else:
                    is_target = (b is getattr(self, "selected_block_target", None))
                    b["frame"].configure(border_width=2 if is_target else 1, border_color="#F59E0B" if is_target else info["color"])

        if hasattr(self, "parent") and self.parent:
            self.parent.after(0, _ui_update)

    def on_capture_screen(self):
        if not self.bot or not self.bot.device:
            if self.gui and hasattr(self.gui, "bot") and self.gui.bot and self.gui.bot.device:
                self.bot = self.gui.bot
            elif not self.bot or not self.bot.connect():
                if self.gui and getattr(self.gui, "current_screen_bgr", None) is not None:
                    self.current_screen_bgr = self.gui.current_screen_bgr
                    self._render_preview(self.current_screen_bgr)
                    self._log("已直接同步主視窗畫面！點擊任一處可選取座標。")
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
            finally:
                def done():
                    self._capturing = False
                    self.btn_capture.configure(state="normal")
                    if screen is not None:
                        self.current_screen_bgr = screen
                        self._render_preview(screen)
                        self._log("畫面擷取成功！點擊畫面任意位置即可選取座標。")
                    else:
                        if self.gui and getattr(self.gui, "current_screen_bgr", None) is not None:
                            self.current_screen_bgr = self.gui.current_screen_bgr
                            self._render_preview(self.current_screen_bgr)
                            self._log("已同步主視窗快取畫面。")
                        else:
                            self._log(f"擷取失敗: {err or '無法從裝置取得畫面'}")
                            messagebox.showerror("錯誤", f"無法從模擬器取得截圖{': ' + str(err) if err else ''}")

                self.parent.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def update_emulator_preview(self, screen_bgr: np.ndarray):
        if screen_bgr is None:
            return
        self.current_screen_bgr = screen_bgr
        self._render_preview(screen_bgr)

    def _render_preview(self, screen_bgr: np.ndarray):
        if screen_bgr is None or self.preview is None:
            return
        self.preview.render(screen_bgr)
        self.preview.set_marker(self.selected_coord)

    def _on_preview_pick(self, x: int, y: int):
        """單擊預覽畫面：記下座標、複製到剪貼簿並在畫面上標示。"""
        self.selected_coord = (x, y)
        self.var_picked_coord.set(f"座標: ({x}, {y})")
        try:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(f"{x}, {y}")
        except Exception:
            pass
        self._log(f"已選取並複製座標: ({x}, {y})")
        self.preview.set_marker(self.selected_coord)

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
                if self.gui and hasattr(self.gui, "bot") and self.gui.bot and self.gui.bot.device:
                    self.bot = self.gui.bot
                else:
                    messagebox.showwarning("提示", "請先連線模擬器")
                    self.var_auto_preview.set(False)
                    return
            self._schedule_auto_refresh(delay_ms=200)
        elif self._auto_preview_job:
            try:
                self.parent.after_cancel(self._auto_preview_job)
            except Exception:
                pass
            self._auto_preview_job = None

    def _schedule_auto_refresh(self, delay_ms: int = 1500):
        if not self.var_auto_preview.get():
            return
        if self._auto_preview_job:
            try:
                self.parent.after_cancel(self._auto_preview_job)
            except Exception:
                pass
        self._auto_preview_job = self.parent.after(delay_ms, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        self._auto_preview_job = None
        if not self.var_auto_preview.get():
            return

        # 檢查並同步 bot 裝置
        if not self.bot or not self.bot.device:
            if self.gui and hasattr(self.gui, "bot") and self.gui.bot and self.gui.bot.device:
                self.bot = self.gui.bot
            else:
                # 尚未連線或斷線時維持心跳重試，絕不強制關閉使用者的自動開關
                self._schedule_auto_refresh(delay_ms=2000)
                return

        if getattr(self, "_capturing", False):
            self._schedule_auto_refresh(delay_ms=600)
            return

        self._capturing = True

        def work():
            screen = None
            try:
                screen = self.bot.capture_screen()
            except Exception:
                screen = None
            finally:
                def done():
                    self._capturing = False
                    if screen is not None:
                        self.current_screen_bgr = screen
                        self._render_preview(screen)
                    self._schedule_auto_refresh(delay_ms=1500)

                self.parent.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def on_device_connected(self):
        """當 ADB 裝置連線或重新連線成功時觸發：立即同步 bot 並恢復預覽刷新"""
        self._capturing = False
        if self.gui and hasattr(self.gui, "bot") and self.gui.bot and self.gui.bot.device:
            self.bot = self.gui.bot

        if self._auto_preview_job:
            try:
                self.parent.after_cancel(self._auto_preview_job)
            except Exception:
                pass
            self._auto_preview_job = None

        if self.var_auto_preview.get():
            self._schedule_auto_refresh(delay_ms=200)
        else:
            self.on_capture_screen()

    def on_run_tasks(self):
        if not self.blocks_list and not self.priority_blocks_list:
            messagebox.showinfo("提示", "程式區目前沒有任何積木步驟，請先加入積木！")
            return

        if self.bot and getattr(self.bot, "is_running", False):
            messagebox.showwarning("提示", "【循序腳本】正在執行中，請先停止循序腳本腳本再啟動任務清單。")
            return

        active_priority_blocks = self._serialize_all_priority_blocks()
        active_blocks = self._serialize_all_blocks()
        loop_cnt = max(0, self.var_loop_count.get())

        self.btn_run.configure(state="disabled")
        self.btn_step.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        if hasattr(self, "indicator_light"):
            self.indicator_light.configure(text_color="#F59E0B")
        self.var_status_text.set("正在執行任務清單...")

        def _on_step(idx, cycle, total_cycles):
            self.highlight_active_step(idx, is_priority=False)
            tot_str = str(total_cycles) if total_cycles > 0 else "∞"
            if idx >= 0:
                self.var_status_text.set(f"執行中 (輪次 {cycle}/{tot_str}，步驟 #{idx + 1})")
            else:
                self.var_status_text.set("任務已結束")

        def _on_priority_hit(p_idx: int):
            self.highlight_active_step(p_idx, is_priority=True)

        def _on_finish(success, msg):
            def _finish_ui():
                self.btn_run.configure(state="normal")
                self.btn_step.configure(state="normal")
                self.btn_stop.configure(state="disabled")
                self.highlight_active_step(-1, is_priority=False)
                if hasattr(self, "indicator_light"):
                    self.indicator_light.configure(text_color="#10B981" if success else "#EF4444")
                self.var_status_text.set(str(msg).strip())
            self.parent.after(0, _finish_ui)

        self.engine.global_settings.update(self.get_global_settings())
        self.engine.start(
            blocks_data=active_blocks,
            priority_blocks_data=active_priority_blocks,
            loop_count=loop_cnt,
            on_step_change=_on_step,
            on_finish=_on_finish,
            global_settings=self.get_global_settings(),
            on_priority_hit=_on_priority_hit
        )

    def on_step_task(self):
        all_blocks = self.priority_blocks_list + self.blocks_list
        if not all_blocks:
            messagebox.showinfo("提示", "程式區目前沒有任何積木步驟！")
            return
        target = getattr(self, "selected_block_target", None)
        if not target:
            target = all_blocks[0]
        s_data = self._serialize_single_block(target)
        is_prio = target in self.priority_blocks_list
        t_idx = self.priority_blocks_list.index(target) if is_prio else self.blocks_list.index(target)

        self.highlight_active_step(t_idx, is_priority=is_prio)
        prefix = "優先步驟" if is_prio else "步驟"
        self._log(f"[單步執行] {prefix} #{t_idx + 1} {s_data['name']}")

        self.engine.global_settings.update(self.get_global_settings())
        if self.bot and hasattr(self.bot, "set_allowed_languages"):
            self.bot.set_allowed_languages(
                allow_tc=bool(self.var_lang_tc.get()),
                allow_sc=bool(self.var_lang_sc.get()),
                allow_en=bool(self.var_lang_en.get())
            )

        # 單步執行時若是普通步驟，亦需同步載入有效優先步驟，確保單步執行時優先步驟同步發揮作用
        if not is_prio:
            self.engine.priority_blocks = [
                self._serialize_single_block(b)
                for b in self.priority_blocks_list
                if b.get("enabled", True)
            ]
        else:
            self.engine.priority_blocks = []

        def _on_priority_hit(hit_idx: int):
            if hit_idx >= 0:
                self.parent.after(0, lambda: self.highlight_active_step(hit_idx, is_priority=True))
            else:
                self.parent.after(0, lambda: self.highlight_active_step(-1, is_priority=True))

        self.engine.on_priority_hit = _on_priority_hit

        def _worker():
            self.engine.execute_block(s_data["type"], s_data["params"])
            self.parent.after(500, lambda: self.highlight_active_step(-1, is_priority=False))

        threading.Thread(target=_worker, daemon=True).start()

    def on_stop_tasks(self):
        self.engine.stop()
        if hasattr(self, "indicator_light"):
            self.indicator_light.configure(text_color="#EF4444")
        self.var_status_text.set("正在停止...")

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
            elif k == "stop_conditions" and isinstance(v, list):
                p["stop_conditions"] = [
                    {
                        "name": str(c.get("name", "條件")),
                        "mode": str(c["mode"].get() if hasattr(c.get("mode"), "get") else c.get("mode", "偵測到文字出現")),
                        "keywords": str(c["keywords"].get() if hasattr(c.get("keywords"), "get") else c.get("keywords", "")),
                        "template_image": str(c["template_image"].get() if hasattr(c.get("template_image"), "get") else c.get("template_image", "")),
                        "threshold": float(c["threshold"].get() if hasattr(c.get("threshold"), "get") else c.get("threshold", 0.80)),
                        "multiscale": bool(c["multiscale"].get() if hasattr(c.get("multiscale"), "get") else c.get("multiscale", False)),
                        "enabled": bool(c["enabled"].get() if hasattr(c.get("enabled"), "get") else c.get("enabled", True)),
                    }
                    for c in v
                ]
            elif hasattr(v, "get"):
                try:
                    raw_v = v.get()
                except Exception:
                    raw_v = 0 if k == "timeout" else None
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

        # 儲存展開/收合狀態
        p["expanded"] = bool(b["expanded"].get()) if "expanded" in b else True

        # 若為純圖片模式，清空關鍵字欄位殘留，杜絕文字辨識誤判
        tt_str = str(p.get("target_type", ""))
        is_pure_img = ("圖片" in tt_str or "image" in tt_str.lower() or "模板" in tt_str) and ("文字" not in tt_str)
        if is_pure_img and "keywords" in p:
            p["keywords"] = ""

        return {
            "type": b.get("type", "tap_coord"),
            "name": str(b["name"].get() if hasattr(b.get("name"), "get") else b.get("name", "積木")),
            "enabled": bool(b["enabled"].get() if hasattr(b.get("enabled"), "get") else b.get("enabled", True)),
            "params": p
        }

    def _serialize_all_priority_blocks(self) -> List[Dict[str, Any]]:
        return [self._serialize_single_block(b) for b in self.priority_blocks_list]

    def _serialize_all_blocks(self) -> List[Dict[str, Any]]:
        return [self._serialize_single_block(b) for b in self.blocks_list]

    def on_clear_blocks(self):
        total_cnt = len(self.priority_blocks_list) + len(self.blocks_list)
        if total_cnt > 0 and not messagebox.askyesno("確認清空", "確定要清空所有優先步驟與一般流程積木嗎？"):
            return
        self._clear_all_blocks()
        self._renumber_blocks()
        self.auto_save_config()

    # ------------------------------------------------------------------
    # 任務資料的載入與儲存（範本、自動存檔、手動載入共用）
    # ------------------------------------------------------------------
    def _task_data(self) -> Dict[str, Any]:
        """目前任務流程的存檔內容。"""
        return {
            "version": "1.1",
            "app_version": version.VERSION,
            "loop_count": self.var_loop_count.get(),
            "global_settings": self.get_global_settings(),
            "priority_blocks": self._serialize_all_priority_blocks(),
            "blocks": self._serialize_all_blocks(),
        }

    def _clear_all_blocks(self, include_priority: bool = True):
        if include_priority:
            for b in self.priority_blocks_list:
                if b.get("frame"):
                    b["frame"].destroy()
            self.priority_blocks_list.clear()
        for b in self.blocks_list:
            for cb in b.get("inner_blocks_list", []):
                if cb.get("frame"):
                    cb["frame"].destroy()
            if b.get("frame"):
                b["frame"].destroy()
        self.blocks_list.clear()
        self.selected_block_target = None

    def _load_blocks(self, data: Dict[str, Any]):
        """依存檔資料建立優先步驟與一般步驟的積木（積木多時預設收合以保持流暢）。"""
        p_blocks = data.get("priority_blocks", [])
        norm_blocks = data.get("blocks", [])
        collapse = (len(p_blocks) + len(norm_blocks)) > 6
        for is_priority, blocks in ((True, p_blocks), (False, norm_blocks)):
            for bd in blocks:
                params = dict(bd.get("params", {}))
                self.add_block(
                    b_type=bd.get("type", "detect_click") if is_priority else bd["type"],
                    params=params,
                    name=bd.get("name", ""),
                    enabled=bd.get("enabled", True),
                    is_priority=is_priority,
                    expanded=params.get("expanded", bd.get("expanded", not collapse)),
                )

    def replace_blocks(self, blocks: List[Dict[str, Any]]):
        """以指定的積木資料取代一般流程步驟（循序腳本的設定檔帶有任務流程時使用）。"""
        self._clear_all_blocks(include_priority=False)
        for bd in blocks:
            self.add_block(b_type=bd["type"], params=bd.get("params", {}), name=bd.get("name", ""),
                           enabled=bd.get("enabled", True))
        self.auto_save_config()

    @staticmethod
    def _is_image_mode_value(value: Any) -> bool:
        return "image" in str(value).lower() or "圖片" in str(value)

    def _apply_recognition_mode(self, data: Dict[str, Any], infer_from_blocks: bool = False):
        """還原存檔中的辨識模式（純圖片或文字 OCR）。"""
        gs = data.get("global_settings", {})
        if gs:
            if "disable_ocr" in gs:
                self.var_disable_ocr.set(bool(gs["disable_ocr"]))
            elif "recognition_mode" in gs:
                self.var_disable_ocr.set(self._is_image_mode_value(gs["recognition_mode"]))
        elif "recognition_mode" in data:
            self.var_disable_ocr.set(self._is_image_mode_value(data["recognition_mode"]))
        elif infer_from_blocks:
            params = [b.get("params", {}) for b in data.get("priority_blocks", []) + data.get("blocks", [])]
            has_img = any(p.get("template_image") or "圖片" in str(p.get("target_type", "")) for p in params)
            has_txt = any("文字" in str(p.get("target_type", "")) and not p.get("template_image") for p in params)
            if has_img and not has_txt:
                self.var_disable_ocr.set(True)

    def _apply_shared_settings(self, gs: Dict[str, Any]):
        """把存檔中的共用設定（掃描間隔、門檻、語言、Telegram）套用到進階設定。"""
        for key, var in (
            ("interval", self.var_interval), ("confidence", self.var_confidence),
            ("idle_strategy", self.var_idle_strategy), ("lang_tc", self.var_lang_tc),
            ("lang_sc", self.var_lang_sc), ("lang_en", self.var_lang_en),
            ("tg_token", self.var_tg_token), ("tg_chat_id", self.var_tg_chat_id),
        ):
            if key in gs:
                var.set(gs[key])

    def load_preset(self, preset_key: str):
        preset = self.presets.get(preset_key) or DAILY_PRESETS.get(preset_key)
        if not preset:
            fpath = os.path.join(self.presets_dir, f"{preset_key}.json")
            if os.path.exists(fpath):
                try:
                    preset = storage.load_config(fpath)
                except Exception:
                    pass
        if not preset:
            messagebox.showwarning("提示", f"找不到指定任務存檔：{preset_key}")
            return
        preset_title = preset.get("title", preset_key)
        total_cnt = len(self.priority_blocks_list) + len(self.blocks_list)
        if total_cnt > 0 and not messagebox.askyesno("載入任務存檔", f"載入任務設定「{preset_title}」將取代目前積木清單，是否繼續？"):
            return
        self._clear_all_blocks()
        if "loop_count" in preset:
            self.var_loop_count.set(preset.get("loop_count", 1))
        self._apply_recognition_mode(preset, infer_from_blocks=True)
        self._load_blocks(preset)
        self._log(f"已成功載入任務存檔: {preset_title} (優先 {len(self.priority_blocks_list)} 個, 一般 {len(self.blocks_list)} 個步驟)")
        self.auto_save_config()

    def auto_save_config(self):
        try:
            storage.save_config(self.save_file, self._task_data())
            if self.gui and hasattr(self.gui, "auto_save_current_config"):
                self.gui.auto_save_current_config()
        except Exception:
            pass

    def load_config_auto(self):
        """啟動時載入上次的任務流程（找不到時改讀舊版檔名的存檔）。"""
        path = self.save_file
        if not os.path.exists(path):
            path = storage.legacy_autosave_path(os.path.dirname(self.save_file), "task", self.instance_id)
            if not os.path.exists(path):
                return
        try:
            data = storage.load_config(path)
            self.var_loop_count.set(data.get("loop_count", 1))
            self._apply_recognition_mode(data)
            if not self.gui:
                self._apply_shared_settings(data.get("global_settings", {}))
            self._clear_all_blocks()
            self._load_blocks(data)
        except Exception as e:
            self._log(f"讀取上次任務清單失敗: {e}")

    def save_as_new_preset(self):
        self.on_save_config_dialog(default_mode="new")

    def on_save_config_dialog(self, default_mode: str = "new"):
        """詢問儲存位置並把目前的任務流程存成設定檔。"""
        if not (self.priority_blocks_list or self.blocks_list):
            if not messagebox.askyesno("提示", "目前任務清單是空的，確定要儲存空的任務嗎？"):
                return

        def do_save(target: str):
            storage.save_config(target, self._task_data())
            self.save_file = target
            self.presets_dir = os.path.dirname(target)
            self.reload_presets()
            self._log(f"任務設定已成功儲存至: {target}")

        ask_save_config(self.parent, "儲存任務設定", getattr(self, "save_file", ""), self.presets_dir,
                        "task_flow.json", "任務設定檔", do_save)

    def on_load_config_dialog(self):
        self._ask_and_load_task_file(self.presets_dir if os.path.exists(self.presets_dir) else self.config_dir,
                                     "載入任務清單")

    def on_load_preset_dialog(self):
        """從內建範本資料夾挑選任務流程載入。"""
        self._ask_and_load_task_file(storage.TASK_PRESETS_DIR, "載入內建任務範本")

    def _ask_and_load_task_file(self, initial_dir: str, title: str):
        path = filedialog.askopenfilename(
            initialdir=initial_dir, title=title,
            filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")]
        )
        if not path or not os.path.exists(path):
            return
        try:
            data = storage.load_config(path)
            self.var_loop_count.set(data.get("loop_count", 1))
            self._apply_recognition_mode(data)
            self._apply_shared_settings(data.get("global_settings", {}))
            self._clear_all_blocks()
            self._load_blocks(data)
            self.auto_save_config()
            messagebox.showinfo("成功", f"成功載入任務清單:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("錯誤", f"載入失敗: {e}")

    def get_block_choices(self) -> List[str]:
        choices = []
        for i, b in enumerate(self.priority_blocks_list, start=1):
            name = b["name"].get() if hasattr(b["name"], "get") else b.get("name", "")
            b_type = b.get("type", "step")
            choices.append(f"#{i} {name} ({b_type})")
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
                return storage.load_config(fpath)
            except Exception:
                pass
        return None

    def get_block_data_by_choice(self, choice_str: str) -> Optional[Dict[str, Any]]:
        if not choice_str:
            return None
        import re
        m_prio = re.match(r"^#(\d+)", choice_str.strip())
        if m_prio:
            idx = int(m_prio.group(1)) - 1
            if 0 <= idx < len(self.priority_blocks_list):
                return self._serialize_single_block(self.priority_blocks_list[idx])

        m = re.match(r"^#(\d+)", choice_str.strip())
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(self.blocks_list):
                return self._serialize_single_block(self.blocks_list[idx])

        for b in self.priority_blocks_list + self.blocks_list:
            name = b["name"].get() if hasattr(b["name"], "get") else b.get("name", "")
            if name and name in choice_str:
                return self._serialize_single_block(b)
        return None

    def on_theme_changed(self, mode: str):
        pass
