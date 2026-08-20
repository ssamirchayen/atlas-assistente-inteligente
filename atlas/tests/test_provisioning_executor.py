from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from atlas.provisioning import (
    CommandResult,
    DeviceInventory,
    ProvisioningExecutor,
    ProvisioningPlan,
    ProvisioningStatus,
    ProvisioningStep,
    ProvisioningStepType,
    StepExecutionStatus,
)


class _Runner:
    def __init__(self, return_codes: tuple[int, ...] = (0,)) -> None:
        self.return_codes = list(return_codes)
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments, *, timeout):
        del timeout
        self.calls.append(tuple(arguments))
        return CommandResult(
            return_code=self.return_codes.pop(0),
            stdout="ok",
            stderr="",
        )


def _inventory() -> DeviceInventory:
    return DeviceInventory(
        os_name="Windows",
        os_version="11",
        architecture="AMD64",
        device_hash=sha256(b"device").hexdigest(),
        winget_available=True,
    )


def _plan(inventory: DeviceInventory) -> ProvisioningPlan:
    return ProvisioningPlan(
        profile_id="school-sales",
        inventory_fingerprint=inventory.fingerprint(),
        steps=(
            ProvisioningStep(
                step_id="folder-1",
                step_type=ProvisioningStepType.CREATE_DIRECTORY,
                description="Criar pasta",
                parameters={"relative_path": "Escola/Leads"},
                reversible=True,
            ),
            ProvisioningStep(
                step_id="package-1",
                step_type=ProvisioningStepType.INSTALL_WINGET_PACKAGE,
                description="Instalar navegador",
                parameters={
                    "package_id": "Google.Chrome",
                    "source": "winget",
                },
                reversible=False,
            ),
        ),
    )


def test_dry_run_never_changes_disk_or_starts_process(tmp_path: Path) -> None:
    runner = _Runner()
    inventory = _inventory()
    executor = ProvisioningExecutor(
        tmp_path,
        runner=runner,
        winget_path="winget.exe",
        dry_run=True,
    )

    evidence = executor.apply(_plan(inventory), inventory)

    assert evidence.status is ProvisioningStatus.DRY_RUN
    assert all(
        item.status is StepExecutionStatus.SIMULATED
        for item in evidence.steps
    )
    assert runner.calls == []
    assert not (tmp_path / "Escola").exists()


def test_real_executor_uses_exact_winget_arguments(tmp_path: Path) -> None:
    runner = _Runner()
    inventory = _inventory()
    executor = ProvisioningExecutor(
        tmp_path,
        runner=runner,
        winget_path="winget.exe",
        dry_run=False,
    )

    evidence = executor.apply(_plan(inventory), inventory)

    assert evidence.status is ProvisioningStatus.SUCCEEDED
    assert (tmp_path / "Escola" / "Leads").is_dir()
    assert runner.calls == [
        (
            "winget.exe",
            "install",
            "--id",
            "Google.Chrome",
            "--exact",
            "--source",
            "winget",
            "--scope",
            "user",
            "--silent",
            "--disable-interactivity",
            "--accept-package-agreements",
            "--accept-source-agreements",
        )
    ]


def test_failure_rolls_back_created_empty_folders(tmp_path: Path) -> None:
    runner = _Runner(return_codes=(1,))
    inventory = _inventory()
    executor = ProvisioningExecutor(
        tmp_path,
        runner=runner,
        winget_path="winget.exe",
        dry_run=False,
    )

    evidence = executor.apply(_plan(inventory), inventory)

    assert evidence.status is ProvisioningStatus.ROLLED_BACK
    assert not (tmp_path / "Escola").exists()
    assert any(
        item.status is StepExecutionStatus.ROLLED_BACK
        for item in evidence.steps
    )
