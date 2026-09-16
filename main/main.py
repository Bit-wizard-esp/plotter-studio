"""Plotter Studio — фото в G-код для 3D-принтера.

Запуск:
    python main.py
"""
import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from plotter.ui import theme as T
    from plotter.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Plotter Studio")
    app.setOrganizationName("PlotterStudio")

    # иконка
    from PySide6.QtGui import QIcon
    import os
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "plotter", "ui", "icons", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    T.apply(app, "dark")

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
