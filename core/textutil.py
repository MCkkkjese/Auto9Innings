"""文字與數值的共用小工具（表情符號清理、安全數值轉換、設定檔正規化）。"""
import re
from typing import Any

# 表情符號範圍。保留功能性符號：☰ (U+2630)、✓✔✕✖ (U+2713-2716)。
_EMOJI_RE = re.compile(
    "(?:["
    "\U0001F000-\U0001FAFF"
    "⌀-⏿"
    "☀-☯☱-✒✗-➿"
    "⬀-⯿"
    "▶◀"
    "⃣"
    "]|️|‍)+[ 　]?"
)

# 這些欄位是使用者自行輸入的內容，載入設定檔時不做任何清理。
USER_TEXT_KEYS = frozenset({
    "name", "title", "desc", "note", "message", "tg_message",
    "keywords", "exclude_keywords", "stop_keywords",
    "template_image", "task_target_item",
    "token", "chat_id", "tg_token", "tg_chat_id", "custom_token", "custom_chat_id",
    "device", "window_name",
})


def strip_emoji(text: str) -> str:
    """移除字串中的表情符號（連同其後的一個空白）。"""
    if not text:
        return text
    return _EMOJI_RE.sub("", text)


def sanitize_config(data: Any, _key: str = "") -> Any:
    """
    遞迴清理設定檔中「選項型」字串的表情符號。
    舊版存檔的選項值帶有表情符號前綴（例如動作、辨識類型），
    清理後才能與目前的選項常數一致；使用者輸入的文字欄位則保持原樣。
    """
    if isinstance(data, dict):
        return {k: sanitize_config(v, str(k)) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_config(v, _key) for v in data]
    if isinstance(data, str) and _key not in USER_TEXT_KEYS:
        return strip_emoji(data).strip()
    return data


def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def num(var: Any, default: Any, cast=float) -> Any:
    """安全讀取 tk 變數或一般值；輸入框為空或格式錯誤時回傳預設值。"""
    try:
        val = var.get() if hasattr(var, "get") else var
        return cast(val)
    except Exception:
        return default


def split_keywords(raw: str) -> list:
    """把以逗號（全形或半形）分隔的關鍵字字串拆成清單。"""
    return [k.strip() for k in str(raw or "").replace("，", ",").split(",") if k.strip()]


def safe_filename(name: str) -> str:
    """只保留英數字、底線與連字號，用於產生預設檔名。"""
    return "".join(c for c in str(name) if c.isalnum() or c in ("_", "-")).strip()
