from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from atlas.vision.overlay import VisionOverlaySpec


class VisionOverlayWindow(QWidget):
    """Overlay temporário e totalmente read-only do Atlas Vision."""

    def __init__(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        transparent_input = getattr(
            Qt.WindowType,
            "WindowTransparentForInput",
            None,
        )
        if transparent_input is not None:
            flags |= transparent_input

        super().__init__(None, flags)

        self._spec: VisionOverlaySpec | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_overlay)

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating,
            True,
        )

    def show_spec(
        self,
        spec: VisionOverlaySpec,
    ) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return

        self._spec = spec
        self.setGeometry(screen.geometry())
        self.show()
        self.update()
        self._timer.start(spec.duration_ms)

    def hide_overlay(self) -> None:
        self._timer.stop()
        self.hide()
        self._spec = None

    def paintEvent(self, event) -> None:
        del event

        if self._spec is None:
            return

        x, y, width, height = self._spec.rect_for_size(
            self.width(),
            self.height(),
        )
        target = QRect(x, y, width, height)

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        border = QColor(38, 174, 255, 235)
        fill = QColor(38, 174, 255, 34)
        text_color = QColor(255, 255, 255)
        label_bg = QColor(17, 24, 39, 225)

        pen = QPen(border)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawRoundedRect(target, 8, 8)

        center_x = target.center().x()
        center_y = target.center().y()
        arm = 10

        painter.drawLine(
            center_x - arm,
            center_y,
            center_x + arm,
            center_y,
        )
        painter.drawLine(
            center_x,
            center_y - arm,
            center_x,
            center_y + arm,
        )

        confidence = round(
            max(0.0, min(self._spec.confidence, 1.0)) * 100
        )
        suffix = (
            f"  •  {confidence}%"
            if confidence
            else ""
        )
        label = (
            f"ATLAS VISION  •  {self._spec.label}"
            f"{suffix}"
        )

        font = QFont("Segoe UI", 10)
        font.setBold(True)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        label_width = metrics.horizontalAdvance(label) + 20
        label_height = metrics.height() + 12

        label_x = max(
            8,
            min(
                target.left(),
                self.width() - label_width - 8,
            ),
        )
        label_y = target.top() - label_height - 6

        if label_y < 8:
            label_y = target.bottom() + 6

        label_rect = QRect(
            label_x,
            label_y,
            label_width,
            label_height,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(label_bg)
        painter.drawRoundedRect(label_rect, 6, 6)

        painter.setPen(text_color)
        painter.drawText(
            label_rect.adjusted(10, 0, -10, 0),
            Qt.AlignmentFlag.AlignVCenter
            | Qt.AlignmentFlag.AlignLeft,
            label,
        )
