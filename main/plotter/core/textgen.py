"""Генерация «фото» из текста: чёрный текст на белом.

Текст потом обрабатывается обычным пайплайном (порог -> контуры/растр),
и принтер «пишет» его ручкой.
"""
from __future__ import annotations

import os

import cv2
import numpy as np

_FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int):
    from PIL import ImageFont
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:  # noqa: BLE001
                continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _measure(text: str, font) -> tuple[int, int, int, int]:
    from PIL import Image, ImageDraw
    tmp = Image.new("L", (8, 8), 0)
    d = ImageDraw.Draw(tmp)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    return l, t, r - l, b - t


def text_to_bgr(text: str, font_size: int = 160, max_width_px: int = 2000) -> np.ndarray:
    """Чёрный текст (может быть многострочным) на белом фоне -> BGR."""
    from PIL import Image, ImageDraw

    text = (text or "").strip() or "Plotter"
    size = max(8, int(font_size))
    while True:
        font = _load_font(size)
        off_l, off_t, tw, th = _measure(text, font)
        pad = max(12, size // 4)
        w, h = tw + 2 * pad, th + 2 * pad
        if w <= max_width_px or size <= 8:
            break
        size = int(size * max_width_px / w)

    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    d.text((pad - off_l, pad - off_t), text, fill=0, font=font)
    arr = np.array(img)
    return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
