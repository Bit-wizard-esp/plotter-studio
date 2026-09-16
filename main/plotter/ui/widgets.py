"""Мелкие переиспользуемые виджеты."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QSlider, QWidget


class SliderRow(QWidget):
    """Строка: подпись + слайдер + числовое поле (синхронизированы).

    value — float в диапазоне [min, max].
    """

    valueChanged = Signal(float)

    def __init__(self, label: str, vmin: float, vmax: float, value: float,
                 step: float = 1, decimals: int = 0, suffix: str = "", parent=None):
        super().__init__(parent)
        self._decimals = decimals
        scale = 10 ** decimals
        self._syncing = False

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)

        lab = QLabel(label)
        lab.setMinimumWidth(150)
        h.addWidget(lab)

        self._slider = QSlider()
        self._slider.setOrientation(Qt.Horizontal)
        self._slider.setRange(int(vmin * scale), int(vmax * scale))
        self._slider.setValue(int(value * scale))
        h.addWidget(self._slider, 1)

        self._spin = QDoubleSpinBox()
        self._spin.setDecimals(decimals)
        self._spin.setRange(vmin, vmax)
        self._spin.setSingleStep(step)
        self._spin.setValue(value)
        if suffix:
            self._spin.setSuffix(suffix)
        self._spin.setFixedWidth(92)
        h.addWidget(self._spin)

        self._slider.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)

    def _on_slider(self, iv: int) -> None:
        if self._syncing:
            return
        v = iv / (10 ** self._decimals)
        self._syncing = True
        self._spin.blockSignals(True)
        self._spin.setValue(v)
        self._spin.blockSignals(False)
        self._syncing = False
        self.valueChanged.emit(float(v))

    def _on_spin(self, v: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        self._slider.blockSignals(True)
        self._slider.setValue(int(round(v * (10 ** self._decimals))))
        self._slider.blockSignals(False)
        self._syncing = False
        self.valueChanged.emit(float(v))

    def value(self) -> float:
        return self._spin.value()

    def setValue(self, v: float) -> None:  # noqa: N802 (API Qt)
        self._syncing = True
        self._spin.blockSignals(True)
        self._spin.setValue(v)
        self._spin.blockSignals(False)
        self._slider.setValue(int(round(v * (10 ** self._decimals))))
        self._syncing = False
        self.valueChanged.emit(float(v))
