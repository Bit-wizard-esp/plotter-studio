"""Генератор G-кода для 3D-принтера-плоттера (режим «ручка»).

Схема:
  * Z = z_pen_down  — ручка прижата к бумаге, рисуем (G1)
  * Z = z_pen_up    — ручка поднята, переходы (G0)
  * между линиями: подъём -> XY-перелёт -> опускание
    (опционально: без подъёма, чистым XY — checkbox в UI)

Координаты изображения: (0,0) в левом верхнем углу, y вниз.
Координаты стола: (0,0) в левом нижнем углу, y вверх (стандарт).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Tuple

from .settings import PrinterSettings
from .tracing import Path, Paths

Point = Tuple[float, float]


@dataclass
class GCodeStats:
    segments: int = 0        # отрезков с ручкой вниз
    draw_mm: float = 0.0     # длина линий, мм
    travel_mm: float = 0.0   # длина переходов, мм
    pen_lifts: int = 0       # подъёмов ручки
    est_minutes: float = 0.0 # оценка времени
    lines: int = 0           # строк в файле

    @property
    def draw_m(self) -> float:
        return self.draw_mm / 1000.0


class GCodeGenerator:
    def __init__(self, printer: PrinterSettings, image_w_mm: float, image_h_mm: float):
        self.p = printer
        self.iw = float(image_w_mm)
        self.ih = float(image_h_mm)
        if printer.center:
            self.x0 = (printer.bed_w_mm - self.iw) / 2.0 + printer.offset_x_mm
            self.y0 = (printer.bed_h_mm - self.ih) / 2.0 + printer.offset_y_mm
        else:
            self.x0 = printer.offset_x_mm
            self.y0 = printer.offset_y_mm
        # не вылезать за стол
        self.x0 = min(max(self.x0, 0.0), max(0.0, printer.bed_w_mm - 1.0))
        self.y0 = min(max(self.y0, 0.0), max(0.0, printer.bed_h_mm - 1.0))

    def to_bed(self, x_mm: float, y_mm: float) -> Point:
        """Изображение (y вниз) -> стол (y вверх)."""
        return (self.x0 + x_mm, self.y0 + (self.ih - y_mm))

    # ------------------------------------------------------------------
    def _fmt(self, x: float, y: float) -> str:
        return f"{x:.3f}", f"{y:.3f}"

    def generate(self, paths: Iterable[Path]) -> tuple[str, GCodeStats]:
        p = self.p
        stats = GCodeStats()
        out: list[str] = []
        A = out.append

        A("; ============================================================")
        A("; Plotter Studio — фото в G-код для 3D-принтера")
        A(f"; {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        A(f"; Стол: {p.bed_w_mm:.1f} x {p.bed_h_mm:.1f} мм, "
          f"рисунок: {self.iw:.1f} x {self.ih:.1f} мм в ({self.x0:.1f}; {self.y0:.1f})")
        A(f"; Ручка: Z {p.z_pen_down:.2f} (рисунок) / Z {p.z_pen_up:.2f} (переход)")
        if p.pen_below_nozzle_mm > 0:
            A(f"; Кончик ручки ниже сопла на {p.pen_below_nozzle_mm:.1f} мм — "
              f"клиренс сопла над бумагой при рисовании ~{p.pen_below_nozzle_mm:.1f} мм")
        else:
            A("; ВНИМАНИЕ: ручка вровень с соплом — сопло может тереть бумагу при рисовании")
        A(f"; Скорость: рисование {p.draw_speed:.0f}, переход {p.travel_speed:.0f} мм/мин")
        A("; ============================================================")

        for line in p.start_gcode.splitlines():
            A(line)

        z_up_cmd = f"G0 Z{p.z_pen_up:.3f} F{p.z_speed:.0f}"
        z_dn_cmd = f"G0 Z{p.z_pen_down:.3f} F{p.z_speed:.0f}"
        F_TRAVEL = f"F{p.travel_speed:.0f}"
        F_DRAW = f"F{p.draw_speed:.0f}"

        cur_x = cur_y = 0.0
        cur_z = p.z_pen_down  # после стартового кода считаем, что ручка внизу

        def set_z(target: float) -> None:
            nonlocal cur_z
            if abs(cur_z - target) < 1e-6:
                return
            A(z_up_cmd if target == p.z_pen_up else z_dn_cmd)
            if target == p.z_pen_up:
                stats.pen_lifts += 1
            cur_z = target

        def travel_to(x: float, y: float) -> None:
            """Переход к точке. Считает stats."""
            nonlocal cur_x, cur_y
            if p.lift_on_travel:
                set_z(p.z_pen_up)
            if abs(cur_x - x) < 1e-6 and abs(cur_y - y) < 1e-6 and \
                    not (p.lift_on_travel and cur_z == p.z_pen_down):
                return
            fx, fy = self._fmt(x, y)
            A(f"G0 X{fx} Y{fy} {F_TRAVEL}")
            stats.travel_mm += math_dist(cur_x, cur_y, x, y)
            cur_x, cur_y = x, y

        def draw_to(x: float, y: float) -> None:
            nonlocal cur_x, cur_y
            set_z(p.z_pen_down)
            fx, fy = self._fmt(x, y)
            A(f"G1 X{fx} Y{fy} {F_DRAW}")
            stats.draw_mm += math_dist(cur_x, cur_y, x, y)
            stats.segments += 1
            cur_x, cur_y = x, y

        passes = max(1, int(p.passes))
        off = abs(float(p.pass_offset_mm))
        if passes > 1 and off == 0:
            off = 0.05

        # подъём в старт и переезд в начало рисунка (принтер «дома»)
        set_z(p.z_pen_up)
        cur_x = cur_y = 0.0
        travel_to(*self.to_bed(0, 0))

        n = 0
        for pass_i in range(passes):
            # смещение прохода по диагонали, чтобы линия легла плотнее
            ox = oy = off * pass_i
            A(f"; ---------- проход {pass_i + 1}/{passes} ----------")
            for path in paths:
                if not path:
                    continue
                n += 1
                bed_pts: list[Point] = [self.to_bed(px + ox, py + oy) for px, py in path]
                sx, sy = bed_pts[0]
                travel_to(sx, sy)
                if len(bed_pts) == 1:
                    # одиночная точка — короткий штрих-«засечка»
                    draw_to(sx + 0.6, sy)
                    draw_to(sx, sy)
                    continue
                for x, y in bed_pts[1:]:
                    draw_to(x, y)
            A(f"; ---------- конец прохода {pass_i + 1} ----------")

        # финал: подъём и возврат к началу
        set_z(p.z_pen_up)
        fx, fy = self._fmt(0.0, 0.0)
        A(f"G0 X{fx} Y{fy} {F_TRAVEL}")
        stats.travel_mm += math_dist(cur_x, cur_y, 0.0, 0.0)
        cur_x = cur_y = 0.0

        for line in p.end_gcode.splitlines():
            A(line)
        A("; ---- конец файла ----")

        # оценка времени
        t = 0.0
        t += stats.draw_mm / max(1.0, p.draw_speed)
        t += stats.travel_mm / max(1.0, p.travel_speed)
        t += stats.pen_lifts * (p.z_pen_up - p.z_pen_down) / max(1.0, p.z_speed)
        # ~10% на задержки/ускорения
        stats.est_minutes = t * 1.1
        stats.lines = len(out)

        return "\n".join(out) + "\n", stats


def math_dist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)
