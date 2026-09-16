"""Все настройки приложения: фото, обработка, трассировка, принтер, G-код."""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Фото
# ---------------------------------------------------------------------------
@dataclass
class ImageSettings:
    path: str = ""
    # Размер рисунка на столе, мм
    size_w_mm: float = 180.0
    size_h_mm: float = 140.0
    keep_aspect: bool = True          # высота считается из ширины
    # Разрешение: целевая ширина изображения в пикселях
    resolution_px: int = 600
    # 0 / 90 / 180 / 270
    rotate: int = 0
    flip_h: bool = False
    flip_v: bool = False

    @property
    def image_h_mm(self) -> float:
        return self.size_h_mm


# ---------------------------------------------------------------------------
# Обработка изображения (идеи из MagicGyver EDITOR)
# ---------------------------------------------------------------------------
@dataclass
class ProcessingSettings:
    brightness: int = 0        # -100 .. 100
    contrast: int = 0          # -100 .. 100
    gamma: float = 1.0         # 0.05 .. 3.0
    blur: int = 0              # 0 .. 10  (ядро гауссиана)
    threshold: float = 0.5     # 0..1 — тёмнее порога рисуем
    edge: str = "none"         # none | median | sobel
    invert: bool = False       # рисовать светлые области
    thicken_px: int = 0        # утолщение «чернил» (dilation маски), 0 = нет
    bridge_px: int = 0         # сшивка разрывов (морф. замыкание), 0 = выкл
                               # (чистый силуэт, как в классике; 1–3 — только
                               # если буква рвётся на куски)


# ---------------------------------------------------------------------------
# Трассировка (идеи из MagicGyver TRACER: Crawl / Waves + свои)
# ---------------------------------------------------------------------------
@dataclass
class TraceSettings:
    mode: str = "raster"       # raster | contour | outline | crawl | waves

    # --- raster: построчные линии ---
    raster_row_step: int = 1        # рисовать каждую N-ю строку
    raster_min_len_px: int = 2      # мин. длина отрезка, px
    raster_vertical: bool = False   # True = вертикальные линии

    # --- contour / outline: контуры ---
    contour_min_area_px: int = 20   # игнорировать контуры меньше, px^2
    contour_smooth_px: float = 1.5  # упрощение полигона (approxPolyDP), px
    precise_contour: bool = True    # субпиксельный контур (marching squares
                                    # по серому) вместо findContours по маске

    # --- crawl: непрерывное «ползание» MagicGyver ---
    crawl_cell_px: int = 1          # размер ячейки сетки, px
    crawl_skip: int = 2             # каждые N шагов кольцо не сбрасывается
    crawl_loop: bool = True         # предпочитать движение по инерции

    # --- waves: волны, амплитуда следует за тёмнотою ---
    waves_rows: int = 20
    waves_amplitude: float = 1.0    # в долях расстояния между рядами
    waves_reverse: bool = False

    # --- skeleton: центральные линии раскрасок ---
    skeleton_min_len_mm: float = 1.0  # отбрасывать штрихи короче, мм

    # --- общее: сглаживание пути (метод Чакина), 0 = выкл ---
    smooth_iters: int = 0           # 0..24; для почерка 2..4, выше — «на глаз»


MODE_LABELS = {
    "raster": "Закраска (линии)",
    "contour": "Контур: все",
    "outline": "Контур: внешний",
    "inner": "Контур: внутренний",
    "skeleton": "Линии раскраски (вектор)",
    "crawl": "Ползание (crawl)",
    "waves": "Волны (waves)",
}


# ---------------------------------------------------------------------------
# Принтер и G-код
# ---------------------------------------------------------------------------
DEFAULT_START_GCODE = """; --- СТАРТ (редактируй) ---
G21            ; единицы — мм
G90            ; абсолютные координаты
G28            ; возврат домой по всем осям
G92 E0         ; обнулить экструдер (если есть)"""

DEFAULT_END_GCODE = """; --- ФИНАЛ (редактируй) ---
G91
G28 Z          ; поднять Z домой
G90
M84 X Y        ; обесточить оси X/Y"""


@dataclass
class PrinterSettings:
    # Стол, мм (картезианская/i3, дефолты умеренные)
    bed_w_mm: float = 220.0
    bed_h_mm: float = 220.0
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    center: bool = True           # центрировать рисунок на столе
    autofit_bed: bool = False     # масштабировать, если рисунок больше стола

    # Ручка: Z прижата / Z поднята, мм
    z_pen_down: float = 0.3
    z_pen_up: float = 2.0
    lift_on_travel: bool = True   # поднимать голову при переходе между линиями
    # Насколько кончик ручки опущен НИЖЕ днища сопла, мм (0 = вровень).
    # Это же — клиренс сопла над бумагой при рисовании.
    pen_below_nozzle_mm: float = 0.0

    # Скорости, мм/мин
    draw_speed: float = 6000.0    # 100 мм/с — рисование
    travel_speed: float = 12000.0 # 200 мм/с — переходы
    z_speed: float = 4800.0       # 80 мм/с — подъём/опускание

    # Несколько проходов для более тёмных линий
    passes: int = 1
    pass_offset_mm: float = 0.05

    start_gcode: str = field(default=DEFAULT_START_GCODE)
    end_gcode: str = field(default=DEFAULT_END_GCODE)
    filename: str = "drawing.gcode"

    # Ускорение — только для информации в комментарии G-кода
    max_accel_mm_s2: float = 1000.0
