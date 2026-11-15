"""Telegram 通知（全專案唯一的發送實作）。"""
import threading
import time
from typing import Callable, Optional

import numpy as np
import requests

from core.imaging import encode_jpeg
from version import APP_NAME

LogFn = Optional[Callable[[str], None]]


def send_telegram(token: str, chat_id: str, text: str,
                  screen_bgr: Optional[np.ndarray] = None, log: LogFn = None) -> bool:
    """
    同步發送 Telegram 訊息。有截圖時先嘗試以相片發送，失敗則退回純文字。
    回傳是否成功送達。
    """
    token = str(token or "").strip()
    chat_id = str(chat_id or "").strip()
    if not token or not chat_id:
        return False

    def _log(msg: str):
        if log:
            try:
                log(msg)
            except Exception:
                pass

    try:
        if screen_bgr is not None:
            jpg = encode_jpeg(screen_bgr)
            if jpg:
                try:
                    resp = requests.post(
                        f"https://api.telegram.org/bot{token}/sendPhoto",
                        data={"chat_id": chat_id, "caption": text},
                        files={"photo": ("screenshot.jpg", jpg, "image/jpeg")},
                        timeout=12,
                    )
                    if resp.status_code == 200 and resp.json().get("ok"):
                        return True
                    _log(f"[Telegram] 相片發送失敗，改送純文字: {resp.text}")
                except Exception as e:
                    _log(f"[Telegram] 相片發送異常，改送純文字: {e}")
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        _log(f"[Telegram] 發送回應異常: {resp.text}")
        return False
    except Exception as e:
        _log(f"[Telegram] 通知發送失敗: {e}")
        return False


def send_telegram_async(token: str, chat_id: str, text: str,
                        screen_bgr: Optional[np.ndarray] = None, log: LogFn = None,
                        on_done: Optional[Callable[[bool], None]] = None) -> bool:
    """背景執行緒發送，不阻塞呼叫端。回傳是否已送出請求（Token 與 Chat ID 是否齊全）。"""
    if not str(token or "").strip() or not str(chat_id or "").strip():
        return False
    img = screen_bgr.copy() if screen_bgr is not None else None

    def _work():
        ok = send_telegram(token, chat_id, text, img, log)
        if on_done:
            try:
                on_done(ok)
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()
    return True


def format_notification(body: str, step_name: str = "", hit_text: str = "") -> str:
    """組合帶有步驟、命中資訊與時間戳記的通知內容。"""
    lines = [f"【{APP_NAME}通知】", f"訊息: {body}"]
    if step_name:
        lines.append(f"步驟: {step_name}")
    if hit_text:
        lines.append(f"命中: {hit_text}")
    lines.append(f"時間: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)
