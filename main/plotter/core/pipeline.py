"""Сквозной конвейер: BGR-изображение -> G-код."""
from __future__ import annotations

import numpy as np

from .gcode import GCodeGenerator, GCodeStats
from .image_processing import apply_geometry, load_bgr, process
from .settings import ImageSettings, ProcessingSettings, PrinterSettings, TraceSettings
from .tracing import Paths, trace


def compute_image_mm(img: ImageSettings, aspect: float | None = None) -> tuple[float, float]:
    """Фактические мм рисунка (с учётом keep_aspect).

    aspect — h/w исходного изображения (если None, считаем из img.path).
    """
    w = float(img.size_w_mm)
    if img.keep_aspect:
        if aspect is None:
            if not img.path:
                return w, float(img.size_h_mm)
            bgr = load_bgr(img.path)
            h, pw = bgr.shape[:2]
            aspect = h / pw
        if img.rotate in (90, 270):
            aspect = 1.0 / aspect
        return w, w * aspect
    return w, float(img.size_h_mm)


def fit_to_bed(iw: float, ih: float, pr: PrinterSettings) -> tuple[float, float]:
    """Если включено autofit_bed и рисунок больше стола — сжать без искажений."""
    if not pr.autofit_bed:
        return iw, ih
    scale = min(pr.bed_w_mm / iw, pr.bed_h_mm / ih)
    if scale < 1.0:
        return iw * scale, ih * scale
    return iw, ih


def run_pipeline(
    bgr: np.ndarray,
    img: ImageSettings,
    proc: ProcessingSettings,
    ts: TraceSettings,
    printer: PrinterSettings,
) -> tuple[str, GCodeStats, Paths, np.ndarray, float]:
    """
    :return: (gcode, stats, paths_mm, mask, mm_per_px)
    """
    h, w = bgr.shape[:2]
    aspect = h / w
    iw, ih = fit_to_bed(*compute_image_mm(img, aspect), printer)
    preview, mask = process(bgr, img, proc)
    h, w = mask.shape
    mm_per_px = iw / w
    paths = trace(mask, mm_per_px, ts, gray=preview, proc=proc)
    gen = GCodeGenerator(printer, iw, ih)
    gcode, stats = gen.generate(paths)
    return gcode, stats, paths, mask, mm_per_px
