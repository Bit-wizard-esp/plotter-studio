"""Обработка фото: resize, поворот, яркость/контраст/гамма/blur, кромки, порог.

Порядок пайплайна повторяет EDITOR из MagicGyver:
size -> brightness -> contrast -> gamma -> blur -> edges -> threshold.

Возвращаемый `mask` — uint8 0/255, где 255 = «рисуем».
"""
from __future__ import annotations

import os

import cv2
import numpy as np

from .settings import ImageSettings, ProcessingSettings

_GAMMA_LUT: dict[float, np.ndarray] = {}


def _gamma_lut(gamma: float) -> np.ndarray:
    key = round(gamma, 3)
    if key not in _GAMMA_LUT:
        inv = 1.0 / max(key, 0.05)
        x = np.arange(256, dtype=np.float32) / 255.0
        _GAMMA_LUT[key] = np.clip(x ** inv * 255.0, 0, 255).astype(np.uint8)
    return _GAMMA_LUT[key]


# ---------------------------------------------------------------------------
# Загрузка файлов — устойчиво к кириллице в путях и «странным» JPEG
# ---------------------------------------------------------------------------
def _sniff_format(path: str) -> str:
    """Определяем реальный формат по сигнатуре (расширение обманчиво)."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return "файл не читается"
    if len(head) < 12:
        return "файл подозрительно короткий"
    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if head.startswith(b"\x89PNG"):
        return "PNG"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WebP"
    if head.startswith(b"GIF8"):
        return "GIF"
    if head.startswith(b"BM"):
        return "BMP"
    if head.startswith(b"II\x2a\x00") or head.startswith(b"MM\x00\x2a"):
        return "TIFF/RAW"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"heim", b"hevc", b"mif1", b"msf1"):
            return "HEIC/HEIF (формат iPhone)"
        if brand in (b"avif", b"avis"):
            return "AVIF"
    return "неопознан (не похоже на изображение)"


def load_bgr(path: str) -> np.ndarray:
    """Загружает изображение в BGR.

    1) OpenCV через imdecode (байты файла) — работает и с кириллицей в путях
       (cv2.imread на Windows с кириллическими путями падает).
    2) Fallback через Pillow — CMYK/16-бит JPEG, WebP, AVIF, GIF, TIFF и пр.
    """
    if not os.path.exists(path):
        raise IOError(f"Файл не найден: {path}")
    size_mb = os.path.getsize(path) / 1048576

    # 1) OpenCV
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size > 0:
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is not None:
                return img
    except Exception:  # noqa: BLE001
        pass

    # 2) Pillow
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
            arr = np.asarray(im.convert("RGB"))
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception as e:  # noqa: BLE001
        fmt = _sniff_format(path)
        hints = [f"Формат по сигнатуре: {fmt}; размер: {size_mb:.1f} МБ."]
        if fmt == "JPEG":
            hints.append("Скорее всего CMYK или 16-бит JPEG — их OpenCV не читает. "
                         "Лечится: ПКМ → «Открыть с помощью» → Paint/Firefox → "
                         "Сохранить как обычный JPEG/PNG.")
        if "HEIC" in fmt:
            hints.append("Это HEIC (iPhone). Сохраните файл как JPEG/PNG.")
        if fmt == "AVIF":
            hints.append("AVIF: доустановите плагин — pip install pillow-avif-plugin")
        if fmt.startswith("неопознан"):
            hints.append("Файл не похож на изображение — возможно, браузер "
                         "сохранил страницу или ответ сервера, а не картинку. "
                         "Перескачайте файл.")
        raise IOError(
            f"Не удалось открыть изображение: {path}\n\n" + "\n".join(hints)
            + f"\n\nДетали: {e}"
        ) from e


def apply_geometry(bgr: np.ndarray, img: ImageSettings) -> np.ndarray:
    """Поворот/зеркалирование, затем ресайз под целевую ширину в пикселях."""
    out = bgr
    if img.rotate == 90:
        out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
    elif img.rotate == 180:
        out = cv2.rotate(out, cv2.ROTATE_180)
    elif img.rotate == 270:
        out = cv2.rotate(out, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if img.flip_h:
        out = cv2.flip(out, 1)
    if img.flip_v:
        out = cv2.flip(out, 0)

    h, w = out.shape[:2]
    target_w = int(img.resolution_px)
    if target_w > 0 and target_w != w:
        target_h = max(1, int(round(h * target_w / w)))
        interp = cv2.INTER_AREA if target_w < w else cv2.INTER_CUBIC
        out = cv2.resize(out, (target_w, target_h), interpolation=interp)
    return out


def process(
    bgr: np.ndarray,
    img: ImageSettings,
    proc: ProcessingSettings,
) -> tuple[np.ndarray, np.ndarray]:
    """
    :return: (gray_preview, mask)
        gray_preview — обработанное серое изображение (до порога), для превью
        mask         — бинарная маска (255 = рисуем)
    """
    out = apply_geometry(bgr, img)
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)

    # Яркость
    if proc.brightness:
        gray = cv2.add(gray, np.full_like(gray, int(proc.brightness * 2.55)))

    # Контраст (классическая формула Photoshop)
    if proc.contrast:
        c = float(proc.contrast)
        factor = (259.0 * (c + 255.0)) / (255.0 * (255.0 - c))
        gray = np.clip(factor * (gray.astype(np.float32) - 128.0) + 128.0, 0, 255)
        gray = gray.astype(np.uint8)

    # Гамма
    if abs(proc.gamma - 1.0) > 1e-3:
        gray = _gamma_lut(proc.gamma)[gray]

    # Размытие
    if proc.blur > 0:
        k = 2 * int(proc.blur) + 1
        gray = cv2.GaussianBlur(gray, (k, k), 0)

    # Кромки
    if proc.edge == "sobel":
        sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        gray = cv2.addWeighted(sx, 0.7071, sy, 0.7071, 0)
        gray = np.clip(gray, 0, 255).astype(np.uint8)
    elif proc.edge == "median":
        blurred = cv2.medianBlur(gray, 5)
        gray = cv2.absdiff(gray, blurred)  # резкие детали = кромки

    preview = gray

    # Порог: тёмное рисуем (или светлое, если invert)
    th = int(np.clip(proc.threshold, 0.0, 1.0) * 255)
    if proc.invert:
        mask = np.where(gray >= th, 255, 0).astype(np.uint8)
    else:
        mask = np.where(gray < th, 255, 0).astype(np.uint8)

    # Утолщение «чернил» (dilation): спасает 1-2 пиксельные линии печати
    k = int(proc.thicken_px)
    if k > 0:
        mask = cv2.dilate(mask, np.ones((2 * k + 1, 2 * k + 1), np.uint8))

    # Сшивка разрывов (морф. замыкание): заделывает «трещины» в тонких
    # линиях, из-за которых буквы рвутся на куски и контур «не замыкается»
    k = int(proc.bridge_px)
    if k > 0:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((2 * k + 1, 2 * k + 1), np.uint8))

    return preview, mask
