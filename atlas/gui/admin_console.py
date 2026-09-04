"""Janela administrativa local e somente leitura do Atlas Core."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from atlas.admin.service import AdminConsoleService, AdminHealth, AdminSnapshot


class AdminConsoleDialog(QDialog):
    def __init__(
        self,
        service: AdminConsoleService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Atlas Core — Admin Console")
        self.resize(860, 620)
        self.setMinimumSize(720, 520)
        self.setModal(False)
        self.setStyleSheet(self._stylesheet())
        self._build_interface()
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def _build_interface(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Admin Console")
        title.setObjectName("adminTitle")
        subtitle = QLabel(
            "Diagnóstico local e somente leitura do Atlas Core"
        )
        subtitle.setObjectName("adminSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.health_label = QLabel("CARREGANDO")
        self.health_label.setObjectName("healthBadge")
        self.health_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.health_label)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.profile_value = self._add_card(
            grid, 0, 0, "PERFIL DE EXECUÇÃO", "—"
        )
        self.pressure_value = self._add_card(
            grid, 0, 1, "PRESSÃO DE RECURSOS", "—"
        )
        self.memory_value = self._add_card(
            grid, 0, 2, "MEMÓRIA DISPONÍVEL", "—"
        )
        self.lazy_value = self._add_card(
            grid, 1, 0, "COMPONENTES LAZY", "—"
        )
        self.model_value = self._add_card(
            grid, 1, 1, "ÚLTIMO MODELO", "—"
        )
        self.audit_value = self._add_card(
            grid, 1, 2, "EVENTOS DE RECURSO", "—"
        )
        layout.addLayout(grid)

        details = QFrame()
        details.setObjectName("detailsCard")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(18, 16, 18, 16)
        details_title = QLabel("ESTADO OPERACIONAL")
        details_title.setObjectName("sectionTitle")
        self.details_label = QLabel("Coletando diagnóstico...")
        self.details_label.setObjectName("detailsText")
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        details_layout.addWidget(details_title)
        details_layout.addWidget(self.details_label)
        layout.addWidget(details, stretch=1)

        footer = QHBoxLayout()
        read_only = QLabel("●  SOMENTE LEITURA  •  PROCESSAMENTO LOCAL")
        read_only.setObjectName("readOnlyLabel")
        footer.addWidget(read_only)
        footer.addStretch()
        refresh_button = QPushButton("Atualizar")
        refresh_button.setObjectName("refreshButton")
        refresh_button.clicked.connect(self.refresh)
        close_button = QPushButton("Fechar")
        close_button.clicked.connect(self.close)
        footer.addWidget(refresh_button)
        footer.addWidget(close_button)
        layout.addLayout(footer)

    @staticmethod
    def _add_card(
        grid: QGridLayout,
        row: int,
        column: int,
        caption: str,
        initial: str,
    ) -> QLabel:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        caption_label = QLabel(caption)
        caption_label.setObjectName("metricCaption")
        value_label = QLabel(initial)
        value_label.setObjectName("metricValue")
        value_label.setWordWrap(True)
        layout.addWidget(caption_label)
        layout.addWidget(value_label)
        grid.addWidget(card, row, column)
        return value_label

    def refresh(self) -> None:
        try:
            snapshot = self.service.snapshot()
        except Exception as error:
            self.health_label.setText("INDISPONÍVEL")
            self.details_label.setText(
                "Não foi possível atualizar o diagnóstico: "
                f"{type(error).__name__}."
            )
            return
        self._render(snapshot)

    def _render(self, snapshot: AdminSnapshot) -> None:
        health_labels = {
            AdminHealth.HEALTHY: "SAUDÁVEL",
            AdminHealth.ATTENTION: "ATENÇÃO",
            AdminHealth.CRITICAL: "CRÍTICO",
            AdminHealth.UNAVAILABLE: "INDISPONÍVEL",
        }
        self.health_label.setText(health_labels[snapshot.health])
        self.health_label.setProperty("health", snapshot.health.value)
        self.health_label.style().unpolish(self.health_label)
        self.health_label.style().polish(self.health_label)

        self.profile_value.setText(
            str(snapshot.profile.get("selected", "Indisponível")).upper()
        )
        pressure = str(snapshot.resources.get("pressure", "indisponível"))
        self.pressure_value.setText(pressure.upper())
        available = snapshot.resources.get("available_memory_gb")
        self.memory_value.setText(
            "Indisponível" if available is None else f"{available} GB"
        )

        loaded = sum(bool(item.get("loaded")) for item in snapshot.lazy_components)
        self.lazy_value.setText(f"{loaded}/{len(snapshot.lazy_components)} carregados")
        self.model_value.setText(
            "Ainda não utilizado"
            if snapshot.model_route is None
            else str(snapshot.model_route.get("model_name", "Indisponível"))
        )
        self.audit_value.setText(
            str(snapshot.resource_audit.get("total_events", "Indisponível"))
        )

        lazy_lines = [
            f"{item.get('name')}: {item.get('state')}"
            for item in snapshot.lazy_components
        ]
        reasons = ", ".join(snapshot.reason_codes)
        self.details_label.setText(
            "Componentes: "
            + (" • ".join(lazy_lines) if lazy_lines else "indisponíveis")
            + "\n"
            + f"Diagnóstico: {reasons}\n"
            + f"Atualizado em: {snapshot.generated_at.astimezone().strftime('%H:%M:%S')}"
        )

    @staticmethod
    def _stylesheet() -> str:
        return """
            QDialog { background: #F4F7FB; }
            QLabel { color: #1D2939; font-family: "Segoe UI"; }
            QLabel#adminTitle { font-size: 24px; font-weight: 750; color: #172033; }
            QLabel#adminSubtitle { font-size: 11px; color: #667085; }
            QLabel#healthBadge {
                padding: 7px 13px; border-radius: 11px; font-size: 10px;
                font-weight: 750; color: #157347; background: #E9F7EF;
                border: 1px solid #B8E0C8;
            }
            QLabel#healthBadge[health="attention"] {
                color: #9A6700; background: #FFF8E6; border-color: #F3D48A;
            }
            QLabel#healthBadge[health="critical"],
            QLabel#healthBadge[health="unavailable"] {
                color: #B42318; background: #FFF0F0; border-color: #F3B8B4;
            }
            QFrame#metricCard, QFrame#detailsCard {
                background: #FFFFFF; border: 1px solid #DCE3EC;
                border-radius: 11px;
            }
            QLabel#metricCaption, QLabel#sectionTitle {
                color: #667085; font-size: 9px; font-weight: 700;
            }
            QLabel#metricValue { color: #172033; font-size: 16px; font-weight: 700; }
            QLabel#detailsText { color: #475467; font-size: 11px; }
            QLabel#readOnlyLabel { color: #157347; font-size: 9px; font-weight: 700; }
            QPushButton {
                min-height: 20px; padding: 8px 14px; border-radius: 8px;
                border: 1px solid #C9D3E0; background: #FFFFFF;
                color: #344054; font-family: "Segoe UI"; font-weight: 650;
            }
            QPushButton#refreshButton {
                color: #FFFFFF; background: #2F6FED; border-color: #2F6FED;
            }
        """

