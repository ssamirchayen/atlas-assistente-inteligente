from __future__ import annotations

import re
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import TYPE_CHECKING, Any, Callable

from atlas.core.config import ATLAS_NAME
from atlas.core.controller import AtlasController, WorkflowProgressSnapshot
from atlas.scheduler.worker import SchedulerWorker
from atlas.automation.url_intent import extract_direct_url_command
from atlas.vision.action_intent import extract_click_target
from atlas.vision.audit import VisionAuditTrail
from atlas.vision.control_intent import (
    StructuredControlRequest,
    extract_structured_control,
)
from atlas.vision.final_action import (
    FinalActionRequest,
    VisionConfirmationError,
    VisionConfirmationStore,
    extract_final_action_confirmation,
    extract_final_action_request,
)
from atlas.vision.uia_action_intent import (
    WindowsUIAActionRequest,
    extract_windows_uia_action,
)
from atlas.vision.analyzer import VisionAnalysisError
from atlas.vision.capture import ScreenCaptureError
from atlas.vision.dom_grounding import (
    BrowserDomMatch,
    find_browser_dom_match,
    locate_browser_dom_element,
)
from atlas.vision.formatter import (
    describe_grounding,
    format_analysis_for_user,
)
from atlas.vision.form_intent import (
    StructuredFormRequest,
    extract_structured_form,
    is_structured_form_attempt,
)
from atlas.vision.grounding_intent import extract_grounding_query
from atlas.vision.interaction_sequence import (
    StructuredInteractionSequence,
    extract_structured_sequence,
    is_structured_sequence_attempt,
)
from atlas.vision.qt_grounding import locate_qt_widget
from atlas.vision.intent import is_read_only_vision_command
from atlas.vision.text_input_intent import (
    StructuredTextInputRequest,
    extract_structured_text_input,
)
from atlas.vision.overlay import VisionOverlaySpec
from atlas.vision.option_select_intent import (
    StructuredContextualFormRequest,
    StructuredOptionSelectionRequest,
    extract_contextual_form,
    extract_structured_option_selection,
    is_contextual_form_attempt,
)
from atlas.vision.post_action import (
    PostActionVerification,
    verify_click_post_action,
    verify_control_state_post_action,
    verify_text_fill_post_action,
    verify_uia_post_action,
)
from atlas.vision.recovery import decide_recovery
from atlas.vision.uia_grounding import (
    WindowsUIAMatch,
    activate_windows_uia_match,
    find_windows_uia_match,
    inspect_uia_interaction_state,
    is_windows_uia_available,
    locate_windows_uia_element,
    perform_windows_uia_action,
    perform_windows_uia_text_fill,
)

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from atlas.core.kernel import AtlasKernel
    from atlas.session.models import (
        OperationalEvent,
        OperationalSession,
        SessionStatus,
    )
    from atlas.session.resumption import ResumptionPlan


@dataclass(frozen=True, slots=True)
class GuiCommandResult:
    """Resposta estruturada enviada pelo backend para a interface."""

    message: str
    source: str
    success: bool = True
    action_count: int = 0
    cancelled: bool = False
    should_close: bool = False
    reason_code: str | None = None
    overlay: VisionOverlaySpec | None = None
    context_token: str | None = None
    requires_confirmation: bool = False
    confirmation_token: str | None = None


class SerialCommandRunner:
    """Executa todos os comandos na mesma thread persistente."""

    def __init__(
        self,
        handler: Callable[[str], GuiCommandResult],
    ) -> None:
        self._handler = handler
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="atlas-gui-command",
        )
        self._closed = False

    def submit(self, command: str) -> Future[GuiCommandResult]:
        if self._closed:
            raise RuntimeError("O executor de comandos já foi encerrado.")

        return self._executor.submit(self._handler, command)

    def submit_callable(
        self,
        callback: Callable[[], GuiCommandResult],
    ) -> Future[GuiCommandResult]:
        """Executa uma operação especial na mesma thread persistente."""

        if self._closed:
            raise RuntimeError("O executor de comandos já foi encerrado.")

        return self._executor.submit(callback)

    def close(self, cleanup: Callable[[], None] | None = None) -> None:
        if self._closed:
            return

        self._closed = True

        if cleanup is not None:
            self._executor.submit(cleanup)

        self._executor.shutdown(
            wait=False,
            cancel_futures=False,
        )


class AtlasGuiService:
    """Conecta a interface ao mesmo núcleo usado pelo modo principal."""

    def __init__(
        self,
        kernel: AtlasKernel | None = None,
        controller: AtlasController | None = None,
        *,
        enable_scheduler: bool = True,
        vision_audit: VisionAuditTrail | None = None,
    ) -> None:
        if kernel is None:
            from atlas.core.kernel import AtlasKernel

            kernel = AtlasKernel()

        self.kernel = kernel
        self.controller = controller or AtlasController(kernel)
        self.scheduler_worker = (
            SchedulerWorker(
                scheduler=self.kernel.scheduler,
                executor=lambda job: self.controller.execute(job.command),
            )
            if enable_scheduler
            else None
        )
        self._started = False
        self.vision_confirmation = VisionConfirmationStore()
        self.vision_audit = vision_audit or VisionAuditTrail(
            Path("data/vision/audit.jsonl")
        )

    def start(self) -> None:
        if self.scheduler_worker is None or self._started:
            return

        self.scheduler_worker.start()
        self._started = True

    def execute(self, command: str) -> GuiCommandResult:
        clean_command = command.strip()

        if not clean_command:
            return GuiCommandResult(
                message="Digite um comando para o Atlas.",
                source="system",
                success=False,
            )

        execution_command = self._strip_optional_wake_word(clean_command)

        if not execution_command:
            return GuiCommandResult(
                message="Pode dizer. O que você quer que eu faça?",
                source="system",
                success=False,
            )

        normalized = execution_command.lower()

        if normalized in {"sair", "fechar atlas", "encerrar atlas"}:
            return GuiCommandResult(
                message="Encerrando o Atlas. Até mais, Ssamir.",
                source="system",
                should_close=True,
            )

        if normalized in {
            "limpar contexto",
            "apagar contexto",
            "esquecer conversa",
        }:
            self.kernel.context.clear()
            return GuiCommandResult(
                message="O contexto da conversa foi apagado.",
                source="system",
            )

        self._save_last_command(clean_command)

        confirmation_token = extract_final_action_confirmation(
            execution_command
        )
        if confirmation_token is not None:
            return self._confirm_final_action(
                clean_command,
                confirmation_token,
            )

        final_action = extract_final_action_request(execution_command)
        if final_action is not None:
            return self._prepare_final_action(clean_command, final_action)

        control_request = extract_structured_control(execution_command)
        if control_request is not None:
            return self._execute_structured_control(
                clean_command,
                control_request,
            )

        # URLs HTTP(S) explícitas devem ser abertas pelo navegador controlado
        # antes do Router/Planner. Sem este guard, strings como
        # ``http://127.0.0.1:8765/...`` podem ser interpretadas como nome de
        # programa/atalho e perder pontuação importante da URL.
        direct_url = extract_direct_url_command(execution_command)
        if direct_url is not None:
            message = self.kernel.automation.browser.open_url(direct_url.url)
            success = not message.casefold().startswith("erro ao abrir")
            self._add_turn(clean_command, message)
            return GuiCommandResult(
                message=message,
                source="browser_url",
                success=success,
                action_count=1 if success else 0,
                reason_code=None if success else "browser_url_open_failed",
            )

        contextual_form = extract_contextual_form(execution_command)
        if contextual_form is not None:
            return self._execute_contextual_form(
                clean_command,
                contextual_form,
            )

        if is_contextual_form_attempt(execution_command):
            message = (
                "Não executei o fluxo contextual. A Etapa 12 exige campos "
                "e seleções explícitos, mantém todos os passos no mesmo "
                "contexto estrutural e não envia o formulário."
            )
            self._add_turn(clean_command, message)
            return GuiCommandResult(
                message=message,
                source="vision_contextual_form",
                success=False,
                reason_code="vision_contextual_form_not_safe",
            )

        option_selection = extract_structured_option_selection(
            execution_command
        )
        if option_selection is not None:
            return self._execute_structured_option_selection(
                clean_command,
                option_selection,
            )

        form_request = extract_structured_form(execution_command)
        if form_request is not None:
            return self._execute_structured_form(
                clean_command,
                form_request,
            )

        if is_structured_form_attempt(execution_command):
            message = (
                "Não preenchi o formulário. A Etapa 11 exige de dois a "
                "cinco campos explícitos, bloqueia campos sensíveis e não "
                "envia o formulário automaticamente."
            )
            self._add_turn(clean_command, message)
            return GuiCommandResult(
                message=message,
                source="vision_form",
                success=False,
                reason_code="vision_form_not_safe",
            )

        sequence = extract_structured_sequence(execution_command)
        if sequence is not None:
            return self._execute_structured_sequence(
                clean_command,
                sequence,
            )

        if is_structured_sequence_attempt(execution_command):
            message = (
                "Não executei a sequência. A Etapa 10 aceita no máximo "
                "três passos estruturais e bloqueia ações sensíveis em "
                "cadeia. Execute a etapa crítica em um comando separado."
            )
            self._add_turn(clean_command, message)
            return GuiCommandResult(
                message=message,
                source="vision_sequence",
                success=False,
                reason_code="vision_sequence_not_safe",
            )

        text_input = extract_structured_text_input(execution_command)
        if text_input is not None:
            return self._execute_structured_text_input(
                clean_command,
                text_input,
            )

        uia_action = extract_windows_uia_action(execution_command)
        if uia_action is not None:
            if self._supports_windows_uia_actions():
                return self._execute_windows_uia_action(
                    clean_command,
                    uia_action,
                )

            message = (
                "Reconheci a ação de interface do Windows, mas o "
                "Windows UI Automation não está disponível neste momento. "
                "Não encaminhei o comando para abertura de programas para "
                "evitar executar o alvo errado."
            )
            self._add_turn(clean_command, message)
            return GuiCommandResult(
                message=message,
                source="vision_action_uia",
                success=False,
                reason_code="uia_runtime_unavailable",
            )

        click_target = extract_click_target(
            execution_command
        )

        if (
            click_target
            and self._supports_controlled_dom_click()
        ):
            overlay: VisionOverlaySpec | None = None
            action_performed = False
            reason_code: str | None = None
            result_source = "vision_click_dom"

            try:
                capture = (
                    self.kernel.vision.capture_service.capture_primary_screen()
                )

                match = find_browser_dom_match(
                    self.kernel.automation.browser,
                    click_target,
                    screen_width=capture.width,
                    screen_height=capture.height,
                )

                if not getattr(
                    self.kernel.vision,
                    "keep_captures",
                    False,
                ):
                    capture.path.unlink(missing_ok=True)

                if match is None:
                    uia_match = find_windows_uia_match(
                        click_target,
                        screen_width=capture.width,
                        screen_height=capture.height,
                    )

                    if uia_match is None:
                        message = (
                            "Não executei o clique. Não consegui confirmar "
                            "o elemento nem pelo DOM do navegador nem pelo "
                            "Windows UI Automation da aplicação ativa. "
                            "O Atlas não usa coordenadas do modelo visual "
                            "como fallback para ações."
                        )
                        success = False
                        reason_code = "vision_click_target_not_confirmed"
                    elif uia_match.confidence < 0.85:
                        overlay = VisionOverlaySpec.from_grounding(
                            uia_match.grounding
                        )
                        message = (
                            "Não executei a ação Windows porque a confiança "
                            f"do UI Automation foi de {uia_match.confidence:.0%}. "
                            "O mínimo para ação controlada é 85%."
                        )
                        success = False
                        reason_code = "vision_uia_click_low_confidence"
                        result_source = "vision_click_uia"
                    else:
                        result_source = "vision_click_uia"
                        overlay = VisionOverlaySpec.from_grounding(
                            uia_match.grounding
                        )
                        before_state = inspect_uia_interaction_state(
                            uia_match
                        )
                        activated = activate_windows_uia_match(uia_match)

                        if activated:
                            action_performed = True
                            verification = self._verify_uia_post_action(
                                uia_match,
                                before_state,
                            )
                            label = (
                                uia_match.grounding.element.label
                                if uia_match.grounding.element is not None
                                else click_target
                            )

                            if verification.verified:
                                message = (
                                    f"Ativei {label} pelo Windows UI "
                                    f"Automation com {uia_match.confidence:.0%} "
                                    "de confiança e confirmei o resultado: "
                                    f"{verification.user_summary}."
                                )
                                success = True
                                reason_code = verification.reason_code
                            else:
                                message = (
                                    f"Executei a ação estrutural em {label} "
                                    "pelo Windows UI Automation, mas não "
                                    "marquei o resultado como confirmado porque "
                                    f"{verification.user_summary}. Não repeti "
                                    "a ação para evitar duplicidade."
                                )
                                success = False
                                reason_code = verification.reason_code
                        else:
                            message = (
                                "Localizei o elemento pelo Windows UI "
                                "Automation, mas não executei a ação porque "
                                "a janela deixou de ser a aplicação ativa, "
                                "o elemento perdeu a validade ou não expôs "
                                "um padrão UIA seguro para ativação."
                            )
                            success = False
                            reason_code = "vision_uia_click_not_executed"
                elif match.confidence < 0.85:
                    message = (
                        "Não executei o clique porque a confiança do "
                        f"grounding foi de {match.confidence:.0%}. "
                        "O mínimo para ação controlada é 85%."
                    )
                    overlay = VisionOverlaySpec.from_grounding(
                        match.grounding
                    )
                    success = False
                    reason_code = "vision_click_low_confidence"
                else:
                    overlay = VisionOverlaySpec.from_grounding(
                        match.grounding
                    )
                    before_state = self._inspect_click_state(match)
                    clicked = (
                        self.kernel.automation.browser
                        .click_interactive_element(
                            match.dom_index,
                            fingerprint=(
                                match.click_fingerprint()
                            ),
                            semantic_kind=(
                                match.semantic_kind
                            ),
                        )
                    )

                    retried = False

                    if not clicked:
                        retry_match = find_browser_dom_match(
                            self.kernel.automation.browser,
                            click_target,
                            screen_width=capture.width,
                            screen_height=capture.height,
                        )

                        if (
                            retry_match is not None
                            and retry_match.confidence >= 0.85
                        ):
                            retried = True
                            match = retry_match
                            overlay = (
                                VisionOverlaySpec.from_grounding(
                                    retry_match.grounding
                                )
                            )
                            before_state = self._inspect_click_state(
                                retry_match
                            )
                            clicked = (
                                self.kernel.automation.browser
                                .click_interactive_element(
                                    retry_match.dom_index,
                                    fingerprint=(
                                        retry_match.click_fingerprint()
                                    ),
                                    semantic_kind=(
                                        retry_match.semantic_kind
                                    ),
                                )
                            )

                    if clicked:
                        action_performed = True
                        verification = self._verify_click_post_action(
                            match,
                            before_state,
                        )
                        label = (
                            match.grounding.element.label
                            if match.grounding.element is not None
                            else click_target
                        )
                        recovery = (
                            " após revalidar o DOM"
                            if retried
                            else ""
                        )

                        if verification.verified:
                            message = (
                                f"Cliquei em {label} pelo DOM{recovery} "
                                f"com {match.confidence:.0%} de confiança "
                                "e confirmei o resultado: "
                                f"{verification.user_summary}."
                            )
                            success = True
                            reason_code = verification.reason_code
                        else:
                            message = (
                                f"Executei um clique em {label} pelo DOM"
                                f"{recovery}, mas não marquei a ação como "
                                "confirmada porque "
                                f"{verification.user_summary}. "
                                "Não repeti o clique para evitar uma ação "
                                "duplicada."
                            )
                            success = False
                            reason_code = verification.reason_code
                    else:
                        message = (
                            "Localizei o elemento, revalidei o DOM, mas "
                            "não executei o clique porque a página perdeu "
                            "o foco ou o elemento continuou instável."
                        )
                        success = False
                        reason_code = "vision_click_not_executed"

            except ScreenCaptureError as exc:
                _LOGGER.warning(
                    "Falha no clique controlado: %s",
                    exc,
                )
                message = (
                    "Não executei o clique porque não consegui validar "
                    f"a tela atual. {exc}"
                )
                success = False
                reason_code = "vision_click_screen_validation_failed"

            self._add_turn(
                clean_command,
                message,
            )
            return GuiCommandResult(
                message=message,
                source=result_source,
                success=success,
                action_count=1 if action_performed else 0,
                reason_code=reason_code,
                overlay=overlay,
            )

        priority_result = self.kernel.router.route_priority(execution_command)

        if priority_result.handled:
            self._add_turn(clean_command, priority_result.message)
            return GuiCommandResult(
                message=priority_result.message,
                source="skill",
            )

        grounding_query = extract_grounding_query(execution_command)

        if grounding_query:
            overlay: VisionOverlaySpec | None = None

            try:
                capture = (
                    self.kernel.vision.capture_service.capture_primary_screen()
                )

                qt_grounding = locate_qt_widget(
                    grounding_query,
                    screen_width=capture.width,
                    screen_height=capture.height,
                )

                dom_grounding = locate_browser_dom_element(
                    self.kernel.automation.browser,
                    grounding_query,
                    screen_width=capture.width,
                    screen_height=capture.height,
                )

                uia_grounding = locate_windows_uia_element(
                    grounding_query,
                    screen_width=capture.width,
                    screen_height=capture.height,
                )

                if not self.kernel.vision.keep_captures:
                    capture.path.unlink(missing_ok=True)

                # A chamada Qt permanece primeiro por compatibilidade, mas a
                # seleção prioriza superfícies estruturais externas quando há
                # uma aplicação aberta atrás do Atlas. Isso evita que termos
                # genéricos como "campo de texto" sejam confundidos com um
                # rótulo da própria GUI apenas porque o usuário digitou o
                # comando nela.
                prefers_atlas_gui = any(
                    phrase in execution_command.lower()
                    for phrase in (
                        "no atlas",
                        "na interface do atlas",
                        "na janela do atlas",
                    )
                )

                selected_grounding = None
                if prefers_atlas_gui and qt_grounding is not None:
                    if qt_grounding.found:
                        selected_grounding = qt_grounding

                if selected_grounding is None:
                    if dom_grounding is not None and dom_grounding.found:
                        selected_grounding = dom_grounding
                    elif uia_grounding is not None and uia_grounding.found:
                        selected_grounding = uia_grounding
                    elif qt_grounding is not None and qt_grounding.found:
                        selected_grounding = qt_grounding

                if selected_grounding is not None:
                    message = describe_grounding(
                        selected_grounding,
                        width=capture.width,
                        height=capture.height,
                    )
                    overlay = VisionOverlaySpec.from_grounding(
                        selected_grounding
                    )
                    success = True
                else:
                    observation, grounding = (
                        self.kernel.vision.locate_on_screen(
                            grounding_query
                        )
                    )
                    message = describe_grounding(
                        grounding,
                        width=observation.capture.width,
                        height=observation.capture.height,
                    )
                    overlay = VisionOverlaySpec.from_grounding(
                        grounding
                    )
                    success = grounding.found

            except (ScreenCaptureError, VisionAnalysisError) as exc:
                _LOGGER.warning(
                    "Falha no grounding visual pela GUI: %s",
                    exc,
                )
                message = (
                    "Não consegui localizar esse elemento agora. "
                    f"{exc}"
                )
                success = False

            self._add_turn(clean_command, message)
            return GuiCommandResult(
                message=message,
                source="vision_grounding",
                success=success,
                overlay=overlay,
            )

        # Vision read-only deve ser resolvido antes do Controller/Planner.
        # A GUI usa AtlasGuiService diretamente, então este guard é
        # necessário além daquele presente em AtlasApp.
        if is_read_only_vision_command(execution_command):
            try:
                observation = self.kernel.vision.observe_screen(
                    execution_command
                )
                message = format_analysis_for_user(
                    observation.analysis
                )
                success = True
            except (ScreenCaptureError, VisionAnalysisError) as exc:
                _LOGGER.warning(
                    "Falha no Atlas Vision pela GUI: %s",
                    exc,
                )
                message = (
                    "Não consegui analisar a tela agora. "
                    f"{exc}"
                )
                success = False

            self._add_turn(clean_command, message)
            return GuiCommandResult(
                message=message,
                source="vision",
                success=success,
            )

        actions, results = self.controller.execute(execution_command)

        if results:
            message = " ".join(str(result) for result in results)
            cancelled = any(
                result.error_code == "workflow_cancelled"
                for result in results
            )
            success = all(result.success for result in results)
            self._add_turn(clean_command, message)

            return GuiCommandResult(
                message=message,
                source=("scheduler" if not actions else "workflow"),
                success=success,
                action_count=len(actions),
                cancelled=cancelled,
            )

        route_result = self.kernel.router.route(execution_command)

        if route_result.handled:
            self._add_turn(clean_command, route_result.message)
            return GuiCommandResult(
                message=route_result.message,
                source="skill",
            )

        memory_context = self.kernel.memory.context(execution_command)
        conversation_context = self.kernel.context.get_recent_history()
        combined_context = self._combine_contexts(
            memory_context,
            conversation_context,
        )
        answer = self.kernel.brain.respond(
            execution_command,
            combined_context,
        )
        self._add_turn(clean_command, answer)

        return GuiCommandResult(
            message=answer,
            source="brain",
        )

    def cancel(
        self,
        *,
        reason: str = "Cancelado pela interface",
        requested_by: str = "Ssamir",
    ) -> bool:
        return self.controller.cancel_active_workflow(
            reason=reason,
            requested_by=requested_by,
        )

    def workflow_snapshot(self) -> WorkflowProgressSnapshot | None:
        """Expõe somente os dados necessários à observabilidade da API."""

        return self.controller.workflow_snapshot()

    def list_operational_sessions(
        self,
        *,
        status: SessionStatus | None = None,
        limit: int = 20,
    ) -> tuple[OperationalSession, ...]:
        """Lista sessões persistidas usando a fonte oficial do núcleo."""

        return self.kernel.session.list_sessions(
            status=status,
            limit=limit,
        )

    def get_operational_timeline(
        self,
        *,
        session_id: str | None = None,
        limit: int = 100,
        after_sequence: int | None = None,
    ) -> tuple[OperationalEvent, ...]:
        """Consulta a linha do tempo cronológica da sessão."""

        return self.kernel.session.get_timeline(
            session_id=session_id,
            limit=limit,
            after_sequence=after_sequence,
        )

    def get_resumption_plan(self) -> ResumptionPlan:
        """Expõe o plano imutável produzido pelo Controller."""

        return self.controller.get_resumption_plan()

    def resume_interrupted_workflow(
        self,
        *,
        confirmation_token: str | None = None,
    ) -> GuiCommandResult:
        """Executa uma retomada já validada e formata o resultado para UI."""

        actions, results = self.controller.resume_interrupted_workflow(
            confirmation_token=confirmation_token,
        )

        if not results:
            return GuiCommandResult(
                message="A retomada não produziu nenhum resultado.",
                source="resumption",
                success=False,
                reason_code="workflow_resume_empty_result",
            )

        message = " ".join(str(result) for result in results)
        success = all(result.success for result in results)
        reason_code = next(
            (
                result.error_code
                for result in results
                if result.error_code is not None
            ),
            None,
        )
        return GuiCommandResult(
            message=message,
            source="resumption",
            success=success,
            action_count=len(actions),
            cancelled=any(
                result.error_code == "workflow_cancelled"
                for result in results
            ),
            reason_code=reason_code,
        )

    def close(self) -> None:
        confirmation_store = getattr(self, "vision_confirmation", None)
        revoke_all = getattr(confirmation_store, "revoke_all", None)
        if callable(revoke_all):
            revoke_all()

        if self.scheduler_worker is not None and self._started:
            self.scheduler_worker.stop()
            self._started = False

        memory = getattr(self.kernel, "memory", None)
        close_memory = getattr(memory, "close", None)

        if callable(close_memory):
            close_memory()

        automation = getattr(self.kernel, "automation", None)
        close_automation = getattr(automation, "close", None)

        if callable(close_automation):
            close_automation()

    def _save_last_command(self, command: str) -> None:
        session = getattr(self.kernel, "session", None)
        save_last_command = getattr(session, "save_last_command", None)

        if callable(save_last_command):
            save_last_command(command)

    def _add_turn(self, command: str, response: str) -> None:
        self.kernel.context.add_turn(command, response)
        self._capture_user_memory(command)

    def _capture_user_memory(self, command: str) -> None:
        auto_memory = getattr(self.kernel, "auto_memory", None)
        capture = getattr(auto_memory, "capture", None)

        if not callable(capture):
            return

        try:
            capture(command)
        except Exception:
            _LOGGER.exception(
                "Falha não bloqueante ao capturar memória automática"
            )

    def _audit_vision_result(
        self,
        operation: str,
        result: GuiCommandResult,
        started_at: float,
    ) -> None:
        audit = getattr(self, "vision_audit", None)
        record = getattr(audit, "record", None)
        if not callable(record):
            return

        try:
            record(
                operation=operation,
                success=result.success,
                reason_code=result.reason_code,
                action_count=result.action_count,
                duration_ms=round((perf_counter() - started_at) * 1000),
                context_token=result.context_token,
            )
        except Exception:
            _LOGGER.exception("Falha não bloqueante na auditoria Vision")

    @staticmethod
    def _combine_contexts(*contexts: Any) -> str:
        return "\n\n".join(
            str(context).strip()
            for context in contexts
            if context and str(context).strip()
        )

    def _execute_structured_control(
        self,
        clean_command: str,
        request: StructuredControlRequest,
    ) -> GuiCommandResult:
        """Altera checkbox/radio/switch com pós-verificação e rollback."""

        started_at = perf_counter()
        overlay: VisionOverlaySpec | None = None
        context_token: str | None = None
        action_count = 0

        try:
            capture = self.kernel.vision.capture_service.capture_primary_screen()
            browser = self.kernel.automation.browser
            match = find_browser_dom_match(
                browser,
                request.target,
                screen_width=capture.width,
                screen_height=capture.height,
            )

            if not getattr(self.kernel.vision, "keep_captures", False):
                capture.path.unlink(missing_ok=True)

            if match is None and self._supports_windows_uia_actions():
                result = self._execute_windows_uia_action(
                    clean_command,
                    WindowsUIAActionRequest(
                        action=request.action,
                        target=request.target,
                    ),
                )
                self._audit_vision_result("control_state_uia", result, started_at)
                return result

            if match is None:
                message = (
                    "Não alterei o controle porque ele não foi confirmado "
                    "pelo DOM ou pelo Windows UI Automation."
                )
                success = False
                reason_code = "vision_control_target_not_confirmed"
            elif match.confidence < 0.85:
                overlay = VisionOverlaySpec.from_grounding(match.grounding)
                message = (
                    "Não alterei o controle porque a confiança estrutural "
                    f"foi de {match.confidence:.0%}. O mínimo é 85%."
                )
                success = False
                reason_code = "vision_control_dom_low_confidence"
            else:
                overlay = VisionOverlaySpec.from_grounding(match.grounding)
                context_token = browser.get_structural_context_token()
                before_state = browser.inspect_interaction_state(
                    match.dom_index,
                    fingerprint=match.click_fingerprint(),
                    semantic_kind=match.semantic_kind,
                )
                before_target = (
                    before_state.get("target")
                    if isinstance(before_state, dict)
                    else None
                )
                if not isinstance(before_target, dict):
                    message = "Não consegui revalidar o controle antes da ação."
                    success = False
                    reason_code = "vision_control_state_unavailable"
                else:
                    input_type = str(before_target.get("type", "")).casefold()
                    role = str(before_target.get("role", "")).casefold()
                    if input_type not in {"checkbox", "radio"} and role not in {
                        "checkbox",
                        "radio",
                        "switch",
                    }:
                        message = (
                            "O alvo localizado não é checkbox, radio ou switch "
                            "estruturalmente verificável."
                        )
                        success = False
                        reason_code = "vision_control_type_not_allowed"
                    elif bool(before_target.get("disabled")):
                        message = "O controle está desabilitado e não foi alterado."
                        success = False
                        reason_code = "vision_control_disabled"
                    else:
                        previous_state = before_target.get("checked")
                        changed = browser.set_interactive_control_state(
                            match.dom_index,
                            request.desired_state,
                            fingerprint=match.click_fingerprint(),
                            semantic_kind=match.semantic_kind,
                        )
                        if not changed:
                            message = (
                                "O controle foi localizado, mas a alteração "
                                "estrutural não pôde ser executada."
                            )
                            success = False
                            reason_code = "vision_control_not_executed"
                        else:
                            action_count = (
                                0
                                if isinstance(previous_state, bool)
                                and previous_state is request.desired_state
                                else 1
                            )
                            after_state = browser.inspect_interaction_state(
                                match.dom_index,
                                fingerprint=match.click_fingerprint(),
                                semantic_kind=match.semantic_kind,
                            )
                            verification = verify_control_state_post_action(
                                after_state,
                                desired_state=request.desired_state,
                            )
                            success = verification.verified
                            reason_code = verification.reason_code
                            if success:
                                message = (
                                    "Atualizei o controle estrutural e confirmei "
                                    f"o resultado: {verification.user_summary}."
                                )
                            else:
                                recovery = decide_recovery(
                                    action_performed=action_count > 0,
                                    verified=False,
                                    reversible=isinstance(previous_state, bool),
                                    attempts=1,
                                )
                                rolled_back = False
                                if recovery.rollback_allowed:
                                    rolled_back = browser.set_interactive_control_state(
                                        match.dom_index,
                                        bool(previous_state),
                                        fingerprint=match.click_fingerprint(),
                                        semantic_kind=match.semantic_kind,
                                    )
                                    if rolled_back:
                                        action_count += 1
                                reason_code = (
                                    "vision_control_not_verified_rolled_back"
                                    if rolled_back
                                    else verification.reason_code
                                )
                                message = (
                                    "A alteração não pôde ser confirmada. "
                                    + (
                                        "Restaurei o estado anterior e não repeti."
                                        if rolled_back
                                        else "Não repeti a ação para evitar duplicidade."
                                    )
                                )

        except ScreenCaptureError as exc:
            message = f"Não alterei o controle porque a tela falhou: {exc}"
            success = False
            reason_code = "vision_control_screen_validation_failed"

        self._add_turn(clean_command, message)
        result = GuiCommandResult(
            message=message,
            source="vision_control_state",
            success=success,
            action_count=action_count,
            reason_code=reason_code,
            overlay=overlay,
            context_token=context_token,
        )
        self._audit_vision_result("control_state", result, started_at)
        return result

    def _prepare_final_action(
        self,
        clean_command: str,
        request: FinalActionRequest,
    ) -> GuiCommandResult:
        """Prepara, mas nunca executa, uma ação final sem confirmação."""

        started_at = perf_counter()
        overlay: VisionOverlaySpec | None = None
        context_token: str | None = None

        try:
            capture = self.kernel.vision.capture_service.capture_primary_screen()
            browser = self.kernel.automation.browser
            match = find_browser_dom_match(
                browser,
                request.target,
                screen_width=capture.width,
                screen_height=capture.height,
            )
            if not getattr(self.kernel.vision, "keep_captures", False):
                capture.path.unlink(missing_ok=True)

            if match is None or match.confidence < 0.90:
                message = (
                    "Não preparei a ação final porque o botão de envio não "
                    "foi confirmado pelo DOM com confiança mínima de 90%."
                )
                result = GuiCommandResult(
                    message=message,
                    source="vision_final_action",
                    success=False,
                    reason_code="vision_final_target_not_confirmed",
                )
            else:
                overlay = VisionOverlaySpec.from_grounding(match.grounding)
                context_token = browser.get_structural_context_token()
                state = browser.inspect_interaction_state(
                    match.dom_index,
                    fingerprint=match.click_fingerprint(),
                    semantic_kind="button",
                )
                target = state.get("target") if isinstance(state, dict) else None
                tag = str(target.get("tag", "")).casefold() if isinstance(target, dict) else ""
                role = str(target.get("role", "")).casefold() if isinstance(target, dict) else ""
                input_type = str(target.get("type", "")).casefold() if isinstance(target, dict) else ""
                is_button = (
                    tag == "button"
                    or role == "button"
                    or (tag == "input" and input_type in {"button", "submit"})
                )
                if not context_token or not is_button or bool(target.get("disabled")):
                    message = (
                        "Não preparei a ação final porque o alvo não é um "
                        "botão estrutural habilitado na página atual."
                    )
                    result = GuiCommandResult(
                        message=message,
                        source="vision_final_action",
                        success=False,
                        reason_code="vision_final_control_not_allowed",
                        overlay=overlay,
                        context_token=context_token,
                    )
                else:
                    pending = self.vision_confirmation.prepare(
                        target=request.target,
                        action=request.action,
                        context_token=context_token,
                        dom_index=match.dom_index,
                        fingerprint=match.click_fingerprint(),
                    )
                    message = (
                        "A ação final está preparada, mas ainda não foi "
                        "executada. Para confirmar nesta mesma página, digite: "
                        f"CONFIRMAR VISÃO {pending.token}"
                    )
                    result = GuiCommandResult(
                        message=message,
                        source="vision_final_action",
                        success=True,
                        reason_code="vision_final_confirmation_required",
                        overlay=overlay,
                        context_token=context_token,
                        requires_confirmation=True,
                        confirmation_token=pending.token,
                    )
        except ScreenCaptureError as exc:
            result = GuiCommandResult(
                message=f"Não preparei a ação final porque a tela falhou: {exc}",
                source="vision_final_action",
                success=False,
                reason_code="vision_final_screen_validation_failed",
            )

        self._add_turn(clean_command, result.message)
        self._audit_vision_result("final_action_prepare", result, started_at)
        return result

    def _confirm_final_action(
        self,
        clean_command: str,
        token: str,
    ) -> GuiCommandResult:
        """Consome confirmação uma vez, revalida contexto e ativa o botão."""

        started_at = perf_counter()
        browser = self.kernel.automation.browser

        try:
            pending = self.vision_confirmation.consume(token)
        except VisionConfirmationError as exc:
            result = GuiCommandResult(
                message=str(exc),
                source="vision_final_action",
                success=False,
                reason_code="vision_final_confirmation_invalid",
            )
        else:
            context_token = browser.get_structural_context_token()
            if context_token != pending.context_token:
                result = GuiCommandResult(
                    message=(
                        "A página/aba mudou depois da preparação. Cancelei a "
                        "confirmação e nenhuma ação final foi executada."
                    ),
                    source="vision_final_action",
                    success=False,
                    reason_code="vision_final_context_changed",
                    context_token=context_token,
                )
            else:
                fingerprint = pending.fingerprint_dict()
                before_state = browser.inspect_interaction_state(
                    pending.dom_index,
                    fingerprint=fingerprint,
                    semantic_kind="button",
                )
                activated = browser.activate_final_control(
                    pending.dom_index,
                    fingerprint=fingerprint,
                    semantic_kind="button",
                )
                if not activated:
                    result = GuiCommandResult(
                        message=(
                            "A confirmação foi consumida, mas o botão final "
                            "não passou pela revalidação estrutural."
                        ),
                        source="vision_final_action",
                        success=False,
                        reason_code="vision_final_not_executed",
                        context_token=context_token,
                    )
                else:
                    after_state = browser.inspect_interaction_state(
                        pending.dom_index,
                        fingerprint=fingerprint,
                        semantic_kind="button",
                    )
                    verification = verify_click_post_action(
                        before_state,
                        after_state,
                        semantic_kind="button",
                    )
                    result = GuiCommandResult(
                        message=(
                            "Ação final executada e confirmada: "
                            f"{verification.user_summary}."
                            if verification.verified
                            else (
                                "A ação final foi enviada, mas a mudança não "
                                "pôde ser confirmada. Não repeti a ação."
                            )
                        ),
                        source="vision_final_action",
                        success=verification.verified,
                        action_count=1,
                        reason_code=verification.reason_code,
                        context_token=context_token,
                    )

        self._add_turn(clean_command, result.message)
        self._audit_vision_result("final_action_confirm", result, started_at)
        return result

    def _execute_contextual_form(
        self,
        clean_command: str,
        request: StructuredContextualFormRequest,
    ) -> GuiCommandResult:
        """Preenche e seleciona controles no mesmo contexto estrutural."""

        action_count = 0
        context_token: str | None = None
        last_overlay: VisionOverlaySpec | None = None
        operations = (*request.fields, *request.selections)

        for index, operation in enumerate(operations, start=1):
            if isinstance(operation, StructuredTextInputRequest):
                result = self._execute_structured_text_input(
                    clean_command,
                    operation,
                    record_turn=False,
                    required_context_token=context_token,
                )
                label = operation.target
            else:
                result = self._execute_structured_option_selection(
                    clean_command,
                    operation,
                    record_turn=False,
                    required_context_token=context_token,
                )
                label = operation.target

            action_count += result.action_count
            last_overlay = result.overlay or last_overlay

            if not result.success:
                message = (
                    f"Interrompi o fluxo contextual no passo {index} de "
                    f"{len(operations)} ({label}) porque ele não foi "
                    f"confirmado. {result.message} Nenhum envio, salvamento "
                    "ou confirmação final foi executado."
                )
                self._add_turn(clean_command, message)
                return GuiCommandResult(
                    message=message,
                    source="vision_contextual_form",
                    success=False,
                    action_count=action_count,
                    reason_code=result.reason_code
                    or "vision_contextual_form_step_failed",
                    overlay=last_overlay,
                    context_token=context_token or result.context_token,
                )

            if result.context_token is None:
                message = (
                    "Interrompi o fluxo contextual porque não consegui "
                    "vincular o passo confirmado à mesma página estrutural. "
                    "Nenhuma ação final foi executada."
                )
                self._add_turn(clean_command, message)
                return GuiCommandResult(
                    message=message,
                    source="vision_contextual_form",
                    success=False,
                    action_count=action_count,
                    reason_code="vision_contextual_context_unavailable",
                    overlay=last_overlay,
                )

            if (
                context_token is not None
                and result.context_token != context_token
            ):
                message = (
                    "Interrompi o fluxo contextual porque a página/aba mudou "
                    "entre os controles. Nenhuma ação final foi executada."
                )
                self._add_turn(clean_command, message)
                return GuiCommandResult(
                    message=message,
                    source="vision_contextual_form",
                    success=False,
                    action_count=action_count,
                    reason_code="vision_contextual_context_changed",
                    overlay=last_overlay,
                    context_token=context_token,
                )

            if context_token is None:
                context_token = result.context_token

        message = (
            f"Fluxo contextual concluído com {len(request.fields)} campos "
            f"preenchidos e {len(request.selections)} opções selecionadas, "
            "todos confirmados no mesmo contexto. Nenhum envio, salvamento "
            "ou confirmação final foi executado."
        )
        self._add_turn(clean_command, message)
        return GuiCommandResult(
            message=message,
            source="vision_contextual_form",
            success=True,
            action_count=action_count,
            reason_code="vision_contextual_form_verified",
            overlay=last_overlay,
            context_token=context_token,
        )

    def _execute_structured_option_selection(
        self,
        clean_command: str,
        request: StructuredOptionSelectionRequest,
        *,
        record_turn: bool = True,
        required_context_token: str | None = None,
    ) -> GuiCommandResult:
        """Seleciona uma opção DOM e confirma o valor selecionado."""

        overlay: VisionOverlaySpec | None = None
        action_performed = False
        context_token: str | None = None
        reason_code: str | None = None

        try:
            capture = self.kernel.vision.capture_service.capture_primary_screen()
            browser = self.kernel.automation.browser
            match = find_browser_dom_match(
                browser,
                request.target,
                screen_width=capture.width,
                screen_height=capture.height,
            )

            if not getattr(self.kernel.vision, "keep_captures", False):
                capture.path.unlink(missing_ok=True)

            if match is None:
                message = (
                    "Não selecionei a opção porque não encontrei um controle "
                    "DOM estrutural compatível. Nesta etapa não uso "
                    "coordenadas visuais como fallback para seleção."
                )
                success = False
                reason_code = "vision_select_target_not_confirmed"
            else:
                overlay = VisionOverlaySpec.from_grounding(match.grounding)
                context_token = browser.get_structural_context_token()

                if (
                    required_context_token is not None
                    and context_token != required_context_token
                ):
                    message = (
                        "Interrompi a seleção porque a aba/página mudou "
                        "durante o fluxo contextual."
                    )
                    success = False
                    reason_code = "vision_contextual_context_changed"
                elif match.confidence < 0.85:
                    message = (
                        "Não selecionei a opção porque a confiança do DOM foi "
                        f"de {match.confidence:.0%}. O mínimo é 85%."
                    )
                    success = False
                    reason_code = "vision_select_dom_low_confidence"
                else:
                    before_state = browser.inspect_interaction_state(
                        match.dom_index,
                        fingerprint=match.click_fingerprint(),
                        semantic_kind=match.semantic_kind,
                    )
                    before_target = (
                        before_state.get("target")
                        if isinstance(before_state, dict)
                        else None
                    )

                    if (
                        not isinstance(before_target, dict)
                        or str(before_target.get("tag", "")).casefold()
                        != "select"
                    ):
                        message = (
                            "Localizei o alvo, mas ele não é um seletor DOM "
                            "nativo validável nesta etapa."
                        )
                        success = False
                        reason_code = "vision_select_not_native_select"
                    else:
                        selected = browser.select_interactive_option(
                            match.dom_index,
                            request.option,
                            fingerprint=match.click_fingerprint(),
                            semantic_kind=match.semantic_kind,
                        )
                        if not selected:
                            message = (
                                "Localizei o seletor, mas não consegui "
                                "selecionar a opção solicitada de forma "
                                "estrutural."
                            )
                            success = False
                            reason_code = "vision_select_not_executed"
                        else:
                            action_performed = True
                            after_state = browser.inspect_interaction_state(
                                match.dom_index,
                                fingerprint=match.click_fingerprint(),
                                semantic_kind=match.semantic_kind,
                            )
                            after_target = (
                                after_state.get("target")
                                if isinstance(after_state, dict)
                                else None
                            )
                            requested = " ".join(
                                request.option.casefold().split()
                            )
                            selected_label = ""
                            selected_value = ""
                            if isinstance(after_target, dict):
                                selected_label = " ".join(
                                    str(
                                        after_target.get(
                                            "selected_label", ""
                                        )
                                    ).casefold().split()
                                )
                                selected_value = " ".join(
                                    str(
                                        after_target.get(
                                            "selected_value", ""
                                        )
                                    ).casefold().split()
                                )

                            verified = requested in {
                                selected_label,
                                selected_value,
                            }
                            if verified:
                                message = (
                                    f"Selecionei {request.option} em "
                                    f"{request.target} pelo DOM e confirmei "
                                    "o valor final do seletor."
                                )
                                success = True
                                reason_code = "vision_select_verified"
                            else:
                                message = (
                                    "Executei a seleção estrutural, mas não "
                                    "marquei o passo como confirmado porque "
                                    "o valor final não correspondeu à opção "
                                    "solicitada. Não repeti a ação."
                                )
                                success = False
                                reason_code = "vision_select_not_verified"

        except ScreenCaptureError as exc:
            message = (
                "Não selecionei a opção porque não consegui validar a tela "
                f"atual. {exc}"
            )
            success = False
            reason_code = "vision_select_screen_validation_failed"

        if record_turn:
            self._add_turn(clean_command, message)

        return GuiCommandResult(
            message=message,
            source="vision_select_dom",
            success=success,
            action_count=1 if action_performed else 0,
            reason_code=reason_code,
            overlay=overlay,
            context_token=context_token,
        )

    def _execute_structured_form(
        self,
        clean_command: str,
        request: StructuredFormRequest,
    ) -> GuiCommandResult:
        """Preenche vários campos no mesmo contexto, sem submeter."""

        action_count = 0
        context_token: str | None = None
        last_overlay: VisionOverlaySpec | None = None

        for index, field in enumerate(request.fields, start=1):
            result = self._execute_structured_text_input(
                clean_command,
                field,
                record_turn=False,
                required_context_token=context_token,
            )
            action_count += result.action_count
            last_overlay = result.overlay or last_overlay

            if not result.success:
                message = (
                    f"Interrompi o formulário no campo {index} de "
                    f"{len(request.fields)} ({field.target}) porque o passo "
                    f"não foi confirmado. {result.message} Nenhum envio ou "
                    "confirmação do formulário foi executado."
                )
                self._add_turn(clean_command, message)
                return GuiCommandResult(
                    message=message,
                    source="vision_form",
                    success=False,
                    action_count=action_count,
                    reason_code=result.reason_code
                    or "vision_form_field_failed",
                    overlay=last_overlay,
                    context_token=context_token or result.context_token,
                )

            if result.context_token is None:
                message = (
                    "Interrompi o formulário porque não consegui vincular "
                    "o campo confirmado a uma página ou janela estrutural. "
                    "Nenhum envio foi executado."
                )
                self._add_turn(clean_command, message)
                return GuiCommandResult(
                    message=message,
                    source="vision_form",
                    success=False,
                    action_count=action_count,
                    reason_code="vision_form_context_unavailable",
                    overlay=last_overlay,
                )

            if (
                context_token is not None
                and result.context_token != context_token
            ):
                message = (
                    "Interrompi o formulário porque o contexto estrutural "
                    "mudou entre os campos. Nenhum envio foi executado."
                )
                self._add_turn(clean_command, message)
                return GuiCommandResult(
                    message=message,
                    source="vision_form",
                    success=False,
                    action_count=action_count,
                    reason_code="vision_form_context_changed",
                    overlay=last_overlay,
                    context_token=context_token,
                )

            if context_token is None:
                context_token = result.context_token

        message = (
            f"Formulário preenchido com {len(request.fields)} campos "
            "estruturais, todos confirmados no mesmo contexto. Nenhum envio "
            "ou confirmação final foi executado."
        )
        self._add_turn(clean_command, message)
        return GuiCommandResult(
            message=message,
            source="vision_form",
            success=True,
            action_count=action_count,
            reason_code="vision_form_verified",
            overlay=last_overlay,
            context_token=context_token,
        )

    def _execute_structured_sequence(
        self,
        clean_command: str,
        sequence: StructuredInteractionSequence,
    ) -> GuiCommandResult:
        """Executa até três passos, parando na primeira falha verificável."""

        action_count = 0

        for index, step in enumerate(sequence.steps, start=1):
            result = self.execute(step)
            action_count += result.action_count

            if not result.success:
                message = (
                    f"Interrompi a sequência no passo {index} de "
                    f"{len(sequence.steps)} porque ele não foi confirmado. "
                    f"{result.message}"
                )
                self._save_last_command(clean_command)
                self._add_turn(clean_command, message)
                return GuiCommandResult(
                    message=message,
                    source="vision_sequence",
                    success=False,
                    action_count=action_count,
                    reason_code=result.reason_code
                    or "vision_sequence_step_failed",
                    overlay=result.overlay,
                )

        message = (
            f"Sequência concluída com {len(sequence.steps)} passos "
            "estruturais, todos confirmados."
        )
        self._save_last_command(clean_command)
        self._add_turn(clean_command, message)
        return GuiCommandResult(
            message=message,
            source="vision_sequence",
            success=True,
            action_count=action_count,
            reason_code="vision_sequence_verified",
        )

    def _execute_structured_text_input(
        self,
        clean_command: str,
        request: StructuredTextInputRequest,
        *,
        record_turn: bool = True,
        required_context_token: str | None = None,
    ) -> GuiCommandResult:
        """Preenche DOM ou UIA somente após grounding estrutural >= 85%.

        Na Etapa 11, ``required_context_token`` impede que uma sequência de
        campos continue em outra aba ou janela caso o contexto mude entre
        os passos.
        """

        overlay: VisionOverlaySpec | None = None
        action_performed = False
        reason_code: str | None = None
        context_token: str | None = None
        dom_match: BrowserDomMatch | None = None

        try:
            capture = self.kernel.vision.capture_service.capture_primary_screen()
            browser = self.kernel.automation.browser
            dom_match = find_browser_dom_match(
                browser,
                request.target,
                screen_width=capture.width,
                screen_height=capture.height,
            )

            if not getattr(self.kernel.vision, "keep_captures", False):
                capture.path.unlink(missing_ok=True)

            if dom_match is not None:
                overlay = VisionOverlaySpec.from_grounding(dom_match.grounding)
                context_token = browser.get_structural_context_token()
                if (
                    required_context_token is not None
                    and context_token != required_context_token
                ):
                    message = (
                        "Interrompi o preenchimento porque a aba/página "
                        "mudou durante o formulário. Nenhum novo campo foi "
                        "preenchido neste passo."
                    )
                    success = False
                    reason_code = "vision_form_context_changed"
                elif dom_match.confidence < 0.85:
                    message = (
                        "Não preenchi o campo porque a confiança do DOM foi "
                        f"de {dom_match.confidence:.0%}. O mínimo é 85%."
                    )
                    success = False
                    reason_code = "vision_fill_dom_low_confidence"
                else:
                    before_state = browser.inspect_interaction_state(
                        dom_match.dom_index,
                        fingerprint=dom_match.click_fingerprint(),
                        semantic_kind=dom_match.semantic_kind,
                    )
                    before_target = (
                        before_state.get("target")
                        if isinstance(before_state, dict)
                        else None
                    )
                    if (
                        isinstance(before_target, dict)
                        and str(before_target.get("type", "")).casefold()
                        == "password"
                    ):
                        message = (
                            "Não preenchi o campo porque ele foi identificado "
                            "como campo de senha."
                        )
                        success = False
                        reason_code = "vision_fill_password_blocked"
                    else:
                        filled = browser.fill_interactive_element(
                            dom_match.dom_index,
                            request.text,
                            fingerprint=dom_match.click_fingerprint(),
                            semantic_kind=dom_match.semantic_kind,
                        )
                        if not filled:
                            message = (
                                "Localizei o campo pelo DOM, mas não consegui "
                                "preenchê-lo por uma operação estrutural segura."
                            )
                            success = False
                            reason_code = "vision_fill_dom_not_executed"
                        else:
                            action_performed = True
                            after_state = browser.inspect_interaction_state(
                                dom_match.dom_index,
                                fingerprint=dom_match.click_fingerprint(),
                                semantic_kind=dom_match.semantic_kind,
                            )
                            verification = verify_text_fill_post_action(
                                before_state,
                                after_state,
                                expected_text=request.text,
                            )
                            success = verification.verified
                            reason_code = verification.reason_code
                            if success:
                                message = (
                                    "Preenchi o campo pelo DOM e confirmei o "
                                    f"resultado: {verification.user_summary}."
                                )
                            else:
                                message = (
                                    "Preenchi o campo estruturalmente, mas não "
                                    "confirmei o resultado porque "
                                    f"{verification.user_summary}. Não repeti "
                                    "a escrita para evitar duplicidade."
                                )
            else:
                uia_match = find_windows_uia_match(
                    request.target,
                    screen_width=capture.width,
                    screen_height=capture.height,
                )
                if uia_match is None:
                    message = (
                        "Não preenchi o campo. Não consegui confirmá-lo nem "
                        "pelo DOM nem pelo Windows UI Automation."
                    )
                    success = False
                    reason_code = "vision_fill_target_not_confirmed"
                else:
                    context_token = (
                        f"uia:{uia_match.process_id}:{uia_match.window_handle}"
                    )

                if (
                    uia_match is not None
                    and required_context_token is not None
                    and context_token != required_context_token
                ):
                    overlay = VisionOverlaySpec.from_grounding(
                        uia_match.grounding
                    )
                    message = (
                        "Interrompi o preenchimento porque a janela/aplicação "
                        "mudou durante o formulário. Nenhum novo campo foi "
                        "preenchido neste passo."
                    )
                    success = False
                    reason_code = "vision_form_context_changed"
                elif uia_match is not None and uia_match.confidence < 0.85:
                    overlay = VisionOverlaySpec.from_grounding(
                        uia_match.grounding
                    )
                    message = (
                        "Não preenchi o campo porque a confiança do Windows "
                        f"UI Automation foi de {uia_match.confidence:.0%}. "
                        "O mínimo é 85%."
                    )
                    success = False
                    reason_code = "vision_fill_uia_low_confidence"
                elif uia_match is not None:
                    overlay = VisionOverlaySpec.from_grounding(
                        uia_match.grounding
                    )
                    before_state = inspect_uia_interaction_state(uia_match)
                    before_target = (
                        before_state.get("target")
                        if isinstance(before_state, dict)
                        else None
                    )
                    if (
                        isinstance(before_target, dict)
                        and bool(before_target.get("is_password"))
                    ):
                        message = (
                            "Não preenchi o campo porque o UI Automation o "
                            "identificou como campo de senha."
                        )
                        success = False
                        reason_code = "vision_fill_password_blocked"
                    else:
                        result = perform_windows_uia_text_fill(
                            uia_match,
                            request.text,
                        )
                        if not result.executed:
                            message = (
                                "Localizei o campo pelo Windows UI Automation, "
                                "mas ele não expôs um padrão seguro para "
                                "preenchimento estrutural."
                            )
                            success = False
                            reason_code = result.reason_code
                        else:
                            action_performed = True
                            sleep(0.08)
                            after_state = inspect_uia_interaction_state(uia_match)
                            verification = verify_text_fill_post_action(
                                before_state,
                                after_state,
                                expected_text=request.text,
                            )
                            success = verification.verified
                            reason_code = verification.reason_code
                            if success:
                                message = (
                                    "Preenchi o campo pelo Windows UI "
                                    "Automation e confirmei o resultado: "
                                    f"{verification.user_summary}."
                                )
                            else:
                                message = (
                                    "Preenchi o campo via UI Automation, mas "
                                    "não confirmei o resultado porque "
                                    f"{verification.user_summary}. Não repeti "
                                    "a escrita para evitar duplicidade."
                                )

        except ScreenCaptureError as exc:
            _LOGGER.warning("Falha no preenchimento estrutural: %s", exc)
            message = (
                "Não preenchi o campo porque não consegui validar a tela "
                f"atual. {exc}"
            )
            success = False
            reason_code = "vision_fill_screen_validation_failed"

        if record_turn:
            self._add_turn(clean_command, message)
        return GuiCommandResult(
            message=message,
            source=(
                "vision_fill_dom"
                if dom_match is not None
                else "vision_fill_uia"
            ),
            success=success,
            action_count=1 if action_performed else 0,
            reason_code=reason_code,
            overlay=overlay,
            context_token=context_token,
        )

    def _execute_windows_uia_action(
        self,
        clean_command: str,
        request: WindowsUIAActionRequest,
    ) -> GuiCommandResult:
        """Executa uma única ação Windows avançada da Etapa 9."""

        overlay: VisionOverlaySpec | None = None
        action_performed = False
        reason_code: str | None = None

        try:
            capture = self.kernel.vision.capture_service.capture_primary_screen()
            match = None
            for delay_seconds in (0.0, 0.15, 0.30, 0.50):
                if delay_seconds:
                    sleep(delay_seconds)
                match = find_windows_uia_match(
                    request.target,
                    screen_width=capture.width,
                    screen_height=capture.height,
                )
                if match is not None:
                    break

            if not getattr(self.kernel.vision, "keep_captures", False):
                capture.path.unlink(missing_ok=True)

            if match is None:
                message = (
                    "Não executei a ação Windows. Não consegui confirmar "
                    "estruturalmente o controle solicitado pelo UI Automation. "
                    "O Atlas não usa coordenadas visuais como fallback para ações."
                )
                success = False
                reason_code = "vision_uia_action_target_not_confirmed"
            elif match.confidence < 0.85:
                overlay = VisionOverlaySpec.from_grounding(match.grounding)
                message = (
                    "Não executei a ação Windows porque a confiança do UI "
                    f"Automation foi de {match.confidence:.0%}. O mínimo para "
                    "ação controlada é 85%."
                )
                success = False
                reason_code = "vision_uia_action_low_confidence"
            else:
                overlay = VisionOverlaySpec.from_grounding(match.grounding)
                before_state = inspect_uia_interaction_state(match)
                result = perform_windows_uia_action(match, request.action)
                label = (
                    match.grounding.element.label
                    if match.grounding.element is not None
                    else request.target
                )

                if result.already_satisfied:
                    message = (
                        f"{label} já estava no estado solicitado. "
                        "Nenhuma ação adicional foi executada."
                    )
                    success = True
                    reason_code = result.reason_code
                elif not result.executed:
                    message = (
                        f"Localizei {label} pelo Windows UI Automation, mas não "
                        "executei a ação porque o controle não expôs um padrão "
                        "UIA compatível, perdeu a validade ou o handoff de foco "
                        "não pôde ser confirmado."
                    )
                    success = False
                    reason_code = result.reason_code
                else:
                    action_performed = True
                    verification = self._verify_uia_post_action(
                        match,
                        before_state,
                        expected_action=request.action,
                    )
                    if verification.verified:
                        message = (
                            f"Executei a ação em {label} pelo Windows UI "
                            f"Automation com {match.confidence:.0%} de confiança "
                            "e confirmei o resultado: "
                            f"{verification.user_summary}."
                        )
                        success = True
                        reason_code = verification.reason_code
                    else:
                        message = (
                            f"Executei a ação estrutural em {label}, mas não "
                            "marquei o resultado como confirmado porque "
                            f"{verification.user_summary}. Não repeti a ação "
                            "para evitar duplicidade."
                        )
                        success = False
                        reason_code = verification.reason_code

        except ScreenCaptureError as exc:
            _LOGGER.warning("Falha na ação Windows controlada: %s", exc)
            message = (
                "Não executei a ação Windows porque não consegui validar a "
                f"tela atual. {exc}"
            )
            success = False
            reason_code = "vision_uia_action_screen_validation_failed"

        self._add_turn(clean_command, message)
        return GuiCommandResult(
            message=message,
            source="vision_action_uia",
            success=success,
            action_count=1 if action_performed else 0,
            reason_code=reason_code,
            overlay=overlay,
        )

    def _inspect_click_state(
        self,
        match: BrowserDomMatch,
    ) -> dict[str, object] | None:
        browser = self.kernel.automation.browser
        return browser.inspect_interaction_state(
            match.dom_index,
            fingerprint=match.click_fingerprint(),
            semantic_kind=match.semantic_kind,
        )

    def _verify_click_post_action(
        self,
        match: BrowserDomMatch,
        before_state: dict[str, object] | None,
    ) -> PostActionVerification:
        """Observa somente leitura; nunca repete o clique nesta etapa."""

        browser = self.kernel.automation.browser
        verification = PostActionVerification(
            verified=False,
            reason_code="post_state_unavailable",
            evidence=(
                "não foi possível ler o estado da página após o clique",
            ),
        )

        for delay_seconds in (0.0, 0.12, 0.24, 0.36):
            if delay_seconds:
                sleep(delay_seconds)

            after_state = browser.inspect_interaction_state(
                match.dom_index,
                fingerprint=match.click_fingerprint(),
                semantic_kind=match.semantic_kind,
            )
            verification = verify_click_post_action(
                before_state,
                after_state,
                semantic_kind=match.semantic_kind,
            )

            if verification.verified:
                return verification

        return verification

    def _verify_uia_post_action(
        self,
        match: WindowsUIAMatch,
        before_state: dict[str, object] | None,
        *,
        expected_action: str = "",
    ) -> PostActionVerification:
        """Observa UIA pós-ação sem executar uma segunda interação."""

        verification = PostActionVerification(
            verified=False,
            reason_code="uia_post_state_unavailable",
            evidence=(
                "não foi possível ler o estado UIA após a ação",
            ),
        )

        for delay_seconds in (0.0, 0.12, 0.24, 0.36):
            if delay_seconds:
                sleep(delay_seconds)

            after_state = inspect_uia_interaction_state(match)
            verification = verify_uia_post_action(
                before_state,
                after_state,
                semantic_kind=match.semantic_kind,
                expected_action=expected_action,
            )
            if verification.verified:
                return verification

        return verification

    def _supports_windows_uia_actions(self) -> bool:
        """Confirma a infraestrutura mínima para ações UIA da Etapa 9."""

        vision = getattr(self.kernel, "vision", None)
        capture_service = getattr(vision, "capture_service", None)
        capture_ready = callable(
            getattr(capture_service, "capture_primary_screen", None)
        )
        return capture_ready and is_windows_uia_available()

    def _supports_controlled_dom_click(self) -> bool:
        """Mantém o contrato da Etapa 6 e delega ao guard híbrido.

        O nome histórico é preservado para compatibilidade com a suíte de
        regressão. Na Etapa 8, o guard aceita DOM ou Windows UI Automation,
        mas continua proibindo fallback visual por coordenadas para ações.
        """

        return self._supports_hybrid_structural_click()

    def _supports_hybrid_structural_click(self) -> bool:
        """Confirma DOM ou Windows UIA sem habilitar clique visual."""

        vision = getattr(self.kernel, "vision", None)
        capture_service = getattr(vision, "capture_service", None)
        if not callable(
            getattr(capture_service, "capture_primary_screen", None)
        ):
            return False

        automation = getattr(self.kernel, "automation", None)
        browser = getattr(automation, "browser", None)
        dom_ready = bool(
            browser is not None
            and callable(
                getattr(browser, "inspect_visible_interactive_elements", None)
            )
            and callable(
                getattr(browser, "click_interactive_element", None)
            )
            and callable(
                getattr(browser, "inspect_interaction_state", None)
            )
        )

        return dom_ready or is_windows_uia_available()

    @staticmethod
    def _strip_optional_wake_word(command: str) -> str:
        """Remove a palavra de ativação sem alterar o restante do texto."""

        wake_names = {
            ATLAS_NAME.strip(),
            "Atlas",
            "Atras",
        }
        wake_expression = "|".join(
            re.escape(name)
            for name in wake_names
            if name
        )
        prefix = (
            r"^\s*(?:(?:ok|ei|ol[áa]|al[oô]|por favor)\s+)?"
            rf"(?:{wake_expression})\b[\s,;:!?.-]*"
        )

        return re.sub(
            prefix,
            "",
            command,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
