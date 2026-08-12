from __future__ import annotations

from collections import OrderedDict

from atlas.planner.results import ExecutionResult
from atlas.planner.task import Task, TaskStatus


class TaskManager:
    """
    Gerencia o ciclo de vida das tarefas do Atlas.

    O TaskManager NÃO executa tarefas.
    Ele apenas controla estados, progresso e histórico.
    """

    def __init__(self) -> None:
        self._tasks: OrderedDict[str, Task] = OrderedDict()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_task(self, description: str, **metadata) -> Task:
        task = Task(
            description=description,
            metadata=metadata,
        )

        self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def clear(self) -> None:
        self._tasks.clear()

    # ------------------------------------------------------------------
    # Estados
    # ------------------------------------------------------------------

    def start_task(self, task_id: str) -> Task:
        task = self._require(task_id)
        task.start()
        return task

    def complete_task(
        self,
        task_id: str,
        result: ExecutionResult,
    ) -> Task:

        task = self._require(task_id)
        task.complete(result)
        return task

    def fail_task(
        self,
        task_id: str,
        result: ExecutionResult,
    ) -> Task:

        task = self._require(task_id)
        task.fail(result)
        return task

    def cancel_task(self, task_id: str) -> Task:
        task = self._require(task_id)
        task.cancel()
        return task

    # ------------------------------------------------------------------
    # Estatísticas
    # ------------------------------------------------------------------

    @property
    def total(self) -> int:
        return len(self._tasks)

    @property
    def completed(self) -> int:
        return sum(
            task.status == TaskStatus.COMPLETED
            for task in self._tasks.values()
        )

    @property
    def failed(self) -> int:
        return sum(
            task.status == TaskStatus.FAILED
            for task in self._tasks.values()
        )

    @property
    def running(self) -> int:
        return sum(
            task.status == TaskStatus.RUNNING
            for task in self._tasks.values()
        )

    @property
    def pending(self) -> int:
        return sum(
            task.status == TaskStatus.PENDING
            for task in self._tasks.values()
        )

    @property
    def cancelled(self) -> int:
        return sum(
            task.status == TaskStatus.CANCELLED
            for task in self._tasks.values()
        )

    @property
    def progress(self) -> float:
        if not self._tasks:
            return 0.0

        finished = (
            self.completed +
            self.failed +
            self.cancelled
        )

        return (finished / self.total) * 100

    # ------------------------------------------------------------------

    def _require(self, task_id: str) -> Task:
        task = self.get_task(task_id)

        if task is None:
            raise KeyError(f"Tarefa '{task_id}' não encontrada.")

        return task