"""
存檔位置與設定檔讀寫。

使用者的存檔資料夾路徑記錄在家目錄的設定檔中，與專案資料夾互相獨立；
各頁面的自動存檔檔名、舊版檔名的相容對照也集中在這裡。
"""
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

from core.textutil import sanitize_config

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESETS_DIR = os.path.join(PROJECT_DIR, "presets")
STEP_PRESETS_DIR = os.path.join(PRESETS_DIR, "循序腳本")
TASK_PRESETS_DIR = os.path.join(PRESETS_DIR, "任務流程")

USER_SETTINGS_FILE = os.path.expanduser("~/.vision_game_bot.json")
LEGACY_SETTINGS_FILE = os.path.expanduser("~/.auto9innings_storage_path.json")

# 測試或可攜式使用時，可用環境變數直接指定存檔資料夾（不會寫回家目錄設定）。
ENV_STORAGE_DIR = "VGB_STORAGE_DIR"

# 自動存檔檔名：(目前檔名, 舊版檔名)
AUTOSAVE_NAMES = {
    "emulator": ("script_emulator_last", "baseball_last_config"),
    "mirror": ("script_mirror_last", "iphone_last_config"),
    "task": ("task_flow_last", "task_flow_save"),
}

SUBDIR_SNIPS = "截圖存檔"


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_user_settings() -> Dict[str, Any]:
    return _read_json(USER_SETTINGS_FILE) or {}


def save_user_settings(**updates: Any) -> None:
    data = load_user_settings()
    data.update(updates)
    try:
        with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _valid_dir(path: str) -> str:
    path = str(path or "").strip()
    if not path:
        return ""
    if os.path.isdir(path):
        return os.path.abspath(path)
    parent = os.path.dirname(path)
    return os.path.abspath(parent) if os.path.isdir(parent) else ""


def get_storage_dir() -> str:
    """取得存檔資料夾：環境變數 > 本程式設定 > 舊版設定 > 專案資料夾。"""
    env = _valid_dir(os.environ.get(ENV_STORAGE_DIR, ""))
    if env:
        return env
    for source in (load_user_settings(), _read_json(LEGACY_SETTINGS_FILE) or {}):
        found = _valid_dir(source.get("storage_dir", ""))
        if found:
            return found
    return PROJECT_DIR


def persist_storage_dir(path: str) -> None:
    if os.environ.get(ENV_STORAGE_DIR):
        return
    save_user_settings(storage_dir=os.path.abspath(path))


def autosave_path(storage_dir: str, kind: str, instance_id: int = 1) -> str:
    suffix = "" if instance_id == 1 else f"_{instance_id}"
    return os.path.join(storage_dir, f"{AUTOSAVE_NAMES[kind][0]}{suffix}.json")


def legacy_autosave_path(storage_dir: str, kind: str, instance_id: int = 1) -> str:
    suffix = "" if instance_id == 1 else f"_{instance_id}"
    return os.path.join(storage_dir, f"{AUTOSAVE_NAMES[kind][1]}{suffix}.json")


def is_autosave_file(filename: str) -> bool:
    """判斷檔名是否為任一頁面的自動存檔（含舊版檔名與多視窗後綴）。"""
    stem = os.path.splitext(os.path.basename(filename))[0]
    for names in AUTOSAVE_NAMES.values():
        for n in names:
            if stem == n or (stem.startswith(n + "_") and stem[len(n) + 1:].isdigit()):
                return True
    return False


def load_config(path: str) -> dict:
    """讀取 JSON 設定檔並清理舊版選項值；失敗時拋出例外。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return sanitize_config(data)


def save_config(path: str, data: Any) -> None:
    """寫入 JSON 設定檔；必要時建立上層資料夾。失敗時拋出例外。"""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def relative_ref(path: str, base_dir: str) -> str:
    """檔案位於 base_dir 之下時回傳檔名，否則回傳絕對路徑（步驟的圖片模板欄位用）。"""
    abs_path = os.path.abspath(path)
    try:
        if base_dir and os.path.commonpath([abs_path, os.path.abspath(base_dir)]) == os.path.abspath(base_dir):
            return os.path.basename(abs_path)
    except ValueError:
        pass
    return abs_path


def resolve_image_path(name: str, search_dirs: List[str]) -> Optional[str]:
    """
    解析圖片模板路徑。依序嘗試：絕對路徑、原字串，以及每個搜尋資料夾下的
    原相對路徑、檔名、截圖存檔/檔名、templates/檔名。
    """
    if not name or not str(name).strip():
        return None
    p = str(name).strip()
    if os.path.isabs(p) and os.path.isfile(p):
        return os.path.abspath(p)
    base = os.path.basename(p)
    candidates = [p]
    seen = set()
    for d in list(search_dirs) + [PROJECT_DIR, os.getcwd()]:
        if not d or d in seen:
            continue
        seen.add(d)
        candidates += [
            os.path.join(d, p),
            os.path.join(d, base),
            os.path.join(d, SUBDIR_SNIPS, base),
            os.path.join(d, SUBDIR_SNIPS, p),
            os.path.join(d, "templates", base),
            os.path.join(d, "templates", p),
        ]
    for c in candidates:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def open_in_file_manager(path: str) -> None:
    """用系統檔案管理員開啟資料夾；失敗時拋出例外。"""
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])
