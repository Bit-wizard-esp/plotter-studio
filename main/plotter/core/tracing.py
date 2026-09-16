"""Трассировка бинарной маски в пути (списки отрезков/полигонов в мм).

Режимы:
  raster  — построчные линии (горизонтальные/вертикальные, классика для фото)
  contour — все контуры, включая внутренние дырки (OpenCV findContours)
  outline — только внешние контуры, один обход, без дырок
  inner   — только внутренние контуры (границы замкнутых областей фона);
            для раскрасок даёт чистые одиночные замкнутые кривые
  skeleton— центральные линии (thinning) — векторный режим для раскрасок
  crawl   — непрерывное «ползание», прямой порт алгоритма из
            MagicGyver (tracer-test/main.js): голова прыгает по тёмным
            пикселям, расширяя поисковое кольцо, ручка почти не отрывается
  waves   — непрерывные волны, амплитуда следует за тёмнотою фото

Общее:
  smooth_iters — сглаживание Чакина (0 = выкл; для почерка 2..4,
                 до 24 «на глаз» — прореживание держит число точек под контролем)
  contour/outline/inner — замкнутые полигоны (первая точка повторяется в конце),
  остальные режимы — открытые ломаные

Все пути — списки точек (x_mm, y_mm) в координатах изображения
(0,0 — верхний левый угол, y — вниз).
"""
from __future__ import annotations

import math
from typing import List

import cv2
import numpy as np

from .settings import TraceSettings

Path = List[tuple[float, float]]
Paths = List[Path]


# ---------------------------------------------------------------------------
# Raster
# ---------------------------------------------------------------------------
def trace_raster(mask: np.ndarray, mm_per_px: float, ts: TraceSettings) -> Paths:
    step = max(1, int(ts.raster_row_step))
    min_len = max(1, int(ts.raster_min_len_px))
    vertical = bool(ts.raster_vertical)
    m = mask.T if vertical else mask
    h, w = m.shape
    paths: Paths = []

    for y in range(0, h, step):
        row = m[y] > 0
        if not row.any():
            continue
        idx = np.flatnonzero(row)
        # границы «зубов» тёмных областей
        breaks = np.flatnonzero(np.diff(idx) > 1) + 1
        runs = np.split(idx, breaks)
        for run in runs:
            if len(run) < min_len:
                continue
            x1, x2 = float(run[0]), float(run[-1] + 1)
            if vertical:
                # сканировали столбцы: (y, x) -> (x, y)
                paths.append(((y * mm_per_px, x1 * mm_per_px),
                              (y * mm_per_px, x2 * mm_per_px)))
            else:
                paths.append(((x1 * mm_per_px, y * mm_per_px),
                              (x2 * mm_per_px, y * mm_per_px)))
    return paths


# ---------------------------------------------------------------------------
# Точный (субпиксельный) контур — marching squares по СЕРОМУ изображению
# ---------------------------------------------------------------------------
def _edge_gray(gray: np.ndarray, proc) -> np.ndarray:
    """Серое изображение «так, как его видит маска»: утолщение + сшивка.
    Морфология коммутирует с порогом, поэтому изоконтур этого изображения
    в точности совпадает с границей финальной бинарной маски — но с
    субпиксельной интерполяцией на анти-алейсированных краях."""
    out = gray
    k = int(proc.thicken_px)
    if k > 0:
        out = cv2.dilate(out, np.ones((2 * k + 1, 2 * k + 1), np.uint8))
    k = int(proc.bridge_px)
    if k > 0:
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, np.ones((2 * k + 1, 2 * k + 1), np.uint8))
    return out


def marching_squares_boundary(gray: np.ndarray, level: float,
                              ink_below: bool = True) -> list[np.ndarray]:
    """Замкнутые изоконтуры уровня level на сером изображении (marching
    squares с линейной интерполяцией). Точки — (x, y) в пикселях (float):
    точное место, где серое значение пересекает порог. На анти-алейсированном
    крае это существенно точнее «лесенки» findContours по бинарной маске.

    :param gray: серое изображение (uint8)
    :param level: порог (0..255)
    :param ink_below: чернила — значения НИЖЕ уровня (тёмное рисуем)
    :return: список контуров (N, 2) float32 без повтора первой точки
    """
    g = gray.astype(np.float32)
    # Подложка «не-чернил» по краям: контуры у границы изображения не рвутся
    pad = 4
    fill = 255.0 if ink_below else 0.0
    g = np.pad(g, pad, mode="constant", constant_values=fill)

    W = np.lib.stride_tricks.sliding_window_view(g, (2, 2))  # (H-1, W-1, 2, 2)
    a = W[..., 0, 0]  # TL
    b = W[..., 0, 1]  # TR
    c = W[..., 1, 1]  # BR
    d = W[..., 1, 0]  # BL

    if ink_below:
        ia, ib, ic, idk = a < level, b < level, c < level, d < level
    else:
        ia, ib, ic, idk = a > level, b > level, c > level, d > level
    case = (ia.view(np.int8) + 2 * ib.view(np.int8)
            + 4 * ic.view(np.int8) + 8 * idk.view(np.int8))

    def _t(v0: np.ndarray, v1: np.ndarray) -> np.ndarray:
        """Доля 0..1, где значение на отрезке v0->v1 пересекает уровень."""
        denom = v1 - v0
        safe = np.where(denom != 0.0, denom, 1.0)
        t = np.where(denom != 0.0, (level - v0) / safe, 0.5)
        return np.clip(t, 0.0, 1.0)

    t_top, t_bot = _t(a, b), _t(d, c)
    t_lft, t_rgt = _t(a, d), _t(b, c)

    Hc, Wc = W.shape[0], W.shape[1]
    xx = np.broadcast_to(np.arange(Wc, dtype=np.float32)[None, :], (Hc, Wc))
    yy = np.broadcast_to(np.arange(Hc, dtype=np.float32)[:, None], (Hc, Wc))
    P = {"T": (xx + t_top, yy),         # верх:    (cx + t, cy)
         "B": (xx + t_bot, yy + 1.0),   # низ:     (cx + t, cy + 1)
         "L": (xx, yy + t_lft),         # лево:    (cx, cy + t)
         "R": (xx + 1.0, yy + t_rgt)}   # право:   (cx + 1, cy + t)

    # Таблица случаев: какие стороны клетки пересекает изоконтур
    # (5 и 10 — седловые: разбиваем согласованно)
    table = {
        1: [("L", "T")], 2: [("T", "R")], 3: [("L", "R")], 4: [("R", "B")],
        5: [("L", "T"), ("R", "B")], 6: [("T", "B")], 7: [("L", "B")],
        8: [("L", "B")], 9: [("T", "B")], 10: [("T", "R"), ("L", "B")],
        11: [("R", "B")], 12: [("L", "R")], 13: [("T", "R")], 14: [("L", "T")],
    }

    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for val, pairs in table.items():
        m = case == val
        if not m.any():
            continue
        for s1, s2 in pairs:
            x1, y1 = P[s1][0][m], P[s1][1][m]
            x2, y2 = P[s2][0][m], P[s2][1][m]
            for i in range(x1.size):
                segs.append(((float(x1[i]), float(y1[i])),
                             (float(x2[i]), float(y2[i]))))
    if not segs:
        return []

    # --- склейка сегментов в замкнутые петли ---
    # Соседние клетки считают общую точку ОДНИМИ И ТОМИ ЖЕ формулами,
    # поэтому «ключи» (координаты с округлением) совпадают строго.
    def _key(p):
        return (int(round(p[0] * 1e4)), int(round(p[1] * 1e4)))

    nbrs: dict[tuple, list[tuple[tuple[float, float], tuple]]] = {}
    coord: dict[tuple, tuple[float, float]] = {}
    for p1, p2 in segs:
        k1, k2 = _key(p1), _key(p2)
        coord[k1] = p1
        coord[k2] = p2
        nbrs.setdefault(k1, []).append((p2, k2))
        nbrs.setdefault(k2, []).append((p1, k1))

    contours: list[np.ndarray] = []
    done: set[tuple] = set()
    for s in list(nbrs):
        if s in done or len(nbrs[s]) < 2:
            continue
        # Обход петли: в каждой вершине идём не «назад».
        # Замкнутая изоконтурная кривая возвращается к стартовой вершине.
        done.add(s)
        loop = [coord[s]]
        prev_k, cur_k = None, s
        closed = False
        for _ in range(len(segs) + 2):
            nxt = None
            for pt, kk in nbrs[cur_k]:
                if kk != prev_k:
                    nxt = (pt, kk)
                    break
            if nxt is None:
                break
            npt, nkk = nxt
            if nkk == s:
                closed = len(loop) >= 3
                break
            loop.append(npt)
            done.add(nkk)
            prev_k, cur_k = cur_k, nkk
        if closed:
            arr = np.array(loop, dtype=np.float32) - pad
            contours.append(arr)
    return contours


def _shoelace_area_px(c: np.ndarray) -> float:
    """Площадь контура (формула шнурка), px^2."""
    x, y = c[:, 0], c[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _filter_external(contours: list[np.ndarray]) -> list[np.ndarray]:
    """Оставить только внешние контуры: удалить «дырки» (контуры,
    целиком лежащие внутри другого, более крупного)."""
    order = sorted(range(len(contours)), key=lambda i: -_shoelace_area_px(contours[i]))
    keep: list[np.ndarray] = []
    big_list: list[np.ndarray] = []
    for i in order:
        c = np.ascontiguousarray(contours[i], dtype=np.float32)
        pt = (float(c[:, 0].mean()), float(c[:, 1].mean()))
        is_hole = False
        for big in big_list:
            if cv2.pointPolygonTest(big, pt, False) >= 0.0:
                is_hole = True
                break
        if not is_hole:
            keep.append(contours[i])
            big_list.append(c)
    return keep


def _trace_contours_precise(gray: np.ndarray, mm_per_px: float,
                            ts: TraceSettings, proc) -> Paths:
    """Точный контур (субпиксельный) по серому изображению.
    gray — обработанное серое (до порога); proc — уровень порога и то же
    утолщение/сшивка, что применены к маске (морфология коммутирует с
    порогом, поэтому изоконтур = граница финальной бинарной маски)."""
    g = _edge_gray(gray, proc)
    level = float(int(np.clip(proc.threshold, 0.0, 1.0) * 255))
    contours = marching_squares_boundary(g, level, ink_below=not bool(proc.invert))
    if ts.mode == "outline":
        contours = _filter_external(contours)
    elif ts.mode == "inner":
        ink_below = not bool(proc.invert)
        ink = (g < level) if ink_below else (g >= level)
        contours = _filter_internal_bands(
            contours, ink.astype(np.uint8), pad_is_ink=not ink_below)
    contours.sort(key=lambda c: -_shoelace_area_px(c))
    h_g, w_g = g.shape
    # Субпиксельная интерполяция на «жёстком» крае у границы изображения
    # может дать точку до ~0.5 px за рамкой (пересечение уровня в зоне
    # подложки). Климпим: G-код не должен уходить за рисунок/стол.
    contours = [np.clip(c, 0.0, np.array([w_g, h_g], dtype=np.float32))
                for c in contours]

    min_area = max(1.0, float(ts.contour_min_area_px))
    eps = float(ts.contour_smooth_px)
    paths: Paths = []
    for c in contours:
        if _shoelace_area_px(c) < min_area:
            continue
        if len(c) > 30_000:  # потолок точек на один контур
            c = c[::len(c) // 30_000 + 1]
        if eps > 0:
            # approxPolyDP на (N,2) возвращает (M,1,2) — приводим обратно
            c = cv2.approxPolyDP(np.ascontiguousarray(c, dtype=np.float32),
                                 float(eps), True).reshape(-1, 2)
        if len(c) < 3:
            continue
        paths.append([(float(x) * mm_per_px, float(y) * mm_per_px) for x, y in c])
    return paths


def trace_contour(mask: np.ndarray, mm_per_px: float, ts: TraceSettings) -> Paths:
    """Все контуры, включая внутренние (дырки): RETR_LIST."""
    return _trace_contours(mask, mm_per_px, ts, mode=cv2.RETR_LIST)


def trace_outline(mask: np.ndarray, mm_per_px: float, ts: TraceSettings) -> Paths:
    """Режим «1 линия»: только внешние контуры, каждый обходится один раз.
    Дырки не рисуются — чистый силуэт для ручного обвода/почерка."""
    return _trace_contours(mask, mm_per_px, ts, mode=cv2.RETR_EXTERNAL)


def trace_inner(mask: np.ndarray, mm_per_px: float, ts: TraceSettings) -> Paths:
    """Только ВНУТРЕННИЕ контуры: границы замкнутых областей фона («дырок»),
    окружённых чернилами. Фон, касающийся края изображения, исключён.

    Важно: RETR_EXTERNAL здесь НЕЛЬЗЯ — вложенные области (светлое «внутри»
    светлого) он пропускает; поэтому RETR_LIST + отсев по касанию границы.
    Для фото с закрашенными фигурами это даёт дырки/внутренние детали;
    для раскрасок-линеек — внутреннюю сторону каждого штриха (чистые
    одиночные линии рисует режим «Линии раскраски (вектор)»).
    """
    inv = cv2.bitwise_not(mask)
    contours, _ = cv2.findContours(inv, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = mask.shape
    # внешний фон = компонент фона, касающийся границы изображения.
    # (По bbox контура это определять НЕНАДЁЖНО: контур внешнего фона
    # рисуется по краю чернил и границу касаться может не обязан.)
    outer = None
    nlab, labels = cv2.connectedComponents(inv)
    if nlab > 1:
        b = np.concatenate([inv[0].ravel(), inv[-1].ravel(),
                            inv[:, 0].ravel(), inv[:, -1].ravel()])
        lb = np.concatenate([labels[0].ravel(), labels[-1].ravel(),
                             labels[:, 0].ravel(), labels[:, -1].ravel()])
        if b.any():
            outer = int(lb[b > 0][0])
    min_area = max(1.0, float(ts.contour_min_area_px))
    eps = max(0.0, float(ts.contour_smooth_px))
    paths: Paths = []
    for c in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) < min_area:
            continue
        if outer is not None:
            xs = np.clip(np.round(c[:, 0, 0]).astype(int), 0, w - 1)
            ys = np.clip(np.round(c[:, 0, 1]).astype(int), 0, h - 1)
            step = max(1, len(xs) // 40)
            touches_enclosed = False
            for i in range(0, len(xs), step):
                y0, y1 = max(0, ys[i] - 2), min(h, ys[i] + 3)
                x0, x1 = max(0, xs[i] - 2), min(w, xs[i] + 3)
                win = inv[y0:y1, x0:x1]
                if (win > 0).any():
                    if labels[y0:y1, x0:x1][win > 0][0] != outer:
                        touches_enclosed = True
                        break
            if not touches_enclosed:
                continue
        if eps > 0:
            c = cv2.approxPolyDP(c, eps, True)
        pts = [(float(p[0][0]) * mm_per_px, float(p[0][1]) * mm_per_px) for p in c]
        if len(pts) >= 3:
            paths.append(pts)
    return paths


def _filter_internal_bands(contours: list[np.ndarray], ink: np.ndarray,
                           pad_is_ink: bool = False) -> list[np.ndarray]:
    """Для прецизионного «Контур: внутренний»: оставить только изоконтуры,
    внутри которых фон (не чернила) — то есть границы замкнутых «дырок».

    Классификация: помечаем компоненты фона в ПОДОПЛАНИРОВАННОМ (pad=4,
    как в marching squares) массиве — с той же подложкой, что и там
    (pad_is_ink: в режиме invert подложка — «чернила»). Угол подложки
    ВСЕГДА «внешний» — даже когда чернила доходят до края изображения и
    реального внешнего фона внутри картинки нет (иначе артефакт подложки
    давал бы лишнюю линию по краю фото). Изоконтур «внутренний», если
    рядом с ним (на стороне фона) встречается замкнутая область."""
    pad = 4
    p_ink = np.pad(ink, pad, mode="constant",
                   constant_values=1 if pad_is_ink else 0)
    ph, pw = p_ink.shape
    bg = (p_ink == 0).astype(np.uint8)
    if not bg.any():
        return []
    _n, labels = cv2.connectedComponents(bg)
    # «внешний» фон = метки, достигающие края изображения.
    #  - подложка-фон:  достаточно угла подложки (она связывает весь
    #    внешний фон, включая реальный, если он есть);
    #  - подложка-чернила (invert): внешнего фонда в подопланировке нет,
    #    берём компоненты фона, касающиеся границы изображения.
    outer_labels: set[int] = set()
    corner_lab = int(labels[0, 0])
    if corner_lab != 0:
        outer_labels.add(corner_lab)
    bi = bg[pad:-pad, pad:-pad]
    li = labels[pad:-pad, pad:-pad]
    b = np.concatenate([bi[0].ravel(), bi[-1].ravel(),
                        bi[:, 0].ravel(), bi[:, -1].ravel()])
    lb = np.concatenate([li[0].ravel(), li[-1].ravel(),
                         li[:, 0].ravel(), li[:, -1].ravel()])
    if b.any():
        outer_labels.update(int(v) for v in np.unique(lb[b > 0]))
    if not outer_labels:
        # чернила (или фон) не дают внешнего фонда — всё замкнуто
        return list(contours)
    keep = []
    for c in contours:
        xs = np.clip(np.round(c[:, 0]).astype(int) + pad, 0, pw - 1)
        ys = np.clip(np.round(c[:, 1]).astype(int) + pad, 0, ph - 1)
        step = max(1, len(xs) // 40)
        is_hole = False
        for i in range(0, len(xs), step):
            y0, y1 = max(0, ys[i] - 2), min(ph, ys[i] + 3)
            x0, x1 = max(0, xs[i] - 2), min(pw, xs[i] + 3)
            win = p_ink[y0:y1, x0:x1]
            if (win == 0).any():
                lab = int(labels[y0:y1, x0:x1][win == 0][0])
                if lab not in outer_labels:
                    is_hole = True
                    break
        if is_hole:
            keep.append(c)
    return keep


def _trace_contours(mask: np.ndarray, mm_per_px: float, ts: TraceSettings,
                    mode: int) -> Paths:
    contours, _ = cv2.findContours(mask, mode, cv2.CHAIN_APPROX_SIMPLE)
    paths: Paths = []
    min_area = max(1.0, float(ts.contour_min_area_px))
    eps = max(0.0, float(ts.contour_smooth_px))

    for c in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) < min_area:
            continue
        if eps > 0:
            c = cv2.approxPolyDP(c, eps, True)
        pts = [(float(p[0][0]) * mm_per_px, float(p[0][1]) * mm_per_px) for p in c]
        if len(pts) >= 2:
            paths.append(pts)
    return paths


# ---------------------------------------------------------------------------
# Skeleton — центральные линии «раскрасок» (векторный режим)
# ---------------------------------------------------------------------------
def thinning(mask: np.ndarray) -> np.ndarray:
    """Осталкивание (Zhang-Suen, numpy-векторизованно): линию любой ширины
    сводит к 1-пиксельному скелету, сохраняя форму и связность.
    :param mask: бинарная маска (255 = чернила)
    :return: скелет (uint8 0/255)
    """
    m = (mask > 0).astype(np.uint8)

    def substep(a1: tuple[str, str, str], a2: tuple[str, str, str]) -> bool:
        P = np.pad(m, 1, mode="constant")
        n = {"P1": P[:-2, 1:-1], "P2": P[:-2, 2:], "P3": P[1:-1, 2:],
             "P4": P[2:, 2:], "P5": P[2:, 1:-1], "P6": P[2:, :-2],
             "P7": P[1:-1, :-2], "P8": P[:-2, :-2]}
        B = sum(n[f"P{i}"] for i in range(1, 9))
        seq = [f"P{i}" for i in range(1, 9)]
        A = sum((n[a] == 0) & (n[b] == 1) for a, b in zip(seq, seq[1:] + seq[:1]))
        base = (m == 1) & (B >= 2) & (B <= 6) & (A == 1)
        cond = base & ((n[a1[0]] * n[a1[1]] * n[a1[2]] == 0)
                       & (n[a2[0]] * n[a2[1]] * n[a2[2]] == 0))
        if not cond.any():
            return False
        m[cond] = 0
        return True

    while True:
        changed_a = substep(("P1", "P3", "P5"), ("P3", "P5", "P7"))
        changed_b = substep(("P1", "P3", "P7"), ("P1", "P5", "P7"))
        if not (changed_a or changed_b):
            break
    return m * 255


def _nbr8(x: int, y: int):
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1),
            (x + 1, y + 1), (x + 1, y - 1), (x - 1, y + 1), (x - 1, y - 1))


def prune_spurs(pts: set, min_branch: int = 5) -> set:
    """Убрать короткие «усы» скелета: ветви короче min_branch пикселей,
    идущие от развилки/конца в тупик. Frontier-обход: пересчитываем степени
    только рядом с удалёнными пикселями (быстро даже на 100k+ px)."""
    from collections import deque
    cur = set(pts)
    deg = {p: sum(1 for q in _nbr8(*p) if q in cur) for p in cur}
    frontier = deque(p for p, d in deg.items() if d == 1)
    while frontier:
        e = frontier.popleft()
        if e not in cur or deg.get(e, 0) != 1:
            continue
        # идём от конца до развилки/другого конца
        path = [e]
        prev, curp = None, e
        while True:
            d = deg.get(curp, 0)
            nxts = [q for q in _nbr8(*curp) if q in cur and q != prev]
            if not nxts or (d >= 3 and len(path) > 1):
                break
            nxt = nxts[0]
            path.append(nxt)
            prev, curp = curp, nxt
        if 2 <= len(path) < min_branch:
            removed = path[:-1]  # развилку/противоположный конец не трогаем
            for p in removed:
                cur.discard(p)
            for p in removed:
                for q in _nbr8(*p):
                    if q in cur:
                        deg[q] -= 1
                        if deg[q] == 1 and q not in path:
                            frontier.append(q)
    return cur


def _merge_collinear(paths_px: list, max_gap: float = 3.0,
                     max_angle: float = 25.0) -> list:
    """Сшить коллинеарные фрагменты (скелет рвёт линии на штрихи).

    Однопроходный вариант: для каждого конца пути ищем «продолжение» —
    конец другого пути в пределах max_gap с углом поворота <= max_angle.
    Полученные ссылки сшиваем в цепочки; цикл = замкнутая дуга."""
    import math
    if len(paths_px) < 2:
        return paths_px
    gap2 = max_gap * max_gap
    max_ang = math.radians(max_angle)
    cell = max(1, int(max_gap))
    NEIGH = ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
             (1, 1), (1, -1), (-1, 1), (-1, -1))

    def exit_dir(p, is_end):
        """Направление движения ВНЕЗ из конца (None для 1-точечного)."""
        if len(p) < 2:
            return None
        a, b = (p[-2], p[-1]) if is_end else (p[1], p[0])
        return math.atan2(b[1] - a[1], b[0] - a[0])

    n = len(paths_px)
    ends = []  # (i, is_end, pt, exit_dir)
    for i, p in enumerate(paths_px):
        ends.append((i, 0, p[0], (exit_dir(p, 0) + math.pi) % (2 * math.pi)))
        ends.append((i, 1, p[-1], exit_dir(p, 1)))
    grid = {}
    for idx, (i, e, pt, d) in enumerate(ends):
        grid.setdefault((pt[0] // cell, pt[1] // cell), []).append(idx)

    # best_link[(i, e)] = (j, e2): выходим из (i, e) -> входим в (j, e2)
    best_link: dict = {}
    for idx, (i, e, pt, d) in enumerate(ends):
        ci, cj = pt[0] // cell, pt[1] // cell
        best = None
        best_ang = max_ang + 1e-9
        for (di, dj) in NEIGH:
            for idx2 in grid.get((ci + di, cj + dj), ()):
                if idx2 == idx:
                    continue
                j, e2, pt2, _ = ends[idx2]
                if j == i:
                    continue
                d2 = (pt[0] - pt2[0]) ** 2 + (pt[1] - pt2[1]) ** 2
                if d2 > gap2:
                    continue
                if d is None:
                    ang = 0.0
                else:
                    # направление, в котором продолжение уходит от pt2
                    cont = exit_dir(paths_px[j], e2)
                    if cont is None:
                        ang = 0.0
                    else:
                        if e2 == 1:
                            cont = (cont + math.pi) % (2 * math.pi)
                        ang = d - cont
                        ang = (ang + math.pi) % (2 * math.pi) - math.pi
                        ang = abs(ang)
                if ang <= best_ang:
                    best, best_ang = (j, e2), ang
        if best is not None:
            best_link[(i, e)] = best

    incoming: dict = {}
    for (k, e2), (i, e) in best_link.items():
        incoming[(i, e)] = (k, e2)

    result = []
    used = set()
    for i in range(n):
        if i in used:
            continue
        start_end = None
        for e in (1, 0):
            if (i, e) not in incoming:
                start_end = (i, e)
                break
        if start_end is None:
            start_end = (i, 0)  # замкнутый цикл фрагментов
        segs = []
        cur = start_end
        seen = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            ci_, ce = cur
            if ci_ in used and not any(
                    s[0] == ci_ for s in segs):
                break
            used.add(ci_)
            segs.append((ci_, ce))
            cur = best_link.get((ci_, 1 - ce))
        pts_out = []
        for (ci_, ce) in segs:
            seg = paths_px[ci_][::-1] if ce else list(paths_px[ci_])
            if pts_out and seg and seg[0] == pts_out[-1]:
                seg = seg[1:]
            pts_out.extend(seg)
        if len(pts_out) < 2:
            continue
        outp = [pts_out[0]]
        for q in pts_out[1:]:
            if q != outp[-1]:
                outp.append(q)
        if len(outp) >= 2:
            result.append(outp)
    return result


def skeleton_to_paths(skel: np.ndarray, mm_per_px: float,
                      min_len_mm: float = 1.0, prune: int = 5) -> Paths:
    """Скелет (1px линия) -> упорядоченные полилинии (вектор).

    Алгоритм: граф пикселей (8-связность) -> обрезка «усов» -> обход от
    концов/развилений + двусторонние цепочки -> прицеп одиночных пикселей
    («бусин») -> сшивка коллинеарных фрагментов (разрывы скелета) ->
    упрощение Douglas-Peucker («лесенка» -> чистые отрезки) -> короткие отбросить.
    """
    ys, xs = np.where(skel > 0)
    if xs.size == 0:
        return []
    pts = set(zip(xs.tolist(), ys.tolist()))
    if prune and prune > 1:
        pts = prune_spurs(pts, prune)

    def nbrs(p):
        x, y = p
        return [q for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1),
                            (x + 1, y + 1), (x + 1, y - 1), (x - 1, y + 1),
                            (x - 1, y - 1)) if q in pts]

    degree = {p: len(nbrs(p)) for p in pts}
    covered: set = set()
    paths_px: list[list[tuple[int, int]]] = []

    def push(path):
        if len(path) >= 2:
            paths_px.append(path)
            covered.update(path)

    # 1) от концов линий: вперёд до развилки/уже покрытого
    for p in sorted(pts):
        if degree[p] == 1 and p not in covered:
            path = [p]
            covered.add(p)
            prev, cur = None, p
            while True:
                cand = [q for q in nbrs(cur)
                        if q != prev and not (len(path) >= 2 and q == path[-2])]
                if not cand:
                    break
                nxt = cand[0]
                if nxt in covered:
                    break
                if degree.get(nxt, 0) >= 3 and len(path) >= 2:
                    path.append(nxt)
                    covered.add(nxt)
                    break
                path.append(nxt)
                covered.add(nxt)
                prev, cur = cur, nxt
            push(path)

    # 2) ветви из развилений (каждая ветвь — свой путь, общий узел)
    for j in sorted(pts):
        if degree.get(j, 0) < 3:
            continue
        for q in nbrs(j):
            if q in covered or degree.get(q, 0) >= 3:
                continue
            path = [j, q]
            covered.add(j)
            covered.add(q)
            prev, cur = j, q
            while True:
                cand = [x for x in nbrs(cur) if x != prev]
                if not cand:
                    break
                nxt = cand[0]
                if nxt in covered:
                    break
                if degree.get(nxt, 0) >= 3:
                    path.append(nxt)
                    covered.add(nxt)
                    break
                path.append(nxt)
                covered.add(nxt)
                prev, cur = cur, nxt
            push(path)

    # 3) оставшиеся цепочки и циклы (степень 2): идём от середины в обе стороны
    for p in sorted(pts):
        if p in covered or degree.get(p, 0) != 2:
            continue
        path = [p]
        covered.add(p)
        for n0 in nbrs(p):
            if n0 in covered and degree.get(n0, 0) < 3:
                continue
            prev, cur = None, n0
            while True:
                if cur in covered:
                    break
                path.append(cur)
                covered.add(cur)
                if degree.get(cur, 0) >= 3:
                    break
                opts = [q for q in nbrs(cur) if q != prev]
                if not opts:
                    break
                prev, cur = cur, opts[0]
        push(path)

    # одиночные пиксели разорванного скелета («бусины»): прицепляем к
    # ближайшему концу пути (пространственный хэш — быстро)
    if pts - covered:
        cell = 4
        end_grid: dict = {}
        for i, path in enumerate(paths_px):
            for end in (0, -1):
                q = path[end]
                end_grid.setdefault((q[0] // cell, q[1] // cell), []).append((i, end))
        for p in sorted(pts - covered):
            cx, cy = p[0] // cell, p[1] // cell
            best = None
            best_d = 3.0 ** 2
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for (i, end) in end_grid.get((cx + di, cy + dj), ()):
                        q = paths_px[i][end]
                        d2 = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2
                        if d2 < best_d:
                            best, best_d = (i, end), d2
            if best is not None:
                i, end = best
                if end == -1:
                    paths_px[i].append(p)
                else:
                    paths_px[i].insert(0, p)
                covered.add(p)

    # сшивка коллинеарных фрагментов (разрывы скелета -> одна линия)
    paths_px = _merge_collinear(paths_px)

    # пиксели -> мм (центры пикселей), упрощение «лесенки» в чистые отрезки
    paths: Paths = []
    for path in paths_px:
        arr = np.array([[x + 0.5, y + 0.5] for x, y in path], dtype=np.float32)
        cnt = arr.reshape(-1, 1, 2).astype(np.float32)
        approx = cv2.approxPolyDP(cnt, 0.35, False).reshape(-1, 2)
        mm = (approx * mm_per_px).tolist()
        L = 0.0
        for a, b in zip(mm, mm[1:]):
            L += math.hypot(b[0] - a[0], b[1] - a[1])
        if L >= min_len_mm:
            paths.append(mm)
    return paths



# Crawl — порт MagicGyver (tracer-test/main.js)
# ---------------------------------------------------------------------------
def trace_crawl(mask: np.ndarray, mm_per_px: float, ts: TraceSettings) -> Paths:
    cell = max(1, int(ts.crawl_cell_px))
    h, w = mask.shape
    gw, gh = max(1, w // cell), max(1, h // cell)
    if gw == w and gh == h:
        grid = (mask > 0).astype(np.uint8)
    else:
        small = cv2.resize(mask, (gw, gh), interpolation=cv2.INTER_AREA)
        grid = (small > 127).astype(np.uint8)

    total_dark = int(grid.sum())
    if total_dark == 0:
        return []

    max_visits = min(total_dark, 60000)  # страховка от вечной работы
    cr_x = cr_y = 0
    cr_size = 1
    cr_head = 0
    cr_count = 0
    skip = max(1, int(ts.crawl_skip))
    loop = bool(ts.crawl_loop)

    coords: list[tuple[int, int]] = [(0, 0)]

    def check_dir(d: int) -> tuple[int, int] | None:
        s = cr_size
        cx, cy = cr_x, cr_y
        if d == 0:  # верх: y = cy - s, x: cx-s .. cx+s-1
            y = cy - s
            if y < 0:  # кольцо выше края — ячейки не существует
                return None
            x1, x2 = cx - s, cx + s
            a, b = max(x1, 0), min(x2, gw)
            if a >= b:
                return None
            hit = np.flatnonzero(grid[y, a:b])
            if hit.size:
                x = a + int(hit[0])
                grid[y, x] = 0
                return x, y
        elif d == 1:  # право: x = cx + s, y: cy-s .. cy+s-1
            x = cx + s
            if x >= gw:
                return None
            y1, y2 = cy - s, cy + s
            a, b = max(y1, 0), min(y2, gh)
            if a >= b:
                return None
            hit = np.flatnonzero(grid[a:b, x])
            if hit.size:
                y = a + int(hit[0])
                grid[y, x] = 0
                return x, y
        elif d == 2:  # низ: y = cy + s, x: cx+s-1 .. cx-s (в обратную сторону)
            y = cy + s
            if y >= gh:
                return None
            x1, x2 = cx + s - 1, cx - s
            a, b = max(x2, 0), min(x1 + 1, gw)
            if a >= b:
                return None
            seg = grid[y, a:b][::-1]
            hit = np.flatnonzero(seg)
            if hit.size:
                x = b - 1 - int(hit[0])
                grid[y, x] = 0
                return x, y
        else:  # d == 3, лево: x = cx - s, y: cy+s-1 .. cy-s (в обратную сторону)
            x = cx - s
            if x < 0:
                return None
            y1, y2 = cy + s - 1, cy - s
            a, b = max(y2, 0), min(y1 + 1, gh)
            if a >= b:
                return None
            seg = grid[a:b, x][::-1]
            hit = np.flatnonzero(seg)
            if hit.size:
                y = b - 1 - int(hit[0])
                grid[y, x] = 0
                return x, y
        return None

    while cr_size < max(gw, gh) and cr_count < max_visits:
        order = list(range(4)) if not loop else [(cr_head + i) % 4 for i in range(4)]
        found = None
        for d in order:
            found = check_dir(d)
            if found is not None:
                cr_head = (d + 2) % 4  # «инерция»: дальше предпочитаем прямое движение
                break
        if found is not None:
            cr_x, cr_y = found
            cr_count += 1
            coords.append(found)
            # skip: каждые N шагов кольцо НЕ сбрасывается — линия реже,
            # прыжки длиннее (в оригинале аналогичный параметр «Skip»)
            if cr_count % skip != 0:
                cr_size = 1
        else:
            cr_size += 1

    step_mm = cell * mm_per_px
    path: Path = [((x + 0.5) * step_mm, (y + 0.5) * step_mm) for x, y in coords]
    if len(path) >= 2:
        return [path]
    return []


# ---------------------------------------------------------------------------
# Waves — непрерывные волны, амплитуда следует за тёмнотою фото
# ---------------------------------------------------------------------------
def trace_waves(mask: np.ndarray, mm_per_px: float, ts: TraceSettings) -> Paths:
    """Одна непрерывная зигзагообразная линия из рядов синусоид.
    Амплитуда в каждой точке пропорциональна тёмноте в этом месте:
    тёмные области фото рисуются «полноволнысто» (много чернил),
    светлые — почти прямой линией (мало чернил). Так волны реально
    отрисовывают изображение, а не просто покрывают поле."""
    h, w = mask.shape
    rows = max(1, int(ts.waves_rows))
    row_h = h / rows
    amp_base = abs(float(ts.waves_amplitude)) * row_h
    period = max(w / max(1.0, rows / 2.0), 2.0)
    step = max(1, w // 300)

    # тёмнота 0..1, сглаженная по горизонтали — стабильная амплитуда
    dark = (mask > 0).astype(np.float32)
    kx = max(3, (w // 40) | 1)
    dark = cv2.GaussianBlur(dark, (kx, 3), 0)

    path: Path = []
    for r in range(rows):
        y0 = (r + 0.5) * row_h
        yi = min(int(y0), h - 1)
        forward = (r % 2 == 0) != bool(ts.waves_reverse)
        xs = range(0, w + 1, step) if forward else range(w, -1, -step)
        phase = r * 0.9
        row_dark = dark[yi]
        for x in xs:
            d = float(row_dark[min(x, w - 1)])
            amp = amp_base * (0.12 + 1.88 * d)  # светлое→плоско, тёмное→высоко
            y = y0 + amp * math.sin(2.0 * math.pi * x / period + phase)
            y = min(max(y, 0.0), float(h))      # не вылезать за изображение
            path.append((x * mm_per_px, y * mm_per_px))
    if path:
        return [path]
    return []


# ---------------------------------------------------------------------------
# Сглаживание пути (метод Чакина) — для почерка/ручного обвода
# ---------------------------------------------------------------------------
_MAX_SMOOTH_PTS = 120_000  # потолок точек на один путь при сглаживании


def _decimate(pts: Path, cap: int) -> Path:
    """Равномерное прореживание до cap точек (кривая уже плавная)."""
    if len(pts) <= cap:
        return pts
    stride = len(pts) // cap + 1
    return pts[::stride]


def chaikin(pts: Path, iters: int, closed: bool = False) -> Path:
    """Сглаживание (срез углов 3/4-1/4). Каждый проход удваивает число точек;
    при итерациях > 8 включается прореживание, чтобы путь не «взрывался»
    — плавность от этого почти не страдает. До 24 итераций можно гнать
    «на глаз», получая очень мягкую кривую."""
    pts = list(pts)
    for _ in range(max(0, int(iters))):
        if len(pts) < 3:
            break
        if closed:
            src = pts + [pts[0]]
        else:
            src = pts
        out: Path = []
        if not closed:
            out.append(pts[0])
        for i in range(len(src) - 1):
            x0, y0 = src[i]
            x1, y1 = src[i + 1]
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        if not closed:
            out.append(pts[-1])
        pts = _decimate(out, _MAX_SMOOTH_PTS)
    return pts


def _close_paths(paths: Paths) -> Paths:
    """Замкнуть контуры: добавить первый пункт в конец, если его нет.
    Без этого у каждой буквы «пропадал» последний отрезок и контур
    выглядел незакрытым."""
    closed_paths: Paths = []
    for p in paths:
        if len(p) >= 2:
            x0, y0 = p[0]
            xn, yn = p[-1]
            if (x0 - xn) ** 2 + (y0 - yn) ** 2 > 1e-12:
                p = list(p) + [(x0, y0)]
        closed_paths.append(p)
    return closed_paths


# ---------------------------------------------------------------------------
# Диспетчер
# ---------------------------------------------------------------------------
def trace(mask: np.ndarray, mm_per_px: float, ts: TraceSettings,
          gray: np.ndarray | None = None, proc=None) -> Paths:
    """mask — бинарная маска (255 = рисуем).

    gray/proc — опционально (для контурных режимов): обработанное серое
    изображение и параметры обработки. Если ts.precise_contour, контур
    ищется субпиксельно по серому (marching squares); при любой ошибке —
    fallback на findContours по маске.
    """
    if ts.mode in ("contour", "outline", "inner") and gray is not None \
            and proc is not None and bool(ts.precise_contour):
        try:
            paths = _trace_contours_precise(gray, mm_per_px, ts, proc)
            if not paths and (mask > 0).any():
                raise RuntimeError("субпиксельный контур пуст, а маска не пуста")
            if paths:
                return _finish_contour_paths(paths, ts)
        except Exception:  # noqa: BLE001 — точность не должна ломать трасс
            pass

    if ts.mode == "raster":
        paths = trace_raster(mask, mm_per_px, ts)
    elif ts.mode == "contour":
        paths = trace_contour(mask, mm_per_px, ts)
    elif ts.mode == "outline":
        paths = trace_outline(mask, mm_per_px, ts)
    elif ts.mode == "inner":
        paths = trace_inner(mask, mm_per_px, ts)
    elif ts.mode == "skeleton":
        skel = thinning(mask)
        paths = skeleton_to_paths(skel, mm_per_px, ts.skeleton_min_len_mm)
    elif ts.mode == "crawl":
        paths = trace_crawl(mask, mm_per_px, ts)
    elif ts.mode == "waves":
        paths = trace_waves(mask, mm_per_px, ts)
    else:
        raise ValueError(f"Неизвестный режим трассировки: {ts.mode}")

    if ts.mode in ("contour", "outline", "inner"):
        return _finish_contour_paths(paths, ts)

    # Сглаживание Чакина для открытых ломаных (растр/ползание/волны)
    iters = int(ts.smooth_iters)
    if iters > 0:
        paths = [chaikin(p, iters, closed=False) for p in paths]
    return paths


def _finish_contour_paths(paths: Paths, ts: TraceSettings) -> Paths:
    """Финализация контурных путей: сглаживание Чакина + замыкание
    полигона (без «хвоста» к началу последняя грань не рисуется)."""
    iters = int(ts.smooth_iters)
    if iters > 0:
        paths = [chaikin(p, iters, closed=True) for p in paths]
    return _close_paths(paths)
