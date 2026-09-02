from hashlib import sha256
import json

import pytest

from atlas.provisioning import (
    DeviceInventory,
    ManagedSettingRequirement,
    ManagedSettingType,
    ProvisioningExecutor,
    ProvisioningPlan,
    ProvisioningPlanner,
    ProvisioningProfile,
    ProvisioningStatus,
    ProvisioningStepType,
)


def _inventory() -> DeviceInventory:
    return DeviceInventory(
        os_name="Windows",
        os_version="11",
        architecture="AMD64",
        device_hash=sha256(b"device").hexdigest(),
        winget_available=True,
    )


def _settings() -> tuple[ManagedSettingRequirement, ...]:
    return (
        ManagedSettingRequirement(
            setting_id="browser-home",
            setting_type=ManagedSettingType.BROWSER,
            description="Definir página corporativa",
            parameters={
                "browser": "chrome",
                "homepage": "https://portal.empresa.test/inicio",
            },
        ),
        ManagedSettingRequirement(
            setting_id="printer-sales",
            setting_type=ManagedSettingType.PRINTER,
            description="Conectar impressora comercial",
            parameters={"connection_name": r"\\print-srv\Comercial"},
        ),
        ManagedSettingRequirement(
            setting_id="vpn-corporate",
            setting_type=ManagedSettingType.VPN,
            description="Criar perfil de VPN",
            parameters={
                "name": "VPN Empresa",
                "server": "vpn.empresa.test",
                "tunnel_type": "ikev2",
                "split_tunnel": "false",
            },
        ),
        ManagedSettingRequirement(
            setting_id="network-corporate",
            setting_type=ManagedSettingType.NETWORK,
            description="Aplicar perfil de rede",
            parameters={"profile": "Rede Empresa", "mode": "corporate"},
        ),
    )


def _plan() -> ProvisioningPlan:
    return ProvisioningPlanner().build(
        ProvisioningProfile(
            profile_id="employee-managed",
            display_name="Funcionário gerenciado",
            settings=_settings(),
        ),
        _inventory(),
    )


def test_planner_emits_all_managed_setting_step_types() -> None:
    plan = _plan()

    assert [step.step_type for step in plan.steps] == [
        ProvisioningStepType.CONFIGURE_BROWSER,
        ProvisioningStepType.CONNECT_PRINTER,
        ProvisioningStepType.CONFIGURE_VPN,
        ProvisioningStepType.CONFIGURE_NETWORK,
    ]
    assert all(not step.reversible for step in plan.steps)


def test_managed_settings_reject_secrets_and_unsafe_values() -> None:
    with pytest.raises(ValueError, match="parâmetros"):
        ManagedSettingRequirement(
            setting_id="vpn",
            setting_type=ManagedSettingType.VPN,
            description="VPN insegura",
            parameters={
                "name": "VPN",
                "server": "vpn.example.test",
                "tunnel_type": "ikev2",
                "split_tunnel": "false",
                "password": "segredo",
            },
        )
    with pytest.raises(ValueError, match="HTTPS"):
        ManagedSettingRequirement(
            setting_id="browser",
            setting_type=ManagedSettingType.BROWSER,
            description="Página insegura",
            parameters={"browser": "chrome", "homepage": "http://site.test"},
        )


def test_printer_and_vpn_are_strictly_validated() -> None:
    with pytest.raises(ValueError, match="UNC"):
        ManagedSettingRequirement(
            setting_id="printer",
            setting_type=ManagedSettingType.PRINTER,
            description="Impressora",
            parameters={"connection_name": "powershell.exe -Command calc"},
        )
    with pytest.raises(ValueError, match="túnel"):
        ManagedSettingRequirement(
            setting_id="vpn",
            setting_type=ManagedSettingType.VPN,
            description="VPN",
            parameters={
                "name": "VPN",
                "server": "vpn.example.test",
                "tunnel_type": "pptp",
                "split_tunnel": "false",
            },
        )


def test_plan_round_trip_preserves_digest() -> None:
    plan = _plan()

    restored = ProvisioningPlan.from_dict(
        json.loads(json.dumps(plan.as_dict()))
    )

    assert restored == plan
    assert restored.digest() == plan.digest()


class _Adapter:
    def __init__(self) -> None:
        self.calls = []

    def apply(self, step):
        self.calls.append(step)
        return f"Configuração {step.step_id} aplicada."


def test_dry_run_never_calls_managed_settings_adapter(tmp_path) -> None:
    adapter = _Adapter()
    evidence = ProvisioningExecutor(
        tmp_path,
        dry_run=True,
        settings_adapter=adapter,
    ).apply(_plan(), _inventory())

    assert evidence.status is ProvisioningStatus.DRY_RUN
    assert adapter.calls == []


def test_real_mode_uses_only_injected_managed_adapter(tmp_path) -> None:
    adapter = _Adapter()
    evidence = ProvisioningExecutor(
        tmp_path,
        dry_run=False,
        settings_adapter=adapter,
    ).apply(_plan(), _inventory())

    assert evidence.status is ProvisioningStatus.SUCCEEDED
    assert len(adapter.calls) == 4


def test_real_mode_fails_closed_without_company_adapter(tmp_path) -> None:
    evidence = ProvisioningExecutor(
        tmp_path,
        dry_run=False,
    ).apply(_plan(), _inventory())

    assert evidence.status is ProvisioningStatus.FAILED
    assert evidence.steps[0].status.value == "failed"
    assert "adaptador corporativo" in evidence.steps[0].message
