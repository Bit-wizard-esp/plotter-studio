"""Канвас превью: три вкладки — фото (обработанное), линии (маска+трасс), путь (G-код на столе).

Сцена измеряется в мм. Зум колесом, панорама левой кнопкой.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QBrush, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView

from ..core.gcode import GCodeGenerator
from ..core.tracing import Paths
from . import theme as T

MODES = ("image", "lines", "path")


class PreviewCanvas(QGraphicsView):
    """image_moved(dx_mm, dy_mm) — тап по рисунку в режиме перемещения
    (dx/dy в координатах СЦЕНЫ: y вниз)."""

    image_moved = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(T.colors("dark")["canvas"]))
        self.setMouseTracking(True)
        self._fit = True

        self.mode: str = "image"
        self._data: Optional[dict] = None
        self._theme = "dark"
        self._placeholder: Optional[QGraphicsSimpleTextItem] = None
        self._move_enabled = False
        self._dragging = False
        self._last_scene = None

    # ------------------------------------------------------------------
    def set_theme(self, name: str) -> None:
        self._theme = name
        self.setBackgroundBrush(QColor(T.colors(name)["canvas"]))
        if self._data:
            self._rebuild()

    def set_data(self, data: Optional[dict]) -> None:
        """data: gray, mask, iw, ih, paths, gen | None (пусто)."""
        self._data = data
        self._rebuild()

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            return
        self.mode = mode
        self._fit = True
        if self._move_enabled:
            self.viewport().setCursor(
                Qt.CrossCursor if mode == "path" else Qt.ArrowCursor)
        self._rebuild()

    def fit(self) -> None:
        self._fit = True
        self._rebuild()

    def set_move_enabled(self, enabled: bool) -> None:
        """Режим перетаскивания рисунка (работает во вкладке «Путь»)."""
        self._move_enabled = bool(enabled) and self.mode == "path"
        self._dragging = False
        self.viewport().setCursor(
            Qt.CrossCursor if self._move_enabled else Qt.ArrowCursor)

    def update_gen(self, gen) -> None:
        """Быстрая перестройка при смене смещения — без повторной трассировки."""
        if self._data is None:
            return
        self._data["gen"] = gen
        self._fit = False
        self._rebuild()

    # ------------------------------------------------------------------
    def _clear(self) -> None:
        self._scene.clear()

    def _rebuild(self) -> None:
        self._clear()
        self._placeholder = None
        d = self._data
        if d is None:
            self._show_placeholder()
            self._scene.setSceneRect(-100, -100, 200, 200)
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            return
        if self.mode == "image":
            self._draw_image(d)
        elif self.mode == "lines":
            self._draw_lines(d)
        else:
            self._draw_path(d)
        if self._fit:
            r = self._scene.sceneRect()
            if r.width() > 0 and r.height() > 0:
                self.fitInView(r, Qt.KeepAspectRatio)

    def _show_placeholder(self) -> None:
        c = T.colors(self._theme)
        self._placeholder = self._scene.addSimpleText("Откройте фото — python main.py и кнопка «Открыть фото»")
        f = self._placeholder.font()
        f.setPointSize(13)
        self._placeholder.setFont(f)
        self._placeholder.setBrush(QBrush(QColor(c["text_hint"])))

    # ------------------------------------------------------------------
    @staticmethod
    def _pixmap_from_gray(arr: np.ndarray) -> QPixmap:
        h, w = arr.shape
        qimg = QImage(arr.data, w, h, w, QImage.Format_Grayscale8).copy()
        return QPixmap.fromImage(qimg.convertToFormat(QImage.Format_ARGB32))

    def _draw_image(self, d: dict) -> None:
        c = T.colors(self._theme)
        if d.get("gray") is not None:  # DXF: фото нет, только рамка
            pm = self._pixmap_from_gray(d["gray"])
            item = QGraphicsPixmapItem(pm)
            item.setTransformationMode(Qt.SmoothTransformation)
            s = d["iw"] / d["gray"].shape[1]
            item.setTransform(item.transform().scale(s, s))
            item.setPos(0, 0)
            self._scene.addItem(item)
        rect = QRectF(0, 0, d["iw"], d["ih"])
        self._scene.addRect(rect, QPen(QColor(c["canvas_image_edge"]), 0.15), Qt.NoBrush)
        self._scene.setSceneRect(-d["iw"] * 0.03, -d["ih"] * 0.03,
                                 d["iw"] * 1.06, d["ih"] * 1.06)

    def _draw_lines(self, d: dict) -> None:
        c = T.colors(self._theme)
        if d.get("mask") is not None:
            # фон: белая «бумага», тёмное — чернила
            pm = self._pixmap_from_gray(255 - d["mask"])
            item = QGraphicsPixmapItem(pm)
            item.setTransformationMode(Qt.SmoothTransformation)
            s = d["iw"] / d["mask"].shape[1]
            item.setTransform(item.transform().scale(s, s))
            item.setPos(0, 0)
            self._scene.addItem(item)

        path = QPainterPath()
        for seg in d["paths"]:
            if not seg:
                continue
            path.moveTo(QPointF(*seg[0]))
            for x, y in seg[1:]:
                path.lineTo(QPointF(x, y))
        if not path.isEmpty():
            self._scene.addPath(path, QPen(QColor(c["canvas_lines"]), 0.08))

        rect = QRectF(0, 0, d["iw"], d["ih"])
        self._scene.addRect(rect, QPen(QColor(c["canvas_image_edge"]), 0.15), Qt.NoBrush)
        self._scene.setSceneRect(-d["iw"] * 0.03, -d["ih"] * 0.03,
                                 d["iw"] * 1.06, d["ih"] * 1.06)

    def _draw_path(self, d: dict) -> None:
        c = T.colors(self._theme)
        gen: GCodeGenerator = d["gen"]
        bed_w, bed_h = d["bed_w"], d["bed_h"]

        # стол
        bed = self._scene.addRect(0, 0, bed_w, bed_h,
                                  QPen(QColor(c["canvas_bed_edge"]), 0.3),
                                  QBrush(QColor(c["canvas_bed"])))
        bed.setZValue(-10)
        # сетка 50 мм
        grid = QPainterPath()
        for x in range(50, int(bed_w), 50):
            grid.moveTo(x, 0); grid.lineTo(x, bed_h)
        for y in range(50, int(bed_h), 50):
            grid.moveTo(0, y); grid.lineTo(bed_w, y)
        self._scene.addPath(grid, QPen(QColor(c["canvas_grid"]), 0.1))

        # координаты стола (Y вверх) -> координаты сцены (Y вниз)
        def to_scene(x: float, y: float) -> QPointF:
            return QPointF(x, bed_h - y)

        # рамка изображения
        img_rect = QRectF(gen.x0, bed_h - gen.y0 - gen.ih, gen.iw, gen.ih)
        self._scene.addRect(img_rect, QPen(QColor(c["canvas_image_edge"]), 0.2, Qt.DashLine), Qt.NoBrush)

        # путь G-кода
        path = QPainterPath()
        for seg in d["paths"]:
            if not seg:
                continue
            scene_pts = [to_scene(*gen.to_bed(x, y)) for x, y in seg]
            path.moveTo(scene_pts[0])
            for p in scene_pts[1:]:
                path.lineTo(p)
        if not path.isEmpty():
            self._scene.addPath(path, QPen(QColor(c["canvas_path"]), 0.07))
            # старт — первая точка первого пути
            fp = to_scene(*gen.to_bed(*d["paths"][0][0]))
            dot = self._scene.addEllipse(fp.x() - 1.2, fp.y() - 1.2, 2.4, 2.4,
                                         QPen(QColor(c["canvas_start"]), 0.3),
                                         QBrush(QColor(c["canvas_start"])))
            dot.setZValue(10)
        self._scene.setSceneRect(-bed_w * 0.04, -bed_h * 0.04,
                                 bed_w * 1.08, bed_h * 1.08)

    # ------------------------------------------------------------------
    def wheelEvent(self, ev) -> None:  # зум
        if self._data is None:
            return
        factor = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        cur = self.transform().m11()
        new = min(max(cur * factor, 0.02), 200.0)
        if new == cur:
            return
        self.scale(new / cur, new / cur)
        self._fit = False

    def _move_active(self) -> bool:
        return self._move_enabled and self.mode == "path" and self._data is not None

    def mousePressEvent(self, ev) -> None:
        if self._move_active() and ev.button() == Qt.LeftButton:
            self._dragging = True
            self._last_scene = self.mapToScene(ev.position().toPoint())
            self.viewport().setCursor(Qt.ClosedHandCursor)
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if self._dragging and self._last_scene is not None:
            cur = self.mapToScene(ev.position().toPoint())
            dx = cur.x() - self._last_scene.x()
            dy = cur.y() - self._last_scene.y()
            self._last_scene = cur
            if dx != 0 or dy != 0:
                self.image_moved.emit(float(dx), float(dy))
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        if self._dragging:
            self._dragging = False
            self._last_scene = None
            if self._move_enabled:
                self.viewport().setCursor(Qt.CrossCursor)
            ev.accept()
            return
        super().mouseReleaseEvent(ev)
