"""
主視窗 (MainWindow)。

負責視窗外框、標題區（名稱、版本、頁面切換、模擬器裝置列）、存檔資料夾管理，
以及建立四個頁面：模擬器腳本、視窗鏡像腳本、任務流程、即時反應輔助。
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core import storage
from ui import theme as T
from ui import widgets as W
from ui.dialogs import make_dialog, show_changelog
from ui.script_page import EmulatorScriptPage, MirrorScriptPage
from ui.task_page import TaskFlowPage
import version

# 視窗最小尺寸：各頁面在這個尺寸下所有區塊仍能完整顯示
MIN_WIDTH = 1280
MIN_HEIGHT = 640

PAGE_EMULATOR = "emulator"
PAGE_MIRROR = "mirror"
PAGE_TASKS = "tasks"
PAGE_ASSIST = "assist"

NAV_ITEMS = [
    (PAGE_EMULATOR, "模擬器腳本"),
    (PAGE_MIRROR, "視窗鏡像腳本"),
    (PAGE_TASKS, "任務流程"),
    (PAGE_ASSIST, "即時反應輔助"),
]


class MainWindow:
    def __init__(self, root, instance_id: int = 1):
        self.root = root
        self.instance_id = instance_id
        T.apply_appearance()

        suffix = f" (視窗 #{instance_id})" if instance_id > 1 else ""
        self.root.title(f"{version.APP_NAME} v{version.VERSION}{suffix}")
        self._fit_to_screen()
        self.root.configure(fg_color=T.COLOR_BG)

        self.storage_dir = storage.get_storage_dir()
        self.var_storage_display = tk.StringVar(value=self.storage_dir)

        self.pages = {}
        self.page_frames = {}
        self.nav_buttons = {}
        self.current_page = PAGE_EMULATOR
        self.assist_tab = None

        self._build_ui()
        self.show_page(PAGE_EMULATOR)
        self.emulator_page.on_refresh_devices()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)
        self.log_message(f"{version.APP_NAME} v{version.VERSION} 已就緒。")
        if instance_id == 1:
            self.root.after(600, self._show_whats_new_once)

    def _fit_to_screen(self):
        """初始大小依螢幕決定，並確保不小於各區塊完整顯示所需的最小尺寸。"""
        try:
            scr_w, scr_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        except Exception:
            scr_w, scr_h = 1440, 900
        min_w, min_h = min(MIN_WIDTH, scr_w - 20), min(MIN_HEIGHT, scr_h - 80)
        width = max(min_w, min(1560, scr_w - 60))
        height = max(min_h, min(960, scr_h - 110))
        x, y = max(0, (scr_w - width) // 2), max(0, (scr_h - height) // 2 - 20)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min_w, min_h)

    # ======================================================================
    # 版面
    # ======================================================================
    def _build_ui(self):
        outer = W.row(self.root)
        outer.pack(fill="both", expand=True, padx=12, pady=(8, 10))

        header = W.card(outer)
        header.pack(fill="x")
        self._build_title_row(header)
        ctk.CTkFrame(header, height=1, fg_color=T.COLOR_CARD_BORDER).pack(fill="x", padx=12)
        device_row = W.row(header)
        device_row.pack(fill="x", padx=14, pady=(6, 8))

        body = W.row(outer)
        body.pack(fill="both", expand=True, pady=(6, 0))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        for key, _ in NAV_ITEMS:
            frame = W.row(body)
            frame.grid(row=0, column=0, sticky="nsew")
            self.page_frames[key] = frame

        # 模擬器腳本（裝置列放在標題區，所有頁面都看得到）
        self.emulator_page = EmulatorScriptPage(self, self.page_frames[PAGE_EMULATOR])
        self.emulator_page.build_connection_bar(device_row).pack(fill="x")
        self.pages[PAGE_EMULATOR] = self.emulator_page

        # 視窗鏡像腳本
        self.mirror_page = MirrorScriptPage(self, self.page_frames[PAGE_MIRROR], emulator_page=self.emulator_page)
        self.pages[PAGE_MIRROR] = self.mirror_page

        # 任務流程（與模擬器腳本共用裝置與進階設定）
        self.task_page = TaskFlowPage(
            self.page_frames[PAGE_TASKS], bot_instance=self.emulator_page.bot, gui_parent=self.emulator_page,
            log_callback=self.log_message, instance_id=self.instance_id,
        )
        self.emulator_page.task_page = self.task_page
        self.mirror_page.task_page = self.task_page
        self.pages[PAGE_TASKS] = self.task_page

        self._build_assist_page(self.page_frames[PAGE_ASSIST])

    def _build_title_row(self, parent):
        flow = W.FlowFrame(parent, hgap=6)
        flow.pack(fill="x", padx=14, pady=(8, 6))
        flow.add(W.label(flow, version.APP_NAME, size=15, bold=True, height=28))
        flow.add(W.button(flow, f"v{version.VERSION}", self.on_show_changelog, kind="neutral", width=58, height=22,
                          size=10, font=T.mono(10, True), text_color=T.COLOR_TEXT_INFO))
        flow.add(ctk.CTkFrame(flow, width=10, height=1, fg_color="transparent"))
        for key, text in NAV_ITEMS:
            btn = W.button(flow, text, lambda k=key: self.show_page(k), width=104, size=12)
            self.nav_buttons[key] = flow.add(btn)
        flow.add(W.button(flow, "存檔資料夾", self.on_open_storage_dialog, width=84, bold=False), right=True)
        flow.add(W.button(flow, "更新紀錄", self.on_show_changelog, width=72, bold=False), right=True)
        flow.add(W.button(flow, "＋ 新視窗", self.on_open_new_window, width=76, bold=False), right=True)

    def _build_assist_page(self, parent):
        """
        即時反應輔助：依畫面即時偵測並在精準時機點擊的實驗功能，目前停用。
        保留原本的頁面與程式，並以遮罩鎖定畫面。
        """
        try:
            from ui.aim_page import BattingAssistTab
            self.assist_tab = BattingAssistTab(parent, bot_instance=self.emulator_page.bot,
                                               gui_parent=self.emulator_page, log_callback=self.log_message)
        except Exception:
            self.assist_tab = None

        overlay = ctk.CTkFrame(parent, fg_color=T.COLOR_INPUT_BG, corner_radius=12, border_width=1,
                               border_color=T.COLOR_INPUT_BORDER)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        overlay.lift()
        box = W.card(overlay, corner_radius=16, width=520, height=230)
        box.place(relx=0.5, rely=0.5, anchor="center")
        box.pack_propagate(False)
        widgets = [
            overlay, box,
            W.label(box, "功能開發中", size=22, bold=True, color=T.COLOR_PAUSED),
            W.label(box, "即時反應輔助目前暫停使用，畫面已鎖定。\n"
                         "背景計算、視窗截圖與按鍵模擬皆未啟動。\n"
                         "請使用「模擬器腳本」、「視窗鏡像腳本」或「任務流程」。",
                    size=13, color=T.COLOR_TEXT_MUTED, justify="center"),
            W.label(box, "功能已停用", bold=True, color=T.COLOR_TEXT_DIM),
        ]
        widgets[2].pack(pady=(40, 10))
        widgets[3].pack(pady=(0, 14))
        widgets[4].pack()
        for w in widgets:
            w.bind("<Button-1>", lambda e: self._warn_assist_disabled())

    def _warn_assist_disabled(self):
        messagebox.showwarning("提示", "即時反應輔助仍在開發中，功能尚不完整。", parent=self.root)

    # ======================================================================
    # 頁面切換
    # ======================================================================
    def show_page(self, key: str):
        self.current_page = key
        self.page_frames[key].tkraise()
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=T.COLOR_BTN_PRIMARY, hover_color=T.COLOR_BTN_PRIMARY_HOVER, text_color="#FFFFFF")
            else:
                btn.configure(fg_color=T.COLOR_BTN_DARK, hover_color=T.COLOR_BTN_DARK_HOVER,
                              text_color=T.COLOR_TEXT_MUTED)
        if key == PAGE_ASSIST:
            self._warn_assist_disabled()
            return
        page = self.pages.get(key)
        if page is not None and hasattr(page, "on_page_shown"):
            page.on_page_shown()

    def is_page_visible(self, page) -> bool:
        return self.pages.get(self.current_page) is page

    # ======================================================================
    # 共用服務
    # ======================================================================
    def log_message(self, text: str):
        self.emulator_page.log_message(text)

    def on_template_snipped(self, path: str):
        """任一頁面裁切了新的模板圖片後，讓其他頁面的「帶入最新截圖」也能取得。"""
        for page in (self.emulator_page, getattr(self, "mirror_page", None), getattr(self, "task_page", None)):
            if page is not None:
                page.last_snipped_template = path

    # ---- 存檔資料夾
    def set_storage_dir(self, new_dir: str):
        """切換存檔資料夾：各頁面的自動存檔與模板搜尋位置一併更新。"""
        self.storage_dir = os.path.abspath(os.path.expanduser(new_dir or storage.PROJECT_DIR))
        storage.persist_storage_dir(self.storage_dir)
        self.var_storage_display.set(self.storage_dir)
        for page in (self.emulator_page, self.mirror_page):
            page.on_storage_changed()
        self.task_page.presets_dir = self.storage_dir
        self.task_page.save_file = self.emulator_page.task_save_file
        self.task_page.reload_presets()

    def adopt_storage_dir(self, new_dir: str):
        """
        另存設定檔後沿用該檔案所在資料夾作為存檔資料夾：
        只更新資料夾與模板搜尋位置，不改動各頁面目前的自動存檔檔名。
        """
        self.storage_dir = os.path.abspath(new_dir)
        storage.persist_storage_dir(self.storage_dir)
        self.var_storage_display.set(self.storage_dir)
        for page in (self.emulator_page, self.mirror_page):
            page.bot.set_templates_dir(self.storage_dir)

    def on_open_storage_dialog(self):
        dlg = make_dialog(self.root, "存檔資料夾", 620, 210)
        box = W.card(dlg)
        box.pack(fill="both", expand=True, padx=16, pady=16)
        W.label(box, "存檔資料夾", size=16, bold=True, color=T.COLOR_TEXT_HIGHLIGHT).pack(anchor="w", padx=16, pady=(14, 2))
        W.label(box, "設定檔、任務存檔與模板圖片都存放在這個資料夾。", size=12,
                color=T.COLOR_TEXT_MUTED).pack(anchor="w", padx=16)
        ctk.CTkEntry(box, textvariable=self.var_storage_display, state="readonly", height=30, font=T.mono(11),
                     fg_color=T.COLOR_INPUT_BG, border_color=T.COLOR_INPUT_BORDER).pack(fill="x", padx=16, pady=10)
        r = W.row(box)
        r.pack(fill="x", padx=16, pady=(0, 14), side="bottom")

        def change():
            d = filedialog.askdirectory(parent=dlg, initialdir=self.storage_dir, title="選擇存檔資料夾")
            if d:
                self.set_storage_dir(d)
                self.log_message(f"存檔資料夾已切換至: {d}")

        def open_dir():
            try:
                storage.open_in_file_manager(self.storage_dir)
            except Exception as ex:
                messagebox.showerror("錯誤", f"無法開啟存檔資料夾: {ex}", parent=dlg)

        W.button(r, "關閉", dlg.destroy, width=72, height=30, bold=False).pack(side="right")
        W.button(r, "變更資料夾", change, kind="primary", width=96, height=30).pack(side="right", padx=6)
        W.button(r, "在檔案管理員開啟", open_dir, width=130, height=30, bold=False).pack(side="right")
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    # ---- 版本與更新紀錄
    def on_show_changelog(self):
        show_changelog(self.root)

    def _show_whats_new_once(self):
        """版本更新後第一次啟動時，自動顯示這一版更新了哪些功能。"""
        settings = storage.load_user_settings()
        if settings.get("last_seen_version") == version.VERSION:
            return
        if os.environ.get(storage.ENV_STORAGE_DIR):
            return
        storage.save_user_settings(last_seen_version=version.VERSION)
        show_changelog(self.root, only_latest=True)

    # ---- 視窗
    def on_open_new_window(self):
        MainWindow(ctk.CTkToplevel(self.root), instance_id=self.instance_id + 1)

    def on_close_window(self):
        for page in (self.emulator_page, self.mirror_page):
            try:
                page.shutdown()
            except Exception:
                pass
        try:
            self.task_page.auto_save_config()
            self.task_page.engine.stop()
        except Exception:
            pass
        if self.assist_tab is not None:
            try:
                self.assist_tab.on_close()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = ctk.CTk()
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
