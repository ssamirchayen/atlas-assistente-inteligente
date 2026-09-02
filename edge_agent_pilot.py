"""Safe local pilot for Sprint 23 Stage 1."""

from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path

from atlas.edge import EdgeStateStore, ITProvisioningAgent
from atlas.provisioning import DeviceInventoryCollector


def main() -> int:
    print("Atlas Edge — piloto seguro da Sprint 23, Etapa 1")
    print("O estado será criado em pasta temporária e nenhuma configuração mudará.")

    with TemporaryDirectory(prefix="atlas-edge-pilot-") as directory:
        agent = ITProvisioningAgent(
            store=EdgeStateStore(Path(directory) / "device.json"),
            collector=DeviceInventoryCollector(),
        )
        challenge = agent.prepare_enrollment("empresa-piloto")
        print(f"Dispositivo local: {challenge.device_id}")
        print("Cadastro preparado. Digite SIM para aprovar localmente.")
        if input("> ").strip() != "SIM":
            print("Cadastro cancelado. Nenhum estado permanente foi criado.")
            return 1

        agent.confirm_enrollment(
            challenge.token,
            approver_id="responsavel-piloto",
        )
        heartbeat = agent.heartbeat()
        print(
            f"Heartbeat local #{heartbeat.sequence}: {heartbeat.status.value} | "
            f"{heartbeat.os_name} {heartbeat.os_version} | "
            f"WinGet: {heartbeat.winget_available}"
        )

    print("Piloto concluído. Nenhum programa ou configuração foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
