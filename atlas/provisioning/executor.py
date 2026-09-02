"""Execução controlada de planos, com dry-run e limpeza reversível."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import time
from typing import Callable
from uuid import uuid4

from atlas.provisioning.inventory import CommandRunner, SubprocessCommandRunner
from atlas.provisioning.models import (
    DeviceInventory,
    ProvisioningEvidence,
    ProvisioningPlan,
    ProvisioningStatus,
    ProvisioningStep,
    ProvisioningStepType,
    StepEvidence,
    StepExecutionStatus,
)
from atlas.provisioning.settings import (
    BlockedManagedSettingsAdapter,
    ManagedSettingsAdapter,
)


@dataclass(frozen=True, slots=True)
class _AppliedDirectory:
    step_id: str
    created_paths: tuple[Path, ...]


class ProvisioningExecutor:
    """Executa sem shell, sem elevação e sem comandos fornecidos pelo usuário."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        runner: CommandRunner | None = None,
        winget_path: str | None = None,
        command_timeout: float = 900.0,
        dry_run: bool = True,
        settings_adapter: ManagedSettingsAdapter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        root = workspace_root.expanduser().resolve()

        if command_timeout <= 0:
            raise ValueError("O timeout de provisionamento deve ser positivo.")

        self._workspace_root = root
        self._runner = runner or SubprocessCommandRunner()
        self._winget_path = winget_path
        self._command_timeout = command_timeout
        self._dry_run = dry_run
        self._settings_adapter = (
            settings_adapter or BlockedManagedSettingsAdapter()
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def apply(
        self,
        plan: ProvisioningPlan,
        inventory: DeviceInventory,
    ) -> ProvisioningEvidence:
        if plan.inventory_fingerprint != inventory.fingerprint():
            raise ValueError("O inventário mudou após a criação do plano.")

        started_at = self._now()

        if self._dry_run:
            evidence = tuple(
                StepEvidence(
                    step_id=step.step_id,
                    status=StepExecutionStatus.SIMULATED,
                    message=f"Simulação: {step.description}.",
                    duration_seconds=0.0,
                )
                for step in plan.steps
            )
            return self._evidence(
                plan,
                inventory,
                status=ProvisioningStatus.DRY_RUN,
                steps=evidence,
                started_at=started_at,
            )

        results: list[StepEvidence] = []
        applied_directories: list[_AppliedDirectory] = []
        non_reversible_completed = False

        for step in plan.steps:
            step_started = time.perf_counter()

            try:
                message, applied = self._apply_step(step)
                results.append(
                    StepEvidence(
                        step_id=step.step_id,
                        status=StepExecutionStatus.SUCCEEDED,
                        message=message,
                        duration_seconds=time.perf_counter() - step_started,
                    )
                )
                if applied is not None:
                    applied_directories.append(applied)
                if not step.reversible:
                    non_reversible_completed = True
            except Exception as error:
                results.append(
                    StepEvidence(
                        step_id=step.step_id,
                        status=StepExecutionStatus.FAILED,
                        message=f"Falha controlada: {error}",
                        duration_seconds=time.perf_counter() - step_started,
                    )
                )
                rollback_results = self._rollback_directories(
                    applied_directories
                )
                results.extend(rollback_results)
                status = (
                    ProvisioningStatus.ROLLED_BACK
                    if rollback_results
                    and not non_reversible_completed
                    and all(
                        item.status is StepExecutionStatus.ROLLED_BACK
                        for item in rollback_results
                    )
                    else ProvisioningStatus.FAILED
                )
                return self._evidence(
                    plan,
                    inventory,
                    status=status,
                    steps=tuple(results),
                    started_at=started_at,
                )

        return self._evidence(
            plan,
            inventory,
            status=ProvisioningStatus.SUCCEEDED,
            steps=tuple(results),
            started_at=started_at,
        )

    def _apply_step(
        self,
        step: ProvisioningStep,
    ) -> tuple[str, _AppliedDirectory | None]:
        if step.step_type is ProvisioningStepType.CREATE_DIRECTORY:
            return self._create_directory(step)

        if step.step_type is ProvisioningStepType.INSTALL_WINGET_PACKAGE:
            return self._install_package(step), None

        if step.step_type in {
            ProvisioningStepType.CONFIGURE_BROWSER,
            ProvisioningStepType.CONNECT_PRINTER,
            ProvisioningStepType.CONFIGURE_VPN,
            ProvisioningStepType.CONFIGURE_NETWORK,
        }:
            return self._settings_adapter.apply(step), None

        raise ValueError("Tipo de etapa não autorizado.")

    def _create_directory(
        self,
        step: ProvisioningStep,
    ) -> tuple[str, _AppliedDirectory | None]:
        relative_path = step.parameters["relative_path"]
        target = (self._workspace_root / relative_path).resolve()

        if not target.is_relative_to(self._workspace_root):
            raise ValueError("A pasta escaparia do workspace autorizado.")
        if target.exists():
            if not target.is_dir():
                raise ValueError("O destino existe e não é uma pasta.")
            return "A pasta já existia; nenhuma alteração foi feita.", None

        missing: list[Path] = []
        cursor = target

        while cursor != self._workspace_root and not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent

        target.mkdir(parents=True, exist_ok=False)
        return (
            "Pasta corporativa criada.",
            _AppliedDirectory(
                step_id=step.step_id,
                created_paths=tuple(missing),
            ),
        )

    def _install_package(self, step: ProvisioningStep) -> str:
        winget = self._winget_path or shutil.which("winget")

        if not winget:
            raise RuntimeError("WinGet não está disponível.")

        package_id = step.parameters["package_id"]
        source = step.parameters["source"]
        result = self._runner.run(
            (
                winget,
                "install",
                "--id",
                package_id,
                "--exact",
                "--source",
                source,
                "--scope",
                "user",
                "--silent",
                "--disable-interactivity",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ),
            timeout=self._command_timeout,
        )

        if result.return_code != 0:
            raise RuntimeError(
                f"WinGet encerrou com código {result.return_code}."
            )

        return f"Pacote {package_id} instalado pelo WinGet."

    def _rollback_directories(
        self,
        applied: list[_AppliedDirectory],
    ) -> tuple[StepEvidence, ...]:
        results: list[StepEvidence] = []

        for item in reversed(applied):
            started = time.perf_counter()

            try:
                for path in item.created_paths:
                    if path.exists():
                        path.rmdir()
                results.append(
                    StepEvidence(
                        step_id=item.step_id,
                        status=StepExecutionStatus.ROLLED_BACK,
                        message="Pasta vazia removida durante a limpeza.",
                        duration_seconds=time.perf_counter() - started,
                    )
                )
            except OSError:
                results.append(
                    StepEvidence(
                        step_id=item.step_id,
                        status=StepExecutionStatus.FAILED,
                        message=(
                            "A limpeza não removeu uma pasta não vazia."
                        ),
                        duration_seconds=time.perf_counter() - started,
                    )
                )

        return tuple(results)

    def _evidence(
        self,
        plan: ProvisioningPlan,
        inventory: DeviceInventory,
        *,
        status: ProvisioningStatus,
        steps: tuple[StepEvidence, ...],
        started_at: datetime,
    ) -> ProvisioningEvidence:
        return ProvisioningEvidence(
            evidence_id=uuid4().hex,
            plan_id=plan.plan_id,
            plan_digest=plan.digest(),
            device_hash=inventory.device_hash,
            status=status,
            steps=steps,
            dry_run=self._dry_run,
            started_at=started_at,
            finished_at=self._now(),
        )

    def _now(self) -> datetime:
        value = self._clock()

        if value.tzinfo is None:
            raise ValueError("O relógio deve possuir fuso horário.")

        return value.astimezone(timezone.utc)
