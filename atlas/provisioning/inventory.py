"""Inventário local sem coleta de serial, usuário ou hostname em claro."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import platform
import shutil
import socket
import subprocess
from typing import Protocol, Sequence

from atlas.provisioning.models import DeviceInventory, PackageRequirement


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Resultado limitado de um processo sem uso de shell."""

    return_code: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(
        self,
        arguments: Sequence[str],
        *,
        timeout: float,
    ) -> CommandResult: ...


class SubprocessCommandRunner:
    """Executa somente listas de argumentos e limita a saída retida."""

    def __init__(self, *, max_output_chars: int = 20_000) -> None:
        if max_output_chars <= 0:
            raise ValueError("O limite da saída deve ser positivo.")
        self._max_output_chars = max_output_chars

    def run(
        self,
        arguments: Sequence[str],
        *,
        timeout: float,
    ) -> CommandResult:
        command = tuple(str(argument) for argument in arguments)

        if not command or any(not item.strip() for item in command):
            raise ValueError("O comando está vazio ou incompleto.")
        if timeout <= 0:
            raise ValueError("O timeout deve ser positivo.")

        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return CommandResult(
            return_code=completed.returncode,
            stdout=completed.stdout[-self._max_output_chars :],
            stderr=completed.stderr[-self._max_output_chars :],
        )


class DeviceInventoryCollector:
    """Verifica apenas os pacotes exatos declarados pelo perfil."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        winget_path: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._runner = runner or SubprocessCommandRunner()
        self._winget_path = winget_path
        self._timeout = timeout

    def capture(
        self,
        packages: tuple[PackageRequirement, ...] = (),
    ) -> DeviceInventory:
        winget_path = self._winget_path or shutil.which("winget")
        installed: set[str] = set()

        if winget_path:
            for package in packages:
                if self._is_installed(winget_path, package):
                    installed.add(package.package_id)

        host_hash = sha256(
            socket.gethostname().casefold().encode("utf-8")
        ).hexdigest()
        return DeviceInventory(
            os_name=platform.system() or "Unknown",
            os_version=platform.version() or "Unknown",
            architecture=platform.machine() or "Unknown",
            device_hash=host_hash,
            winget_available=bool(winget_path),
            installed_package_ids=frozenset(installed),
        )

    def _is_installed(
        self,
        winget_path: str,
        package: PackageRequirement,
    ) -> bool:
        result = self._runner.run(
            (
                winget_path,
                "list",
                "--id",
                package.package_id,
                "--exact",
                "--source",
                package.source,
                "--disable-interactivity",
            ),
            timeout=self._timeout,
        )
        return (
            result.return_code == 0
            and package.package_id.casefold() in result.stdout.casefold()
        )
