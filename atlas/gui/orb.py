from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QConicalGradient, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

ORB_STATE_COLORS: dict[str, tuple[str, str]] = {
    "ONLINE": ("#6B8AFF", "#67E8F9"),
    "ESCUTA ATIVA": ("#67E8F9", "#22D3EE"),
    "OUVINDO": ("#FCD34D", "#FB923C"),
    "EXECUTANDO": ("#60A5FA", "#818CF8"),
    "PROCESSANDO": ("#60A5FA", "#A78BFA"),
    "FALANDO": ("#A78BFA", "#E879F9"),
    "CONCLUÍDO": ("#34D399", "#67E8F9"),
    "CANCELANDO": ("#FB923C", "#F59E0B"),
    "CANCELADO": ("#FB923C", "#F59E0B"),
    "INTERROMPIDO": ("#FB923C", "#F59E0B"),
    "NÃO ENTENDI": ("#FB923C", "#F59E0B"),
    "ATENÇÃO": ("#FB923C", "#F59E0B"),
    "ERRO": ("#FB7185", "#F43F5E"),
    "DEFAULT": ("#94A3B8", "#CBD5E1"),
}

ACTIVE_STATES = {
    "ESCUTA ATIVA",
    "OUVINDO",
    "EXECUTANDO",
    "PROCESSANDO",
    "FALANDO",
    "CANCELANDO",
}


class AtlasOrb(QWidget):
    """Orb visual leve para refletir o estado operacional do Atlas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = "ONLINE"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(33)
        self.setMinimumSize(108, 108)
        self.setMaximumSize(108, 108)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        normalized = str(state).upper().strip() or "ONLINE"
        if normalized != self._state:
            self._state = normalized
            self.update()

    def _advance(self) -> None:
        speed = 0.055 if self._state in ACTIVE_STATES else 0.018
        self._phase = (self._phase + speed) % (math.tau)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = float(self.width())
        height = float(self.height())
        center = QPointF(width / 2.0, height / 2.0)
        pulse = (math.sin(self._phase) + 1.0) / 2.0
        active = self._state in ACTIVE_STATES
        primary_hex, secondary_hex = ORB_STATE_COLORS.get(
            self._state,
            ORB_STATE_COLORS["DEFAULT"],
        )
        primary = QColor(primary_hex)
        secondary = QColor(secondary_hex)

        outer_radius = min(width, height) * (0.44 + (0.018 * pulse if active else 0.0))
        glow_radius = outer_radius * 1.04

        glow = QLinearGradient(
            0.0,
            center.y() - glow_radius,
            0.0,
            center.y() + glow_radius,
        )
        glow_top = QColor(primary)
        glow_top.setAlpha(68 if active else 38)
        glow_bottom = QColor(secondary)
        glow_bottom.setAlpha(18)
        glow.setColorAt(0.0, glow_top)
        glow.setColorAt(1.0, glow_bottom)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, glow_radius, glow_radius)

        shell_radius = outer_radius * 0.78
        shell_gradient = QConicalGradient(center, math.degrees(self._phase) * 0.75)
        shell_gradient.setColorAt(0.0, primary)
        shell_gradient.setColorAt(0.44, secondary)
        shell_gradient.setColorAt(0.72, QColor("#1B2740"))
        shell_gradient.setColorAt(1.0, primary)
        painter.setBrush(shell_gradient)
        painter.drawEllipse(center, shell_radius, shell_radius)

        inner_radius = shell_radius * 0.72
        inner_gradient = QLinearGradient(
            center.x() - inner_radius,
            center.y() - inner_radius,
            center.x() + inner_radius,
            center.y() + inner_radius,
        )
        inner_gradient.setColorAt(0.0, QColor("#111C31"))
        inner_gradient.setColorAt(1.0, QColor("#070D18"))
        painter.setBrush(inner_gradient)
        painter.drawEllipse(center, inner_radius, inner_radius)

        ring_rect = QRectF(
            center.x() - shell_radius * 0.91,
            center.y() - shell_radius * 0.91,
            shell_radius * 1.82,
            shell_radius * 1.82,
        )
        ring_color = QColor(secondary)
        ring_color.setAlpha(220 if active else 145)
        pen = QPen(ring_color, 2.2 if active else 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        start_angle = int((self._phase * 180.0 / math.pi) * 16.0)
        span = int((120.0 + 45.0 * pulse) * 16.0)
        painter.drawArc(ring_rect, -start_angle, span)
        painter.drawArc(ring_rect, -start_angle + 180 * 16, span // 2)

        core_radius = inner_radius * (0.31 + (0.045 * pulse if active else 0.0))
        core = QColor(primary)
        core.setAlpha(235)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core)
        painter.drawEllipse(center, core_radius, core_radius)

        highlight = QColor("#FFFFFF")
        highlight.setAlpha(110)
        painter.setBrush(highlight)
        painter.drawEllipse(
            QPointF(center.x() - core_radius * 0.24, center.y() - core_radius * 0.24),
            core_radius * 0.18,
            core_radius * 0.18,
        )
