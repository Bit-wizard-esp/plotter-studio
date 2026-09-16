"""Ядро: обработка фото, трассировка, генерация G-кода. Без Qt."""
from .settings import (
    ImageSettings,
    ProcessingSettings,
    PrinterSettings,
    TraceSettings,
    DEFAULT_START_GCODE,
    DEFAULT_END_GCODE,
    MODE_LABELS,
)
from .dxf import load_dxf
from .gcode import GCodeGenerator, GCodeStats
from .pipeline import run_pipeline, compute_image_mm, fit_to_bed
from .tracing import trace, chaikin, thinning, skeleton_to_paths
from .image_processing import process, load_bgr, apply_geometry
from .textgen import text_to_bgr

__all__ = [
    "ImageSettings", "ProcessingSettings", "PrinterSettings", "TraceSettings",
    "DEFAULT_START_GCODE", "DEFAULT_END_GCODE",
    "GCodeGenerator", "GCodeStats", "run_pipeline", "compute_image_mm",
    "fit_to_bed", "load_dxf", "trace", "chaikin", "thinning", "skeleton_to_paths",
    "process", "load_bgr", "apply_geometry",
    "MODE_LABELS",
]
