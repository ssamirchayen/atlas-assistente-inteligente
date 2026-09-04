from __future__ import annotations

from atlas.automation.engine import AutomationEngine
from atlas.context.manager import ContextManager
from atlas.core.config import (
    ATLAS_RUNTIME_PROFILE,
    MIC_ENABLED,
    ROOT_DIR,
    VISION_CAPTURE_DIR,
    VISION_KEEP_CAPTURES,
    WAKE_WORD_ENABLED,
)
from atlas.core.lazy import LazyComponent, LazyComponentRegistry, LazyProxy
from atlas.core.runtime_profile import RuntimeProfileService
from atlas.core.resource_manager import ResourceManager
from atlas.memory.automatic import AutoMemoryManager
from atlas.memory.database import MemoryStore
from atlas.memory.lifecycle import MemoryLifecycleManager
from atlas.planner.executor import Executor
from atlas.planner.planner import Planner
from atlas.planner.task_manager import TaskManager
from atlas.reasoning.engine import ReasoningEngine
from atlas.scheduler.parser import SchedulerParser
from atlas.scheduler.scheduler import Scheduler
from atlas.skills.router import SkillRouter
from atlas.voice.speech import SpeechInterface
from atlas.workflow.builder import WorkflowBuilder
from atlas.workflow.engine import WorkflowEngine
from atlas.voice.session import VoiceSession


class AtlasKernel:
    """
    Núcleo principal do Atlas.

    Este módulo apenas instancia e conecta
    os componentes do sistema.

    Ele não executa comandos nem toma decisões.
    """

    def __init__(self) -> None:

        # Perfil global somente diagnóstico nesta etapa. A decisão é pública,
        # registra qualquer fallback e não altera recursos silenciosamente.
        self.runtime_profile = RuntimeProfileService(
            project_root=ROOT_DIR,
        ).resolve(ATLAS_RUNTIME_PROFILE)
        self.resource_manager = ResourceManager(
            profile=self.runtime_profile,
        )

        # Interface de voz
        self.voice_session = VoiceSession()
        self.speech = SpeechInterface(
            MIC_ENABLED,
            session=self.voice_session,
        )

        # Memória e contexto
        self.memory = MemoryStore()
        self.auto_memory = AutoMemoryManager(self.memory)
        self.memory_lifecycle = MemoryLifecycleManager(self.memory)
        self.memory_lifecycle.run_decay()
        self.context = ContextManager()
        self.session = self.context.session

        # Roteamento de skills
        self.router = SkillRouter(
            self.memory,
            self.memory_lifecycle,
        )

        # Brain e visão permanecem descarregados até o primeiro uso. Os proxies
        # preservam a interface pública para os consumidores existentes.
        self._brain_component = LazyComponent(
            "brain",
            self._build_brain,
        )
        self._vision_component = LazyComponent(
            "vision",
            self._build_vision,
        )
        self.lazy_components = LazyComponentRegistry(
            (self._brain_component, self._vision_component),
        )
        self.brain = LazyProxy(self._brain_component)
        self.vision = LazyProxy(self._vision_component)

        # Camada de raciocínio
        self.reasoner = ReasoningEngine()

        # Planejamento
        self.planner = Planner(
            self.context,
            brain=self.brain,
        )

        # Agendamento
        self.scheduler = Scheduler()
        self.scheduler_parser = SchedulerParser()

        # Execução
        self.automation = AutomationEngine(
            browser_session=self.context.browser,
            domain_responder=lambda text: self.brain.respond(text),
        )

        self.executor = Executor(
            self.automation
        )

        # Gerenciamento de tarefas
        self.task_manager = TaskManager()

        # Workflow
        self.workflow_builder = WorkflowBuilder()

        self.workflow_engine = WorkflowEngine(
            executor=self.executor,
            task_manager=self.task_manager,
            resource_manager=self.resource_manager,
        )

        # Configuração
        self.wake_word_enabled = (
            WAKE_WORD_ENABLED
        )

    def _build_brain(self):
        from atlas.brain.model_router import create_default_model_router
        from atlas.brain.ollama import OllamaBrain

        return OllamaBrain(
            self.context,
            model_router=create_default_model_router(
                self.runtime_profile,
                self.resource_manager,
            ),
        )

    def _build_vision(self):
        from atlas.vision.analyzer import OllamaVisionAnalyzer
        from atlas.vision.capture import ScreenCaptureService
        from atlas.vision.service import VisionService

        return VisionService(
            ScreenCaptureService(VISION_CAPTURE_DIR),
            OllamaVisionAnalyzer(),
            keep_captures=VISION_KEEP_CAPTURES,
        )
