"""Загрузка DXF -> пути в мм (конвенция «изображения»: y вниз, (0,0) сверху-слева).

Поддерживаются сущности modelspace:
  LINE, LWPOLYLINE (с bulge-дугами), POLYLINE/VERTEX (с bulge), CIRCLE,
  ARC, SPLINE, ELLIPSE (SPLINE/ELLIPSE — через flattening ezdxf).
TEXT/MTEXT/INSERT и 3D-геометрия пропускаются (плоттеру нечем их «рисуночить»).

Единицы: $INSUNITS (0/не задано — считаем мм; 1 мм, 2 см, 4 дюйм, 5 фут).
Возврат: (paths_mm, w_mm, h_mm) — w/h — габариты рисунка.
"""
from __future__ import annotations

import math

from .tracing import Path, Paths

# $INSUNITS -> множитель до мм
_UNIT_TO_MM = {0: 1.0, 1: 1.0, 2: 10.0, 3: 100.0, 4: 25.4,
               5: 304.8, 6: 3048.0, 7: 3048000.0, 8: 3048000000.0,
               9: 3048000000000.0}


def _arc_from_bulge(p0: tuple[float, float], p1: tuple[float, float],
                    bulge: float, max_step_deg: float = 10.0) -> list:
    """Дуга по хорде P0->P1 и bulge (tan(θ/4)) -> список точек (без P0)."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    chord = math.hypot(dx, dy)
    if chord < 1e-9 or abs(bulge) < 1e-9:
        return []
    theta = 4.0 * math.atan(bulge)  # signed
    half = chord / 2.0
    r = half / abs(math.sin(theta / 2.0))
    d = math.sqrt(max(r * r - half * half, 0.0))
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    nx, ny = -dy / chord, dx / chord
    ccw = theta > 0
    for sgn in (1.0, -1.0):
        cx, cy = mx + sgn * nx * d, my + sgn * ny * d
        a0 = math.atan2(y0 - cy, x0 - cx)
        a1 = math.atan2(y1 - cy, x1 - cx)
        if ccw:
            sweep = (a1 - a0) % (2 * math.pi)
        else:
            sweep = -((a0 - a1) % (2 * math.pi))
        if abs(sweep - abs(theta)) > 5e-3:
            continue
        nseg = max(4, int(abs(theta) / math.radians(max_step_deg)))
        pts = []
        for s in range(1, nseg + 1):
            a = a0 + sweep * s / nseg
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return pts
    return []


def _circle_points(r: float, cx: float, cy: float) -> list:
    nseg = max(16, min(720, int(2 * math.pi * r / 0.5)))  # хорда ~0.5 мм
    pts = []
    for s in range(nseg + 1):
        a = 2 * math.pi * s / nseg
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _arc_points(r: float, cx: float, cy: float,
                a0_deg: float, a1_deg: float) -> list:
    a0 = math.radians(a0_deg)
    a1 = math.radians(a1_deg)
    sweep = (a1 - a0) % (2 * math.pi)  # DXF: против часовой
    if sweep < 1e-6:
        sweep = 2 * math.pi
    nseg = max(4, int(sweep / math.radians(10.0)))
    pts = []
    for s in range(nseg + 1):
        a = a0 + sweep * s / nseg
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _lwpline(e) -> list:
    pts_raw = list(e.get_points(format="xyseb"))
    if not pts_raw:
        return []
    closed = bool(e.closed)
    n = len(pts_raw)
    pts = []
    for i in range(n):
        x, y, _sw, _ew, bulge = pts_raw[i]
        pts.append((x, y))
        if abs(bulge) > 1e-9:
            j = (i + 1) % n if closed else i + 1
            if i + 1 < n or closed:
                x2, y2, _s2, _e2, _b2 = pts_raw[j]
                pts.extend(_arc_from_bulge((x, y), (x2, y2), bulge))
    if closed and n > 1:
        pts.append(pts[0])
    return pts


def _polyline(e) -> list:
    verts = [(v.dxf.location.x, v.dxf.location.y, v.get("dxf.bulge", 0.0))
             for v in e if v.dxftype() == "VERTEX"]
    if not verts:
        return []
    closed = bool(getattr(e.dxf, "flags", 0) & 1)
    n = len(verts)
    pts = []
    for i in range(n):
        x, y, b = verts[i]
        pts.append((x, y))
        if abs(b) > 1e-9 and (i + 1 < n or closed):
            x2, y2, _b2 = verts[(i + 1) % n]
            pts.extend(_arc_from_bulge((x, y), (x2, y2), b))
    if closed and n > 1:
        pts.append(pts[0])
    return pts


def load_dxf(path: str) -> tuple[Paths, float, float]:
    """Читает DXF. :return: (paths в мм «image-конвенции», w_mm, h_mm).

    Пустой/несовместимый файл -> ([], 0.0, 0.0) (UI покажет сообщение).
    """
    import ezdxf
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    try:
        unit = int(doc.header.get("$INSUNITS", 0))
    except Exception:
        unit = 0
    k = _UNIT_TO_MM.get(unit, 1.0)

    raw: list[list[tuple[float, float]]] = []
    for e in msp:
        t = e.dxftype()
        try:
            if t == "LINE":
                s, en = e.dxf.start, e.dxf.end
                pts = [(s.x, s.y), (en.x, en.y)]
            elif t == "LWPOLYLINE":
                pts = _lwpline(e)
            elif t == "POLYLINE":
                pts = _polyline(e)
            elif t == "CIRCLE":
                pts = _circle_points(e.dxf.radius, e.dxf.center.x, e.dxf.center.y)
            elif t == "ARC":
                pts = _arc_points(e.dxf.radius, e.dxf.center.x, e.dxf.center.y,
                                  e.dxf.start_angle, e.dxf.end_angle)
            elif t in ("SPLINE", "ELLIPSE"):
                pts = [(float(x), float(y)) for x, y in e.flattening(0.1)]
            else:
                continue
        except Exception:
            continue
        if len(pts) >= 2:
            raw.append([(x * k, y * k) for x, y in pts])

    if not raw:
        return [], 0.0, 0.0

    xs = [x for path in raw for x, _ in path]
    ys = [y for path in raw for _x, y in path]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = maxx - minx
    h = maxy - miny
    # image-конвенция: (0,0) сверху-слева, y вниз (как у картинок) —
    # GCodeGenerator сам перевернёт y на стол
    out: Paths = []
    for path in raw:
        out.append([(x - minx, maxy - y) for x, y in path])
    return out, float(w), float(h)
