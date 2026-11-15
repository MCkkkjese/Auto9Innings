"""影像讀寫共用函式（支援含中文的檔名與路徑）。"""
import os
from typing import Optional, Tuple

import cv2
import numpy as np

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp")


def imread_unicode(path: str, flags: int = cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
    """以原生檔案 IO 讀取圖片，避開 OpenCV 在中文路徑上的失敗。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
    except Exception:
        return None


def imwrite_unicode(path: str, img: np.ndarray) -> bool:
    """以原生檔案 IO 寫入圖片；缺副檔名時補上 .png，必要時建立上層資料夾。"""
    try:
        p = os.path.abspath(path)
        ext = os.path.splitext(p)[1]
        if not ext:
            ext = ".png"
            p += ext
        parent_dir = os.path.dirname(p)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        ok, encoded = cv2.imencode(ext, img)
        if not ok:
            return False
        with open(p, "wb") as f:
            f.write(encoded.tobytes())
        return os.path.exists(p) and os.path.getsize(p) > 0
    except Exception:
        return False


def encode_jpeg(img: np.ndarray, quality: int = 85) -> Optional[bytes]:
    """把 BGR 影像編碼為 JPEG 位元組。"""
    try:
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return buf.tobytes() if ok else None
    except Exception:
        return None


def fit_size(img_w: int, img_h: int, avail_w: int, avail_h: int) -> Tuple[float, int, int]:
    """計算把影像等比縮放進可用區域的比例與尺寸，回傳 (scale, new_w, new_h)。"""
    scale = min(avail_w / max(1, img_w), avail_h / max(1, img_h))
    return scale, max(1, int(img_w * scale)), max(1, int(img_h * scale))


def newest_image_in(directory: str) -> str:
    """回傳資料夾中最近修改的圖片完整路徑；找不到時回傳空字串。"""
    try:
        files = [
            os.path.join(directory, f) for f in os.listdir(directory)
            if f.lower().endswith(IMAGE_EXTENSIONS)
        ]
        files = [f for f in files if os.path.isfile(f)]
        return max(files, key=os.path.getmtime) if files else ""
    except Exception:
        return ""
