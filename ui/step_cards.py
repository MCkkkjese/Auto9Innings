"""
步驟卡片編輯器 (StepListEditor)。

一個循序腳本頁面有兩份清單：「優先動作」與「一般步驟」。兩者的卡片外觀、
新增／刪除／拖曳排序、存檔格式與執行設定幾乎相同，只有少數欄位不同
（優先動作有「條件存在時重複執行」，一般步驟有「超時未命中跳過」），
因此全部由這個類別以同一份程式碼處理，模擬器頁與視窗鏡像頁共用。
"""
import os
import tkinter as tk
from typing import Any, Dict, List, Optional

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

from core import options as O
from core.imaging import imread_unicode
from core.textutil import num, split_keywords
from ui import theme as T
from ui import widgets as W
from ui.dialogs import ask_insert_position

PRIORITY = "priority"
NORMAL = "normal"

# 欄位預設值（同時決定 tk 變數型別）
_COMMON_FIELDS: Dict[str, Any] = {
    "enabled": True,
    "name": "",
    "target_type": O.TARGET_TEXT,
    "template_image": "",
    "image_threshold": 0.80,
    "image_multiscale": False,
    "keywords": "",
    "exclude_keywords": "",
    "action": O.ACTION_TARGET_IMAGE,
    "custom_x": 960,
    "custom_y": 540,
    "delay": 2.5,
    "roi": "右下角區域",
    "repeat_enabled": False,
    "repeat_mode": "持續連點",
    "repeat_count": 5,
    "repeat_speed": 0.25,
    "repeat_area": "右下角區域",
    "repeat_custom_x": 960,
    "repeat_custom_y": 540,
    "tg_enabled": False,
    "tg_message": "",
    "tg_attach_screenshot": True,
    "task_target_mode": O.TASK_MODE_FULL,
    "task_target_item": "",
    "task_cooldown": 60.0,
}

_KIND_INFO = {
    PRIORITY: {
        "label": "優先動作",
        "fields": {"delay": 2.0, "roi": "全畫面比對", "while_condition": False},
        "run_delay_default": 1.0,
        "empty_text": "尚無優先動作，可用上方「＋ 優先動作」或「＋ 任務跳轉」新增",
    },
    NORMAL: {
        "label": "步驟",
        "fields": {"timeout_enabled": False, "timeout_seconds": 20},
        "run_delay_default": 2.5,
        "empty_text": "尚無一般步驟，可用上方「＋ 一般步驟」新增",
    },
}


def _fields_for(kind: str) -> Dict[str, Any]:
    fields = dict(_COMMON_FIELDS)
    fields.update(_KIND_INFO[kind]["fields"])
    return fields


def _make_var(default: Any, value: Any):
    """依預設值型別建立 tk 變數；值無法轉型時退回預設值。"""
    try:
        if isinstance(default, bool):
            return tk.BooleanVar(value=bool(value))
        if isinstance(default, int):
            return tk.IntVar(value=int(float(value)))
        if isinstance(default, float):
            return tk.DoubleVar(value=float(value))
        return tk.StringVar(value=str(value))
    except Exception:
        return _make_var(default, default)


def _read_var(var, default: Any) -> Any:
    """安全讀取 tk 變數（輸入框為空時回傳預設值）。"""
    if isinstance(default, bool):
        return bool(num(var, default, bool))
    if isinstance(default, int):
        return num(var, default, lambda v: int(float(v)))
    if isinstance(default, float):
        return num(var, default, float)
    return num(var, default, str)


class StepListEditor:
    """
    管理「優先動作」與「一般步驟」兩份步驟卡片清單。

    host 需提供：
      var_recognition_mode, root, task_page (可為 None), is_loading_config(),
      notify_steps_changed(), resolve_image_path(name), log_message(text),
      on_snip_template(step), on_browse_template(step), on_apply_last_snippet(step),
      on_open_templates_folder()
    """

    def __init__(self, host):
        self.host = host
        self.lists: Dict[str, List[Dict[str, Any]]] = {PRIORITY: [], NORMAL: []}
        self._containers: Dict[str, ctk.CTkFrame] = {}
        self._empty_labels: Dict[str, ctk.CTkLabel] = {}
        self._count_labels: Dict[str, ctk.CTkLabel] = {}
        self.scroll: Optional[ctk.CTkScrollableFrame] = None

    # 方便外部以屬性取得兩份清單
    @property
    def priority(self) -> List[Dict[str, Any]]:
        return self.lists[PRIORITY]

    @property
    def normal(self) -> List[Dict[str, Any]]:
        return self.lists[NORMAL]

    # ------------------------------------------------------------------ 版面
    def build(self, parent) -> ctk.CTkScrollableFrame:
        self.scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=8, height=60)
        self.scroll._scrollbar.configure(height=0)   # 預設最小高度 200 會在空間不足時超出卡片
        self._build_section(PRIORITY, "優先動作", "由上而下比對，命中即中斷目前流程並執行", T.COLOR_TEXT_HIGHLIGHT, (0, 6))
        self._build_section(NORMAL, "一般步驟", "依序循環執行", T.COLOR_TEXT_INFO, (6, 0))
        return self.scroll

    def _build_section(self, kind: str, title: str, hint: str, color: str, pady):
        section = W.row(self.scroll)
        section.pack(fill="x", pady=pady)
        head = W.row(section)
        head.pack(fill="x", pady=(2, 4))
        W.label(head, title, size=12, bold=True, color=color).pack(side="left")
        self._count_labels[kind] = W.label(head, "(0)", color=T.COLOR_TEXT_MUTED)
        self._count_labels[kind].pack(side="left", padx=4)
        W.label(head, hint, size=10, color=T.COLOR_TEXT_DIM).pack(side="left", padx=4)
        self._containers[kind] = W.row(section)
        self._containers[kind].pack(fill="x")
        self._empty_labels[kind] = W.label(section, _KIND_INFO[kind]["empty_text"], color=T.COLOR_TEXT_DIM)
        self._empty_labels[kind].pack(pady=4)

    def _is_image_mode(self) -> bool:
        return O.is_image_mode(self.host.var_recognition_mode.get())

    # ------------------------------------------------------------------ 新增／刪除
    def add_interactive(self, kind: str, task_trigger: bool = False):
        """由工具列按鈕呼叫：先詢問插入位置，再建立一張展開的新卡片。"""
        info = _KIND_INFO[kind]
        item_label = "任務跳轉步驟" if task_trigger else ("優先步驟" if kind == PRIORITY else "步驟")
        idx = ask_insert_position(
            self.host.root, self.lists[kind], item_label,
            title=f"新增{'任務跳轉' if task_trigger else info['label']} - 選擇插入位置",
        )
        if idx is None:
            return None
        is_img = self._is_image_mode()
        if task_trigger:
            data = {"name": f"任務跳轉 {idx + 1}", "action": O.ACTION_TASK_FLOW,
                    "task_target_mode": O.TASK_MODE_FULL, "task_cooldown": 60.0}
        else:
            data = {
                "name": f"{'優先' if kind == PRIORITY else '步驟'} {idx + 1}",
                "target_type": O.TARGET_IMAGE if is_img else O.TARGET_TEXT,
                "action": O.ACTION_TARGET_IMAGE if is_img else O.ACTION_TARGET_TEXT,
            }
        step = self.add(kind, data, insert_index=idx, expanded=True, from_file=False)
        self.host.notify_steps_changed()
        return step

    def add(self, kind: str, data: Optional[dict] = None, insert_index: Optional[int] = None,
            expanded: bool = False, from_file: bool = True) -> Dict[str, Any]:
        """
        建立一張步驟卡片。data 為存檔格式的 dict（可省略欄位）。
        from_file=True 時套用讀檔的相容規則（關鍵字清單、telegram 巢狀設定、
        優先動作缺少 while_condition 時視為開啟）。
        """
        values = self._values_from_data(kind, data or {}, from_file)
        return self._build_card(kind, values, insert_index, expanded)

    def _values_from_data(self, kind: str, data: dict, from_file: bool) -> Dict[str, Any]:
        values = _fields_for(kind)
        if from_file:
            values["name"] = "優先動作" if kind == PRIORITY else "步驟"
            if kind == PRIORITY:
                values["while_condition"] = True
        for key in values:
            if key in data and data[key] is not None:
                values[key] = data[key]
        for key in ("keywords", "exclude_keywords"):
            if isinstance(values[key], (list, tuple)):
                values[key] = ", ".join(str(k) for k in values[key])
        tg = data.get("telegram")
        if isinstance(tg, dict):
            values["tg_enabled"] = tg.get("enabled", values["tg_enabled"])
            values["tg_message"] = tg.get("message", values["tg_message"])
            values["tg_attach_screenshot"] = tg.get("attach_screenshot", values["tg_attach_screenshot"])
        if "roi" not in data and "roi_name" in data:
            values["roi"] = data["roi_name"]
        values["target_type"] = O.normalize_target_type(values["target_type"])
        is_img = self._is_image_mode() or ("圖片" in values["target_type"])
        values["action"] = O.normalize_action(data.get("action", ""), is_image=is_img)
        return values

    def delete(self, step: Dict[str, Any]):
        kind = step["type"]
        steps = self.lists[kind]
        if step in steps:
            steps.remove(step)
            step["frame"].destroy()
            self._renumber(kind)
            self.host.notify_steps_changed()

    def clear(self, kind: Optional[str] = None):
        for k in ([kind] if kind else [PRIORITY, NORMAL]):
            for step in self.lists[k]:
                step["frame"].destroy()
            self.lists[k].clear()
            self._renumber(k)

    def load(self, kind: str, items: list):
        """以存檔資料取代指定清單的全部卡片。"""
        self.clear(kind)
        for data in items:
            if isinstance(data, dict):
                self.add(kind, data)

    # ------------------------------------------------------------------ 編號與排序
    def _renumber(self, kind: str):
        steps = self.lists[kind]
        prefix = "P" if kind == PRIORITY else ""
        for i, step in enumerate(steps, start=1):
            step["lbl_num"].configure(text=f"{prefix}{i}")
        self._count_labels[kind].configure(text=f"({len(steps)})")
        if steps:
            self._empty_labels[kind].pack_forget()
        else:
            self._empty_labels[kind].pack(pady=4)

    def _repack(self, kind: str):
        for step in self.lists[kind]:
            step["frame"].pack_forget()
        for step in self.lists[kind]:
            step["frame"].pack(fill="x", pady=4, padx=2)
        self._renumber(kind)

    def _bind_drag(self, handle, step: Dict[str, Any]):
        """拖曳卡片左側把手可上下調整順序。"""
        kind = step["type"]
        state = {}

        def on_start(e):
            steps = self.lists[kind]
            state["y"] = e.y_root
            state["idx"] = steps.index(step) if step in steps else 0

        def on_motion(e):
            steps = self.lists[kind]
            if step not in steps or "y" not in state:
                return
            moved = int((e.y_root - state["y"]) // 40)
            new_idx = max(0, min(len(steps) - 1, state["idx"] + moved))
            if new_idx != steps.index(step):
                steps.remove(step)
                steps.insert(new_idx, step)
                self._repack(kind)

        def on_end(_e):
            self.host.notify_steps_changed()

        handle.bind("<Button-1>", on_start)
        handle.bind("<B1-Motion>", on_motion)
        handle.bind("<ButtonRelease-1>", on_end)

    # ------------------------------------------------------------------ 批次操作
    def all_steps(self) -> List[Dict[str, Any]]:
        return self.lists[PRIORITY] + self.lists[NORMAL]

    def expanded_step(self) -> Optional[Dict[str, Any]]:
        """回傳第一張展開中的卡片（優先動作在前）。"""
        for step in self.all_steps():
            if step["expanded"].get():
                return step
        return None

    def refresh_mode(self):
        """辨識模式切換後，更新所有卡片顯示的欄位。"""
        for step in self.all_steps():
            step["_refresh_target_ui"]()

    def refresh_thumbs(self):
        for step in self.all_steps():
            step["_update_thumb"]()

    # ------------------------------------------------------------------ 序列化
    def serialize(self, kind: str) -> List[dict]:
        """輸出存檔格式。"""
        fields = _fields_for(kind)
        result = []
        for step in self.lists[kind]:
            item = {key: _read_var(step[key], default) for key, default in fields.items()}
            item["target_type"] = O.normalize_target_type(item["target_type"])
            item["template_image"] = item["template_image"].strip()
            result.append(item)
        return result

    def active_config(self, kind: str, tg_token: str, tg_chat_id: str) -> List[dict]:
        """輸出執行引擎 (GameBot.run_loop) 使用的步驟設定。"""
        info = _KIND_INFO[kind]
        is_img = self._is_image_mode()
        target_type = O.TARGET_IMAGE if is_img else O.TARGET_TEXT
        result = []
        for step in self.lists[kind]:
            keywords = split_keywords(step["keywords"].get())
            template = step["template_image"].get().strip()
            valid_target = bool(template) if is_img else bool(keywords)
            delay = num(step["delay"], info["run_delay_default"])
            repeat_on = bool(step["repeat_enabled"].get())
            action = step["action"].get()
            rep_x = num(step["repeat_custom_x"], 0, int)
            rep_y = num(step["repeat_custom_y"], 0, int)
            cfg = {
                "name": step["name"].get().strip() or info["label"],
                "target_type": target_type,
                "template_image": template,
                "image_threshold": num(step["image_threshold"], 0.80),
                "image_multiscale": bool(step["image_multiscale"].get()),
                "keywords": keywords,
                "exclude_keywords": split_keywords(step["exclude_keywords"].get()),
                "action": "custom_coord" if O.is_custom_coord_action(action) else action,
                "custom_x": num(step["custom_x"], 0, int),
                "custom_y": num(step["custom_y"], 0, int),
                "delay": delay,
                "delay_min": max(0.05, delay - 0.15),
                "delay_max": delay + 0.15,
                "enabled": bool(step["enabled"].get()) and valid_target,
                "roi": O.roi_to_tuple(step["roi"].get()),
                "roi_name": step["roi"].get(),
                "repeat_enabled": repeat_on,
                "repeat_mode": "count" if step["repeat_mode"].get() == "指定次數" else "until_next",
                "repeat_count": num(step["repeat_count"], 15, int) if repeat_on else 1,
                "repeat_speed": num(step["repeat_speed"], 0.3),
                "repeat_area": step["repeat_area"].get(),
                "repeat_custom_x": rep_x,
                "repeat_custom_y": rep_y,
                "repeat_custom_coord": (rep_x, rep_y),
                "telegram": {
                    "enabled": bool(step["tg_enabled"].get()),
                    "message": step["tg_message"].get().strip(),
                    "attach_screenshot": bool(step["tg_attach_screenshot"].get()),
                    "token": tg_token,
                    "chat_id": tg_chat_id,
                },
                "task_target_mode": step["task_target_mode"].get(),
                "task_target_item": step["task_target_item"].get(),
                "task_cooldown": num(step["task_cooldown"], 60.0),
            }
            if kind == PRIORITY:
                cfg["type"] = "priority"
                cfg["while_condition"] = bool(step["while_condition"].get())
                cfg["max_continuous"] = 25
            else:
                cfg["timeout_enabled"] = bool(step["timeout_enabled"].get())
                cfg["timeout_seconds"] = num(step["timeout_seconds"], 15, int)
            result.append(cfg)
        return result

    # ------------------------------------------------------------------ 卡片
    def _summary(self, step: Dict[str, Any]) -> str:
        """收合狀態下顯示的一行摘要。"""
        kind = step["type"]
        is_img = self._is_image_mode()
        action = step["action"].get()
        delay_default = _KIND_INFO[kind]["run_delay_default"]
        if O.is_custom_coord_action(action):
            act = f"點擊座標 ({num(step['custom_x'], 0, int)}, {num(step['custom_y'], 0, int)})"
        elif O.is_task_flow_action(action):
            mode, item = step["task_target_mode"].get(), step["task_target_item"].get()
            act = f"跳轉: {item if mode != O.TASK_MODE_FULL and item else mode}"
        elif action in (O.ACTION_REPEAT, O.ACTION_WAIT):
            act = action
        else:
            act = "點擊目標圖片" if is_img else "點擊目標文字"
        parts = []
        if is_img:
            template = step["template_image"].get().strip()
            name = os.path.basename(template) if template else "(未選圖)"
            parts.append(f"模板: {name} ({num(step['image_threshold'], 0.80):.2f})")
        parts += [act, step["roi"].get(), f"延遲 {num(step['delay'], delay_default):g}s"]
        if is_img and step["image_multiscale"].get():
            parts.append("多尺度")
        if kind == PRIORITY and step["while_condition"].get():
            parts.append("存在時重複")
        if step["repeat_enabled"].get():
            rep = "連點"
            if step["repeat_mode"].get() == "指定次數":
                rep += f"×{num(step['repeat_count'], 15, int)}"
            area = step["repeat_area"].get()
            if "自訂" in area:
                area = f"({num(step['repeat_custom_x'], 0, int)}, {num(step['repeat_custom_y'], 0, int)})"
            parts.append(f"{rep}@{area}")
        if kind == NORMAL and step["timeout_enabled"].get():
            parts.append(f"{num(step['timeout_seconds'], 20, int)}s 超時跳過")
        if not is_img:
            exclude = step["exclude_keywords"].get().strip()
            if exclude:
                parts.append(f"排除: {exclude}")
        if step["tg_enabled"].get():
            parts.append("Telegram+截圖" if step["tg_attach_screenshot"].get() else "Telegram")
        return "  ·  ".join(parts)

    def _build_card(self, kind: str, values: Dict[str, Any], insert_index: Optional[int],
                    expanded: bool) -> Dict[str, Any]:
        steps = self.lists[kind]
        host = self.host
        color = T.COLOR_PRIORITY if kind == PRIORITY else T.STEP_COLORS[len(steps) % len(T.STEP_COLORS)]
        frame = ctk.CTkFrame(self._containers[kind], fg_color=T.COLOR_CARD_ITEM, corner_radius=8,
                             border_width=1, border_color=color)
        frame.pack(fill="x", pady=4, padx=2)

        fields = _fields_for(kind)
        step: Dict[str, Any] = {key: _make_var(default, values.get(key, default)) for key, default in fields.items()}
        step.update({"type": kind, "expanded": tk.BooleanVar(value=expanded), "frame": frame,
                     "border_color": color, "_thumb_img": None})
        if insert_index is not None and 0 <= insert_index <= len(steps):
            steps.insert(insert_index, step)
        else:
            steps.append(step)

        def on_var_changed(*_):
            if not host.is_loading_config():
                host.notify_steps_changed()

        for key in fields:
            step[key].trace_add("write", on_var_changed)

        # ---- 標題列
        head = W.row(frame)
        head.pack(fill="x", padx=8, pady=6)
        handle = ctk.CTkLabel(head, text="☰", font=T.font(13, True), text_color=color, width=16, cursor="hand2")
        handle.pack(side="left", padx=(0, 4))
        self._bind_drag(handle, step)
        W.checkbox(head, "", step["enabled"]).pack(side="left", padx=(0, 2))
        step["lbl_num"] = ctk.CTkLabel(head, text="", font=T.font(12, True), text_color=color, width=26)
        step["lbl_num"].pack(side="left")
        W.entry(head, step["name"], width=88, height=26, monospace=False).pack(side="left", padx=(0, 4))

        btn_toggle = W.button(head, "▸", lambda: step["expanded"].set(not step["expanded"].get()),
                              width=26, height=26)
        btn_toggle.pack(side="right", padx=(2, 0))
        W.button(head, "✕", lambda: self.delete(step), kind="danger", width=26, height=26).pack(side="right", padx=2)

        # 文字模式：關鍵字 + 打勾／叉叉符號
        box_text = W.row(head)

        def add_symbol(tag: str):
            current = step["keywords"].get().strip()
            step["keywords"].set(f"{current}, {tag}" if current else tag)

        W.button(box_text, "✕", lambda: add_symbol("[叉叉]"), width=24, height=26).pack(side="right", padx=1)
        W.button(box_text, "✓", lambda: add_symbol("[打勾]"), width=24, height=26).pack(side="right", padx=1)
        W.entry(box_text, step["keywords"], height=26, monospace=False, width=60,
                placeholder_text="關鍵字 (以逗號分隔)").pack(side="left", fill="x", expand=True)

        # 圖片模式：模板檔名 + 瀏覽／截圖／帶入
        box_image = W.row(head)
        W.button(box_image, "帶入", lambda: host.on_apply_last_snippet(step), kind="warning",
                 width=40, height=26, size=10).pack(side="right", padx=1)
        W.button(box_image, "截圖", lambda: host.on_snip_template(step), kind="primary",
                 width=40, height=26, size=10).pack(side="right", padx=1)
        W.button(box_image, "瀏覽", lambda: host.on_browse_template(step),
                 width=40, height=26, size=10, bold=False).pack(side="right", padx=1)
        W.entry(box_image, step["template_image"], height=26, monospace=False, width=60,
                placeholder_text="模板圖檔 (如: 開始.png)").pack(side="left", fill="x", expand=True, padx=(0, 2))

        lbl_summary = W.label(frame, "", color=T.COLOR_TEXT_MUTED, anchor="w", justify="left", wraplength=440)
        frame.bind("<Configure>", lambda e: lbl_summary.configure(wraplength=max(160, e.width - 36)), add="+")
        detail = W.row(frame)
        ui: Dict[str, Any] = {}   # 展開內容的元件，第一次展開時才建立

        # ---- 縮圖
        def update_thumb(*_):
            lbl = ui.get("thumb")
            if lbl is None:
                return
            name = step["template_image"].get().strip()
            if not name:
                lbl.configure(image="", text="未選圖", fg=T.COLOR_TEXT_DIM, width=8, height=2)
                step["_thumb_img"] = None
                return
            path = host.resolve_image_path(name)
            bgr = imread_unicode(path) if path and os.path.exists(path) else None
            if bgr is None:
                lbl.configure(image="", text="缺檔", fg=T.COLOR_STOPPED, width=8, height=2)
                step["_thumb_img"] = None
                return
            h, w = bgr.shape[:2]
            scale = min(36 / max(1, w), 36 / max(1, h))
            tw, th = max(1, int(w * scale)), max(1, int(h * scale))
            small = cv2.resize(bgr, (tw, th), interpolation=cv2.INTER_AREA)
            photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
            lbl.configure(image=photo, text="", width=tw, height=th)
            step["_thumb_img"] = photo

        step["_update_thumb"] = update_thumb
        step["template_image"].trace_add("write", update_thumb)

        # ---- 依狀態顯示／隱藏展開內容的各區塊
        def refresh_sections(*_):
            if not ui:
                return
            action = step["action"].get()
            is_img = self._is_image_mode()
            ui["row_action"].set_visible(ui["act_xy"], O.is_custom_coord_action(action))
            if O.is_task_flow_action(action):
                _show(ui["task_box"], True, fill="x", pady=(4, 0), before=ui["anchor_task"])
                ui["update_task_items"]()
            else:
                _show(ui["task_box"], False)
            _show(ui["row_exclude"], not is_img, fill="x", pady=(4, 0), before=ui["anchor_target"])
            _show(ui["image_box"], is_img, fill="x", pady=(4, 0), before=ui["anchor_target"])
            repeat_on = bool(step["repeat_enabled"].get())
            _show(ui["repeat_box"], repeat_on, fill="x", pady=(2, 0), before=ui["anchor_repeat"])
            if repeat_on:
                ui["repeat_opts"].set_visible(ui["repeat_count_box"], step["repeat_mode"].get() == "指定次數")
                ui["repeat_loc"].set_visible(ui["repeat_xy"], "自訂" in step["repeat_area"].get())
            if "timeout_box" in ui:
                ui["row_timeout"].set_visible(ui["timeout_box"], bool(step["timeout_enabled"].get()))
            tg_on = bool(step["tg_enabled"].get())
            ui["row_tg"].set_visible(ui["tg_attach"], tg_on)
            _show(ui["tg_msg_box"], tg_on, fill="x", pady=(2, 0), before=ui["anchor_tg"])

        for key in ("action", "repeat_enabled", "repeat_mode", "repeat_area", "tg_enabled"):
            step[key].trace_add("write", refresh_sections)
        if kind == NORMAL:
            step["timeout_enabled"].trace_add("write", refresh_sections)

        # ---- 辨識模式切換
        def refresh_target_ui(*_):
            is_img = self._is_image_mode()
            step["target_type"].set(O.TARGET_IMAGE if is_img else O.TARGET_TEXT)
            action = step["action"].get()
            if O.is_target_center_action(action):
                wanted = O.ACTION_TARGET_IMAGE if is_img else O.ACTION_TARGET_TEXT
                if action != wanted:
                    step["action"].set(wanted)
            if "menu_action" in ui:
                ui["menu_action"].configure(values=O.ACTION_OPTIONS_IMAGE if is_img else O.ACTION_OPTIONS_TEXT)
            if is_img:
                box_text.pack_forget()
                box_image.pack(side="left", fill="x", expand=True, padx=(0, 4))
            else:
                box_image.pack_forget()
                box_text.pack(side="left", fill="x", expand=True, padx=(0, 4))
            refresh_sections()
            if is_img:
                update_thumb()
            if not step["expanded"].get():
                lbl_summary.configure(text=self._summary(step))

        step["_refresh_target_ui"] = refresh_target_ui

        # ---- 展開／收合
        def refresh_expanded(*_):
            if step["expanded"].get():
                if not ui:
                    self._build_detail(step, detail, ui)
                    refresh_sections()
                    update_thumb()
                btn_toggle.configure(text="▾")
                lbl_summary.pack_forget()
                detail.pack(fill="x", padx=10, pady=(0, 8))
            else:
                btn_toggle.configure(text="▸")
                detail.pack_forget()
                lbl_summary.configure(text=self._summary(step))
                lbl_summary.pack(fill="x", padx=12, pady=(0, 6))

        step["expanded"].trace_add("write", refresh_expanded)
        refresh_target_ui()
        refresh_expanded()

        if insert_index is not None:
            self._repack(kind)
        else:
            self._renumber(kind)
        return step

    def _build_detail(self, step: Dict[str, Any], detail: ctk.CTkFrame, ui: Dict[str, Any]):
        """建立卡片展開後的設定內容。各列都使用自動換行容器，寬度不足時換行而不裁切。"""
        host = self.host
        kind = step["type"]
        is_img = self._is_image_mode()
        muted = T.COLOR_TEXT_MUTED

        def anchor() -> tk.Frame:
            # 永遠存在的 1px 定位點：條件顯示的區塊以 before=anchor 插回固定位置
            a = tk.Frame(detail, height=1, bg=T.COLOR_CARD_ITEM)
            a.pack(fill="x")
            return a

        # 動作
        row_action = W.FlowFrame(detail)
        row_action.pack(fill="x", pady=(4, 2))
        row_action.add(W.label(row_action, "動作", bold=True, height=24))
        ui["menu_action"] = row_action.add(W.option_menu(
            row_action, step["action"], O.ACTION_OPTIONS_IMAGE if is_img else O.ACTION_OPTIONS_TEXT, width=176))
        act_xy = W.row(row_action)
        W.label(act_xy, "X", size=10, color=muted).pack(side="left")
        W.entry(act_xy, step["custom_x"]).pack(side="left", padx=(3, 6))
        W.label(act_xy, "Y", size=10, color=muted).pack(side="left")
        W.entry(act_xy, step["custom_y"]).pack(side="left", padx=(3, 6))
        W.label(act_xy, "點預覽畫面可取點", size=10, color=T.COLOR_BTN_WARN).pack(side="left")
        row_action.add(act_xy)
        row_action.set_visible(act_xy, False)
        ui["row_action"] = row_action

        ui["act_xy"] = act_xy

        # 比對範圍與延遲
        row_roi = W.FlowFrame(detail)
        row_roi.pack(fill="x", pady=2)
        row_roi.add(W.label(row_roi, "比對範圍", bold=True, height=24))
        row_roi.add(W.option_menu(row_roi, step["roi"], O.ROI_OPTIONS, width=124))
        box_delay = W.row(row_roi)
        W.label(box_delay, "延遲", bold=True).pack(side="left", padx=(6, 4))
        W.entry(box_delay, step["delay"], width=44).pack(side="left")
        W.label(box_delay, "秒", color=muted).pack(side="left", padx=(3, 0))
        row_roi.add(box_delay)

        # 任務跳轉設定（動作為「執行任務清單」時顯示）
        task_box = ctk.CTkFrame(detail, fg_color="#1E1B4B", corner_radius=6, border_width=1,
                                border_color=T.COLOR_BTN_VIOLET)
        violet = "#A78BFA"
        tf1 = W.FlowFrame(task_box)
        tf1.pack(fill="x", padx=8, pady=(6, 2))
        tf1.add(W.label(tf1, "跳轉目標", bold=True, color=violet, height=24))
        tf1.add(W.option_menu(tf1, step["task_target_mode"], O.TASK_TARGET_MODES, width=126))
        menu_item = tf1.add(W.option_menu(tf1, step["task_target_item"], ["(無)"], width=180))

        def update_task_items(*_):
            mode = step["task_target_mode"].get()
            task_page = getattr(host, "task_page", None)
            if mode == O.TASK_MODE_BLOCK:
                choices = task_page.get_block_choices() if task_page else []
                empty = "(無步驟)"
            elif "任務檔" in mode or "範本" in mode:
                choices = task_page.get_preset_choices() if task_page else []
                empty = "(無存檔)"
            else:
                tf1.set_visible(menu_item, False)
                return
            menu_item.configure(values=choices or [empty])
            if choices and step["task_target_item"].get() not in choices:
                step["task_target_item"].set(choices[0])
            tf1.set_visible(menu_item, True)

        step["task_target_mode"].trace_add("write", update_task_items)
        ui["update_task_items"] = update_task_items
        tf2 = W.FlowFrame(task_box)
        tf2.pack(fill="x", padx=8, pady=(2, 6))
        tf2.add(W.label(tf2, "冷卻時間", color=violet, height=24))
        tf2.add(W.entry(tf2, step["task_cooldown"]))
        tf2.add(W.label(tf2, "秒（避免短時間重複觸發）", size=10, color=muted, height=24))
        tf2.add(W.button(tf2, "重新整理清單", update_task_items, kind="violet", width=86, height=22,
                         size=10, bold=False), right=True)
        ui["task_box"] = task_box
        ui["anchor_task"] = anchor()

        # 排除字詞（文字模式）
        row_exclude = W.row(detail)
        W.label(row_exclude, "排除字詞", bold=True, color="#F87171").pack(side="left", padx=(0, 6))
        W.entry(row_exclude, step["exclude_keywords"], monospace=False).pack(side="left", fill="x", expand=True)
        ui["row_exclude"] = row_exclude

        # 圖片模板設定（圖片模式）
        image_box = ctk.CTkFrame(detail, fg_color=T.COLOR_INPUT_BG, corner_radius=6, border_width=1,
                                 border_color=T.COLOR_CARD_BORDER)
        id1 = W.FlowFrame(image_box)
        id1.pack(fill="x", padx=8, pady=(6, 2))
        ui["thumb"] = tk.Label(id1, bg=T.COLOR_CANVAS_BG, fg=T.COLOR_TEXT_DIM, font=(T.FONT_FAMILY, 10),
                               text="未選圖", width=8, height=2)
        id1.add(ui["thumb"])
        box_th = W.row(id1)
        W.label(box_th, "門檻", bold=True).pack(side="left", padx=(2, 4))
        lbl_th = ctk.CTkLabel(box_th, text=f"{num(step['image_threshold'], 0.8):.2f}", width=34, font=T.mono(11))
        slider = ctk.CTkSlider(box_th, from_=0.50, to=0.98, number_of_steps=48, variable=step["image_threshold"],
                               width=110, height=16, command=lambda v: lbl_th.configure(text=f"{float(v):.2f}"))
        slider.pack(side="left")
        lbl_th.pack(side="left", padx=(4, 0))
        id1.add(box_th)
        id1.add(W.checkbox(id1, "多尺度容錯 (±5%)", step["image_multiscale"], height=24))
        id2 = W.FlowFrame(image_box)
        id2.pack(fill="x", padx=8, pady=(2, 6))
        id2.add(W.label(id2, "模板操作", size=10, bold=True, color=muted, height=24))
        id2.add(W.button(id2, "截圖", lambda: host.on_snip_template(step), kind="primary", width=48, height=24, size=10))
        id2.add(W.button(id2, "瀏覽", lambda: host.on_browse_template(step), width=48, height=24, size=10, bold=False))
        id2.add(W.button(id2, "帶入最新截圖", lambda: host.on_apply_last_snippet(step), kind="warning",
                         width=88, height=24, size=10))
        id2.add(W.button(id2, "開啟資料夾", host.on_open_templates_folder, width=74, height=24, size=10, bold=False))
        ui["image_box"] = image_box
        ui["anchor_target"] = anchor()

        # 條件存在時重複執行（僅優先動作）
        if kind == PRIORITY:
            row_while = W.row(detail)
            row_while.pack(fill="x", pady=(4, 0))
            W.checkbox(row_while, "條件存在時重複執行（直到消失）", step["while_condition"]).pack(side="left")

        # 命中後連點
        row_rep = W.row(detail)
        row_rep.pack(fill="x", pady=(4, 0))
        W.checkbox(row_rep, "命中後連點（過場跳過）", step["repeat_enabled"], bold=True,
                   color=T.COLOR_BTN_WARN).pack(side="left")
        repeat_box = ctk.CTkFrame(detail, fg_color=T.COLOR_BG, corner_radius=6, border_width=1,
                                  border_color=T.COLOR_CARD_BORDER)
        rep_opts = W.FlowFrame(repeat_box)
        rep_opts.pack(fill="x", padx=8, pady=(6, 2))
        rep_opts.add(W.label(rep_opts, "模式", color=muted, height=22))
        rep_opts.add(W.option_menu(rep_opts, step["repeat_mode"], O.REPEAT_MODES, width=96, height=22))
        count_box = W.row(rep_opts)
        W.label(count_box, "次數", color=muted).pack(side="left", padx=(4, 4))
        W.entry(count_box, step["repeat_count"], width=42, height=22).pack(side="left")
        W.label(count_box, "次", color=muted).pack(side="left", padx=(3, 0))
        rep_opts.add(count_box)
        speed_box = W.row(rep_opts)
        W.label(speed_box, "間隔", color=muted).pack(side="left", padx=(4, 4))
        W.entry(speed_box, step["repeat_speed"], width=42, height=22).pack(side="left")
        W.label(speed_box, "秒", color=muted).pack(side="left", padx=(3, 0))
        rep_opts.add(speed_box)
        rep_loc = W.FlowFrame(repeat_box)
        rep_loc.pack(fill="x", padx=8, pady=(2, 6))
        rep_loc.add(W.label(rep_loc, "位置", color=muted, height=22))
        rep_loc.add(W.option_menu(rep_loc, step["repeat_area"], O.REPEAT_AREAS, width=120, height=22))
        rep_xy = W.row(rep_loc)
        W.label(rep_xy, "X", size=10, color=muted).pack(side="left", padx=(4, 0))
        W.entry(rep_xy, step["repeat_custom_x"], height=22).pack(side="left", padx=(3, 6))
        W.label(rep_xy, "Y", size=10, color=muted).pack(side="left")
        W.entry(rep_xy, step["repeat_custom_y"], height=22).pack(side="left", padx=(3, 0))
        rep_loc.add(rep_xy)
        ui.update(repeat_box=repeat_box, repeat_opts=rep_opts, repeat_count_box=count_box,
                  repeat_loc=rep_loc, repeat_xy=rep_xy)
        ui["anchor_repeat"] = anchor()

        # 超時未命中跳過（僅一般步驟）
        if kind == NORMAL:
            row_timeout = W.FlowFrame(detail)
            row_timeout.pack(fill="x", pady=(4, 0))
            row_timeout.add(W.checkbox(row_timeout, "超時未命中跳過", step["timeout_enabled"], height=22))
            timeout_box = W.row(row_timeout)
            W.label(timeout_box, "等候上限", color=muted).pack(side="left", padx=(6, 4))
            W.entry(timeout_box, step["timeout_seconds"], width=42, height=22).pack(side="left")
            W.label(timeout_box, "秒", color=muted).pack(side="left", padx=(3, 0))
            row_timeout.add(timeout_box)
            ui.update(row_timeout=row_timeout, timeout_box=timeout_box)

        # Telegram 通知
        row_tg = W.FlowFrame(detail)
        row_tg.pack(fill="x", pady=(4, 0))
        row_tg.add(W.checkbox(row_tg, "成功後發送 Telegram 通知", step["tg_enabled"], color="#38BDF8", height=22))
        ui["tg_attach"] = row_tg.add(W.checkbox(row_tg, "附帶截圖", step["tg_attach_screenshot"],
                                                color=T.COLOR_TEXT_HIGHLIGHT, height=22))
        ui["row_tg"] = row_tg
        tg_msg = W.row(detail)
        W.label(tg_msg, "訊息內容", size=10, color="#38BDF8").pack(side="left", padx=(22, 6))
        W.entry(tg_msg, step["tg_message"], height=22, monospace=False).pack(side="left", fill="x", expand=True)
        ui["tg_msg_box"] = tg_msg
        ui["anchor_tg"] = anchor()


def _show(widget, visible: bool, **pack_opts):
    """以 pack 顯示或隱藏一個區塊（pack_opts 可帶 before= 讓區塊回到固定位置）。"""
    if visible:
        if widget.winfo_manager() != "pack":
            widget.pack(**pack_opts)
    else:
        widget.pack_forget()
