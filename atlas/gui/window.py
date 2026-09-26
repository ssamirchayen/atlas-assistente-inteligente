from __future__ import annotations

import html
import logging
import os
import threading
from concurrent.futures import Future
from datetime import datetime
from typing import TYPE_CHECKING

import psutil
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from atlas.core.config import ATLAS_NAME, USER_NAME
from atlas.copilot.local_api import create_copilot_server
from atlas.copilot.nexyra_bridge import NexyraCopilotBridge
from atlas.admin.service import AdminConsoleService
from atlas.gui.admin_console import AdminConsoleDialog
from atlas.gui.orb import AtlasOrb
from atlas.gui.theme import (
    MESSAGE_PALETTE,
    STATUS_PALETTE,
    VERSION_LABEL,
    application_stylesheet,
)
from atlas.gui.service import (
    AtlasGuiService,
    GuiCommandResult,
    SerialCommandRunner,
)
from atlas.gui.vision_overlay import VisionOverlayWindow
from atlas.voice.continuous import ContinuousVoiceListener
from atlas.voice.interruption import (
    VoiceInterruptionIntent,
    VoiceInterruptionMonitor,
)
from atlas.voice.session import VoiceSnapshot, VoiceState

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent


_LOGGER = logging.getLogger(__name__)


class AtlasSignals(QObject):
    command_finished = Signal(object)
    voice_ready = Signal(str)
    voice_state_changed = Signal(object)
    voice_interruption = Signal(object)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    speech_finished = Signal()


class AtlasWindow(QMainWindow):
    """Interface corporativa conectada ao backend oficial do Atlas."""

    def __init__(
        self,
        service: AtlasGuiService | None = None,
        *,
        speak_on_start: bool = True,
    ) -> None:
        super().__init__()

        self.service = service or AtlasGuiService()
        self.speech = self.service.kernel.speech
        self.voice_session = self.speech.session
        self.command_runner = SerialCommandRunner(
            self.service.execute
        )
        self.signals = AtlasSignals()
        self.wake_word_enabled = bool(
            getattr(self.service.kernel, "wake_word_enabled", True)
        )
        self.continuous_listener = ContinuousVoiceListener(
            self.speech,
            self._continuous_voice_command,
            wake_word=ATLAS_NAME,
            listen_timeout=(
                self.speech.performance_profile.continuous_listen_timeout
            ),
            phrase_time_limit=(
                self.speech.performance_profile.continuous_phrase_time_limit
            ),
            idle_wait=self.speech.performance_profile.continuous_idle_wait,
        )
        self.interruption_monitor = VoiceInterruptionMonitor(
            self.speech,
            self._voice_interruption_detected,
            wake_word=ATLAS_NAME,
        )
        self.processing = False
        self.listening = False
        self.voice_processing = False
        self.speaking = False
        self._resume_available = False
        self.vision_overlay = VisionOverlayWindow()
        self.admin_console: AdminConsoleDialog | None = None
        self._copilot_server = None
        self._copilot_thread: threading.Thread | None = None

        self._connect_signals()
        self._configure_window()
        self._build_interface()
        self.voice_session.subscribe(self._on_voice_state_changed)
        self._start_system_monitor()
        self.service.start()
        self._start_nexyra_copilot_bridge()
        self._refresh_resumption_state()
        self._ensure_interruption_monitor()

        self.add_atlas_message(
            "Interface conectada ao núcleo do Atlas. "
            "Todos os sistemas estão online."
        )
        self.set_status("ONLINE")

        if speak_on_start:
            self.speak_async(
                f"{ATLAS_NAME} iniciado. Olá, {USER_NAME}."
            )

    def _connect_signals(self) -> None:
        self.signals.command_finished.connect(self.receive_result)
        self.signals.voice_ready.connect(self.receive_voice_command)
        self.signals.voice_state_changed.connect(
            self.apply_voice_state
        )
        self.signals.voice_interruption.connect(
            self.receive_voice_interruption
        )
        self.signals.status_changed.connect(self.set_status)
        self.signals.error_occurred.connect(self.show_error)
        self.signals.speech_finished.connect(self.on_speech_finished)

    def _configure_window(self) -> None:
        self.setWindowTitle(f"{ATLAS_NAME} — Intelligence Workspace")
        self.resize(1500, 920)
        self.setMinimumSize(1180, 760)
        self.setStyleSheet(
            application_stylesheet() + "\n" + self._authorial_stylesheet()
        )

    def _build_interface(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._build_sidebar())

        workspace = QWidget()
        workspace.setObjectName("workspace")
        page = QVBoxLayout(workspace)
        page.setContentsMargins(31, 22, 27, 29)
        page.setSpacing(13)
        page.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(21)

        conversation_column = QWidget()
        conversation_column.setObjectName("conversationColumn")
        conversation_layout = QVBoxLayout(conversation_column)
        conversation_layout.setContentsMargins(0, 0, 0, 0)
        conversation_layout.setSpacing(7)
        conversation_layout.addWidget(
            self._build_conversation_card(),
            stretch=1,
        )
        conversation_layout.addWidget(self._build_command_panel())

        body.addWidget(conversation_column, stretch=1)
        body.addWidget(self._build_insights_rail())
        page.addLayout(body, stretch=1)

        shell.addWidget(workspace, stretch=1)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(238)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(19, 25, 17, 16)
        layout.setSpacing(11)

        brand = QFrame()
        brand.setObjectName("brandBlock")
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 12)
        brand_layout.setSpacing(2)

        brand_index = QLabel("A / 01")
        brand_index.setObjectName("brandIndex")
        brand_name = QLabel(ATLAS_NAME.upper())
        brand_name.setObjectName("sidebarBrand")
        brand_caption = QLabel("LOCAL INTELLIGENCE  ·  NEXYRA")
        brand_caption.setObjectName("sidebarCaption")
        brand_layout.addWidget(brand_index)
        brand_layout.addWidget(brand_name)
        brand_layout.addWidget(brand_caption)
        layout.addWidget(brand)

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        section = QLabel("WORKSPACE / CONTROL")
        section.setObjectName("sidebarSection")
        layout.addWidget(section)

        active_area = QFrame()
        active_area.setObjectName("activeArea")
        active_layout = QHBoxLayout(active_area)
        active_layout.setContentsMargins(10, 9, 10, 9)
        active_layout.setSpacing(8)
        area_mark = QLabel("▍")
        area_mark.setObjectName("activeAreaMark")
        area_label = QLabel("conversa")
        area_label.setObjectName("activeAreaText")
        active_layout.addWidget(area_mark)
        active_layout.addWidget(area_label)
        active_layout.addStretch()
        layout.addWidget(active_area)

        self.history_button = QPushButton("Histórico da sessão")
        self.history_button.setObjectName("sidebarButton")
        self.history_button.clicked.connect(self.show_session_history)
        layout.addWidget(self.history_button)

        self.admin_button = QPushButton("Admin Console")
        self.admin_button.setObjectName("sidebarButton")
        self.admin_button.clicked.connect(self.show_admin_console)
        layout.addWidget(self.admin_button)

        self.resume_button = QPushButton("Retomar pendência")
        self.resume_button.setObjectName("sidebarAccentButton")
        self.resume_button.setEnabled(False)
        self.resume_button.clicked.connect(self.resume_workflow)
        layout.addWidget(self.resume_button)

        layout.addStretch()

        privacy = QFrame()
        privacy.setObjectName("privacyCard")
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(11, 10, 11, 10)
        privacy_layout.setSpacing(3)
        privacy_title = QLabel("LOCAL / PRIVATE")
        privacy_title.setObjectName("privacyTitle")
        privacy_text = QLabel(
            "Dados e contexto permanecem locais por padrão."
        )
        privacy_text.setWordWrap(True)
        privacy_text.setObjectName("privacyText")
        privacy_layout.addWidget(privacy_title)
        privacy_layout.addWidget(privacy_text)
        layout.addWidget(privacy)

        version = QLabel(VERSION_LABEL)
        version.setObjectName("versionLabel")
        layout.addWidget(version)
        return sidebar

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("topHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        heading = QVBoxLayout()
        heading.setSpacing(1)
        eyebrow = QLabel("NEXYRA  /  ATLAS INTELLIGENCE")
        eyebrow.setObjectName("pageEyebrow")
        title = QLabel("Command workspace")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "memória  ·  raciocínio  ·  automação  ·  visão"
        )
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        layout.addLayout(heading)
        layout.addStretch()

        telemetry = QFrame()
        telemetry.setObjectName("headerTelemetry")
        telemetry_layout = QHBoxLayout(telemetry)
        telemetry_layout.setContentsMargins(4, 6, 2, 4)
        telemetry_layout.setSpacing(8)

        runtime = QLabel("core/local")
        runtime.setObjectName("headerTechValue")
        telemetry_layout.addWidget(runtime)

        separator = QLabel("/")
        separator.setObjectName("headerTechSeparator")
        telemetry_layout.addWidget(separator)

        self.clock_label = QLabel(datetime.now().strftime("%H:%M"))
        self.clock_label.setObjectName("headerTechValue")
        telemetry_layout.addWidget(self.clock_label)
        layout.addWidget(telemetry)

        user_card = QFrame()
        user_card.setObjectName("userCard")
        user_layout = QVBoxLayout(user_card)
        user_layout.setContentsMargins(10, 6, 10, 6)
        user_layout.setSpacing(0)
        user_name = QLabel(USER_NAME)
        user_name.setObjectName("userName")
        self.status_label = QLabel("↳ online")
        self.status_label.setObjectName("status")
        user_layout.addWidget(user_name)
        user_layout.addWidget(self.status_label)
        layout.addWidget(user_card)
        return frame

    def _build_conversation_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("conversationCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        conversation_header = QFrame()
        conversation_header.setObjectName("conversationHeader")
        header_layout = QHBoxLayout(conversation_header)
        header_layout.setContentsMargins(16, 11, 16, 10)
        header_layout.setSpacing(10)

        signature = QLabel("A/")
        signature.setObjectName("assistantSignature")
        header_layout.addWidget(signature)

        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        title = QLabel("Atlas / dialogue stream")
        title.setObjectName("conversationTitle")
        caption = QLabel("contexto persistente · execução supervisionada")
        caption.setObjectName("conversationCaption")
        title_block.addWidget(title)
        title_block.addWidget(caption)
        header_layout.addLayout(title_block)
        header_layout.addStretch()

        self.session_label = QLabel("● sessão local ativa")
        self.session_label.setObjectName("sessionLabel")
        header_layout.addWidget(self.session_label)
        layout.addWidget(conversation_header)

        self.chat = QTextEdit()
        self.chat.setObjectName("chat")
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText(
            "Converse com o Atlas ou execute uma tarefa."
        )
        self.chat.document().setDocumentMargin(18)
        layout.addWidget(self.chat, stretch=1)
        return frame

    def _build_command_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("commandPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(8)

        activity = QHBoxLayout()
        activity.setSpacing(7)
        activity_mark = QLabel("↳")
        activity_mark.setObjectName("activityMark")
        self.activity_label = QLabel("pronto para receber comandos")
        self.activity_label.setObjectName("activityText")
        activity.addWidget(activity_mark)
        activity.addWidget(self.activity_label)
        activity.addStretch()

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_workflow)
        activity.addWidget(self.cancel_button)
        layout.addLayout(activity)

        command_bar = QHBoxLayout()
        command_bar.setSpacing(7)

        self.input = QLineEdit()
        self.input.setObjectName("commandInput")
        self.input.setPlaceholderText("mensagem, pergunta ou comando…")
        self.input.returnPressed.connect(self.send_command)

        self.mic_button = QPushButton("Microfone")
        self.mic_button.setObjectName("secondaryButton")
        self.mic_button.clicked.connect(self.start_listening)

        self.continuous_button = QPushButton("Escuta contínua")
        self.continuous_button.setObjectName("secondaryButton")
        self.continuous_button.clicked.connect(
            self.toggle_continuous_listening
        )

        self.send_button = QPushButton("Enviar")
        self.send_button.setObjectName("primaryButton")
        self.send_button.clicked.connect(self.send_command)

        command_bar.addWidget(self.input, stretch=1)
        command_bar.addWidget(self.mic_button)
        command_bar.addWidget(self.continuous_button)
        command_bar.addWidget(self.send_button)
        layout.addLayout(command_bar)

        self.processing_bar = QProgressBar()
        self.processing_bar.setObjectName("processingBar")
        self.processing_bar.setRange(0, 100)
        self.processing_bar.setValue(100)
        self.processing_bar.setTextVisible(False)
        layout.addWidget(self.processing_bar)

        hint = QLabel(
            "ENTER envia  /  ATLAS, PARE interrompe  /  execução local"
        )
        hint.setObjectName("commandHint")
        layout.addWidget(hint)
        return frame

    def _build_insights_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("insightsRail")
        rail.setFixedWidth(304)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(7, 3, 0, 5)
        layout.setSpacing(17)

        rail_index = QLabel("A/OS   LIVE SIGNAL")
        rail_index.setObjectName("railIndex")
        layout.addWidget(rail_index)

        # Atlas Pulse deixa de ser um card de dashboard. Ele funciona como
        # um instrumento visual aberto, conectado diretamente ao rail.
        pulse = QFrame()
        pulse.setObjectName("atlasPulseDeck")
        pulse_layout = QVBoxLayout(pulse)
        pulse_layout.setContentsMargins(3, 0, 5, 15)
        pulse_layout.setSpacing(8)

        pulse_axis = QLabel("PULSE ───────── cognitive / operational")
        pulse_axis.setObjectName("pulseAxis")
        pulse_layout.addWidget(pulse_axis)

        orb_row = QHBoxLayout()
        orb_row.setContentsMargins(8, 1, 0, 2)
        orb_row.setSpacing(15)
        self.atlas_orb = AtlasOrb()
        orb_row.addWidget(
            self.atlas_orb,
            alignment=Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
        )

        pulse_copy = QVBoxLayout()
        pulse_copy.setSpacing(0)
        self.orb_state_label = QLabel("online")
        self.orb_state_label.setObjectName("orbState")
        pulse_text = QLabel("reasoning stream / local")
        pulse_text.setObjectName("pulseText")
        pulse_copy.addWidget(self.orb_state_label)
        pulse_copy.addWidget(pulse_text)
        pulse_copy.addStretch()
        orb_row.addLayout(pulse_copy, stretch=1)
        pulse_layout.addLayout(orb_row)

        state_row = QHBoxLayout()
        state_row.setContentsMargins(8, 1, 0, 0)
        state_row.setSpacing(14)
        self.workflow_label = QLabel("workflow: pronto")
        self.workflow_label.setObjectName("workflowState")
        self.mode_label = QLabel("io: texto + voz")
        self.mode_label.setObjectName("workflowStateMuted")
        state_row.addWidget(self.workflow_label)
        state_row.addWidget(self.mode_label)
        state_row.addStretch()
        pulse_layout.addLayout(state_row)
        layout.addWidget(pulse)

        # O Trace é o elemento proprietário da interface: mais parecido com
        # um instrumento de execução do que com um conjunto de métricas SaaS.
        trace = QFrame()
        trace.setObjectName("traceCard")
        trace_layout = QVBoxLayout(trace)
        trace_layout.setContentsMargins(13, 9, 6, 11)
        trace_layout.setSpacing(5)
        trace_title = QLabel("ATLAS TRACE / 04")
        trace_title.setObjectName("traceTitle")
        trace_caption = QLabel("capture → route → reason → act")
        trace_caption.setObjectName("traceCaption")
        trace_layout.addWidget(trace_title)
        trace_layout.addWidget(trace_caption)

        self.trace_labels: dict[str, QLabel] = {}
        for key, label_text in (
            ("capture", "01  capture"),
            ("route", "02  route"),
            ("reason", "03  reason"),
            ("act", "04  act"),
        ):
            node = QLabel(label_text)
            node.setObjectName("traceNode")
            self.trace_labels[key] = node
            trace_layout.addWidget(node)
        layout.addWidget(trace)

        # Telemetria vira rodapé técnico em linha — sem card, sem título +
        # número empilhado e sem barras visuais de dashboard.
        telemetry = QFrame()
        telemetry.setObjectName("telemetryStrip")
        telemetry_layout = QVBoxLayout(telemetry)
        telemetry_layout.setContentsMargins(2, 3, 3, 0)
        telemetry_layout.setSpacing(4)

        telemetry_axis = QLabel("LOCAL TELEMETRY / 1500ms")
        telemetry_axis.setObjectName("telemetryAxis")
        telemetry_layout.addWidget(telemetry_axis)

        telemetry_values = QHBoxLayout()
        telemetry_values.setContentsMargins(7, 0, 0, 0)
        telemetry_values.setSpacing(10)
        self.cpu_label = QLabel("cpu: 000%")
        self.cpu_label.setObjectName("telemetryValue")
        separator = QLabel("/")
        separator.setObjectName("telemetrySeparator")
        self.ram_label = QLabel("mem: 000%")
        self.ram_label.setObjectName("telemetryValue")
        local = QLabel("local")
        local.setObjectName("localState")
        telemetry_values.addWidget(self.cpu_label)
        telemetry_values.addWidget(separator)
        telemetry_values.addWidget(self.ram_label)
        telemetry_values.addStretch()
        telemetry_values.addWidget(local)
        telemetry_layout.addLayout(telemetry_values)

        # Mantidos invisíveis para preservar o contrato/telemetria existente.
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setObjectName("resourceBar")
        self.cpu_bar.setRange(0, 100)
        self.cpu_bar.setValue(0)
        self.cpu_bar.setTextVisible(False)
        self.cpu_bar.setVisible(False)
        self.ram_bar = QProgressBar()
        self.ram_bar.setObjectName("resourceBar")
        self.ram_bar.setRange(0, 100)
        self.ram_bar.setValue(0)
        self.ram_bar.setTextVisible(False)
        self.ram_bar.setVisible(False)
        telemetry_layout.addWidget(self.cpu_bar)
        telemetry_layout.addWidget(self.ram_bar)
        layout.addStretch()
        layout.addWidget(telemetry)

        self._update_trace_state("ONLINE")
        return rail

    def _update_trace_state(self, status: str) -> None:
        if not hasattr(self, "trace_labels"):
            return

        normalized = status.upper()
        if normalized in {"OUVINDO", "ESCUTA ATIVA"}:
            active = "capture"
        elif normalized in {"PROCESSANDO", "PENSANDO"}:
            active = "reason"
        elif normalized in {"EXECUTANDO", "CANCELANDO"}:
            active = "act"
        elif normalized in {"FALANDO", "CONCLUÍDO"}:
            active = "act"
        else:
            active = "route"

        order = ("capture", "route", "reason", "act")
        active_index = order.index(active)
        for index, key in enumerate(order):
            label = self.trace_labels[key]
            if index == active_index:
                label.setStyleSheet(
                    "QLabel#traceNode {"
                    "color:#e8f2ed; background:#12211e;"
                    "border-left:2px solid #56e0c1;"
                    "padding:6px 8px;"
                    "font-family:'Cascadia Mono', Consolas;"
                    "font-size:10px; font-weight:600;}"
                )
            elif index < active_index:
                label.setStyleSheet(
                    "QLabel#traceNode {"
                    "color:#789a90; background:transparent;"
                    "border-left:2px solid #28564f;"
                    "padding:6px 8px;"
                    "font-family:'Cascadia Mono', Consolas;"
                    "font-size:10px;}"
                )
            else:
                label.setStyleSheet(
                    "QLabel#traceNode {"
                    "color:#4d5b56; background:transparent;"
                    "border-left:2px solid #1c2a26;"
                    "padding:6px 8px;"
                    "font-family:'Cascadia Mono', Consolas;"
                    "font-size:10px;}"
                )

    @staticmethod
    def _authorial_stylesheet() -> str:
        return r"""
        QMainWindow, QWidget#root, QWidget#workspace { background:#090d0c; color:#dfe8e3; }
        QWidget { font-family:Bahnschrift, "Segoe UI"; font-size:12px; }

        QFrame#sidebar { background:#0b100f; border:none; border-right:1px solid #1c2a26; }
        QFrame#brandBlock { background:transparent; border:none; }
        QLabel#brandIndex { color:#d7a94b; font-family:"Cascadia Mono", Consolas; font-size:10px; font-weight:600; }
        QLabel#sidebarBrand { color:#eff5f1; font-family:Bahnschrift, "Segoe UI Semibold"; font-size:26px; font-weight:600; letter-spacing:2px; }
        QLabel#sidebarCaption, QLabel#pageEyebrow, QLabel#sidebarSection, QLabel#privacyTitle, QLabel#commandHint, QLabel#railIndex, QLabel#pulseAxis, QLabel#traceTitle, QLabel#telemetryAxis { color:#64736d; font-family:"Cascadia Mono", Consolas; font-size:9px; font-weight:600; letter-spacing:1px; }
        QFrame#sidebarDivider { background:#1c2a26; border:none; max-height:1px; }
        QFrame#activeArea { background:#101816; border:none; border-left:2px solid #56e0c1; border-radius:0; }
        QLabel#activeAreaMark { color:#56e0c1; font-size:13px; }
        QLabel#activeAreaText { color:#dce9e3; font-family:Bahnschrift; font-size:12px; }
        QPushButton#sidebarButton { background:transparent; color:#84928c; border:none; border-left:1px solid #24332f; border-radius:0; padding:8px 10px; text-align:left; }
        QPushButton#sidebarButton:hover { color:#e6efea; border-left:2px solid #d7a94b; }
        QPushButton#sidebarAccentButton { background:transparent; color:#56e0c1; border:none; border-left:2px solid #28564f; border-radius:0; padding:8px 10px; text-align:left; }
        QFrame#privacyCard { background:transparent; border:none; border-left:1px solid #293a35; border-radius:0; }
        QLabel#privacyText, QLabel#versionLabel { color:#65736d; font-size:10px; }

        QFrame#topHeader { background:transparent; border:none; }
        QLabel#pageTitle { color:#f0f5f2; font-family:Bahnschrift, "Segoe UI Semibold"; font-size:30px; font-weight:600; }
        QLabel#pageSubtitle { color:#75837d; font-family:"Cascadia Mono", Consolas; font-size:10px; }
        QFrame#headerTelemetry { background:transparent; border:none; border-bottom:1px solid #26332f; border-radius:0; }
        QLabel#headerTechValue { color:#9db0a8; font-family:"Cascadia Mono", Consolas; font-size:10px; }
        QLabel#headerTechSeparator { color:#d7a94b; }
        QFrame#userCard { background:transparent; border:none; }
        QLabel#userName { color:#aebbb5; font-family:Bahnschrift; font-size:11px; }

        QFrame#conversationCard { background:#0b1110; border:1px solid #1b2925; border-left:2px solid #223d37; border-radius:0; }
        QFrame#conversationHeader { background:#0d1412; border:none; border-bottom:1px solid #1b2925; }
        QLabel#assistantSignature { color:#56e0c1; font-family:Bahnschrift; font-size:22px; font-weight:600; }
        QLabel#conversationTitle { color:#dfe9e4; font-family:Bahnschrift; font-size:13px; }
        QLabel#conversationCaption, QLabel#sessionLabel { color:#61706a; font-family:"Cascadia Mono", Consolas; font-size:9px; }
        QTextEdit#chat { background:#090e0d; color:#dfe8e3; border:none; border-radius:0; padding:4px; selection-background-color:#1c6b63; }

        QFrame#commandPanel { background:#0d1412; border:none; border-left:2px solid #6f5930; border-bottom:1px solid #22312d; border-radius:0; }
        QLabel#activityMark { color:#d7a94b; font-family:Consolas; }
        QLabel#activityText { color:#72817a; font-family:"Cascadia Mono", Consolas; font-size:9px; }
        QLineEdit#commandInput { background:#090e0d; color:#e6efea; border:none; border-bottom:1px solid #344740; border-radius:0; padding:10px 7px; selection-background-color:#1c6b63; }
        QLineEdit#commandInput:focus { border-bottom:2px solid #3b8277; }
        QPushButton#primaryButton { background:#1c6b63; color:#eef7f3; border:none; border-radius:0; padding:9px 16px; font-family:Bahnschrift; font-weight:600; }
        QPushButton#primaryButton:hover { background:#237a71; }
        QPushButton#secondaryButton, QPushButton#cancelButton { background:transparent; color:#899991; border:none; border-bottom:1px solid #293a35; border-radius:0; padding:9px 10px; }
        QPushButton#secondaryButton:hover { color:#e5eee9; border-bottom-color:#4b665f; }
        QProgressBar#processingBar { min-height:2px; max-height:2px; background:#16211e; border:none; border-radius:0; }
        QProgressBar#processingBar::chunk { background:#56e0c1; }

        QFrame#insightsRail { background:transparent; border:none; }
        QLabel#railIndex { color:#d7a94b; padding-left:3px; }
        QFrame#atlasPulseDeck { background:transparent; border:none; border-left:1px solid #29433c; border-radius:0; }
        QLabel#pulseAxis { color:#60716a; padding-left:8px; }
        QLabel#orbState { color:#56e0c1; font-family:Bahnschrift; font-size:24px; font-weight:600; }
        QLabel#pulseText { color:#64736d; font-family:"Cascadia Mono", Consolas; font-size:9px; }
        QLabel#workflowState { color:#d7a94b; font-family:"Cascadia Mono", Consolas; font-size:9px; border:none; padding:0; }
        QLabel#workflowStateMuted { color:#708078; font-family:"Cascadia Mono", Consolas; font-size:9px; }

        QFrame#traceCard { background:#0a100e; border:none; border-left:1px solid #6f5930; border-radius:0; }
        QLabel#traceCaption { color:#5f6d67; font-family:"Cascadia Mono", Consolas; font-size:9px; margin-bottom:4px; }
        QLabel#traceNode { color:#4d5b56; border-left:2px solid #1c2a26; padding:6px 8px; font-family:"Cascadia Mono", Consolas; font-size:10px; }

        QFrame#telemetryStrip { background:transparent; border:none; border-top:1px solid #1c2a26; border-radius:0; }
        QLabel#telemetryAxis { color:#4f5e58; padding-top:5px; }
        QLabel#telemetryValue { color:#8fa099; font-family:"Cascadia Mono", Consolas; font-size:10px; }
        QLabel#telemetrySeparator { color:#4c5c56; font-family:"Cascadia Mono", Consolas; font-size:10px; }
        QLabel#localState { color:#4f897e; font-family:"Cascadia Mono", Consolas; font-size:9px; }

        QScrollBar:vertical { background:#090d0c; width:7px; margin:0; }
        QScrollBar::handle:vertical { background:#263631; min-height:28px; border-radius:0; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        """

    def _start_system_monitor(self) -> None:
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1500)

    def update_stats(self) -> None:
        cpu = round(psutil.cpu_percent())
        ram = round(psutil.virtual_memory().percent)
        self.cpu_label.setText(f"cpu: {cpu:03d}%")
        self.ram_label.setText(f"mem: {ram:03d}%")
        self.cpu_bar.setValue(cpu)
        self.ram_bar.setValue(ram)
        self.clock_label.setText(datetime.now().strftime("%H:%M"))

    def send_command(self) -> None:
        command = self.input.text().strip()

        if not command or self.processing or self.listening:
            return

        self.input.clear()
        self.process_command(command)

    def process_command(self, command: str) -> None:
        if self.processing:
            return

        self.vision_overlay.hide_overlay()
        self.continuous_listener.pause()
        self.interruption_monitor.arm()
        self.processing = True
        self.add_user_message(command)
        self.set_status("EXECUTANDO")
        self.activity_label.setText("Analisando e executando o comando...")
        self.workflow_label.setText("Em execução")
        self._update_controls()

        future = self.command_runner.submit(command)
        future.add_done_callback(self._command_finished)

    def _command_finished(
        self,
        future: Future[GuiCommandResult],
    ) -> None:
        try:
            result = future.result()
            self.signals.command_finished.emit(result)
        except Exception as exc:
            self.signals.error_occurred.emit(
                f"{type(exc).__name__}: {exc}"
            )

    def receive_result(self, result: GuiCommandResult) -> None:
        self.processing = False
        self.workflow_label.setText("Pronto")
        self.activity_label.setText(self._activity_text(result))
        self.add_atlas_message(result.message)

        if result.overlay is not None:
            self.vision_overlay.show_spec(result.overlay)

        if result.cancelled:
            self.set_status("CANCELADO")
        elif result.success:
            self.set_status("CONCLUÍDO")
        else:
            self.set_status("ATENÇÃO")

        self._refresh_resumption_state()
        self._update_controls()

        if result.should_close:
            self.interruption_monitor.disarm()
            QTimer.singleShot(1200, self.close)
            return

        self.speak_async(result.message)

    @staticmethod
    def _activity_text(result: GuiCommandResult) -> str:
        if result.cancelled:
            return "Execução cancelada com segurança"
        if result.source == "scheduler":
            return "Tarefa adicionada ao agendador"
        if result.source == "vision_grounding":
            return "Elemento localizado e marcado na tela"
        if result.action_count:
            return f"{result.action_count} ação(ões) processada(s)"
        return "Resposta concluída"

    def cancel_workflow(self) -> None:
        if not self.processing:
            return

        if self.service.cancel():
            self.set_status("CANCELANDO")
            self.activity_label.setText(
                "Solicitação de cancelamento enviada..."
            )
            self.cancel_button.setEnabled(False)
            self.add_system_message(
                "Cancelamento solicitado. A etapa atual será encerrada "
                "com segurança."
            )
        else:
            self.add_system_message(
                "Ainda não existe um workflow ativo para cancelar."
            )

    def show_session_history(self) -> None:
        """Exibe no chat os eventos recentes da sessão operacional."""

        try:
            events = self.service.get_operational_timeline(limit=12)
        except Exception as exc:
            self.add_system_message(
                "Não foi possível consultar o histórico operacional: "
                f"{type(exc).__name__}."
            )
            return

        if not events:
            self.add_system_message(
                "A sessão atual ainda não possui eventos registrados."
            )
            return

        entries: list[str] = []

        for event in events:
            event_name = event.event_type.value.replace(".", " › ")
            message = " ".join(event.message.split())

            if len(message) > 110:
                message = f"{message[:107]}..."

            entries.append(
                f"#{event.sequence} · {event_name}: {message}"
            )

        self.add_system_message(
            "Histórico operacional recente:\n" + "\n".join(entries)
        )

    def show_admin_console(self) -> None:
        """Abre o diagnóstico local sem carregar componentes lazy."""

        if self.admin_console is None:
            self.admin_console = AdminConsoleDialog(
                AdminConsoleService(self.service.kernel),
                parent=self,
            )
        self.admin_console.refresh()
        self.admin_console.show()
        self.admin_console.raise_()
        self.admin_console.activateWindow()

    def resume_workflow(self) -> None:
        """Solicita confirmação e retoma somente etapas pendentes."""

        if self.processing:
            return

        try:
            plan = self.service.get_resumption_plan()
        except Exception as exc:
            self.add_system_message(
                "Não foi possível consultar a retomada: "
                f"{type(exc).__name__}."
            )
            return

        if not plan.can_resume:
            self._resume_available = False
            self.add_system_message(plan.reason)
            self._update_controls()
            return

        confirmation_token: str | None = None

        if plan.requires_confirmation:
            answer = QMessageBox.question(
                self,
                "Confirmar retomada",
                (
                    f"{plan.reason}\n\n"
                    f"Etapas pendentes: {len(plan.remaining_steps)}.\n"
                    "Deseja executar somente as etapas restantes?"
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if answer != QMessageBox.StandardButton.Yes:
                return

            confirmation_token = plan.confirmation_token

        self.continuous_listener.pause()
        self.interruption_monitor.arm()
        self.processing = True
        self.set_status("EXECUTANDO")
        self.activity_label.setText(
            "Retomando as etapas pendentes com segurança..."
        )
        self.workflow_label.setText("Retomando")
        self._update_controls()

        future = self.command_runner.submit_callable(
            lambda: self.service.resume_interrupted_workflow(
                confirmation_token=confirmation_token,
            )
        )
        future.add_done_callback(self._command_finished)

    def _refresh_resumption_state(self) -> None:
        """Atualiza os indicadores sem executar nenhuma ação pendente."""

        try:
            plan = self.service.get_resumption_plan()
        except Exception:
            self._resume_available = False
        else:
            self._resume_available = plan.can_resume

        self.resume_button.setEnabled(
            self._resume_available and not self.processing
        )
        self.session_label.setText(
            "●  Retomada disponível"
            if self._resume_available
            else "●  Sessão local ativa"
        )

    def start_listening(self) -> None:
        if (
            self.listening
            or self.processing
            or self.speaking
            or self.continuous_listener.is_active
        ):
            return

        self.listening = True
        self.set_status("OUVINDO")
        self.activity_label.setText("Aguardando sua voz...")
        self._update_controls()

        threading.Thread(
            target=self._microphone_worker,
            daemon=True,
        ).start()

    def toggle_continuous_listening(self) -> None:
        """Ativa ou desativa o modo mãos-livres da interface."""

        if self.continuous_listener.is_active:
            self.continuous_listener.stop(wait=False)
            self.mode_label.setText("Texto + voz")
            self.activity_label.setText("Pronto para receber comandos")

            if not self.processing and not self.speaking:
                self.set_status("ONLINE")

            self._update_controls()
            return

        if not self.wake_word_enabled:
            self.add_system_message(
                "A palavra de ativação está desativada no arquivo .env."
            )
            return

        if (
            not self.speech.microphone_enabled
            and not self.speech.enable_microphone()
        ):
            self.show_error("Não consegui ativar o microfone.")
            return

        self._ensure_interruption_monitor()

        if not self.continuous_listener.start():
            self.show_error("Não consegui iniciar a escuta contínua.")
            return

        self.mode_label.setText("Voz contínua")
        self.set_status("ESCUTA ATIVA")
        self.activity_label.setText(
            f'Diga "{ATLAS_NAME}" seguido do comando'
        )
        self._update_controls()

    def _continuous_voice_command(self, command: str) -> None:
        """Encaminha com segurança um comando da thread de escuta."""

        self.signals.voice_ready.emit(command)

    def _ensure_interruption_monitor(self) -> None:
        if (
            self.wake_word_enabled
            and self.speech.microphone_enabled
            and not self.interruption_monitor.is_active
        ):
            self.interruption_monitor.start()

    def _voice_interruption_detected(
        self,
        intent: VoiceInterruptionIntent,
    ) -> None:
        """Transporta a interrupção da thread de áudio para o Qt."""

        self.signals.voice_interruption.emit(intent)

    def receive_voice_interruption(
        self,
        intent: VoiceInterruptionIntent,
    ) -> None:
        """Interrompe fala e workflow a partir de ``Atlas, pare``."""

        self.interruption_monitor.disarm()
        self.continuous_listener.pause()
        reason = f"Interrompido por voz: {intent.command}"
        voice_interrupted = self.speech.request_interruption(reason)
        workflow_cancelled = self.processing and self.service.cancel()

        if workflow_cancelled:
            self.set_status("CANCELANDO")
            self.activity_label.setText(
                "Interrupção recebida; cancelando a execução..."
            )
            message = (
                "Comando de parada reconhecido. O workflow será "
                "encerrado com segurança."
            )
        else:
            self.set_status("INTERROMPIDO")
            self.activity_label.setText("Resposta de voz interrompida")
            message = "Comando de parada reconhecido. A voz foi interrompida."

        if voice_interrupted or workflow_cancelled:
            self.add_system_message(message)

    def _microphone_worker(self) -> None:
        try:
            profile = self.speech.performance_profile
            command = self.speech.listen(
                "Ouvindo seu comando...",
                timeout=profile.command_timeout,
                phrase_time_limit=profile.command_phrase_time_limit,
            )

            if command:
                self.signals.voice_ready.emit(command)
            else:
                self.signals.status_changed.emit("NÃO ENTENDI")
        except Exception as exc:
            self.signals.error_occurred.emit(
                f"Erro no microfone: {exc}"
            )

    def receive_voice_command(self, command: str) -> None:
        self.listening = False
        self.voice_processing = False
        self._update_controls()
        self.process_command(command)

    def _on_voice_state_changed(
        self,
        snapshot: VoiceSnapshot,
    ) -> None:
        self.signals.voice_state_changed.emit(snapshot)

    def apply_voice_state(self, snapshot: VoiceSnapshot) -> None:
        """Reflete na interface o estado central da sessão de voz."""

        state = snapshot.state

        if state is VoiceState.LISTENING:
            continuous = self.continuous_listener.is_active
            self.listening = not continuous
            self.voice_processing = False
            self.speaking = False

            if continuous:
                self.set_status("ESCUTA ATIVA")
                self.activity_label.setText(
                    f'Diga "{ATLAS_NAME}" seguido do comando'
                )
            else:
                self.set_status("OUVINDO")
                self.activity_label.setText("Aguardando sua voz...")

        elif state is VoiceState.PROCESSING:
            self.listening = False
            self.voice_processing = True
            self.speaking = False
            self.set_status("PROCESSANDO")
            self.activity_label.setText("Interpretando o comando de voz...")

        elif state is VoiceState.SPEAKING:
            self.listening = False
            self.voice_processing = False
            self.speaking = True
            self.set_status("FALANDO")
            self.activity_label.setText("Atlas está respondendo...")

        elif state is VoiceState.INTERRUPTED:
            self.listening = False
            self.voice_processing = False
            self.speaking = False
            self.set_status("INTERROMPIDO")
            self.activity_label.setText(
                snapshot.interruption_reason
                or "Interação por voz interrompida"
            )

        elif state is VoiceState.ERROR:
            self.listening = False
            self.voice_processing = False
            self.speaking = False
            self.set_status("ERRO")
            self.activity_label.setText(
                snapshot.error_message
                or "Falha no sistema de voz"
            )

        elif state is VoiceState.IDLE:
            self.listening = False
            self.voice_processing = False
            self.speaking = False

            if not self.processing:
                if self.continuous_listener.is_active:
                    self.set_status("ESCUTA ATIVA")
                    self.activity_label.setText(
                        f'Diga "{ATLAS_NAME}" seguido do comando'
                    )
                else:
                    self.set_status("ONLINE")

        self._update_controls()

    def speak_async(self, message: str) -> None:
        if not message:
            self.on_speech_finished()
            return

        if self.voice_session.interruption_requested():
            self.on_speech_finished()
            return

        self.interruption_monitor.arm()
        self.speaking = True
        self.set_status("FALANDO")
        self._update_controls()

        threading.Thread(
            target=self._speech_worker,
            args=(message,),
            daemon=True,
        ).start()

    def _speech_worker(self, message: str) -> None:
        try:
            self.speech.say(message)
        except Exception as exc:
            self.signals.error_occurred.emit(f"Erro na voz: {exc}")
        finally:
            self.signals.speech_finished.emit()

    def on_speech_finished(self) -> None:
        self.speaking = False

        if self.voice_session.is_state(VoiceState.INTERRUPTED):
            self.voice_session.reset()

        if not self.processing and not self.listening:
            self.interruption_monitor.disarm()

            if self.continuous_listener.is_active:
                self.continuous_listener.resume()
                self.set_status("ESCUTA ATIVA")
                self.activity_label.setText(
                    f'Diga "{ATLAS_NAME}" seguido do comando'
                )
            else:
                self.set_status("ONLINE")

            self._update_controls()
            self.input.setFocus()

    def set_status(self, status: str) -> None:
        normalized = status.upper()
        foreground, _background, _border = STATUS_PALETTE.get(
            normalized,
            STATUS_PALETTE["DEFAULT"],
        )
        self.status_label.setText(f"↳ {normalized.lower()}")
        if hasattr(self, "atlas_orb"):
            self.atlas_orb.set_state(normalized)
        if hasattr(self, "orb_state_label"):
            self.orb_state_label.setText(normalized.lower())
        if hasattr(self, "trace_labels"):
            self._update_trace_state(normalized)
        if hasattr(self, "processing_bar"):
            active_states = {
                "EXECUTANDO",
                "PROCESSANDO",
                "OUVINDO",
                "FALANDO",
                "CANCELANDO",
            }
            if normalized in active_states:
                self.processing_bar.setRange(0, 0)
            else:
                self.processing_bar.setRange(0, 100)
                self.processing_bar.setValue(100)
        self.status_label.setStyleSheet(
            "QLabel#status {"
            f"color: {foreground};"
            "background: transparent;"
            "border: none;"
            "border-left: none;"
            "padding: 1px 0;"
            "font-family: 'Cascadia Mono', Consolas;"
            "font-size: 9px;"
            "font-weight: 600;"
            "}"
        )

        if normalized == "NÃO ENTENDI":
            self.listening = False
            self.activity_label.setText("não consegui reconhecer sua fala")
            self._update_controls()
            QTimer.singleShot(1800, lambda: self.set_status("ONLINE"))

    def show_error(self, error: str) -> None:
        self.processing = False
        self.listening = False
        self.voice_processing = False
        self.speaking = False
        self.workflow_label.setText("Erro")
        self.activity_label.setText("A execução encontrou um erro")
        self.add_atlas_message(f"Ocorreu um erro interno: {error}")
        self.set_status("ERRO")
        self._update_controls()
        self.interruption_monitor.disarm()

        if self.continuous_listener.is_active:
            self.continuous_listener.resume()

    def _update_controls(self) -> None:
        idle = not any(
            (
                self.processing,
                self.listening,
                self.voice_processing,
                self.speaking,
            )
        )
        self.input.setEnabled(idle)
        self.send_button.setEnabled(idle)
        continuous = self.continuous_listener.is_active
        self.mic_button.setEnabled(idle and not continuous)
        self.continuous_button.setEnabled(not self.listening)
        self.cancel_button.setEnabled(self.processing)
        self.history_button.setEnabled(idle)
        self.admin_button.setEnabled(idle)
        self.resume_button.setEnabled(idle and self._resume_available)
        self.mic_button.setText(
            "Ouvindo..." if self.listening else "Usar microfone"
        )
        self.continuous_button.setText(
            "Desativar escuta" if continuous else "Escuta contínua"
        )

    def add_user_message(self, message: str) -> None:
        palette = MESSAGE_PALETTE["user"]
        self._append_message(
            "VOCÊ",
            message,
            accent=palette["accent"],
            background=palette["background"],
            foreground=palette["foreground"],
            align_right=True,
        )

    def add_atlas_message(self, message: str) -> None:
        palette = MESSAGE_PALETTE["atlas"]
        self._append_message(
            ATLAS_NAME.upper(),
            message,
            accent=palette["accent"],
            background=palette["background"],
            foreground=palette["foreground"],
        )

    def add_system_message(self, message: str) -> None:
        palette = MESSAGE_PALETTE["system"]
        self._append_message(
            "SISTEMA",
            message,
            accent=palette["accent"],
            background=palette["background"],
            foreground=palette["foreground"],
        )

    def _append_message(
        self,
        author: str,
        message: str,
        *,
        accent: str,
        background: str,
        foreground: str,
        align_right: bool = False,
    ) -> None:
        safe_author = html.escape(author)
        safe_message = html.escape(str(message)).replace("\n", "<br>")
        timestamp = datetime.now().strftime("%H:%M:%S")
        role = "you" if align_right else "atlas"
        author_label = "você" if align_right else safe_author.lower()
        rule = "#d7a94b" if align_right else "#56e0c1"

        self.chat.append(
            "<table width='100%' cellspacing='0' cellpadding='0'>"
            "<tr>"
            f"<td width='3' bgcolor='{rule}'></td>"
            "<td width='12'></td>"
            "<td>"
            f"<span style='color:#73817b; font-family:Consolas; "
            f"font-size:9px;'>{timestamp} / {role}</span><br>"
            f"<span style='color:{rule}; font-family:Bahnschrift; "
            f"font-size:11px; font-weight:600;'>{author_label} /</span><br>"
            f"<span style='color:{foreground}; font-size:13px; "
            f"line-height:1.45;'>{safe_message}</span>"
            "</td></tr></table>"
            "<div style='height:11px;'></div>"
        )
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _start_nexyra_copilot_bridge(self) -> None:
        raw_enabled = os.getenv("ATLAS_COPILOT_ENABLED")
        enabled = (
            raw_enabled.strip().lower() not in {"0", "false", "no", "off"}
            if raw_enabled is not None
            else bool(os.getenv("ATLAS_NEXYRA_URL"))
        )
        if not enabled:
            return

        host = os.getenv("ATLAS_COPILOT_HOST", "127.0.0.1")
        try:
            port = int(os.getenv("ATLAS_COPILOT_PORT", "8766"))
            timeout = float(os.getenv("ATLAS_COPILOT_TIMEOUT_SECONDS", "45"))
        except ValueError:
            _LOGGER.warning("Configuração inválida do Atlas Copilot Bridge.")
            return

        bridge = NexyraCopilotBridge(
            self.command_runner.submit,
            timeout_seconds=timeout,
        )
        try:
            server = create_copilot_server(
                host=host,
                port=port,
                copilot_handler=bridge.handle,
                allowed_origin=os.getenv(
                    "ATLAS_COPILOT_ALLOWED_ORIGIN",
                    "http://127.0.0.1:5173",
                ),
                api_token=os.getenv("ATLAS_COPILOT_TOKEN", ""),
            )
        except OSError as exc:
            _LOGGER.warning("Atlas Copilot Bridge indisponível: %s", exc)
            return

        self._copilot_server = server
        self._copilot_thread = threading.Thread(
            target=server.serve_forever,
            name="atlas-nexyra-copilot",
            daemon=True,
        )
        self._copilot_thread.start()
        _LOGGER.info(
            "Atlas Copilot Bridge ativo em http://%s:%s",
            host,
            port,
        )

    def _stop_nexyra_copilot_bridge(self) -> None:
        server = self._copilot_server
        if server is None:
            return
        self._copilot_server = None
        try:
            server.shutdown()
            server.server_close()
        except OSError:
            _LOGGER.exception("Falha ao encerrar Atlas Copilot Bridge.")
        thread = self._copilot_thread
        self._copilot_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.admin_console is not None:
            self.admin_console.close()
        self.vision_overlay.hide_overlay()
        self.vision_overlay.close()
        self.service.cancel()
        self.continuous_listener.stop(wait=True, timeout=3.0)
        self.interruption_monitor.stop(wait=True, timeout=2.0)
        self.voice_session.unsubscribe(self._on_voice_state_changed)
        self.speech.disable_microphone()
        self._stop_nexyra_copilot_bridge()
        self.command_runner.close(cleanup=self.service.close)
        event.accept()

    @staticmethod
    def _stylesheet() -> str:
        """Compatibilidade com chamadas antigas da camada gráfica."""

        return application_stylesheet() + "\n" + AtlasWindow._authorial_stylesheet()
