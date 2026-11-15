"""
共用對話框：插入位置、儲存設定檔、框選模板截圖、更新紀錄、存檔資料夾。
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk

from core.imaging import IMAGE_EXTENSIONS, fit_size, imwrite_unicode
from core.textutil import safe_filename
from ui import theme as T
from ui import widgets as W
import version


def _toplevel(parent):
    return parent.winfo_toplevel() if parent is not None and hasattr(parent, "winfo_toplevel") else parent


def make_dialog(parent, title: str, width: int, height: int, resizable: bool = False) -> ctk.CTkToplevel:
    """建立置中於父視窗的模態對話框。"""
    top = _toplevel(parent)
    dlg = ctk.CTkToplevel(top)
    dlg.title(title)
    dlg.configure(fg_color=T.COLOR_BG)
    dlg.resizable(resizable, resizable)
    x = y = None
    try:
        top.update_idletasks()
        x = top.winfo_rootx() + max(0, (top.winfo_width() - width) // 2)
        y = top.winfo_rooty() + max(0, (top.winfo_height() - height) // 2)
    except Exception:
        pass
    dlg.geometry(f"{width}x{height}+{x}+{y}" if x is not None else f"{width}x{height}")
    if top is not None:
        dlg.transient(top)
    dlg.grab_set()
    return dlg


# ============================================================================
# 插入位置
# ============================================================================
def ask_insert_position(parent, items: list, item_label: str = "步驟",
                        title: str = "選擇新增位置") -> Optional[int]:
    """
    詢問新項目要插入清單的哪個位置。
    清單為空時直接回傳 0；使用者確認時回傳 0 ~ len(items) 的索引，取消則回傳 None。
    預設選取最後一個位置。
    """
    if not items:
        return 0
    n = len(items)
    top = _toplevel(parent)
    dlg = make_dialog(parent, title, 480, 250)

    def name_of(item, fallback):
        if isinstance(item, dict) and "name" in item:
            v = item["name"]
            raw = str(v.get() if hasattr(v, "get") else v).strip()
            if raw:
                return raw[:15] + "..." if len(raw) > 18 else raw
        return fallback

    options = []
    for i in range(n + 1):
        if i == 0:
            options.append(f"第 1 步 (最前面，在「{name_of(items[0], f'{item_label} 1')}」之前)")
        elif i == n:
            options.append(f"第 {n + 1} 步 (最後一步) [預設]")
        else:
            options.append(f"第 {i + 1} 步 (在「{name_of(items[i - 1], f'{item_label} {i}')}」之後)")
    index_of = {t: i for i, t in enumerate(options)}
    result = [None]

    box = W.card(dlg)
    box.pack(fill="both", expand=True, padx=14, pady=14)
    W.label(box, f"選擇新{item_label}的插入位置", size=15, bold=True,
            color=T.COLOR_TEXT_HIGHLIGHT).pack(anchor="w", padx=14, pady=(12, 2))
    W.label(box, f"目前已有 {n} 個{item_label}，請選擇新{item_label}要放在哪裡：",
            size=12).pack(anchor="w", padx=14, pady=(0, 10))

    var_choice = tk.StringVar(value=options[-1])
    var_num = tk.StringVar(value=str(n + 1))

    r1 = W.row(box)
    r1.pack(fill="x", padx=14, pady=(0, 8))
    W.label(r1, "位置清單", bold=True, color=T.COLOR_TEXT_MUTED).pack(side="left", padx=(0, 8))
    combo = W.option_menu(r1, var_choice, options, width=320, height=28)
    combo.pack(side="left", fill="x", expand=True)

    r2 = W.row(box)
    r2.pack(fill="x", padx=14, pady=(0, 10))
    W.label(r2, "或直接指定序號：第", color=T.COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))
    W.entry(r2, var_num, width=50, height=26, justify="center").pack(side="left", padx=(0, 4))

    def step(delta):
        s = var_num.get().strip()
        cur = int(s) if s.isdigit() else n + 1
        var_num.set(str(max(1, min(n + 1, cur + delta))))

    W.button(r2, "－", lambda: step(-1), width=26, height=24).pack(side="left", padx=(0, 2))
    W.button(r2, "＋", lambda: step(1), width=26, height=24).pack(side="left", padx=(0, 6))
    W.label(r2, f"步 (可輸入 1 ~ {n + 1})", color=T.COLOR_TEXT_MUTED).pack(side="left")

    syncing = [False]

    def on_choice(val):
        if syncing[0]:
            return
        syncing[0] = True
        var_num.set(str(index_of.get(val, n) + 1))
        syncing[0] = False

    def on_num(*_):
        if syncing[0]:
            return
        s = var_num.get().strip()
        if s.isdigit() and 1 <= int(s) <= n + 1:
            syncing[0] = True
            var_choice.set(options[int(s) - 1])
            syncing[0] = False

    combo.configure(command=on_choice)
    var_num.trace_add("write", on_num)

    def confirm():
        s = var_num.get().strip()
        result[0] = int(s) - 1 if (s.isdigit() and 1 <= int(s) <= n + 1) else index_of.get(var_choice.get(), n)
        dlg.destroy()

    def cancel():
        result[0] = None
        dlg.destroy()

    rb = W.row(box)
    rb.pack(fill="x", padx=14, pady=(4, 10), side="bottom")
    W.button(rb, "取消 (Esc)", cancel, width=90, height=30, bold=False).pack(side="left")
    btn_ok = W.button(rb, "確認新增 (Enter)", confirm, kind="success", width=130, height=30)
    btn_ok.pack(side="right")

    dlg.bind("<Return>", lambda e: confirm())
    dlg.bind("<KP_Enter>", lambda e: confirm())
    dlg.bind("<Escape>", lambda e: cancel())
    dlg.protocol("WM_DELETE_WINDOW", cancel)
    btn_ok.focus_set()
    (top or dlg).wait_window(dlg)
    return result[0]


# ============================================================================
# 儲存設定檔
# ============================================================================
def ask_save_config(parent, title: str, default_path: str, fallback_dir: str,
                    default_filename: str, noun: str,
                    do_save: Callable[[str], None]) -> Optional[str]:
    """
    儲存設定檔對話框：使用者輸入或選擇 .json 路徑，檔案已存在時先確認覆蓋，
    再呼叫 do_save(絕對路徑) 寫檔（失敗請拋出例外）。成功時回傳儲存路徑。
    """
    top = _toplevel(parent)
    dlg = make_dialog(parent, title, 600, 250)
    result = [None]

    box = W.card(dlg)
    box.pack(fill="both", expand=True, padx=16, pady=16)
    W.label(box, title, size=16, bold=True, color=T.COLOR_TEXT_HIGHLIGHT).pack(anchor="w", padx=16, pady=(14, 2))
    W.label(box, f"請選擇或輸入{noun}要儲存的位置（.json 檔案）：", size=12).pack(anchor="w", padx=16)

    path_box = ctk.CTkFrame(box, fg_color=T.COLOR_INPUT_BG, corner_radius=8, border_width=1,
                            border_color=T.COLOR_CARD_BORDER)
    path_box.pack(fill="x", padx=16, pady=(10, 10))
    inner = W.row(path_box)
    inner.pack(fill="x", padx=10, pady=10)
    var_path = tk.StringVar(value=default_path or os.path.join(fallback_dir, default_filename))
    W.entry(inner, var_path, height=32, font=T.mono(11)).pack(side="left", fill="x", expand=True, padx=(0, 8))

    def browse():
        cur = var_path.get().strip()
        init_dir = os.path.dirname(cur) if cur and os.path.isdir(os.path.dirname(cur)) else fallback_dir
        init_file = os.path.basename(cur) if cur else default_filename
        if not init_file.endswith(".json"):
            init_file += ".json"
        f = filedialog.asksaveasfilename(
            parent=dlg, title="選擇存檔位置與檔案名稱", initialdir=init_dir, initialfile=init_file,
            defaultextension=".json", filetypes=[("JSON 設定檔", "*.json"), ("所有檔案", "*.*")],
        )
        if f:
            var_path.set(os.path.abspath(f))

    W.button(inner, "選擇位置", browse, kind="primary", width=84, height=32).pack(side="left")

    def save():
        p = var_path.get().strip()
        if not p:
            messagebox.showwarning("提示", "請輸入或選擇儲存路徑！", parent=dlg)
            return
        if not p.lower().endswith(".json"):
            p += ".json"
            var_path.set(p)
        target = os.path.abspath(p)
        if os.path.exists(target) and not messagebox.askyesno(
            "檔案衝突提醒",
            f"{noun}「{os.path.basename(target)}」已經存在！\n\n路徑：{target}\n\n"
            "確定要覆蓋嗎？\n（此動作將取代現有檔案內容，無法復原）",
            parent=dlg,
        ):
            return
        try:
            do_save(target)
        except Exception as ex:
            messagebox.showerror("儲存失敗", f"無法寫入檔案: {ex}", parent=dlg)
            return
        result[0] = target
        messagebox.showinfo("儲存成功", f"{noun}已成功儲存至：\n{target}", parent=dlg)
        dlg.destroy()

    rb = W.row(box)
    rb.pack(fill="x", padx=16, pady=(0, 14), side="bottom")
    W.button(rb, "確認儲存", save, kind="success", width=110, height=32, size=12).pack(side="right", padx=(8, 0))
    W.button(rb, "取消", dlg.destroy, width=72, height=32, size=12, bold=False).pack(side="right")
    dlg.bind("<Escape>", lambda e: dlg.destroy())
    (top or dlg).wait_window(dlg)
    return result[0]


def confirm_overwrite_image(parent, path: str) -> bool:
    """圖片已存在時詢問是否覆蓋；不存在時直接回傳 True。"""
    if not os.path.exists(path):
        return True
    return messagebox.askyesno(
        "圖片衝突提醒",
        f"模板圖片「{os.path.basename(path)}」已經存在！\n\n路徑：{path}\n\n是否確認要覆蓋此圖片檔案？",
        parent=parent,
    )


# ============================================================================
# 框選模板截圖
# ============================================================================
class TemplateSnipperDialog(ctk.CTkToplevel):
    """在目前畫面上拖曳框選局部區域，裁切後儲存為圖片模板。"""

    def __init__(self, parent, screen_bgr: np.ndarray, initial_name: str, templates_dir: str,
                 on_save_callback: Callable[[str], None]):
        top = _toplevel(parent)
        super().__init__(top)
        self.title("從畫面框選按鈕模板")
        scr_w, scr_h = self.winfo_screenwidth(), self.winfo_screenheight()
        win_w, win_h = min(980, scr_w - 80), min(700, scr_h - 120)
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(720, 480)
        self.configure(fg_color=T.COLOR_BG)
        self.transient(top)
        self.grab_set()

        self.screen_bgr = screen_bgr
        self.save_dir = templates_dir if (templates_dir and os.path.exists(templates_dir)) else os.getcwd()
        self.on_save_callback = on_save_callback
        self.crop_bgr = None
        self.orig_h, self.orig_w = screen_bgr.shape[:2]
        self.scale = 1.0
        self.offset_x = self.offset_y = 0
        self.rect_id = None
        self.start_x = self.start_y = 0
        self._sel = None
        self._resize_job = None

        tip = W.card(self, corner_radius=8)
        tip.pack(fill="x", padx=12, pady=(10, 6))
        W.label(tip, "在下方畫面上按住滑鼠左鍵拖曳框選目標按鈕，放開後即可預覽並儲存為模板圖片。",
                size=12, bold=True, color=T.COLOR_TEXT_HIGHLIGHT).pack(side="left", padx=12, pady=8)

        # 底部操作列先放（side=bottom），畫布再佔滿剩餘空間，視窗再小按鈕也不會被擠掉
        bottom = W.card(self, corner_radius=8)
        bottom.pack(side="bottom", fill="x", padx=12, pady=(4, 10))
        self.lbl_thumb = ctk.CTkLabel(bottom, text="尚未框選", width=80, height=60, fg_color=T.COLOR_INPUT_BG,
                                      corner_radius=6, font=T.font(10), text_color=T.COLOR_TEXT_DIM)
        self.lbl_thumb.pack(side="left", padx=10, pady=8)

        btn_box = W.row(bottom)
        btn_box.pack(side="right", padx=10)
        self.btn_save = W.button(btn_box, "儲存並套用", self._do_save, kind="success", width=100, height=32,
                                 size=12, state="disabled")
        self.btn_save.pack(side="left", padx=(0, 6))
        W.button(btn_box, "取消", self.destroy, width=68, height=32, size=12, bold=False).pack(side="left")

        info = W.row(bottom)
        info.pack(side="left", fill="x", expand=True, padx=6)
        self.lbl_info = W.label(info, "選取尺寸: 尚未框選", color=T.COLOR_TEXT_MUTED)
        self.lbl_info.pack(anchor="w")
        r_dir = W.row(info)
        r_dir.pack(fill="x", pady=2)
        W.label(r_dir, "儲存目錄").pack(side="left", padx=(0, 6))
        W.button(r_dir, "變更目錄", self._choose_dir, width=70, height=24, size=10, bold=False).pack(side="right")
        self.lbl_dir = ctk.CTkLabel(r_dir, text=self.save_dir, font=T.mono(10), text_color=T.COLOR_TEXT_MUTED,
                                    anchor="w", width=120)
        self.lbl_dir.pack(side="left", fill="x", expand=True, padx=(0, 4))
        r_name = W.row(info)
        r_name.pack(fill="x", pady=(2, 0))
        W.label(r_name, "儲存檔名").pack(side="left", padx=(0, 6))
        self.var_filename = tk.StringVar(value=f"{safe_filename(initial_name) or 'btn_template'}.png")
        W.entry(r_name, self.var_filename, width=180, height=26, monospace=False).pack(side="left", padx=(0, 6))
        W.button(r_name, "另存為...", self._choose_save_as, width=70, height=26, size=10, bold=False).pack(side="left")

        holder = ctk.CTkFrame(self, fg_color=T.COLOR_CANVAS_BG, corner_radius=8)
        holder.pack(fill="both", expand=True, padx=12, pady=4)
        self.canvas = tk.Canvas(holder, bg=T.COLOR_CANVAS_BG, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_up)

    # ---- 畫面縮放
    def _on_resize(self, _e=None):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(60, self._draw)

    def _draw(self):
        self._resize_job = None
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        self.scale, dw, dh = fit_size(self.orig_w, self.orig_h, cw, ch)
        self.offset_x, self.offset_y = (cw - dw) // 2, (ch - dh) // 2
        resized = cv2.resize(self.screen_bgr, (dw, dh), interpolation=cv2.INTER_AREA)
        self.photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)))
        self.canvas.delete("all")
        self.rect_id = None
        self.canvas.create_image(cw // 2, ch // 2, image=self.photo, anchor="center")
        if self._sel:
            rx1, ry1, rx2, ry2 = self._sel
            self.rect_id = self.canvas.create_rectangle(
                rx1 * self.scale + self.offset_x, ry1 * self.scale + self.offset_y,
                rx2 * self.scale + self.offset_x, ry2 * self.scale + self.offset_y,
                outline=T.COLOR_RUNNING, width=2, dash=(4, 2))

    # ---- 儲存位置
    def _choose_dir(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.save_dir, title="選擇模板圖片儲存目錄")
        if d:
            self.save_dir = os.path.abspath(d)
            self.lbl_dir.configure(text=self.save_dir)

    def _choose_save_as(self):
        f = filedialog.asksaveasfilename(
            parent=self, title="選擇模板儲存位置與檔名", initialdir=self.save_dir,
            initialfile=self.var_filename.get().strip() or "template.png", defaultextension=".png",
            filetypes=[("PNG 圖片", "*.png"), ("所有檔案", "*.*")],
        )
        if f:
            self.save_dir = os.path.dirname(os.path.abspath(f))
            self.var_filename.set(os.path.basename(f))
            self.lbl_dir.configure(text=self.save_dir)

    # ---- 框選
    def _on_down(self, e):
        self.start_x, self.start_y = e.x, e.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None

    def _on_drag(self, e):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, e.x, e.y)
        else:
            self.rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, e.x, e.y,
                                                        outline=T.COLOR_RUNNING, width=2, dash=(4, 2))

    def _to_real(self, x, y):
        return (max(0, min(self.orig_w, int((x - self.offset_x) / self.scale))),
                max(0, min(self.orig_h, int((y - self.offset_y) / self.scale))))

    def _on_up(self, e):
        rx1, ry1 = self._to_real(min(self.start_x, e.x), min(self.start_y, e.y))
        rx2, ry2 = self._to_real(max(self.start_x, e.x), max(self.start_y, e.y))
        w, h = rx2 - rx1, ry2 - ry1
        if w < 8 or h < 8:
            self.lbl_info.configure(text="選取範圍過小，請重新框選")
            self.btn_save.configure(state="disabled")
            self.crop_bgr = None
            self._sel = None
            return
        self._sel = (rx1, ry1, rx2, ry2)
        self.crop_bgr = self.screen_bgr[ry1:ry2, rx1:rx2].copy()
        self.lbl_info.configure(text=f"選取尺寸: {w} × {h} 像素 (範圍: X {rx1}~{rx2}, Y {ry1}~{ry2})")
        pil_img = Image.fromarray(cv2.cvtColor(self.crop_bgr, cv2.COLOR_BGR2RGB))
        pil_img.thumbnail((76, 56))
        self.crop_photo = ImageTk.PhotoImage(pil_img)
        self.lbl_thumb.configure(image=self.crop_photo, text="")
        self.btn_save.configure(state="normal")

    def _do_save(self):
        if self.crop_bgr is None:
            messagebox.showwarning("提示", "尚未框選按鈕範圍！請在畫面上拖曳框選。", parent=self)
            return
        fname = self.var_filename.get().strip() or "template.png"
        if not fname.lower().endswith(IMAGE_EXTENSIONS):
            fname += ".png"
        target = os.path.join(self.save_dir, fname)
        if not confirm_overwrite_image(self, target):
            return
        try:
            if imwrite_unicode(target, self.crop_bgr):
                self.on_save_callback(target)
                messagebox.showinfo("截圖成功", f"模板圖片已成功儲存至：\n{target}\n\n已自動套用至步驟！", parent=self)
                self.destroy()
            else:
                messagebox.showerror("錯誤", f"無法儲存模板檔案至: {target}\n請檢查是否有寫入權限或磁碟空間。", parent=self)
        except Exception as ex:
            messagebox.showerror("錯誤", f"儲存模板發生異常: {ex}", parent=self)


# ============================================================================
# 更新紀錄
# ============================================================================
def show_changelog(parent, only_latest: bool = False):
    """顯示版本與更新紀錄。only_latest=True 時只列出最新一版（更新後首次啟動用）。"""
    dlg = make_dialog(parent, f"{version.APP_NAME} - 更新紀錄", 640, 560, resizable=True)
    dlg.minsize(480, 360)

    head = W.row(dlg)
    head.pack(fill="x", padx=18, pady=(16, 6))
    W.label(head, version.APP_NAME, size=18, bold=True).pack(side="left")
    ctk.CTkLabel(head, text=f"v{version.VERSION}", font=T.mono(12, True), text_color="#FFFFFF",
                 fg_color=T.COLOR_BTN_PRIMARY, corner_radius=6, width=64, height=24).pack(side="left", padx=10)
    if only_latest:
        W.label(head, "已更新至新版本", color=T.COLOR_RUNNING, bold=True).pack(side="left")

    W.button(dlg, "關閉", dlg.destroy, kind="primary", width=96, height=32, size=12).pack(side="bottom", pady=(6, 14))

    body = ctk.CTkScrollableFrame(dlg, fg_color=T.COLOR_CARD, corner_radius=10, border_width=1,
                                  border_color=T.COLOR_CARD_BORDER)
    body.pack(fill="both", expand=True, padx=16, pady=4)

    entries = version.CHANGELOG[:1] if only_latest else version.CHANGELOG
    wrap = 540
    for i, item in enumerate(entries):
        r = W.row(body)
        r.pack(fill="x", padx=8, pady=(10 if i == 0 else 16, 2))
        ctk.CTkLabel(r, text=f"v{item['version']}", font=T.mono(12, True), text_color="#FFFFFF",
                     fg_color=T.COLOR_BTN_PRIMARY if i == 0 else T.COLOR_BTN_DARK,
                     corner_radius=6, width=62, height=22).pack(side="left")
        W.label(r, item.get("date", ""), color=T.COLOR_TEXT_DIM).pack(side="left", padx=8)
        if item.get("title"):
            W.label(body, item["title"], size=13, bold=True, color=T.COLOR_TEXT_HIGHLIGHT,
                    anchor="w", justify="left", wraplength=wrap).pack(fill="x", padx=10, pady=(2, 2))
        for change in item.get("changes", []):
            line = W.row(body)
            line.pack(fill="x", padx=10, pady=1)
            W.label(line, "•", color=T.COLOR_TEXT_DIM, width=14).pack(side="left", anchor="n")
            W.label(line, change, size=12, anchor="w", justify="left",
                    wraplength=wrap - 24).pack(side="left", fill="x", expand=True)
    if only_latest and len(version.CHANGELOG) > 1:
        W.label(body, "完整的歷史紀錄可隨時點擊標題列的版本號查看。", color=T.COLOR_TEXT_DIM,
                anchor="w").pack(fill="x", padx=10, pady=(14, 6))
    dlg.bind("<Escape>", lambda e: dlg.destroy())
    return dlg
