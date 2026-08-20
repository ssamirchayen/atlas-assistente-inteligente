from __future__ import annotations

from atlas.automation.engine import AutomationEngine
from atlas.brain.ollama import OllamaBrain
from atlas.context.manager import ContextManager
from atlas.core.config import MIC_ENABLED, WAKE_WORD_ENABLED
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

        # Modelo de linguagem
        self.brain = OllamaBrain(
            self.context
        )

        # Camada de raciocínio
        self.reasoner = ReasoningEngine()

        # Planejamento
        self.planner = Planner(
            self.context
        )

        # Agendamento
        self.scheduler = Scheduler()
        self.scheduler_parser = SchedulerParser()

        # Execução
        self.automation = AutomationEngine(
            browser_session=self.context.browser,
            domain_responder=self.brain.respond,
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
        )

        # Configuração
        self.wake_word_enabled = (
            WAKE_WORD_ENABLED
        )
