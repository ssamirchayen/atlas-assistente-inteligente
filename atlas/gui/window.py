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
from atlas.gui.service import (
    AtlasGuiService,
    GuiCommandResult,
    SerialCommandRunner,
)
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
        self.setWindowTitle(f"{ATLAS_NAME} — Assistente Inteligente")
        self.resize(1280, 800)
        self.setMinimumSize(1000, 650)
        self.setStyleSheet(self._stylesheet())

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
        page.setContentsMargins(30, 24, 30, 24)
        page.setSpacing(18)
        page.addWidget(self._build_header())
        page.addWidget(self._build_conversation_card(), stretch=1)
        page.addWidget(self._build_command_panel())

        shell.addWidget(workspace, stretch=1)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(248)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(22, 24, 22, 22)
        layout.setSpacing(16)

        brand = QHBoxLayout()
        brand.setSpacing(12)

        logo = QLabel("A")
        logo.setObjectName("logoBadge")
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        identity = QVBoxLayout()
        identity.setSpacing(1)
        brand_name = QLabel(ATLAS_NAME.upper())
        brand_name.setObjectName("sidebarBrand")
        brand_caption = QLabel("INTELLIGENCE CORE")
        brand_caption.setObjectName("sidebarCaption")
        identity.addWidget(brand_name)
        identity.addWidget(brand_caption)

        brand.addWidget(logo)
        brand.addLayout(identity)
        brand.addStretch()
        layout.addLayout(brand)

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        section = QLabel("ÁREA DE TRABALHO")
        section.setObjectName("sidebarSection")
        layout.addWidget(section)

        current_area = QFrame()
        current_area.setObjectName("activeArea")
        current_layout = QHBoxLayout(current_area)
        current_layout.setContentsMargins(12, 11, 12, 11)
        current_layout.setSpacing(10)
        area_mark = QLabel("●")
        area_mark.setObjectName("activeAreaMark")
        area_label = QLabel("Conversa")
        area_label.setObjectName("activeAreaText")
        current_layout.addWidget(area_mark)
        current_layout.addWidget(area_label)
        current_layout.addStretch()
        layout.addWidget(current_area)

        overview_title = QLabel("OPERAÇÃO")
        overview_title.setObjectName("sidebarSection")
        layout.addWidget(overview_title)

        operation = QFrame()
        operation.setObjectName("operationCard")
        operation_layout = QVBoxLayout(operation)
        operation_layout.setContentsMargins(14, 14, 14, 14)
        operation_layout.setSpacing(12)

        workflow_caption = QLabel("Workflow")
        workflow_caption.setObjectName("sideMetricCaption")
        self.workflow_label = QLabel("Pronto")
        self.workflow_label.setObjectName("sideMetricValue")

        mode_caption = QLabel("Modo de interação")
        mode_caption.setObjectName("sideMetricCaption")
        self.mode_label = QLabel("Texto + voz")
        self.mode_label.setObjectName("sideMetricValue")

        operation_layout.addWidget(workflow_caption)
        operation_layout.addWidget(self.workflow_label)
        operation_layout.addWidget(mode_caption)
        operation_layout.addWidget(self.mode_label)
        layout.addWidget(operation)

        resources_title = QLabel("RECURSOS DO SISTEMA")
        resources_title.setObjectName("sidebarSection")
        layout.addWidget(resources_title)

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

        layout.addWidget(self.cpu_label)
        layout.addWidget(self.cpu_bar)
        layout.addWidget(self.ram_label)
        layout.addWidget(self.ram_bar)
        layout.addStretch()

        local_badge = QLabel("●  PROCESSAMENTO LOCAL")
        local_badge.setObjectName("localBadge")
        layout.addWidget(local_badge)

        version = QLabel("ATLAS CORE  •  SPRINT 21")
        version.setObjectName("versionLabel")
        layout.addWidget(version)
        return sidebar

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("topHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 2, 0, 2)

        heading = QVBoxLayout()
        heading.setSpacing(3)
        title = QLabel(f"Conversa com o {ATLAS_NAME}")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Comande suas rotinas e acompanhe cada execução em tempo real."
        )
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        layout.addLayout(heading)
        layout.addStretch()

        user_block = QVBoxLayout()
        user_block.setSpacing(4)
        user_name = QLabel(USER_NAME)
        user_name.setObjectName("userName")
        user_name.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_label = QLabel("●  ONLINE")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_block.addWidget(user_name)
        user_block.addWidget(self.status_label)
        layout.addLayout(user_block)
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
        header_layout.setContentsMargins(20, 15, 20, 15)

        title = QLabel("Conversa")
        title.setObjectName("conversationTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.history_button = QPushButton("Histórico")
        self.history_button.setObjectName("headerButton")
        self.history_button.clicked.connect(self.show_session_history)
        header_layout.addWidget(self.history_button)

        self.resume_button = QPushButton("Retomar pendência")
        self.resume_button.setObjectName("resumeButton")
        self.resume_button.setEnabled(False)
        self.resume_button.clicked.connect(self.resume_workflow)
        header_layout.addWidget(self.resume_button)

        self.session_label = QLabel("●  Sessão local ativa")
        self.session_label.setObjectName("sessionLabel")
        header_layout.addWidget(self.session_label)
        layout.addWidget(conversation_header)

        self.chat = QTextEdit()
        self.chat.setObjectName("chat")
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText(
            "Sua conversa com o Atlas aparecerá aqui."
        )
        self.chat.document().setDocumentMargin(16)
        layout.addWidget(self.chat, stretch=1)
        return frame

    def _build_command_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("commandPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        activity = QHBoxLayout()
        activity.setSpacing(10)
        activity_mark = QLabel("●")
        activity_mark.setObjectName("activityMark")
        self.activity_label = QLabel("Pronto para receber comandos")
        self.activity_label.setObjectName("activityText")
        activity.addWidget(activity_mark)
        activity.addWidget(self.activity_label)
        activity.addStretch()

        self.cancel_button = QPushButton("Cancelar execução")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_workflow)
        activity.addWidget(self.cancel_button)
        layout.addLayout(activity)

        command_bar = QHBoxLayout()
        command_bar.setSpacing(10)

        self.input = QLineEdit()
        self.input.setObjectName("commandInput")
        self.input.setPlaceholderText(
            "Digite uma mensagem ou comando para o Atlas..."
        )
        self.input.returnPressed.connect(self.send_command)

        self.mic_button = QPushButton("Usar microfone")
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

        hint = QLabel(
            "Pressione Enter para enviar  •  "
            "Os comandos são processados pelo núcleo local do Atlas"
        )
        hint.setObjectName("commandHint")
        layout.addWidget(hint)
        return frame

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

    def send_command(self) -> None:
        command = self.input.text().strip()

        if not command or self.processing or self.listening:
            return

        self.input.clear()
        self.process_command(command)

    def process_command(self, command: str) -> None:
        if self.processing:
            return

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
            command = self.speech.listen("Ouvindo seu comando...")

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
        colors = {
            "ONLINE": ("#157347", "#E9F7EF", "#B8E0C8"),
            "ESCUTA ATIVA": ("#036666", "#E8FAF8", "#A7DED8"),
            "OUVINDO": ("#9A6700", "#FFF8E6", "#F3D48A"),
            "EXECUTANDO": ("#1D4ED8", "#EEF4FF", "#BBD0FF"),
            "PROCESSANDO": ("#1D4ED8", "#EEF4FF", "#BBD0FF"),
            "FALANDO": ("#6D28D9", "#F4F0FF", "#D8C7FF"),
            "CONCLUÍDO": ("#157347", "#E9F7EF", "#B8E0C8"),
            "CANCELANDO": ("#A14D00", "#FFF4E8", "#F4C99D"),
            "CANCELADO": ("#A14D00", "#FFF4E8", "#F4C99D"),
            "INTERROMPIDO": ("#A14D00", "#FFF4E8", "#F4C99D"),
            "NÃO ENTENDI": ("#A14D00", "#FFF4E8", "#F4C99D"),
            "ATENÇÃO": ("#A14D00", "#FFF4E8", "#F4C99D"),
            "ERRO": ("#B42318", "#FFF0F0", "#F3B8B4"),
        }
        foreground, background, border = colors.get(
            normalized,
            ("#475467", "#F2F4F7", "#D0D5DD"),
        )
        self.status_label.setText(f"●  {normalized}")
        self.status_label.setStyleSheet(
            "QLabel#status {"
            f"color: {foreground};"
            f"background: {background};"
            f"border: 1px solid {border};"
            "border-radius: 11px;"
            "padding: 5px 11px;"
            "font-size: 10px;"
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
        self.resume_button.setEnabled(idle and self._resume_available)
        self.mic_button.setText(
            "Ouvindo..." if self.listening else "Usar microfone"
        )
        self.continuous_button.setText(
            "Desativar escuta" if continuous else "Escuta contínua"
        )

    def add_user_message(self, message: str) -> None:
        self._append_message(
            "VOCÊ",
            message,
            accent="#DBEAFE",
            background="#2563EB",
            foreground="#FFFFFF",
            align_right=True,
        )

    def add_atlas_message(self, message: str) -> None:
        self._append_message(
            ATLAS_NAME.upper(),
            message,
            accent="#2563EB",
            background="#F1F5F9",
            foreground="#1E293B",
        )

    def add_system_message(self, message: str) -> None:
        self._append_message(
            "SISTEMA",
            message,
            accent="#B45309",
            background="#FFF7ED",
            foreground="#78350F",
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
        bubble_width = "74%" if align_right else "82%"

        self.chat.append(
            f"<table align='{alignment}' width='{bubble_width}' "
            "cellspacing='0' cellpadding='10' "
            f"bgcolor='{background}'>"
            "<tr><td>"
            f"<span style='color:{accent}; font-size:10px; "
            f"font-weight:700;'>{safe_author}</span>"
            f"<span style='color:{accent}; font-size:9px;'>"
            f" &nbsp; {timestamp}</span><br>"
            f"<span style='color:{foreground}; font-size:13px;'>"
            f"{safe_message}</span>"
            "</td></tr></table>"
            "<div style='height:7px;'></div>"
        )
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event: QCloseEvent) -> None:
        self.service.cancel()
        self.continuous_listener.stop(wait=True, timeout=3.0)
        self.interruption_monitor.stop(wait=True, timeout=2.0)
        self.voice_session.unsubscribe(self._on_voice_state_changed)
        self.speech.disable_microphone()
        self.command_runner.close(cleanup=self.service.close)
        event.accept()

    @staticmethod
    def _stylesheet() -> str:
        return """
            QMainWindow, QWidget#root, QWidget#workspace {
                background: #F4F7FB;
            }
            QLabel {
                color: #1D2939;
                font-family: "Segoe UI";
            }
            QFrame#sidebar {
                background: #101C2E;
                border: none;
            }
            QLabel#logoBadge {
                background: #2F6FED;
                color: #FFFFFF;
                border-radius: 10px;
                font-family: "Segoe UI";
                font-size: 22px;
                font-weight: 800;
            }
            QLabel#sidebarBrand {
                color: #FFFFFF;
                font-size: 18px;
                font-weight: 750;
                letter-spacing: 2px;
            }
            QLabel#sidebarCaption {
                color: #8191A8;
                font-size: 8px;
                font-weight: 600;
                letter-spacing: 1px;
            }
            QFrame#sidebarDivider {
                color: #26364C;
                background: #26364C;
                border: none;
                max-height: 1px;
            }
            QLabel#sidebarSection {
                color: #718198;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
                margin-top: 4px;
            }
            QFrame#activeArea {
                background: #1B2B43;
                border: 1px solid #2C405C;
                border-radius: 9px;
            }
            QLabel#activeAreaMark {
                color: #5B8FF9;
                font-size: 9px;
            }
            QLabel#activeAreaText {
                color: #F8FAFC;
                font-size: 12px;
                font-weight: 650;
            }
            QFrame#operationCard {
                background: #16253A;
                border: 1px solid #263A55;
                border-radius: 10px;
            }
            QLabel#sideMetricCaption {
                color: #8191A8;
                font-size: 10px;
            }
            QLabel#sideMetricValue {
                color: #F8FAFC;
                font-size: 12px;
                font-weight: 650;
            }
            QLabel#resourceLabel {
                color: #A8B4C6;
                font-size: 9px;
                font-weight: 650;
            }
            QProgressBar#resourceBar {
                min-height: 5px;
                max-height: 5px;
                background: #26364C;
                border: none;
                border-radius: 2px;
            }
            QProgressBar#resourceBar::chunk {
                background: #4F7FE8;
                border-radius: 2px;
            }
            QLabel#localBadge {
                color: #77D6A3;
                font-size: 9px;
                font-weight: 700;
            }
            QLabel#versionLabel {
                color: #53647B;
                font-size: 8px;
                letter-spacing: 1px;
            }
            QFrame#topHeader {
                background: transparent;
                border: none;
            }
            QLabel#pageTitle {
                color: #172033;
                font-size: 24px;
                font-weight: 750;
            }
            QLabel#pageSubtitle {
                color: #667085;
                font-size: 11px;
            }
            QLabel#userName {
                color: #344054;
                font-size: 11px;
                font-weight: 650;
            }
            QFrame#conversationCard, QFrame#commandPanel {
                background: #FFFFFF;
                border: 1px solid #DCE3EC;
                border-radius: 12px;
            }
            QFrame#conversationHeader {
                background: #FFFFFF;
                border: none;
                border-bottom: 1px solid #E7ECF2;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#conversationTitle {
                color: #1D2939;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#sessionLabel {
                color: #157347;
                font-size: 10px;
                font-weight: 650;
            }
            QPushButton#headerButton,
            QPushButton#resumeButton {
                min-height: 14px;
                background: #F8FAFC;
                color: #344054;
                border: 1px solid #D0D8E4;
                border-radius: 7px;
                padding: 5px 9px;
                font-size: 9px;
            }
            QPushButton#headerButton:hover,
            QPushButton#resumeButton:hover {
                background: #EEF4FF;
                color: #1D4ED8;
                border-color: #AFC5F5;
            }
            QPushButton#resumeButton {
                background: #EEF4FF;
                color: #1D4ED8;
                border-color: #BBD0FF;
            }
            QTextEdit#chat {
                background: #FFFFFF;
                color: #1D2939;
                border: none;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                font-family: "Segoe UI";
                font-size: 13px;
                selection-background-color: #D7E5FF;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 4px 2px 4px 0;
            }
            QScrollBar::handle:vertical {
                background: #C9D2DF;
                border-radius: 4px;
                min-height: 32px;
            }
            QScrollBar::handle:vertical:hover {
                background: #AEBAC9;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            QLabel#activityMark {
                color: #2F6FED;
                font-size: 8px;
            }
            QLabel#activityText {
                color: #667085;
                font-size: 10px;
                font-weight: 550;
            }
            QLineEdit#commandInput {
                min-height: 22px;
                background: #F8FAFC;
                color: #172033;
                border: 1px solid #CCD6E3;
                border-radius: 9px;
                padding: 11px 13px;
                font-family: "Segoe UI";
                font-size: 12px;
            }
            QLineEdit#commandInput:focus {
                background: #FFFFFF;
                border: 1px solid #2F6FED;
            }
            QPushButton {
                min-height: 22px;
                border-radius: 9px;
                padding: 10px 16px;
                font-family: "Segoe UI";
                font-size: 11px;
                font-weight: 650;
            }
            QPushButton#primaryButton {
                background: #2F6FED;
                color: #FFFFFF;
                border: 1px solid #2F6FED;
            }
            QPushButton#primaryButton:hover {
                background: #245DCE;
                border-color: #245DCE;
            }
            QPushButton#secondaryButton {
                background: #FFFFFF;
                color: #344054;
                border: 1px solid #C9D3E0;
            }
            QPushButton#secondaryButton:hover {
                background: #F1F5F9;
                border-color: #AEBBCC;
            }
            QPushButton#cancelButton {
                min-height: 16px;
                background: transparent;
                color: #B42318;
                border: 1px solid #E5AAA5;
                padding: 5px 10px;
                font-size: 9px;
            }
            QPushButton#cancelButton:hover {
                background: #FFF1F0;
                border-color: #D47A73;
            }
            QPushButton:disabled {
                background: #F2F4F7;
                color: #98A2B3;
                border-color: #E4E7EC;
            }
            QLabel#commandHint {
                color: #98A2B3;
                font-size: 9px;
            }
        """
