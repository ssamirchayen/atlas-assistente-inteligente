from __future__ import annotations

import html
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

        self._connect_signals()
        self._configure_window()
        self._build_interface()
        self.voice_session.subscribe(self._on_voice_state_changed)
        self._start_system_monitor()
        self.service.start()
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
        self.setStyleSheet(application_stylesheet())

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
        page.setContentsMargins(28, 24, 28, 24)
        page.setSpacing(18)
        page.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(16)

        conversation_column = QWidget()
        conversation_column.setObjectName("conversationColumn")
        conversation_layout = QVBoxLayout(conversation_column)
        conversation_layout.setContentsMargins(0, 0, 0, 0)
        conversation_layout.setSpacing(12)
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
        sidebar.setFixedWidth(246)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 22, 20, 20)
        layout.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = QLabel("A")
        logo.setObjectName("logoBadge")
        logo.setFixedSize(46, 46)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        identity = QVBoxLayout()
        identity.setSpacing(0)
        brand_name = QLabel(ATLAS_NAME.upper())
        brand_name.setObjectName("sidebarBrand")
        brand_caption = QLabel("by NEXYRA")
        brand_caption.setObjectName("sidebarCaption")
        identity.addWidget(brand_name)
        identity.addWidget(brand_caption)

        brand.addWidget(logo)
        brand.addLayout(identity)
        brand.addStretch()
        layout.addLayout(brand)

        product_caption = QLabel("LOCAL INTELLIGENCE SYSTEM")
        product_caption.setObjectName("productCaption")
        layout.addWidget(product_caption)

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        section = QLabel("WORKSPACE")
        section.setObjectName("sidebarSection")
        layout.addWidget(section)

        active_area = QFrame()
        active_area.setObjectName("activeArea")
        active_layout = QHBoxLayout(active_area)
        active_layout.setContentsMargins(12, 10, 12, 10)
        active_layout.setSpacing(10)
        area_mark = QLabel("●")
        area_mark.setObjectName("activeAreaMark")
        area_label = QLabel("Conversa")
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
        privacy_layout.setContentsMargins(13, 12, 13, 12)
        privacy_layout.setSpacing(4)
        privacy_title = QLabel("PRIVACY FIRST")
        privacy_title.setObjectName("privacyTitle")
        privacy_text = QLabel(
            "Processamento local por padrão. Integrações externas "
            "somente quando habilitadas."
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
        layout.setSpacing(12)

        heading = QVBoxLayout()
        heading.setSpacing(3)
        eyebrow = QLabel("NEXYRA  /  ATLAS INTELLIGENCE")
        eyebrow.setObjectName("pageEyebrow")
        title = QLabel("Workspace")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Comando, contexto e automação em uma única interface operacional."
        )
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        layout.addLayout(heading)
        layout.addStretch()

        for caption_text, value_text in (
            ("ENGINE", "Atlas Core"),
            ("RUNTIME", "Local"),
        ):
            signal = QFrame()
            signal.setObjectName("headerSignal")
            signal_layout = QVBoxLayout(signal)
            signal_layout.setContentsMargins(12, 8, 12, 8)
            signal_layout.setSpacing(1)
            caption = QLabel(caption_text)
            caption.setObjectName("headerSignalCaption")
            value = QLabel(value_text)
            value.setObjectName("headerSignalValue")
            signal_layout.addWidget(caption)
            signal_layout.addWidget(value)
            layout.addWidget(signal)

        clock_signal = QFrame()
        clock_signal.setObjectName("headerSignal")
        clock_layout = QVBoxLayout(clock_signal)
        clock_layout.setContentsMargins(12, 8, 12, 8)
        clock_layout.setSpacing(1)
        clock_caption = QLabel("LOCAL TIME")
        clock_caption.setObjectName("headerSignalCaption")
        self.clock_label = QLabel(datetime.now().strftime("%H:%M"))
        self.clock_label.setObjectName("headerSignalValue")
        clock_layout.addWidget(clock_caption)
        clock_layout.addWidget(self.clock_label)
        layout.addWidget(clock_signal)

        user_card = QFrame()
        user_card.setObjectName("userCard")
        user_layout = QHBoxLayout(user_card)
        user_layout.setContentsMargins(10, 7, 11, 7)
        user_layout.setSpacing(9)

        avatar = QLabel(USER_NAME[:1].upper() if USER_NAME else "U")
        avatar.setObjectName("userAvatar")
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        user_block = QVBoxLayout()
        user_block.setSpacing(2)
        user_name = QLabel(USER_NAME)
        user_name.setObjectName("userName")
        self.status_label = QLabel("●  ONLINE")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_block.addWidget(user_name)
        user_block.addWidget(self.status_label)

        user_layout.addWidget(avatar)
        user_layout.addLayout(user_block)
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
        header_layout.setContentsMargins(18, 13, 18, 13)
        header_layout.setSpacing(10)

        assistant_avatar = QLabel("A")
        assistant_avatar.setObjectName("assistantAvatar")
        assistant_avatar.setFixedSize(34, 34)
        assistant_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(assistant_avatar)

        title_block = QVBoxLayout()
        title_block.setSpacing(1)
        title = QLabel("Atlas")
        title.setObjectName("conversationTitle")
        caption = QLabel("Canal principal  •  Atlas Core")
        caption.setObjectName("conversationCaption")
        title_block.addWidget(title)
        title_block.addWidget(caption)
        header_layout.addLayout(title_block)
        header_layout.addStretch()

        self.session_label = QLabel("●  Sessão local ativa")
        self.session_label.setObjectName("sessionLabel")
        header_layout.addWidget(self.session_label)
        layout.addWidget(conversation_header)

        self.chat = QTextEdit()
        self.chat.setObjectName("chat")
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText(
            "Converse com o Atlas ou execute uma tarefa."
        )
        self.chat.document().setDocumentMargin(20)
        layout.addWidget(self.chat, stretch=1)
        return frame

    def _build_command_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("commandPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 11, 14, 12)
        layout.setSpacing(9)

        activity = QHBoxLayout()
        activity.setSpacing(8)
        activity_mark = QLabel("●")
        activity_mark.setObjectName("activityMark")
        self.activity_label = QLabel("Pronto para receber comandos")
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
        command_bar.setSpacing(8)

        self.input = QLineEdit()
        self.input.setObjectName("commandInput")
        self.input.setPlaceholderText(
            "Mensagem, pergunta ou comando para o Atlas..."
        )
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
            "Enter para enviar  •  processamento local  •  "
            "diga 'Atlas, pare' para interromper"
        )
        hint.setObjectName("commandHint")
        layout.addWidget(hint)
        return frame

    def _build_insights_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("insightsRail")
        rail.setFixedWidth(300)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        pulse = QFrame()
        pulse.setObjectName("heroMetricCard")
        pulse_layout = QVBoxLayout(pulse)
        pulse_layout.setContentsMargins(16, 15, 16, 15)
        pulse_layout.setSpacing(10)

        orb_row = QHBoxLayout()
        orb_row.setSpacing(12)
        self.atlas_orb = AtlasOrb()
        orb_copy = QVBoxLayout()
        orb_copy.setSpacing(3)
        pulse_title = QLabel("Atlas Pulse")
        pulse_title.setObjectName("pulseTitle")
        pulse_text = QLabel("Estado cognitivo e operacional")
        pulse_text.setObjectName("pulseText")
        self.orb_state_label = QLabel("ONLINE")
        self.orb_state_label.setObjectName("orbState")
        orb_copy.addWidget(pulse_title)
        orb_copy.addWidget(pulse_text)
        orb_copy.addSpacing(4)
        orb_copy.addWidget(self.orb_state_label)
        orb_copy.addStretch()
        orb_row.addWidget(self.atlas_orb)
        orb_row.addLayout(orb_copy, stretch=1)
        pulse_layout.addLayout(orb_row)

        pulse_divider = QFrame()
        pulse_divider.setObjectName("softDivider")
        pulse_divider.setFrameShape(QFrame.Shape.HLine)
        pulse_layout.addWidget(pulse_divider)

        workflow_caption = QLabel("WORKFLOW")
        workflow_caption.setObjectName("metricCaption")
        self.workflow_label = QLabel("Pronto")
        self.workflow_label.setObjectName("metricValue")
        mode_caption = QLabel("INTERAÇÃO")
        mode_caption.setObjectName("metricCaption")
        self.mode_label = QLabel("Texto + voz")
        self.mode_label.setObjectName("metricValue")
        pulse_layout.addWidget(workflow_caption)
        pulse_layout.addWidget(self.workflow_label)
        pulse_layout.addWidget(mode_caption)
        pulse_layout.addWidget(self.mode_label)

        capability_row = QHBoxLayout()
        capability_row.setSpacing(6)
        for label_text in ("VOICE", "VISION", "MEMORY"):
            chip = QLabel(label_text)
            chip.setObjectName("capabilityChip")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            capability_row.addWidget(chip)
        pulse_layout.addLayout(capability_row)
        layout.addWidget(pulse)

        resources = QFrame()
        resources.setObjectName("infoCard")
        resources_layout = QVBoxLayout(resources)
        resources_layout.setContentsMargins(16, 14, 16, 15)
        resources_layout.setSpacing(8)
        resources_title = QLabel("Recursos")
        resources_title.setObjectName("cardTitle")
        resources_caption = QLabel("Telemetria local")
        resources_caption.setObjectName("cardCaption")
        resources_layout.addWidget(resources_title)
        resources_layout.addWidget(resources_caption)

        self.cpu_label = QLabel("CPU   0%")
        self.cpu_label.setObjectName("resourceLabel")
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setObjectName("resourceBar")
        self.cpu_bar.setRange(0, 100)
        self.cpu_bar.setValue(0)
        self.cpu_bar.setTextVisible(False)

        self.ram_label = QLabel("MEMÓRIA   0%")
        self.ram_label.setObjectName("resourceLabel")
        self.ram_bar = QProgressBar()
        self.ram_bar.setObjectName("resourceBar")
        self.ram_bar.setRange(0, 100)
        self.ram_bar.setValue(0)
        self.ram_bar.setTextVisible(False)

        resources_layout.addWidget(self.cpu_label)
        resources_layout.addWidget(self.cpu_bar)
        resources_layout.addWidget(self.ram_label)
        resources_layout.addWidget(self.ram_bar)
        layout.addWidget(resources)

        quick = QFrame()
        quick.setObjectName("infoCard")
        quick_layout = QVBoxLayout(quick)
        quick_layout.setContentsMargins(16, 14, 16, 15)
        quick_layout.setSpacing(7)
        quick_title = QLabel("Ações rápidas")
        quick_title.setObjectName("cardTitle")
        quick_caption = QLabel("Acesso às ferramentas do workspace")
        quick_caption.setObjectName("cardCaption")
        quick_layout.addWidget(quick_title)
        quick_layout.addWidget(quick_caption)

        history_quick = QPushButton("Histórico operacional")
        history_quick.setObjectName("quickButton")
        history_quick.clicked.connect(self.show_session_history)
        admin_quick = QPushButton("Abrir Admin Console")
        admin_quick.setObjectName("quickButton")
        admin_quick.clicked.connect(self.show_admin_console)
        quick_layout.addWidget(history_quick)
        quick_layout.addWidget(admin_quick)
        layout.addWidget(quick)

        trust = QFrame()
        trust.setObjectName("infoCard")
        trust_layout = QVBoxLayout(trust)
        trust_layout.setContentsMargins(16, 14, 16, 15)
        trust_layout.setSpacing(7)
        trust_title = QLabel("Ambiente")
        trust_title.setObjectName("cardTitle")
        trust_caption = QLabel(
            "Execução local e controle do usuário como padrão."
        )
        trust_caption.setObjectName("cardBody")
        trust_caption.setWordWrap(True)
        local = QLabel("●  Núcleo local ativo")
        local.setObjectName("localState")
        trust_layout.addWidget(trust_title)
        trust_layout.addWidget(trust_caption)
        trust_layout.addWidget(local)
        layout.addWidget(trust)
        layout.addStretch()
        return rail

    def _start_system_monitor(self) -> None:
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1500)

    def update_stats(self) -> None:
        cpu = round(psutil.cpu_percent())
        ram = round(psutil.virtual_memory().percent)
        self.cpu_label.setText(f"CPU   {cpu}%")
        self.ram_label.setText(f"MEMÓRIA   {ram}%")
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
        foreground, background, border = STATUS_PALETTE.get(
            normalized,
            STATUS_PALETTE["DEFAULT"],
        )
        self.status_label.setText(f"●  {normalized}")
        if hasattr(self, "atlas_orb"):
            self.atlas_orb.set_state(normalized)
        if hasattr(self, "orb_state_label"):
            self.orb_state_label.setText(normalized)
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
            f"background: {background};"
            f"border: 1px solid {border};"
            "border-radius: 10px;"
            "padding: 4px 9px;"
            "font-size: 9px;"
            "font-weight: 700;"
            "}"
        )

        if normalized == "NÃO ENTENDI":
            self.listening = False
            self.activity_label.setText("Não consegui reconhecer sua fala")
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
        timestamp = datetime.now().strftime("%H:%M")
        alignment = "right" if align_right else "left"
        bubble_width = "68%" if align_right else "78%"

        self.chat.append(
            f"<table align='{alignment}' width='{bubble_width}' "
            "cellspacing='0' cellpadding='12' "
            f"bgcolor='{background}'>"
            "<tr><td>"
            f"<span style='color:{accent}; font-size:10px; "
            f"font-weight:700;'>{safe_author}</span>"
            f"<span style='color:{accent}; font-size:9px;'>"
            f" &nbsp; {timestamp}</span><br>"
            f"<span style='color:{foreground}; font-size:13px; line-height:1.45;'>"
            f"{safe_message}</span>"
            "</td></tr></table>"
            "<div style='height:7px;'></div>"
        )
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

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
        self.command_runner.close(cleanup=self.service.close)
        event.accept()

    @staticmethod
    def _stylesheet() -> str:
        """Compatibilidade com chamadas antigas da camada gráfica."""

        return application_stylesheet()
