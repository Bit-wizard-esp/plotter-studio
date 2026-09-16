"""Главное окно Plotter Studio."""
from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, fields

import numpy as np
from PySide6.QtCore import QByteArray, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QTabBar, QVBoxLayout, QWidget, QPushButton,
)

from ..core import (
    GCodeGenerator, GCodeStats, ImageSettings, ProcessingSettings, PrinterSettings,
    TraceSettings, compute_image_mm, fit_to_bed, load_bgr, load_dxf, process,
    text_to_bgr, trace,
)
from . import theme as T
from .panels import SettingsPanel
from .preview_canvas import PreviewCanvas

PREVIEW_PX = 560  # разрешение для live-превью (быстро; не слишком мало —
# иначе тонкие линии раскрасок рвутся на штрихи прямо в превью)
IMAGE_FILTER = "Изображения (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;Все файлы (*)"
GCODE_FILTER = "G-код (*.gcode *.gco *.g *.txt);;Все файлы (*)"
DXF_FILTER = "DXF (*.dxf);;Все файлы (*)"


class GenerateWorker(QThread):
    """Полная генерация в фоне: обработка + трассировка + G-код."""

    ok = Signal(dict)
    fail = Signal(str)

    def __init__(self, bgr: np.ndarray, img: ImageSettings, proc: ProcessingSettings,
                 ts: TraceSettings, pr: PrinterSettings, aspect: float | None = None):
        super().__init__()
        self.bgr = bgr
        self.img = copy.deepcopy(img)
        self.proc = copy.deepcopy(proc)
        self.ts = copy.deepcopy(ts)
        self.pr = copy.deepcopy(pr)
        self.aspect = aspect

    def run(self) -> None:
        try:
            gray, mask = process(self.bgr, self.img, self.proc)
            h, w = mask.shape
            iw, ih = fit_to_bed(*compute_image_mm(self.img, self.aspect), self.pr)
            mpp = iw / w
            paths = trace(mask, mpp, self.ts, gray=gray, proc=self.proc)
            gen = GCodeGenerator(self.pr, iw, ih)
            gcode, stats = gen.generate(paths)
            self.ok.emit({
                "gcode": gcode, "stats": stats, "paths": paths, "gen": gen,
                "iw": iw, "ih": ih, "pr": self.pr, "gray": gray, "mask": mask,
            })
        except Exception as e:  # noqa: BLE001
            self.fail.emit(f"{type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plotter Studio — фото в G-код для 3D-принтера")
        self.resize(1420, 880)
        self.setMinimumSize(1120, 680)

        self._bgr: np.ndarray | None = None
        self._dxf: dict | None = None  # {"paths", "w", "h", "name", "path"}
        self._gcode: str = ""
        self._worker: GenerateWorker | None = None
        self._theme = "dark"

        # ---- вкладки превью ----
        self.tabs = QTabBar()
        self.tabs.addTab("Фото")
        self.tabs.addTab("Линии")
        self.tabs.addTab("Путь (G-код)")
        self.tabs.setCurrentIndex(0)
        self.tabs.currentChanged.connect(self._on_tab)

        self.canvas = PreviewCanvas()
        self.canvas.image_moved.connect(self._on_image_moved)

        # ---- панель настроек ----
        self.panel = SettingsPanel()
        self.panel.changed.connect(self._on_settings_changed)

        # ---- шапка ----
        self.header = self._build_header()

        # ---- сборка ----
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        split = QHBoxLayout()
        split.setContentsMargins(8, 4, 8, 8)
        split.setSpacing(8)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(0, 0, 0, 0)
        tabs_row.addWidget(self.tabs, 1)
        self.btn_move = QPushButton("✥ Двигать рисунок")
        self.btn_move.setProperty("flat", "true")
        self.btn_move.setCheckable(True)
        self.btn_move.setToolTip(
            "Вкладка «Путь»: перетаскивай рисунок мышью по столу — смещения X/Y "
            "обновятся автоматически. Так удобно отцентрировать или сдвинуть.")
        self.btn_move.toggled.connect(self._on_move_toggled)
        tabs_row.addWidget(self.btn_move)
        left.addLayout(tabs_row)
        left.addWidget(self.canvas, 1)
        split.addLayout(left, 1)
        split.addWidget(self.panel, 0)
        cv.addLayout(split)

        root = QWidget()
        rv = QVBoxLayout(root)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(self.header)
        rv.addWidget(center, 1)
        self.setCentralWidget(root)

        # ---- статусбар ----
        self.lbl_stats = QLabel("")
        self.statusBar().addWidget(self.lbl_stats, 1)
        self.lbl_hint = QLabel("Откройте фото, чтобы начать")
        self.lbl_hint.setProperty("hint", "true")
        self.statusBar().addPermanentWidget(self.lbl_hint)

        # ---- меню/действия ----
        self._make_actions()

        # ---- текст (письмо) ----
        self.panel.btn_text.clicked.connect(self.on_text_make)
        self.panel.btn_dxf.clicked.connect(self.open_dxf)

        # ---- дебаунс превью ----
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._run_preview)

        # ---- автосохранение настроек (дебаунс) ----
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000)
        self._save_timer.timeout.connect(self._save_state)

        self.btn_generate.setEnabled(False)
        self.btn_save.setEnabled(False)
        T.apply(QApplication.instance(), self._theme)
        self.canvas.set_theme(self._theme)

        # восстановление сохранённых настроек
        self._load_state()
        if self._bgr is not None:
            self._run_preview()

    # ------------------------------------------------------------------
    def _build_header(self) -> QFrame:
        h = QFrame()
        h.setProperty("header", "true")
        h.setFixedHeight(56)
        lay = QHBoxLayout(h)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        app = QLabel("Plotter Studio")
        app.setProperty("app", "true")
        sub = QLabel("фото → G-код · 3D-принтер как машина для рисования")
        sub.setProperty("subtitle", "true")
        titles.addWidget(app)
        titles.addWidget(sub)
        lay.addLayout(titles)
        lay.addStretch(1)

        self.btn_open = QPushButton("Открыть фото")
        self.btn_open.clicked.connect(self.open_photo)
        self.btn_fit = QPushButton("Вписать")
        self.btn_fit.setProperty("flat", "true")
        self.btn_fit.clicked.connect(self.canvas.fit)
        self.btn_theme = QPushButton("Светлая тема")
        self.btn_theme.setProperty("flat", "true")
        self.btn_theme.clicked.connect(self._toggle_theme)
        self.btn_generate = QPushButton("Сгенерировать G-код")
        self.btn_generate.setProperty("accent", "true")
        self.btn_generate.clicked.connect(self.generate)
        self.btn_save = QPushButton("Сохранить…")
        self.btn_save.clicked.connect(self.save_gcode)
        for b in (self.btn_open, self.btn_fit, self.btn_theme, self.btn_generate, self.btn_save):
            lay.addWidget(b)
        return h

    def _make_actions(self) -> None:
        a_open = QAction("Открыть фото…", self)
        a_open.setShortcut(QKeySequence.Open)
        a_open.triggered.connect(self.open_photo)
        a_dxf = QAction("Открыть DXF…", self)
        a_dxf.setShortcut(QKeySequence("Ctrl+Shift+D"))
        a_dxf.triggered.connect(self.open_dxf)
        a_gen = QAction("Сгенерировать G-код", self)
        a_gen.setShortcut(QKeySequence("Ctrl+G"))
        a_gen.triggered.connect(self.generate)
        a_save = QAction("Сохранить G-код…", self)
        a_save.setShortcut(QKeySequence.Save)
        a_save.triggered.connect(self.save_gcode)
        self.menu = self.menuBar()
        m = self.menu.addMenu("&Файл")
        m.addAction(a_open)
        m.addAction(a_dxf)
        m.addAction(a_gen)
        m.addAction(a_save)

    # ------------------------------------------------------------------
    def _aspect(self) -> float | None:
        """Соотношение h/w текущего «источника» (фото, текст или DXF)."""
        if self._dxf is not None:
            w = self._dxf["w"]
            return (self._dxf["h"] / w) if w > 0 else 1.0
        if self._bgr is None:
            return None
        return self._bgr.shape[0] / self._bgr.shape[1]

    def _clear_dxf(self) -> None:
        if self._dxf is not None:
            self._dxf = None
            self.panel.set_dxf_mode(False)

    def open_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Открыть фото", "", IMAGE_FILTER)
        if not path:
            return
        try:
            self._bgr = load_bgr(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть фото:\n{e}")
            return
        self._clear_dxf()
        self.panel.set_photo_path(path)
        name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        self.lbl_hint.setText(f"Фото: {name}")
        self.btn_generate.setEnabled(True)
        self._update_aspect()
        self._run_preview()
        self._save_timer.start()
        self.statusBar().showMessage(f"Загружено: {name} {self._bgr.shape[1]}×{self._bgr.shape[0]}", 5000)

    def open_dxf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Открыть DXF", "", DXF_FILTER)
        if path:
            self._load_dxf_file(path)

    def _load_dxf_file(self, path: str) -> bool:
        try:
            paths, w, h = load_dxf(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть DXF:\n{e}")
            return False
        if not paths:
            QMessageBox.critical(
                self, "Ошибка",
                "В DXF нет поддерживаемой геометрии (LINE/LWPOLYLINE/POLYLINE/"
                "CIRCLE/ARC/SPLINE/ELLIPSE в modelspace).")
            return False
        self._bgr = None
        self._dxf = {"paths": paths, "w": w, "h": h,
                     "name": os.path.basename(path), "path": path}
        self.panel.set_photo_path("")
        self.panel.set_dxf_mode(True, self._dxf["name"])
        self.lbl_hint.setText(f"DXF: {self._dxf['name']} · {w:.0f}×{h:.0f} мм")
        self.btn_generate.setEnabled(True)
        # ширина по умолчанию = ширина чертежа (в пределах спинбокса)
        self.panel.spin_size_w.blockSignals(True)
        self.panel.spin_size_w.setValue(round(min(max(w, 1.0), 500.0), 1))
        self.panel.spin_size_w.blockSignals(False)
        self._update_aspect()
        self._run_preview()
        self._save_timer.start()
        self.statusBar().showMessage(
            f"DXF загружен: {len(paths)} объектов, {w:.0f}×{h:.0f} мм "
            f"(«Размер, ширина» масштабирует чертёж)", 8000)
        return True

    def _dxf_scaled(self) -> tuple[list, float, float]:
        """Пути DXF, отмасштабированные под текущие «Размер»/стол. (paths, iw, ih)."""
        img, _proc, _ts, pr = self.panel.collect()
        iw, ih = fit_to_bed(*compute_image_mm(img, self._aspect()), pr)
        scale = iw / self._dxf["w"] if self._dxf["w"] > 0 else 1.0
        paths = [[(x * scale, y * scale) for x, y in p] for p in self._dxf["paths"]]
        return paths, iw, ih

    def _update_aspect(self) -> None:
        img, *_ = self.panel.collect()
        self.panel.set_keep_aspect_lock(img.keep_aspect)
        if img.keep_aspect:
            _, ih = compute_image_mm(img, self._aspect())
            self.panel.spin_size_h.blockSignals(True)
            self.panel.spin_size_h.setValue(round(ih, 1))
            self.panel.spin_size_h.blockSignals(False)

    def on_text_make(self) -> None:
        """Сделать «фото» из текста (режим письма)."""
        text = self.panel.pte_text.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Plotter Studio", "Сначала введите текст.")
            return
        try:
            self._bgr = text_to_bgr(text, int(self.panel.spin_text_size.value()))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать текст:\n{e}")
            return
        self._clear_dxf()
        self.panel.set_photo_path("")
        short = text.replace("\n", " ⏎ ")
        if len(short) > 32:
            short = short[:32] + "…"
        self.lbl_hint.setText(f"Текст: {short}")
        self.btn_generate.setEnabled(True)
        # для письма лучше всего работают контуры
        if self.panel.combo_mode.currentIndex() != 1:
            self.panel.combo_mode.setCurrentIndex(1)
        self._update_aspect()
        self._run_preview()
        self.statusBar().showMessage(
            f"Текст создан: {self._bgr.shape[1]}×{self._bgr.shape[0]} px (режим «Контуры»)", 6000)

    # ------------------------------------------------------------------
    def _on_settings_changed(self) -> None:
        cur_aspect = self.panel.chk_aspect.isChecked()
        if cur_aspect != self._last_aspect:
            self._last_aspect = cur_aspect
            self._update_aspect()
        if self._bgr is not None:
            self._timer.start()
        self._save_timer.start()

    _last_aspect: bool = True

    # ------------------------------------------------------------------
    def _on_tab(self, idx: int) -> None:
        from .preview_canvas import MODES
        self.canvas.set_mode(MODES[idx])

    # ---- перемещение рисунка мышью ----
    def _on_move_toggled(self, on: bool) -> None:
        if on and self.tabs.currentIndex() != 2:
            self.tabs.setCurrentIndex(2)
        self.canvas.set_move_enabled(on)

    def _on_image_moved(self, dx_mm: float, dy_mm: float) -> None:
        # сцена: y вниз; стол: y вверх
        self.panel.spin_off_x.blockSignals(True)
        self.panel.spin_off_y.blockSignals(True)
        self.panel.spin_off_x.setValue(self.panel.spin_off_x.value() + dx_mm)
        self.panel.spin_off_y.setValue(self.panel.spin_off_y.value() - dy_mm)
        self.panel.spin_off_x.blockSignals(False)
        self.panel.spin_off_y.blockSignals(False)
        # быстрая перестройка без повторной трассировки
        img, _proc, _ts, pr = self.panel.collect()
        iw, ih = fit_to_bed(*compute_image_mm(img, self._aspect()), pr)
        self.canvas.update_gen(GCodeGenerator(pr, iw, ih))
        # после остановки — полный refresh (дебаунс)
        self._timer.start()

    def _preview_dxf(self) -> None:
        try:
            _img, _proc, _ts, pr = self.panel.collect()
            paths, iw, ih = self._dxf_scaled()
            gen = GCodeGenerator(pr, iw, ih)
            self.canvas.set_data({
                "gray": None, "mask": None, "iw": iw, "ih": ih,
                "paths": paths, "gen": gen,
                "bed_w": pr.bed_w_mm, "bed_h": pr.bed_h_mm,
            })
            segs = sum(len(p) - 1 for p in paths if len(p) > 1)
            self.lbl_stats.setText(
                f"DXF {self._dxf['name']} · объектов: {len(paths)} · сегментов: "
                f"{segs} · рисунок {iw:.0f}×{ih:.0f} мм")
        except Exception as e:  # noqa: BLE001
            self.lbl_stats.setText(f"Ошибка превью DXF: {e}")

    def _run_preview(self) -> None:
        if self._dxf is not None:
            self._preview_dxf()
            return
        if self._bgr is None:
            self.canvas.set_data(None)
            return
        try:
            img, proc, ts, pr = self.panel.collect()
            iw, ih = fit_to_bed(*compute_image_mm(img, self._aspect()), pr)
            prev_img = copy.deepcopy(img)
            prev_img.resolution_px = PREVIEW_PX
            gray, mask = process(self._bgr, prev_img, proc)
            h, w = mask.shape
            mpp = iw / w
            paths = trace(mask, mpp, ts, gray=gray, proc=proc)
            gen = GCodeGenerator(pr, iw, ih)
            self.canvas.set_data({
                "gray": gray, "mask": mask, "iw": iw, "ih": ih,
                "paths": paths, "gen": gen,
                "bed_w": pr.bed_w_mm, "bed_h": pr.bed_h_mm,
            })
            segs = sum(len(p) - 1 for p in paths if len(p) > 1)
            extra = ""
            if ts.mode in ("contour", "outline", "inner", "skeleton"):
                pppm = w / iw if iw > 0 else 0.0
                warn = 3.0 if ts.mode != "skeleton" else 4.0
                if pppm < warn:
                    extra = (f" · ⚠ разрешение низкое: {pppm:.1f} px/мм — "
                             "уменьшите размер или увеличьте px в «Разрешение»")
            self.lbl_stats.setText(
                f"{w}×{h} px · путей: {len(paths)} · сегментов: {segs} · "
                f"рисунок {iw:.0f}×{ih:.0f} мм{extra}")
        except Exception as e:  # noqa: BLE001
            self.lbl_stats.setText(f"Ошибка превью: {e}")

    # ------------------------------------------------------------------
    def _generate_dxf(self) -> None:
        """DXF -> G-код напрямую (без обработки/трассировки)."""
        try:
            _img, _proc, _ts, pr = self.panel.collect()
            paths, iw, ih = self._dxf_scaled()
            if iw > pr.bed_w_mm + 0.01 or ih > pr.bed_h_mm + 0.01:
                QMessageBox.warning(
                    self, "Внимание",
                    f"Чертёж {iw:.0f}×{ih:.0f} мм больше стола {pr.bed_w_mm:.0f}×"
                    f"{pr.bed_h_mm:.0f} мм. Часть окажется за краем стола.")
            gen = GCodeGenerator(pr, iw, ih)
            gcode, stats = gen.generate(paths)
            self._gcode = gcode
            self.btn_save.setEnabled(True)
            self.canvas.set_data({
                "gray": None, "mask": None, "iw": iw, "ih": ih,
                "paths": paths, "gen": gen,
                "bed_w": pr.bed_w_mm, "bed_h": pr.bed_h_mm,
            })
            self.tabs.setCurrentIndex(2)
            self.statusBar().showMessage(
                f"Готово (DXF): {stats.lines} строк · {stats.segments} сегментов · "
                f"рисунок {stats.draw_m:.2f} м · переходы {stats.travel_mm/1000:.2f} м · "
                f"~{stats.est_minutes:.0f} мин", 15000)
            self.lbl_stats.setText(
                f"G-код: {len(gcode)/1024:.0f} КБ · {stats.segments} сегментов · "
                f"~{stats.est_minutes:.0f} мин")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка генерации", f"{type(e).__name__}: {e}")

    def generate(self) -> None:
        if self._dxf is not None:
            self._generate_dxf()
            return
        if self._bgr is None:
            return
        img, proc, ts, pr = self.panel.collect()
        iw, ih = fit_to_bed(*compute_image_mm(img, self._aspect()), pr)
        if iw > pr.bed_w_mm + 0.01 or ih > pr.bed_h_mm + 0.01:
            QMessageBox.warning(
                self, "Внимание",
                f"Рисунок {iw:.0f}×{ih:.0f} мм больше стола {pr.bed_w_mm:.0f}×{pr.bed_h_mm:.0f} мм.\n"
                "Часть рисунка окажется за краем стола.")
        self._worker = GenerateWorker(self._bgr, img, proc, ts, pr, self._aspect())
        self._worker.ok.connect(self._on_generated)
        self._worker.fail.connect(self._on_failed)
        self.btn_generate.setEnabled(False)
        self.statusBar().showMessage("Генерация G-кода…")
        self._worker.start()

    def _on_generated(self, d: dict) -> None:
        self._gcode = d["gcode"]
        self.btn_save.setEnabled(True)
        self.btn_generate.setEnabled(True)
        st: GCodeStats = d["stats"]
        pr: PrinterSettings = d["pr"]
        self.canvas.set_data({
            "gray": d["gray"], "mask": d["mask"], "iw": d["iw"], "ih": d["ih"],
            "paths": d["paths"], "gen": d["gen"],
            "bed_w": pr.bed_w_mm, "bed_h": pr.bed_h_mm,
        })
        self.tabs.setCurrentIndex(2)
        self.statusBar().showMessage(
            f"Готово: {st.lines} строк · {st.segments} сегментов · "
            f"рисунок {st.draw_m:.2f} м · переходы {st.travel_mm/1000:.2f} м · "
            f"подъёмов {st.pen_lifts} · ~{st.est_minutes:.0f} мин", 15000)
        self.lbl_stats.setText(
            f"G-код: {len(self._gcode)/1024:.0f} КБ · {st.segments} сегментов · "
            f"~{st.est_minutes:.0f} мин печати")

    def _on_failed(self, msg: str) -> None:
        self.btn_generate.setEnabled(True)
        self.statusBar().showMessage("Ошибка генерации", 8000)
        QMessageBox.critical(self, "Ошибка генерации", msg)

    # ------------------------------------------------------------------
    def save_gcode(self) -> None:
        if not self._gcode:
            QMessageBox.information(self, "Plotter Studio", "Сначала сгенерируйте G-код.")
            return
        pr: PrinterSettings = self.panel.collect()[3]
        default = pr.filename or "drawing.gcode"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить G-код", default, GCODE_FILTER)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._gcode)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
            return
        self.statusBar().showMessage(f"Сохранено: {path} ({len(self._gcode)/1024:.0f} КБ)", 10000)

    # ------------------------------------------------------------------
    def _set_theme(self, name: str) -> None:
        self._theme = name
        T.apply(QApplication.instance(), name)
        self.canvas.set_theme(name)
        self.btn_theme.setText("Светлая тема" if name == "dark" else "Тёмная тема")

    def _toggle_theme(self) -> None:
        self._set_theme("light" if self._theme == "dark" else "dark")

    # ------------------------------------------------------------------
    # Сохранение/восстановление настроек (QSettings: реестр в Windows)
    # ------------------------------------------------------------------
    def _save_state(self) -> None:
        try:
            img, proc, ts, pr = self.panel.collect()
            state = {
                "img": asdict(img), "proc": asdict(proc),
                "ts": asdict(ts), "pr": asdict(pr),
                "theme": self._theme,
                "dxf": self._dxf["path"] if self._dxf else None,
                "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            }
            QSettings().setValue("plotter/state", json.dumps(state, ensure_ascii=False))
        except Exception:  # noqa: BLE001 — сохранение не должно ронять приложение
            pass

    @staticmethod
    def _dc(cls, d: dict):
        """Собрать dataclass, отбрасывая неизвестные/пропущенные ключи."""
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in valid})

    def _load_state(self) -> None:
        try:
            raw = QSettings().value("plotter/state")
            if not raw:
                return
            state = json.loads(raw)
            img = self._dc(ImageSettings, state.get("img"))
            proc = self._dc(ProcessingSettings, state.get("proc"))
            ts = self._dc(TraceSettings, state.get("ts"))
            pr = self._dc(PrinterSettings, state.get("pr"))
            self.panel.apply_state(img, proc, ts, pr)
            if state.get("theme") in ("dark", "light"):
                self._set_theme(state["theme"])
            geo = state.get("geometry")
            if geo:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
            # автозагрузка последнего DXF (приоритет над фото)
            dxf_path = state.get("dxf")
            if dxf_path and os.path.exists(dxf_path):
                if self._load_dxf_file(dxf_path):
                    return
            # автозагрузка последнего фото
            if img.path and os.path.exists(img.path):
                self._bgr = load_bgr(img.path)
                self.panel.set_photo_path(img.path)
                self.lbl_hint.setText(f"Фото: {os.path.basename(img.path)}")
                self.btn_generate.setEnabled(True)
                self._update_aspect()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    def closeEvent(self, ev) -> None:
        self._save_state()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)
        super().closeEvent(ev)
