"""
共用介面元件：按鈕／卡片工廠、自動換行容器、日誌面板、畫面預覽面板。

各頁面都使用這裡的元件，預覽的座標換算、框選、縮放與日誌的佇列寫入只實作一次。
"""
import datetime
import os
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, List, Optional, Tuple

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk

from core.imaging import fit_size
from ui import theme as T


# ============================================================================
# 基本元件工廠
# ============================================================================
def card(parent, **kw) -> ctk.CTkFrame:
    """帶邊框的圓角卡片。"""
    opts = dict(fg_color=T.COLOR_CARD, corner_radius=10, border_width=1, border_color=T.COLOR_CARD_BORDER)
    opts.update(kw)
    return ctk.CTkFrame(parent, **opts)


def row(parent, **kw) -> ctk.CTkFrame:
    """透明的水平容器。"""
    return ctk.CTkFrame(parent, fg_color="transparent", **kw)


def button(parent, text: str, command=None, kind: str = "neutral", width: int = 64,
           height: int = 28, size: int = 11, bold: bool = True, **kw) -> ctk.CTkButton:
    fg, hover = T.BUTTON_KINDS.get(kind, T.BUTTON_KINDS["neutral"])
    opts = dict(text=text, command=command, width=width, height=height, corner_radius=6,
                fg_color=fg, hover_color=hover, font=T.font(size, bold))
    opts.update(kw)
    return ctk.CTkButton(parent, **opts)


def label(parent, text: str = "", size: int = 11, bold: bool = False,
          color: str = T.COLOR_TEXT_PRIMARY, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=T.font(size, bold), text_color=color, **kw)


def entry(parent, textvariable=None, width: int = 46, height: int = 24, monospace: bool = True, **kw) -> ctk.CTkEntry:
    opts = dict(textvariable=textvariable, width=width, height=height, corner_radius=5,
                fg_color=T.COLOR_INPUT_BG, border_color=T.COLOR_INPUT_BORDER,
                font=T.mono(10) if monospace else T.font(11))
    opts.update(kw)
    return ctk.CTkEntry(parent, **opts)


def checkbox(parent, text: str, variable, size: int = 11, bold: bool = False,
             color: str = T.COLOR_TEXT_PRIMARY, **kw) -> ctk.CTkCheckBox:
    opts = dict(text=text, variable=variable, font=T.font(size, bold), text_color=color,
                width=18, height=18, checkbox_width=16, checkbox_height=16, corner_radius=4)
    opts.update(kw)
    return ctk.CTkCheckBox(parent, **opts)


def option_menu(parent, variable, values: List[str], width: int = 110, height: int = 24, **kw) -> ctk.CTkOptionMenu:
    opts = dict(variable=variable, values=values, width=width, height=height, corner_radius=5,
                font=T.font(11), dropdown_font=T.font(11),
                fg_color=T.COLOR_BTN_DARK, button_color=T.COLOR_INPUT_BORDER,
                button_hover_color=T.COLOR_BTN_PRIMARY)
    opts.update(kw)
    return ctk.CTkOptionMenu(parent, **opts)


# ============================================================================
# 自動換行容器
# ============================================================================
class FlowFrame(ctk.CTkFrame):
    """
    由左至右排列子元件，寬度不足時自動換到下一行。
    用於工具列，確保視窗變窄時按鈕會換行而不是被裁切。
    以 add() 加入的元件才會參與排版；right=True 的元件靠右對齊。
    """

    def __init__(self, parent, hgap: int = 4, vgap: int = 4, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(parent, height=28, **kw)
        self._hgap = hgap
        self._vgap = vgap
        self._items: List[Tuple[tk.Widget, bool]] = []
        self._hidden = set()
        self._job = None
        self._last = None
        self.bind("<Configure>", lambda e: self._schedule())
        self.bind("<Map>", lambda e: self._schedule())

    def add(self, widget, right: bool = False):
        self._items.append((widget, right))
        # 子元件自身尺寸改變（例如文字變長）時也要重新排版
        widget.bind("<Configure>", lambda e: self._schedule(), add="+")
        self._schedule()
        return widget

    def set_visible(self, widget, visible: bool):
        if visible:
            self._hidden.discard(widget)
        else:
            self._hidden.add(widget)
            widget.place_forget()
        self._last = None
        self._schedule()

    def _schedule(self):
        if self._job is None:
            self._job = self.after_idle(self.reflow)

    def reflow(self):
        self._job = None
        try:
            if not self.winfo_exists():
                return
            width = self.winfo_width()
        except Exception:
            return
        if width <= 1:
            return  # 尚未顯示；顯示後的 <Configure> 事件會再觸發排版
        scale = self._get_widget_scaling()
        left = [w for w, r in self._items if not r and w not in self._hidden]
        right = [w for w, r in self._items if r and w not in self._hidden]
        sizes = {w: (w.winfo_reqwidth(), w.winfo_reqheight()) for w in left + right}
        signature = (width, tuple(sizes[w] for w in left + right))
        if signature == self._last:
            return
        self._last = signature

        right_w = sum(sizes[w][0] for w in right) + self._hgap * max(0, len(right) - 1)
        placements = []
        x = y = row_h = 0
        for w in left:
            rw, rh = sizes[w]
            if x > 0 and x + rw > width:
                x, y, row_h = 0, y + row_h + self._vgap, 0
            placements.append((w, x, y))
            x += rw + self._hgap
            row_h = max(row_h, rh)
        if right:
            # 靠右群組放得下就與最後一行同列，否則另起一行
            if x > 0 and x + right_w > width:
                x, y, row_h = 0, y + row_h + self._vgap, 0
            rx = max(x, width - right_w)
            for w in right:
                rw, rh = sizes[w]
                if rx > 0 and rx + rw > width:
                    rx, y, row_h = 0, y + row_h + self._vgap, 0
                placements.append((w, rx, y))
                rx += rw + self._hgap
                row_h = max(row_h, rh)
        for w, px, py in placements:
            w.place(x=px / scale, y=py / scale)
        total_h = max(1, y + row_h)
        self.configure(height=total_h / scale)


# ============================================================================
# 日誌面板
# ============================================================================
class LogPanel(ctk.CTkFrame):
    """
    等寬字型的執行日誌。log() 可從任何執行緒呼叫，內容經佇列在主執行緒寫入。
    內建清除、儲存與自動捲動；extra_buttons 可加入額外的工具按鈕。
    """

    def __init__(self, parent, title: str = "執行日誌", extra_buttons=(), font_size: int = 11,
                 show_save: bool = True, **kw):
        opts = dict(fg_color=T.COLOR_CARD, corner_radius=10, border_width=1, border_color=T.COLOR_CARD_BORDER)
        opts.update(kw)
        super().__init__(parent, **opts)
        self._queue: "queue.Queue[str]" = queue.Queue()
        self.auto_scroll = True

        tools = row(self)
        tools.pack(fill="x", padx=12, pady=(8, 4))
        label(tools, title, size=12, bold=True).pack(side="left")

        self._sw = ctk.CTkSwitch(tools, text="自動捲動", font=T.font(11), width=40,
                                 command=self._toggle_scroll, progress_color=T.COLOR_BTN_PRIMARY)
        self._sw.select()
        self._sw.pack(side="right", padx=(8, 0))
        if show_save:
            button(tools, "儲存", self.export, width=48, height=24, size=10, bold=False).pack(side="right", padx=2)
        button(tools, "清除", self.clear, width=48, height=24, size=10, bold=False).pack(side="right", padx=2)
        for text, cmd in extra_buttons:
            button(tools, text, cmd, width=48, height=24, size=10, bold=False).pack(side="right", padx=2)

        self.textbox = ctk.CTkTextbox(
            self, font=T.mono(font_size), fg_color=T.COLOR_INPUT_BG, text_color=T.COLOR_TEXT_PRIMARY,
            border_width=1, border_color=T.COLOR_CARD_BORDER, corner_radius=8, wrap="char", height=60,
        )
        self.textbox.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.textbox.configure(state="disabled")
        self.after(60, self._drain)

    def log(self, text: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._queue.put(f"[{now}] {text}\n")

    def _drain(self):
        batch = []
        while True:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            try:
                self.textbox.configure(state="normal")
                self.textbox.insert("end", "".join(batch))
                if self.auto_scroll:
                    self.textbox.see("end")
                self.textbox.configure(state="disabled")
            except Exception:
                pass
        try:
            self.after(60, self._drain)
        except Exception:
            pass

    def _toggle_scroll(self):
        self.auto_scroll = bool(self._sw.get())

    def get_text(self) -> str:
        return self.textbox.get("1.0", "end").strip()

    def clear(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")

    def export(self):
        content = self.get_text()
        top = self.winfo_toplevel()
        if not content:
            messagebox.showinfo("提示", "目前沒有任何日誌可匯出。", parent=top)
            return
        path = filedialog.asksaveasfilename(
            parent=top, title="儲存執行日誌", defaultextension=".log",
            filetypes=[("Log 檔案", "*.log"), ("文字檔案", "*.txt"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.log(f"日誌已儲存至: {os.path.basename(path)}")
            messagebox.showinfo("成功", f"日誌已成功儲存至:\n{path}", parent=top)
        except Exception as e:
            messagebox.showerror("錯誤", f"無法儲存日誌檔案: {e}", parent=top)


# ============================================================================
# 畫面預覽面板
# ============================================================================
class PreviewPanel(ctk.CTkFrame):
    """
    即時畫面預覽。畫布會隨面板大小自動縮放，影像等比置中顯示。

    功能：
    - 滑鼠移動顯示實際座標；單擊回呼 on_click(x, y)
    - enable_selection=True 時可拖曳框選，放開後啟用「裁切截圖」按鈕並回呼 on_crop
    - set_marker() 在畫面上標示已選取的座標
    - 工具列提供收合、截取、刷新間隔（或自動刷新開關）
    """

    SELECT_COLOR = "#F59E0B"
    MIN_SELECTION = 8

    def __init__(
        self,
        parent,
        placeholder: str,
        on_capture: Callable[[], None],
        on_click: Optional[Callable[[int, int], None]] = None,
        on_crop: Optional[Callable[[], None]] = None,
        coords_var: Optional[tk.StringVar] = None,
        interval_var: Optional[tk.StringVar] = None,
        interval_values: Optional[List[str]] = None,
        on_interval_change: Optional[Callable[[str], None]] = None,
        auto_var: Optional[tk.BooleanVar] = None,
        on_auto_toggle: Optional[Callable[[], None]] = None,
        coord_formatter: Optional[Callable[[int, int], str]] = None,
        enable_selection: bool = True,
        on_fold: Optional[Callable[[bool], None]] = None,
        capture_text: str = "立即截取",
        min_canvas: Tuple[int, int] = (240, 135),
        **kw,
    ):
        opts = dict(fg_color=T.COLOR_CARD, corner_radius=10, border_width=1, border_color=T.COLOR_CARD_BORDER)
        opts.update(kw)
        super().__init__(parent, **opts)

        self._placeholder = placeholder
        self._on_click = on_click
        self._on_crop = on_crop
        self._on_fold = on_fold
        self._formatter = coord_formatter or (lambda x, y: f"X: {x}, Y: {y}")
        self._enable_selection = enable_selection
        self.coords_var = coords_var or tk.StringVar(value="")

        self.is_open = True
        self.is_dragging = False
        self.crop_coords: Optional[Tuple[int, int, int, int]] = None
        self.raw_w = 0
        self.raw_h = 0
        self.scale = 1.0
        self.img_w = 0
        self.img_h = 0
        self._image: Optional[np.ndarray] = None
        self._matched = None
        self._marker: Optional[Tuple[int, int]] = None
        self._photo = None
        self._drag_start: Optional[Tuple[int, int]] = None
        self._resize_job = None

        # ---- 工具列（自動換行）
        self.toolbar = FlowFrame(self)
        self.toolbar.pack(fill="x", padx=12, pady=(10, 6))
        self.btn_fold = self.toolbar.add(button(self.toolbar, "畫面 ▾", self.toggle_fold, width=58, bold=False))
        self.btn_capture = self.toolbar.add(button(self.toolbar, capture_text, on_capture, kind="primary", width=76))
        if interval_var is not None:
            box = row(self.toolbar)
            label(box, "刷新", color=T.COLOR_TEXT_MUTED).pack(side="left", padx=(4, 4))
            option_menu(box, interval_var, interval_values or [], width=78, height=28,
                        dynamic_resizing=False, command=on_interval_change).pack(side="left")
            self.toolbar.add(box)
        if auto_var is not None:
            sw = ctk.CTkSwitch(self.toolbar, text="自動刷新", variable=auto_var, font=T.font(11), width=40,
                               command=on_auto_toggle, progress_color=T.COLOR_BTN_PRIMARY)
            self.toolbar.add(sw)
        self.btn_crop = None
        if enable_selection and on_crop is not None:
            self.btn_crop = self.toolbar.add(
                button(self.toolbar, "裁切截圖", on_crop, width=84, state="disabled",
                       text_color_disabled=T.COLOR_TEXT_DIM))
        self.lbl_coords = self.toolbar.add(
            ctk.CTkLabel(self.toolbar, textvariable=self.coords_var, font=T.mono(11, True),
                         text_color=T.COLOR_TEXT_INFO, anchor="e", height=28), right=True)

        # ---- 畫布
        self.holder = ctk.CTkFrame(self, fg_color=T.COLOR_CANVAS_BG, corner_radius=8,
                                   border_width=1, border_color=T.COLOR_CARD_BORDER)
        self.holder.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.canvas = tk.Canvas(self.holder, width=min_canvas[0], height=min_canvas[1],
                                bg=T.COLOR_CANVAS_BG, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=2, pady=2)
        self._draw_placeholder()

        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    # ------------------------------------------------------------ 尺寸與座標
    def _canvas_size(self) -> Tuple[int, int]:
        return max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())

    def _offsets(self) -> Tuple[int, int]:
        cw, ch = self._canvas_size()
        return max(0, (cw - self.img_w) // 2), max(0, (ch - self.img_h) // 2)

    def to_real(self, ex: int, ey: int) -> Tuple[Optional[int], Optional[int]]:
        """畫布座標 -> 實際畫面座標；游標不在影像範圍內時回傳 (None, None)。"""
        if not self.raw_w or not self.scale:
            return None, None
        ox, oy = self._offsets()
        ix, iy = ex - ox, ey - oy
        if 0 <= ix <= self.img_w and 0 <= iy <= self.img_h:
            return (min(self.raw_w, max(0, int(ix / self.scale))),
                    min(self.raw_h, max(0, int(iy / self.scale))))
        return None, None

    def to_real_clamped(self, ex: int, ey: int) -> Tuple[int, int]:
        """畫布座標 -> 實際畫面座標，超出影像範圍時夾到邊界。"""
        if not self.raw_w or not self.scale:
            return 0, 0
        ox, oy = self._offsets()
        return (min(self.raw_w, max(0, int((ex - ox) / self.scale))),
                min(self.raw_h, max(0, int((ey - oy) / self.scale))))

    def _to_canvas(self, rx: int, ry: int) -> Tuple[int, int]:
        ox, oy = self._offsets()
        return int(rx * self.scale) + ox, int(ry * self.scale) + oy

    # ------------------------------------------------------------ 繪製
    def _draw_placeholder(self):
        self.canvas.delete("placeholder")
        if self._image is not None:
            return
        cw, ch = self._canvas_size()
        self.canvas.create_text(cw // 2, ch // 2, text=self._placeholder, fill=T.COLOR_TEXT_DIM,
                                font=(T.FONT_FAMILY, 12), justify="center", tags="placeholder",
                                width=max(120, cw - 40))

    def render(self, screen_bgr: Optional[np.ndarray], matched=None):
        """顯示一張畫面；matched 為命中結果時在命中點畫上標記。拖曳框選期間不更新。"""
        if screen_bgr is None or self.is_dragging:
            return
        self._image = screen_bgr
        self._matched = matched
        self._render_frame()

    def redraw(self):
        if self._image is not None:
            self._render_frame()
        else:
            self._draw_placeholder()

    def _render_frame(self):
        if not self.is_open:
            return
        try:
            frame = self._image
            if self._matched is not None and isinstance(self._matched, (list, tuple)) and len(self._matched) >= 4:
                try:
                    tx, ty = int(self._matched[2]), int(self._matched[3])
                    frame = frame.copy()
                    cv2.circle(frame, (tx, ty), 16, (0, 255, 0), 2)
                    cv2.drawMarker(frame, (tx, ty), (0, 255, 0), cv2.MARKER_CROSS, 24, 2)
                except Exception:
                    frame = self._image
            h, w = frame.shape[:2]
            self.raw_w, self.raw_h = w, h
            cw, ch = self._canvas_size()
            self.scale, self.img_w, self.img_h = fit_size(w, h, cw, ch)
            resized = cv2.resize(frame, (self.img_w, self.img_h), interpolation=cv2.INTER_AREA)
            self._photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)))
            self.canvas.delete("placeholder")
            if self.canvas.find_withtag("bg_image"):
                self.canvas.coords("bg_image", cw // 2, ch // 2)
                self.canvas.itemconfig("bg_image", image=self._photo)
            else:
                self.canvas.create_image(cw // 2, ch // 2, image=self._photo, anchor="center", tags="bg_image")
                self.canvas.tag_lower("bg_image")
            self._draw_selection()
            self._draw_marker()
        except Exception:
            pass

    def _draw_selection(self):
        self.canvas.delete("selection_box")
        self.canvas.delete("selection_text")
        if not self.crop_coords:
            return
        rx1, ry1, rx2, ry2 = self.crop_coords
        bx1, by1 = self._to_canvas(rx1, ry1)
        bx2, by2 = self._to_canvas(rx2, ry2)
        self._selection_items(bx1, by1, bx2, by2, f"{rx2 - rx1}×{ry2 - ry1}")

    def _selection_items(self, x1, y1, x2, y2, text):
        if self.canvas.find_withtag("selection_box"):
            self.canvas.coords("selection_box", x1, y1, x2, y2)
        else:
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=self.SELECT_COLOR, width=2,
                                         dash=(4, 2), tags="selection_box")
        tx, ty = x1 + 4, max(14, y1 - 10)
        if self.canvas.find_withtag("selection_text"):
            self.canvas.coords("selection_text", tx, ty)
            self.canvas.itemconfig("selection_text", text=text)
        else:
            self.canvas.create_text(tx, ty, text=text, fill=T.COLOR_TEXT_HIGHLIGHT,
                                    font=(T.FONT_FAMILY, 11, "bold"), anchor="w", tags="selection_text")
        self.canvas.tag_raise("selection_box")
        self.canvas.tag_raise("selection_text")

    def _draw_marker(self):
        self.canvas.delete("marker")
        if not self._marker or not self.raw_w:
            return
        rx, ry = self._marker
        cx, cy = self._to_canvas(rx, ry)
        c = "#FACC15"
        self.canvas.create_oval(cx - 9, cy - 9, cx + 9, cy + 9, outline=c, width=2, tags="marker")
        self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, outline="", fill="#EF4444", tags="marker")
        self.canvas.create_line(cx - 14, cy, cx + 14, cy, fill=c, tags="marker")
        self.canvas.create_line(cx, cy - 14, cx, cy + 14, fill=c, tags="marker")
        cw, _ = self._canvas_size()
        anchor = "w" if cx < cw - 110 else "e"
        dx = 14 if anchor == "w" else -14
        self.canvas.create_text(cx + dx, max(12, cy - 16), text=f"({rx}, {ry})", fill=c,
                                font=(T.MONO_FAMILY, 11, "bold"), anchor=anchor, tags="marker")

    def set_marker(self, coord: Optional[Tuple[int, int]]):
        self._marker = coord
        self._draw_marker()

    # ------------------------------------------------------------ 框選狀態
    def clear_selection(self):
        self.crop_coords = None
        self.canvas.delete("selection_box")
        self.canvas.delete("selection_text")
        if self.btn_crop is not None:
            fg, hover = T.BUTTON_KINDS["neutral"]
            self.btn_crop.configure(state="disabled", text="裁切截圖", fg_color=fg, hover_color=hover)
            self.toolbar.reflow()

    def get_crop(self) -> Optional[np.ndarray]:
        """回傳目前框選範圍的影像（BGR）；沒有畫面或框選時回傳 None。"""
        if self._image is None or not self.crop_coords:
            return None
        rx1, ry1, rx2, ry2 = self.crop_coords
        return self._image[ry1:ry2, rx1:rx2].copy()

    @property
    def image(self) -> Optional[np.ndarray]:
        return self._image

    # ------------------------------------------------------------ 事件
    def _on_canvas_resize(self, _e=None):
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(60, self._after_resize)

    def _after_resize(self):
        self._resize_job = None
        self.redraw()

    def _on_motion(self, e):
        if self.is_dragging:
            return
        rx, ry = self.to_real(e.x, e.y)
        if rx is None:
            return
        if self.crop_coords:
            x1, y1, x2, y2 = self.crop_coords
            self.coords_var.set(f"選取: {x2 - x1}×{y2 - y1} | 游標: ({rx}, {ry})")
        else:
            self.coords_var.set(self._formatter(rx, ry))

    def _on_leave(self, _e):
        if not self.is_dragging and not self.crop_coords:
            self.coords_var.set("")

    def _clamp(self, e) -> Tuple[int, int]:
        cw, ch = self._canvas_size()
        return max(0, min(cw, e.x)), max(0, min(ch, e.y))

    def _on_press(self, e):
        self._drag_start = self._clamp(e)
        self.is_dragging = False
        if self._enable_selection:
            self.clear_selection()

    def _on_drag(self, e):
        if not self._enable_selection or self._drag_start is None:
            return
        cx, cy = self._clamp(e)
        sx, sy = self._drag_start
        if abs(cx - sx) <= 4 and abs(cy - sy) <= 4:
            return
        self.is_dragging = True
        x1, y1, x2, y2 = min(sx, cx), min(sy, cy), max(sx, cx), max(sy, cy)
        rx1, ry1 = self.to_real_clamped(x1, y1)
        rx2, ry2 = self.to_real_clamped(x2, y2)
        rw, rh = max(0, rx2 - rx1), max(0, ry2 - ry1)
        self._selection_items(x1, y1, x2, y2, f"{rw}×{rh}")
        self.coords_var.set(f"框選範圍: {rw}×{rh} (X:{rx1}~{rx2}, Y:{ry1}~{ry2})")

    def _on_release(self, e):
        start = self._drag_start
        self._drag_start = None
        if self.is_dragging and start is not None:
            self.is_dragging = False
            cx, cy = self._clamp(e)
            sx, sy = start
            rx1, ry1 = self.to_real_clamped(min(sx, cx), min(sy, cy))
            rx2, ry2 = self.to_real_clamped(max(sx, cx), max(sy, cy))
            rw, rh = rx2 - rx1, ry2 - ry1
            if rw >= self.MIN_SELECTION and rh >= self.MIN_SELECTION and self._image is not None:
                self.crop_coords = (rx1, ry1, rx2, ry2)
                if self.btn_crop is not None:
                    fg, hover = T.BUTTON_KINDS["success"]
                    self.btn_crop.configure(state="normal", text=f"裁切截圖 ({rw}×{rh})",
                                            fg_color=fg, hover_color=hover)
                    self.toolbar.reflow()
                self.coords_var.set(f"已選取 {rw}×{rh} (X:{rx1}~{rx2}, Y:{ry1}~{ry2})，請按「裁切截圖」")
            else:
                self.clear_selection()
            return
        self.is_dragging = False
        if self._enable_selection:
            self.clear_selection()
        if self._on_click:
            rx, ry = self.to_real(e.x, e.y)
            if rx is not None:
                self._on_click(rx, ry)

    # ------------------------------------------------------------ 收合
    def toggle_fold(self):
        self.is_open = not self.is_open
        if self.is_open:
            self.holder.pack(fill="both", expand=True, padx=12, pady=(0, 10))
            self.btn_fold.configure(text="畫面 ▾")
        else:
            self.holder.pack_forget()
            self.btn_fold.configure(text="畫面 ▸")
        if self._on_fold:
            self._on_fold(self.is_open)
        if self.is_open:
            self.after(80, self.redraw)

    def set_capture_enabled(self, enabled: bool):
        self.btn_capture.configure(state="normal" if enabled else "disabled")
