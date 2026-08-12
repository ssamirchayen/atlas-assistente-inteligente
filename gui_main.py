import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from atlas.gui.window import AtlasWindow


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Atlas")
    app.setOrganizationName("Ssamir")
    app.setStyle("Fusion")

    icon_path = (
        Path(__file__).resolve().parent
        / "atlas"
        / "gui"
        / "assets"
        / "atlas_mark.svg"
    )
    app.setWindowIcon(QIcon(str(icon_path)))

    window = AtlasWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
