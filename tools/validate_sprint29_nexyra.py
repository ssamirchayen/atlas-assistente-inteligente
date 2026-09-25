from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

@dataclass(slots=True)
class EnvFile:
    path: Path
    values: dict[str, str]
    counts: dict[str, int]

def _strip_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value.strip()

def read_env(path: Path) -> EnvFile:
    values: dict[str, str] = {}
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = KEY_RE.match(line)
        if not match:
            continue
        key, raw = match.groups()
        counts[key] = counts.get(key, 0) + 1
        values[key] = _strip_value(raw)
    return EnvFile(path, values, counts)

def ok(message: str) -> None:
    print(f"[OK] {message}")

def warn(message: str) -> None:
    print(f"[AVISO] {message}")

def fail(message: str, errors: list[str]) -> None:
    errors.append(message)
    print(f"[ERRO] {message}")

def _required(env: EnvFile, key: str, errors: list[str]) -> str:
    if env.counts.get(key, 0) > 1:
        fail(f"{env.path}: {key} aparece mais de uma vez.", errors)
    value = env.values.get(key, "")
    if not value:
        fail(f"{env.path}: {key} não está configurado.", errors)
    else:
        ok(f"{key} configurado em {env.path.name}.")
    return value

def _request_json(url: str, *, headers: dict[str, str] | None = None) -> dict:
    request = Request(url, headers=headers or {}, method="GET")
    with urlopen(request, timeout=8) as response:
        body = response.read().decode("utf-8")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("Resposta não é um objeto JSON.")
        return data

def validate(atlas_env: Path, nexyra_env: Path, *, online: bool) -> int:
    errors: list[str] = []
    if not atlas_env.is_file():
        fail(f"Arquivo não encontrado: {atlas_env}", errors)
        return 1
    if not nexyra_env.is_file():
        fail(f"Arquivo não encontrado: {nexyra_env}", errors)
        return 1

    atlas = read_env(atlas_env)
    nexyra = read_env(nexyra_env)

    atlas_url = _required(atlas, "ATLAS_NEXYRA_URL", errors)
    atlas_integration_token = _required(atlas, "ATLAS_NEXYRA_TOKEN", errors)
    workspace_id = _required(atlas, "ATLAS_NEXYRA_WORKSPACE_ID", errors)
    actor_id = _required(atlas, "ATLAS_NEXYRA_ACTOR_USER_ID", errors)
    atlas_copilot_token = _required(atlas, "ATLAS_COPILOT_TOKEN", errors)
    atlas_copilot_port = _required(atlas, "ATLAS_COPILOT_PORT", errors)

    nexyra_integration_token = _required(nexyra, "ATLAS_INTEGRATION_TOKEN", errors)
    nexyra_copilot_token = _required(nexyra, "ATLAS_COPILOT_TOKEN", errors)
    bridge_url = _required(nexyra, "ATLAS_COPILOT_BRIDGE_URL", errors)

    if atlas_integration_token and nexyra_integration_token:
        if atlas_integration_token == nexyra_integration_token:
            ok("Token Atlas -> Nexyra coincide nos dois .env.")
        else:
            fail("ATLAS_NEXYRA_TOKEN e ATLAS_INTEGRATION_TOKEN são diferentes.", errors)

    if atlas_copilot_token and nexyra_copilot_token:
        if atlas_copilot_token == nexyra_copilot_token:
            ok("Token Nexyra -> Atlas Copilot coincide nos dois .env.")
        else:
            fail("ATLAS_COPILOT_TOKEN é diferente entre Atlas e Nexyra.", errors)

    if atlas_integration_token and atlas_copilot_token and atlas_integration_token == atlas_copilot_token:
        warn("Os dois canais usam o mesmo token. Funciona, mas gere tokens distintos antes de produção.")
    else:
        ok("Tokens de integração e Copilot são distintos.")

    if workspace_id and not PUBLIC_ID_RE.fullmatch(workspace_id):
        fail("ATLAS_NEXYRA_WORKSPACE_ID possui formato inválido.", errors)
    if actor_id and not PUBLIC_ID_RE.fullmatch(actor_id):
        fail("ATLAS_NEXYRA_ACTOR_USER_ID possui formato inválido.", errors)

    try:
        port = str(urlsplit(bridge_url).port or "")
    except ValueError:
        port = ""
    if atlas_copilot_port and port:
        if atlas_copilot_port == port:
            ok(f"Copilot usa a mesma porta nos dois lados ({port}).")
        else:
            fail(f"Porta do Copilot diverge: Atlas={atlas_copilot_port}, Nexyra={port}.", errors)
    if atlas_copilot_port == "8765":
        warn("8765 também é a porta padrão da API normal do Atlas; prefira 8766 para o Copilot Nexyra.")

    if online and not errors:
        base = atlas_url.rstrip("/")
        common_headers = {
            "Accept": "application/json",
            "X-Nexyra-Integration-Token": atlas_integration_token,
            "X-Nexyra-Actor-User": actor_id,
        }
        probes = [
            ("Nexyra integration health", f"{base}/api/v1/integrations/atlas/health", {}),
            ("Nexyra capabilities/token", f"{base}/api/v1/integrations/atlas/capabilities", {
                "Accept": "application/json", "X-Nexyra-Integration-Token": atlas_integration_token,
            }),
            ("Nexyra workspace/actor", f"{base}/api/v1/integrations/atlas/workspaces/{workspace_id}/context", common_headers),
            ("Atlas Copilot health", f"{bridge_url.rstrip('/')}/health", {}),
        ]
        for name, url, request_headers in probes:
            try:
                payload = _request_json(url, headers=request_headers)
                if payload.get("ok") is False:
                    raise ValueError("Serviço respondeu ok=false.")
                ok(f"{name} online.")
            except HTTPError as exc:
                fail(f"{name}: HTTP {exc.code}.", errors)
            except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                fail(f"{name}: {exc}", errors)

    print()
    if errors:
        print(f"Validação concluída com {len(errors)} erro(s). Nenhum segredo foi exibido.")
        return 1
    print("Sprint 29: configuração Atlas <-> Nexyra validada. Nenhum segredo foi exibido.")
    return 0

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Valida a integração final Atlas <-> Nexyra sem imprimir tokens.")
    parser.add_argument("--atlas-env", type=Path, default=root / ".env")
    parser.add_argument("--nexyra-root", type=Path, default=Path(os.getenv("NEXYRA_CRM_SOURCE", r"C:\Nexyra_CRM_Atlas")))
    parser.add_argument("--online", action="store_true", help="Também consulta os serviços locais em execução.")
    args = parser.parse_args()
    return validate(args.atlas_env, args.nexyra_root / ".env", online=args.online)

if __name__ == "__main__":
    sys.exit(main())
