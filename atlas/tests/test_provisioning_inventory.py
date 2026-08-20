from __future__ import annotations

from atlas.provisioning import (
    CommandResult,
    DeviceInventoryCollector,
    PackageRequirement,
)


class _Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments, *, timeout):
        del timeout
        command = tuple(arguments)
        self.calls.append(command)
        package_id = command[command.index("--id") + 1]
        return CommandResult(
            return_code=0,
            stdout=f"Nome  {package_id}  1.0",
            stderr="",
        )


def test_inventory_probes_only_exact_declared_packages() -> None:
    runner = _Runner()
    package = PackageRequirement(
        package_id="Google.Chrome",
        display_name="Google Chrome",
    )
    collector = DeviceInventoryCollector(
        runner,
        winget_path="winget.exe",
    )

    inventory = collector.capture((package,))

    assert inventory.installed_package_ids == frozenset({"Google.Chrome"})
    assert runner.calls == [
        (
            "winget.exe",
            "list",
            "--id",
            "Google.Chrome",
            "--exact",
            "--source",
            "winget",
            "--disable-interactivity",
        )
    ]
    assert len(inventory.device_hash) == 64
