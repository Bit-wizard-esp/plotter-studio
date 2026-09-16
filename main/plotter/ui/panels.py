"""Правая панель настроек: карточки с параметрами (стиль Windows 11)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout,
    QWidget,
)

from ..core import (
    DEFAULT_END_GCODE, DEFAULT_START_GCODE,
    ImageSettings, ProcessingSettings, PrinterSettings, TraceSettings, MODE_LABELS,
)
from . import theme as T
from .widgets import SliderRow


def make_card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setProperty("card", "true")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(14, 12, 14, 14)
    lay.setSpacing(8)
    t = QLabel(title)
    t.setProperty("title", "true")
    lay.addWidget(t)
    return card, lay


def row(label: str, widget: QWidget, hint: str = "") -> QHBoxLayout:
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(10)
    lab = QLabel(label)
    lab.setMinimumWidth(150)
    if hint:
        lab.setToolTip(hint)
    h.addWidget(lab)
    h.addWidget(widget, 1)
    return h


class SettingsPanel(QScrollArea):
    """Все карточки настроек. Собирает dataclass'ы через collect()."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumWidth(340)
        self.setMaximumWidth(460)

        outer = QWidget()
        v = QVBoxLayout(outer)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        # ================= ФОТО =================
        self.card_photo, lay = make_card("Фото")
        self.btn_open = QPushButton("Открыть фото…")
        self.btn_open.clicked.connect(self._emit)
        lay.addWidget(self.btn_open)
        self.btn_dxf = QPushButton("Открыть DXF…")
        self.btn_dxf.setToolTip(
            "Загрузить векторный чертёж DXF (LINE, LWPOLYLINE, CIRCLE, ARC, "
            "SPLINE, ELLIPSE). Обработка/трассировка не нужны — пути идут в G-код "
            "как есть. Единицы: $INSUNITS; без полей — считаем мм.")
        lay.addWidget(self.btn_dxf)
        self.lbl_dxf = QLabel("")
        self.lbl_dxf.setProperty("hint", "true")
        self.lbl_dxf.setWordWrap(True)
        lay.addWidget(self.lbl_dxf)
        hint_h = "Если включено «Автосоотношение», высота считается из ширины по пропорциям фото"
        self.spin_size_w = self._ds(10, 500, 180, 1, " мм")
        self.spin_size_w.valueChanged.connect(self._emit)
        self.spin_size_h = self._ds(10, 500, 140, 1, " мм")
        self.spin_size_h.valueChanged.connect(self._emit)
        self.chk_aspect = QCheckBox("Автосоотношение")
        self.chk_aspect.setChecked(True)
        self.chk_aspect.toggled.connect(self._emit)
        lay.addLayout(row("Размер, ширина", self.spin_size_w))
        r_h = row("Размер, высота", self.spin_size_h, hint_h)
        self.spin_size_h_layout = r_h
        lay.addLayout(r_h)
        self.chk_aspect.setContentsMargins(150, 0, 0, 0)
        lay.addWidget(self.chk_aspect)

        self.spin_res = self._is(100, 1200, 600, 20, " px")
        self.spin_res.setToolTip("Чем больше — тем детальнее рисунок, но медленнее")
        self.spin_res.valueChanged.connect(self._emit)
        lay.addLayout(row("Разрешение", self.spin_res))

        self.combo_rotate = QComboBox()
        for deg in (0, 90, 180, 270):
            self.combo_rotate.addItem(f"{deg}°", deg)
        self.combo_rotate.currentIndexChanged.connect(self._emit)
        self.chk_flip_h = QCheckBox("Зеркало X")
        self.chk_flip_v = QCheckBox("Зеркало Y")
        self.chk_flip_h.toggled.connect(self._emit)
        self.chk_flip_v.toggled.connect(self._emit)
        fh = QHBoxLayout()
        fh.addWidget(self.chk_flip_h)
        fh.addWidget(self.chk_flip_v)
        lay.addLayout(fh)
        lay.addLayout(row("Поворот", self.combo_rotate))
        v.addWidget(self.card_photo)

        # ================= ТЕКСТ (ПИСЬМО) =================
        self.card_text, lay = make_card("Текст (письмо)")
        hint = QLabel("Введите текст — он станет «фото» (чёрное на белом). "
                      "Далее рисуйте режимом «Контуры» — и принтер напишет его.")
        hint.setProperty("hint", "true")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.pte_text = QPlainTextEdit()
        self.pte_text.setPlaceholderText("Например: Привет, мир!\nСтрока 2…")
        self.pte_text.setFixedHeight(72)
        lay.addWidget(self.pte_text)
        self.spin_text_size = self._is(16, 400, 160, 10, " px")
        self.spin_text_size.setToolTip("Размер шрифта в исходных пикселях")
        self.spin_text_size.valueChanged.connect(self._emit)
        lay.addLayout(row("Размер шрифта", self.spin_text_size))
        self.btn_text = QPushButton("Сделать из текста «фото»")
        self.btn_text.clicked.connect(self._emit)
        lay.addWidget(self.btn_text)
        v.addWidget(self.card_text)

        # ================= ОБРАБОТКА =================
        self.card_proc, lay = make_card("Обработка фото")
        self.slr_bright = SliderRow("Яркость", -100, 100, 0)
        self.slr_contrast = SliderRow("Контраст", -100, 100, 0)
        self.slr_gamma = SliderRow("Гамма", 0.05, 3.0, 1.0, step=0.05, decimals=2)
        self.slr_blur = SliderRow("Размытие", 0, 10, 0)
        self.slr_thresh = SliderRow("Порог", 0, 100, 50, suffix="%")
        for s in (self.slr_bright, self.slr_contrast, self.slr_gamma, self.slr_blur, self.slr_thresh):
            s.valueChanged.connect(self._emit)
            lay.addWidget(s)
        self.combo_edge = QComboBox()
        self.combo_edge.addItem("Нет", "none")
        self.combo_edge.addItem("Median (детали)", "median")
        self.combo_edge.addItem("Sobel (кромки)", "sobel")
        self.combo_edge.currentIndexChanged.connect(self._emit)
        lay.addLayout(row("Кромки", self.combo_edge))
        self.chk_invert = QCheckBox("Инверсия (светлое = чернила)")
        self.chk_invert.toggled.connect(self._emit)
        lay.addWidget(self.chk_invert)
        self.slr_bridge = SliderRow("Сшивка разрывов", 0, 7, 0, suffix=" px")
        self.slr_bridge.setToolTip(
            "Заделывает «трещины» в тонких линиях маски (морф. замыкание). "
            "По умолчанию выключена — силуэт остаётся точным, как в классике. "
            "Поднимите до 1–3, только если буква рвётся на куски.")
        self.slr_thicken = SliderRow("Утолщение линии", 0, 5, 0, suffix=" px")
        self.slr_thicken.setToolTip(
            "Утолщает «чернила» на N пикселей в каждую сторону — для очень тонких "
            "линий, которые теряются на пороге. 0 = без изменений.")
        for s in (self.slr_bridge, self.slr_thicken):
            s.valueChanged.connect(self._emit)
            lay.addWidget(s)
        v.addWidget(self.card_proc)

        # ================= ТРАССИРОВКА =================
        self.card_trace, lay = make_card("Трассировка")
        self.combo_mode = QComboBox()
        for key, label in MODE_LABELS.items():
            self.combo_mode.addItem(label, key)
        self.combo_mode.currentIndexChanged.connect(self._on_mode)
        lay.addLayout(row("Режим", self.combo_mode))
        self.lbl_mode_hint = QLabel("")
        self.lbl_mode_hint.setProperty("hint", "true")
        self.lbl_mode_hint.setWordWrap(True)
        lay.addWidget(self.lbl_mode_hint)
        self._mode_hints = {
            "raster": "Закрашивает тёмные места построчными линиями — фотографии, "
                      "тонировка, полутона.",
            "contour": "Контур каждого штриха (обе его кромки). Хорошо для фото "
                       "с закрашенными фигурами; у раскрасок линия получится «двойной».",
            "outline": "Только внешние силуэты тёмных областей, один обход.",
            "inner": "Только внутренние контуры: «дырки» и детали внутри тёмных "
                     "фигур (светлые замкнутые области).",
            "skeleton": "Центральная линия каждого штриха — одна чистая линия, "
                        "как в векторе. ЭТО режим для раскрасок и обводок от руки.",
            "crawl": "Один непрерывный путь «по тёмным пикселям» (алгоритм MagicGyver).",
            "waves": "Непрерывные волны, амплитуда следует за тёмнотою.",
        }

        # raster
        self.grp_raster = QWidget()
        gr = QVBoxLayout(self.grp_raster)
        gr.setContentsMargins(0, 0, 0, 0)
        gr.setSpacing(6)
        self.spin_raster_step = self._is(1, 20, 1, 1, "")
        self.spin_raster_step.setToolTip("Рисовать каждую N-ю строку (2 = вдвое быстрее)")
        self.spin_raster_step.valueChanged.connect(self._emit)
        self.spin_raster_min = self._is(1, 40, 2, 1, " px")
        self.spin_raster_min.setToolTip("Игнорировать отрезки короче")
        self.chk_raster_vertical = QCheckBox("Вертикальные линии")
        self.chk_raster_vertical.setToolTip("Сканировать столбцы вместо строк")
        self.chk_raster_vertical.toggled.connect(self._emit)
        gr.addLayout(row("Шаг строк", self.spin_raster_step))
        gr.addLayout(row("Мин. длина", self.spin_raster_min))
        gr.addWidget(self.chk_raster_vertical)

        # contour
        self.grp_contour = QWidget()
        gc = QVBoxLayout(self.grp_contour)
        gc.setContentsMargins(0, 0, 0, 0)
        gc.setSpacing(6)
        self.spin_contour_area = self._is(1, 2000, 20, 5, " px²")
        self.spin_contour_area.valueChanged.connect(self._emit)
        self.spin_contour_smooth = self._ds(0, 10, 1.5, 0.5, " px")
        self.spin_contour_smooth.valueChanged.connect(self._emit)
        gc.addLayout(row("Мин. площадь", self.spin_contour_area))
        gc.addLayout(row("Сглаживание", self.spin_contour_smooth))
        self.chk_precise = QCheckBox("Точный контур (субпиксельный)")
        self.chk_precise.setChecked(True)
        self.chk_precise.setToolTip(
            "Контур ищется по серому изображению (marching squares) — проходит "
            "по реальному анти-алейсированному краю, а не по «лесенке» пикселей. "
            "Точнее для печатного текста/почерка. Выкл = классический findContours.")
        self.chk_precise.toggled.connect(self._emit)
        gc.addWidget(self.chk_precise)

        # skeleton (раскраски)
        self.grp_skeleton = QWidget()
        gs = QVBoxLayout(self.grp_skeleton)
        gs.setContentsMargins(0, 0, 0, 0)
        gs.setSpacing(6)
        self.spin_skel_minlen = self._ds(0, 20, 1.0, 0.5, " мм")
        self.spin_skel_minlen.setToolTip(
            "Отбрасывать короткие штрихи (короткие обрезки/шум). "
            "Для раскрасок обычно 1 мм хватает.")
        self.spin_skel_minlen.valueChanged.connect(self._emit)
        gs.addLayout(row("Мин. длина штриха", self.spin_skel_minlen))

        # crawl
        self.grp_crawl = QWidget()
        gk = QVBoxLayout(self.grp_crawl)
        gk.setContentsMargins(0, 0, 0, 0)
        gk.setSpacing(6)
        self.spin_crawl_cell = self._is(1, 6, 1, 1, " px")
        self.spin_crawl_cell.setToolTip("Размер ячейки сетки «ползания»")
        self.spin_crawl_cell.valueChanged.connect(self._emit)
        self.spin_crawl_skip = self._is(1, 10, 2, 1, "")
        self.spin_crawl_skip.setToolTip("Каждые N шагов поисковое кольцо не сбрасывается — линия реже, прыжки длиннее")
        self.spin_crawl_skip.valueChanged.connect(self._emit)
        self.chk_crawl_loop = QCheckBox("Loop (движение по инерции)")
        self.chk_crawl_loop.setChecked(True)
        self.chk_crawl_loop.toggled.connect(self._emit)
        gk.addLayout(row("Ячейка", self.spin_crawl_cell))
        gk.addLayout(row("Skip", self.spin_crawl_skip))
        gk.addWidget(self.chk_crawl_loop)

        # waves
        self.grp_waves = QWidget()
        gw = QVBoxLayout(self.grp_waves)
        gw.setContentsMargins(0, 0, 0, 0)
        gw.setSpacing(6)
        self.spin_waves_rows = self._is(1, 200, 20, 1, "")
        self.spin_waves_rows.valueChanged.connect(self._emit)
        self.slr_waves_amp = SliderRow("Амплитуда", 0, 3, 1.0, step=0.1, decimals=1)
        self.slr_waves_amp.valueChanged.connect(self._emit)
        self.chk_waves_reverse = QCheckBox("Reverse")
        self.chk_waves_reverse.toggled.connect(self._emit)
        gw.addLayout(row("Рядов", self.spin_waves_rows))
        gw.addWidget(self.slr_waves_amp)
        gw.addWidget(self.chk_waves_reverse)

        self._groups = {"raster": self.grp_raster, "contour": self.grp_contour,
                        "outline": self.grp_contour,   # общие параметры с «Контуры»
                        "inner": self.grp_contour,
                        "skeleton": self.grp_skeleton,
                        "crawl": self.grp_crawl, "waves": self.grp_waves}
        for g in (self.grp_raster, self.grp_contour, self.grp_skeleton,
                  self.grp_crawl, self.grp_waves):
            lay.addWidget(g)

        # общее для всех режимов
        self.spin_smooth = self._is(0, 24, 0, 1, "")
        self.spin_smooth.setToolTip(
            "Сглаживание линии (метод Чакина). Для почерка/ручного обвода ставь 2–4, "
            "можно докручивать до 24 «на глаз». 0 = выключено.")
        self.spin_smooth.valueChanged.connect(self._emit)
        lay.addLayout(row("Сглаживание линии", self.spin_smooth))
        v.addWidget(self.card_trace)

        # ================= ПРИНТЕР =================
        self.card_printer, lay = make_card("Принтер (картезианский/i3)")
        self.spin_bed_w = self._ds(50, 1000, 220, 1, " мм")
        self.spin_bed_h = self._ds(50, 1000, 220, 1, " мм")
        for s in (self.spin_bed_w, self.spin_bed_h):
            s.valueChanged.connect(self._emit)
        lay.addLayout(row("Стол, X", self.spin_bed_w))
        lay.addLayout(row("Стол, Y", self.spin_bed_h))
        self.chk_center = QCheckBox("Центрировать рисунок на столе")
        self.chk_center.setChecked(True)
        self.chk_center.toggled.connect(self._emit)
        lay.addWidget(self.chk_center)
        self.chk_autofit = QCheckBox("Вписать в стол, если не влезает")
        self.chk_autofit.setToolTip(
            "Если рисунок больше стола — автоматически уменьшить пропорционально, "
            "а не обрезать. Движок: перетаскивай рисунок мышью во вкладке «Путь».")
        self.chk_autofit.toggled.connect(self._emit)
        lay.addWidget(self.chk_autofit)
        self.spin_off_x = self._ds(-1000, 1000, 0, 0.5, " мм")
        self.spin_off_y = self._ds(-1000, 1000, 0, 0.5, " мм")
        for s in (self.spin_off_x, self.spin_off_y):
            s.valueChanged.connect(self._emit)
        lay.addLayout(row("Смещение X", self.spin_off_x, "Добавляется к позиции рисунка"))
        lay.addLayout(row("Смещение Y", self.spin_off_y))

        self.slr_z_down = SliderRow("Z ручка: вниз", 0.05, 5, 0.3, step=0.05, decimals=2, suffix=" мм")
        self.slr_z_down.setToolTip("Высота, на которой ручка касается бумаги")
        self.slr_z_up = SliderRow("Z ручка: вверх", 0.1, 40, 2.0, step=0.1, decimals=1, suffix=" мм")
        self.slr_z_up.setToolTip("Высота подъёма для переходов")
        for s in (self.slr_z_down, self.slr_z_up):
            s.valueChanged.connect(self._emit)
            lay.addWidget(s)
        self.chk_lift = QCheckBox("Поднимать голову при переходах")
        self.chk_lift.setChecked(True)
        self.chk_lift.setToolTip("Выкл = переходы чистым XY-движением (без Z)")
        self.chk_lift.toggled.connect(self._emit)
        lay.addWidget(self.chk_lift)

        self.slr_pen_offset = SliderRow(
            "Кончик ручки ниже сопла", 0, 10, 0, step=0.1, decimals=1, suffix=" мм")
        self.slr_pen_offset.setToolTip(
            "Насколько кончик ручки опущен относительно днища сопла. "
            "0 = вровень: при рисовании сопло будет тереть бумагу!")
        self.slr_pen_offset.valueChanged.connect(self._emit)
        lay.addWidget(self.slr_pen_offset)
        self.lbl_clearance = QLabel("")
        self.lbl_clearance.setWordWrap(True)
        self.slr_pen_offset.valueChanged.connect(self._update_clearance)
        lay.addWidget(self.lbl_clearance)
        self._update_clearance()

        self.spin_draw_speed = self._is(500, 60000, 6000, 100, " мм/мин")
        self.spin_travel_speed = self._is(500, 120000, 12000, 100, " мм/мин")
        self.spin_z_speed = self._is(200, 30000, 4800, 100, " мм/мин")
        for s in (self.spin_draw_speed, self.spin_travel_speed, self.spin_z_speed):
            s.valueChanged.connect(self._emit)
        lay.addLayout(row("Скорость рисунка", self.spin_draw_speed, "Не выше ускорения/массы головы!"))
        lay.addLayout(row("Скорость перехода", self.spin_travel_speed))
        lay.addLayout(row("Скорость Z", self.spin_z_speed))

        self.spin_passes = self._is(1, 5, 1, 1, "")
        self.spin_passes.setToolTip("Несколько проходов = более тёмные линии")
        self.spin_passes.valueChanged.connect(self._emit)
        self.spin_pass_off = self._ds(0, 1, 0.05, 0.01, " мм")
        self.spin_pass_off.valueChanged.connect(self._emit)
        lay.addLayout(row("Проходов", self.spin_passes))
        lay.addLayout(row("Смещение прохода", self.spin_pass_off))
        v.addWidget(self.card_printer)

        # ================= G-CODE =================
        self.card_gcode, lay = make_card("G-код: старт / финал")
        hint = QLabel("Вставляется в начало и конец файла. Меняй под свой прошивочный набор команд.")
        hint.setProperty("hint", "true")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.pte_start = QPlainTextEdit(DEFAULT_START_GCODE)
        self.pte_start.setFixedHeight(120)
        self.pte_start.setFont(T.monospace_font())
        self.pte_start.textChanged.connect(self._emit)
        self.pte_end = QPlainTextEdit(DEFAULT_END_GCODE)
        self.pte_end.setFixedHeight(90)
        self.pte_end.setFont(T.monospace_font())
        self.pte_end.textChanged.connect(self._emit)
        lay.addWidget(self.pte_start)
        lay.addWidget(self.pte_end)
        self.btn_reset_gc = QPushButton("Сбросить по умолчанию")
        self.btn_reset_gc.setProperty("flat", "true")
        self.btn_reset_gc.clicked.connect(self._reset_gcode)
        lay.addWidget(self.btn_reset_gc, alignment=Qt.AlignRight)
        v.addWidget(self.card_gcode)

        v.addStretch(1)
        self.setWidget(outer)
        self._on_mode(self.combo_mode.currentIndex())

    # ------------------------------------------------------------------
    @staticmethod
    def _is(vmin, vmax, val, step, suffix) -> QSpinBox:
        s = QSpinBox()
        s.setRange(vmin, vmax)
        s.setValue(val)
        s.setSingleStep(step)
        if suffix:
            s.setSuffix(suffix)
        return s

    @staticmethod
    def _ds(vmin, vmax, val, step, suffix) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(vmin, vmax)
        s.setValue(val)
        s.setSingleStep(step)
        if suffix:
            s.setSuffix(suffix)
        return s

    def _emit(self, *_) -> None:
        self.changed.emit()

    def _update_clearance(self, *_) -> None:
        """Живой подсчёт клиренса сопла над бумагой при рисовании."""
        d = float(self.slr_pen_offset.value())
        if d < 0.5:
            self.lbl_clearance.setText(
                "⚠ Ручка вровень с соплом: при рисовании сопло будет тереть бумагу. "
                "Опусти кончик ручки на 2–3 мм ниже сопла (удлини крепление) или "
                "сними сопло — «Z ручка: вниз» выставь по фактическому касанию.")
            self.lbl_clearance.setProperty("warn", "true")
            self.lbl_clearance.setProperty("ok", "false")
        else:
            self.lbl_clearance.setText(
                f"Клиренс сопла над бумагой при рисовании ≈ {d:.1f} мм — сопло "
                "бумагу не заденет.")
            self.lbl_clearance.setProperty("ok", "true")
            self.lbl_clearance.setProperty("warn", "false")
        # перестильзовать виджет после смены динамического свойства
        self.lbl_clearance.style().unpolish(self.lbl_clearance)
        self.lbl_clearance.style().polish(self.lbl_clearance)

    def _reset_gcode(self) -> None:
        self.pte_start.setPlainText(DEFAULT_START_GCODE)
        self.pte_end.setPlainText(DEFAULT_END_GCODE)

    def _on_mode(self, _=0) -> None:
        mode = self.combo_mode.currentData()
        for key, grp in self._groups.items():
            grp.setVisible(key == mode)
        self.lbl_mode_hint.setText(self._mode_hints.get(mode, ""))
        self._emit()

    # ------------------------------------------------------------------
    def collect(self) -> tuple[ImageSettings, ProcessingSettings, TraceSettings, PrinterSettings]:
        img = ImageSettings(
            path=self._photo_path or "",
            size_w_mm=float(self.spin_size_w.value()),
            size_h_mm=float(self.spin_size_h.value()),
            keep_aspect=self.chk_aspect.isChecked(),
            resolution_px=int(self.spin_res.value()),
            rotate=int(self.combo_rotate.currentData()),
            flip_h=self.chk_flip_h.isChecked(),
            flip_v=self.chk_flip_v.isChecked(),
        )
        proc = ProcessingSettings(
            brightness=int(self.slr_bright.value()),
            contrast=int(self.slr_contrast.value()),
            gamma=float(self.slr_gamma.value()),
            blur=int(self.slr_blur.value()),
            threshold=float(self.slr_thresh.value()) / 100.0,
            edge=self.combo_edge.currentData(),
            invert=self.chk_invert.isChecked(),
            thicken_px=int(self.slr_thicken.value()),
            bridge_px=int(self.slr_bridge.value()),
        )
        ts = TraceSettings(
            mode=self.combo_mode.currentData(),
            raster_row_step=int(self.spin_raster_step.value()),
            raster_min_len_px=int(self.spin_raster_min.value()),
            raster_vertical=self.chk_raster_vertical.isChecked(),
            contour_min_area_px=int(self.spin_contour_area.value()),
            contour_smooth_px=float(self.spin_contour_smooth.value()),
            precise_contour=self.chk_precise.isChecked(),
            crawl_cell_px=int(self.spin_crawl_cell.value()),
            crawl_skip=int(self.spin_crawl_skip.value()),
            crawl_loop=self.chk_crawl_loop.isChecked(),
            waves_rows=int(self.spin_waves_rows.value()),
            waves_amplitude=float(self.slr_waves_amp.value()),
            waves_reverse=self.chk_waves_reverse.isChecked(),
            skeleton_min_len_mm=float(self.spin_skel_minlen.value()),
            smooth_iters=int(self.spin_smooth.value()),
        )
        pr = PrinterSettings(
            bed_w_mm=float(self.spin_bed_w.value()),
            bed_h_mm=float(self.spin_bed_h.value()),
            offset_x_mm=float(self.spin_off_x.value()),
            offset_y_mm=float(self.spin_off_y.value()),
            center=self.chk_center.isChecked(),
            autofit_bed=self.chk_autofit.isChecked(),
            z_pen_down=float(self.slr_z_down.value()),
            z_pen_up=float(self.slr_z_up.value()),
            lift_on_travel=self.chk_lift.isChecked(),
            pen_below_nozzle_mm=float(self.slr_pen_offset.value()),
            draw_speed=float(self.spin_draw_speed.value()),
            travel_speed=float(self.spin_travel_speed.value()),
            z_speed=float(self.spin_z_speed.value()),
            passes=int(self.spin_passes.value()),
            pass_offset_mm=float(self.spin_pass_off.value()),
            start_gcode=self.pte_start.toPlainText(),
            end_gcode=self.pte_end.toPlainText(),
        )
        return img, proc, ts, pr

    # ------------------------------------------------------------------
    def apply_state(self, img: ImageSettings, proc: ProcessingSettings,
                    ts: TraceSettings, pr: PrinterSettings) -> None:
        """Восстановить значения виджетов из сохранённых dataclass'ов."""
        def set_spin(w, v):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)

        def set_slider(w, v):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)

        def set_chk(w, v):
            w.blockSignals(True)
            w.setChecked(bool(v))
            w.blockSignals(False)

        # Фото
        set_spin(self.spin_size_w, img.size_w_mm)
        set_spin(self.spin_size_h, img.size_h_mm)
        set_chk(self.chk_aspect, img.keep_aspect)
        set_spin(self.spin_res, img.resolution_px)
        self.combo_rotate.blockSignals(True)
        self.combo_rotate.setCurrentIndex(max(0, self.combo_rotate.findData(img.rotate)))
        self.combo_rotate.blockSignals(False)
        set_chk(self.chk_flip_h, img.flip_h)
        set_chk(self.chk_flip_v, img.flip_v)
        self._photo_path = img.path or self._photo_path

        # Обработка
        set_slider(self.slr_bright, proc.brightness)
        set_slider(self.slr_contrast, proc.contrast)
        set_slider(self.slr_gamma, proc.gamma)
        set_slider(self.slr_blur, proc.blur)
        set_slider(self.slr_thresh, int(round(proc.threshold * 100)))
        self.combo_edge.blockSignals(True)
        self.combo_edge.setCurrentIndex(max(0, self.combo_edge.findData(proc.edge)))
        self.combo_edge.blockSignals(False)
        set_chk(self.chk_invert, proc.invert)
        set_slider(self.slr_thicken, proc.thicken_px)
        set_slider(self.slr_bridge, proc.bridge_px)

        # Трассировка
        self.combo_mode.blockSignals(True)
        idx = max(0, self.combo_mode.findData(ts.mode))
        self.combo_mode.setCurrentIndex(idx)
        self.combo_mode.blockSignals(False)
        set_spin(self.spin_raster_step, ts.raster_row_step)
        set_spin(self.spin_raster_min, ts.raster_min_len_px)
        set_chk(self.chk_raster_vertical, ts.raster_vertical)
        set_spin(self.spin_contour_area, ts.contour_min_area_px)
        set_spin(self.spin_contour_smooth, ts.contour_smooth_px)
        set_chk(self.chk_precise, ts.precise_contour)
        set_spin(self.spin_crawl_cell, ts.crawl_cell_px)
        set_spin(self.spin_crawl_skip, ts.crawl_skip)
        set_chk(self.chk_crawl_loop, ts.crawl_loop)
        set_spin(self.spin_waves_rows, ts.waves_rows)
        set_slider(self.slr_waves_amp, ts.waves_amplitude)
        set_chk(self.chk_waves_reverse, ts.waves_reverse)
        set_spin(self.spin_skel_minlen, ts.skeleton_min_len_mm)
        set_spin(self.spin_smooth, ts.smooth_iters)

        # Принтер
        set_spin(self.spin_bed_w, pr.bed_w_mm)
        set_spin(self.spin_bed_h, pr.bed_h_mm)
        set_chk(self.chk_center, pr.center)
        set_chk(self.chk_autofit, pr.autofit_bed)
        set_spin(self.spin_off_x, pr.offset_x_mm)
        set_spin(self.spin_off_y, pr.offset_y_mm)
        set_slider(self.slr_z_down, pr.z_pen_down)
        set_slider(self.slr_z_up, pr.z_pen_up)
        set_chk(self.chk_lift, pr.lift_on_travel)
        set_slider(self.slr_pen_offset, pr.pen_below_nozzle_mm)
        set_spin(self.spin_draw_speed, pr.draw_speed)
        set_spin(self.spin_travel_speed, pr.travel_speed)
        set_spin(self.spin_z_speed, pr.z_speed)
        set_spin(self.spin_passes, pr.passes)
        set_spin(self.spin_pass_off, pr.pass_offset_mm)
        self.pte_start.blockSignals(True)
        self.pte_start.setPlainText(pr.start_gcode)
        self.pte_start.blockSignals(False)
        self.pte_end.blockSignals(True)
        self.pte_end.setPlainText(pr.end_gcode)
        self.pte_end.blockSignals(False)

        # синхронизировать зависимое UI
        self._on_mode()
        self._update_clearance()

    # ------------------------------------------------------------------
    _photo_path: str = ""

    def set_photo_path(self, path: str) -> None:
        self._photo_path = path

    def set_dxf_mode(self, on: bool, name: str = "") -> None:
        """DXF загружен: обработка/трассировка/текст не применяются."""
        for w in (self.card_text, self.card_proc, self.card_trace,
                  self.spin_res, self.combo_rotate, self.chk_flip_h,
                  self.chk_flip_v):
            w.setEnabled(not on)
        self.lbl_dxf.setText(
            f"DXF: {name}" if (on and name) else "")

    def set_keep_aspect_lock(self, locked: bool) -> None:
        """Запретить ручную высоту, когда автосоотношение включено."""
        self.spin_size_h.setEnabled(not locked)
