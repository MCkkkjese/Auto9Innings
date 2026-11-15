"""步驟編輯器的選項常數與正規化函式（循序腳本與任務流程共用）。"""
from typing import Tuple

ROI_OPTIONS = ["右下角區域", "右半側螢幕", "下半部區域", "中央區域", "全畫面比對", "自訂特定區塊"]
REPEAT_MODES = ["持續連點", "指定次數"]
REPEAT_AREAS = ["右下角區域", "中央區域", "右上角 (Skip)", "右半側中央", "跟隨命中目標", "自訂座標"]
IDLE_TAP_AREAS = ["右下角區域", "中央區域", "右上角 (Skip)", "右半側中央"]
IDLE_STRATEGIES = ["常規等待", "快速跳過", "自動停止"]

TARGET_TEXT = "文字辨識 (OCR)"
TARGET_IMAGE = "圖片特徵 (模板比對)"
TARGET_CHECK = "勾選方塊 (打勾)"
TARGET_CROSS = "關閉按鈕 (叉叉)"
TARGET_TYPES = [TARGET_TEXT, TARGET_IMAGE, TARGET_CHECK, TARGET_CROSS]

MODE_IMAGE = "圖片特徵比對模式"
MODE_TEXT = "文字辨識模式"
RECOGNITION_MODES = [MODE_IMAGE, MODE_TEXT]

ACTION_TARGET_IMAGE = "點擊目標圖片 (按鈕中心)"
ACTION_TARGET_TEXT = "點擊目標文字 (詞條中心)"
ACTION_CUSTOM_COORD = "點擊指定座標 (自訂)"
ACTION_CUSTOM_BLOCK = "自訂特定區塊"
ACTION_REPEAT = "持續連點"
ACTION_WAIT = "無動作(僅等待)"
ACTION_TASK_FLOW = "執行任務清單"

_ACTION_TAIL = [ACTION_CUSTOM_COORD, ACTION_CUSTOM_BLOCK, ACTION_REPEAT, ACTION_WAIT, ACTION_TASK_FLOW]
ACTION_OPTIONS_IMAGE = [ACTION_TARGET_IMAGE] + _ACTION_TAIL
ACTION_OPTIONS_TEXT = [ACTION_TARGET_TEXT] + _ACTION_TAIL

TASK_MODE_FULL = "完整任務清單"
TASK_MODE_BLOCK = "指定積木步驟"
TASK_MODE_FILE = "已儲存任務檔"
TASK_TARGET_MODES = [TASK_MODE_FULL, TASK_MODE_BLOCK, TASK_MODE_FILE]

PREVIEW_INTERVALS = ["0.5秒", "1.0秒", "1.5秒", "2.0秒", "3.0秒", "5.0秒"]

# 比對範圍名稱 -> (ymin, xmin, ymax, xmax) 比例
_ROI_MAP = {
    "右下角區域": (0.45, 0.45, 1.0, 1.0),
    "右半側螢幕": (0.0, 0.45, 1.0, 1.0),
    "下半部區域": (0.50, 0.0, 1.0, 1.0),
    "中央區域": (0.25, 0.25, 0.75, 0.75),
    "全畫面比對": (0.0, 0.0, 1.0, 1.0),
}


def roi_to_tuple(roi_name: str) -> Tuple[float, float, float, float]:
    return _ROI_MAP.get(roi_name, (0.0, 0.0, 1.0, 1.0))


def is_image_mode(mode: str) -> bool:
    return "圖片" in str(mode or "")


def is_task_flow_action(a: str) -> bool:
    return a == ACTION_TASK_FLOW or "任務清單" in str(a or "") or "jump_task" in str(a or "")


def is_custom_coord_action(a: str) -> bool:
    """動作是否為點擊指定座標／自訂區塊。"""
    if not a:
        return False
    s = str(a).strip()
    return (
        s in ("自訂座標", "點擊指定座標", "custom_coord", ACTION_CUSTOM_COORD, ACTION_CUSTOM_BLOCK)
        or "指定座標" in s or "自訂" in s or "custom" in s.lower()
    )


def is_target_center_action(a: str) -> bool:
    """動作是否為點擊辨識到的目標中心（圖片或文字）。"""
    if not a:
        return True
    if is_custom_coord_action(a):
        return False
    s = str(a).strip()
    if s in (ACTION_REPEAT, ACTION_WAIT) or is_task_flow_action(s) or "連點" in s or "等待" in s:
        return False
    return True


def normalize_target_type(t: str) -> str:
    if not t:
        return TARGET_TEXT
    t = str(t)
    low = t.lower()
    if "圖片" in t or "image" in low or "模板" in t:
        return TARGET_IMAGE
    if "打勾" in t or "check" in low:
        return TARGET_CHECK
    if "叉叉" in t or "cross" in low or "關閉" in t:
        return TARGET_CROSS
    return TARGET_TEXT


def normalize_action(a: str, is_image: bool = True) -> str:
    """把各版本存檔的動作字串正規化為目前的選項；依辨識模式區分圖片或文字。"""
    default = ACTION_TARGET_IMAGE if is_image else ACTION_TARGET_TEXT
    if not a:
        return default
    a = str(a).strip()
    if is_custom_coord_action(a):
        return ACTION_CUSTOM_BLOCK if (a == ACTION_CUSTOM_BLOCK or "區塊" in a) else ACTION_CUSTOM_COORD
    if a == ACTION_REPEAT:
        return ACTION_REPEAT
    if a in (ACTION_WAIT, "僅等待", "無動作"):
        return ACTION_WAIT
    if is_task_flow_action(a):
        return ACTION_TASK_FLOW
    return default


def normalize_recognition_mode(mode: str) -> str:
    return MODE_IMAGE if is_image_mode(mode) else MODE_TEXT


def idle_strategy_code(label: str) -> str:
    label = str(label or "")
    return "skip" if "跳過" in label else "stop" if "停止" in label else "wait"
