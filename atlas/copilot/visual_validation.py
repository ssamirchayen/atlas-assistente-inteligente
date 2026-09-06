from __future__ import annotations

import json
import statistics
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

DEFAULT_BUSINESS_LAB_URL = "http://127.0.0.1:5055"
DEFAULT_ATLAS_BRIDGE_URL = "http://127.0.0.1:8765"
DEFAULT_OUTPUT_DIR = Path("data/business_lab_benchmark")


@dataclass(frozen=True, slots=True)
class HttpJsonResponse:
    ok: bool
    status_code: int
    data: dict[str, Any]
    elapsed_ms: float
    error: str = ""


@dataclass(frozen=True, slots=True)
class VisualValidationStep:
    step_id: str
    name: str
    ok: bool
    elapsed_ms: float
    status_code: int = 0
    endpoint: str = ""
    intent: str = ""
    answer: str = ""
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VisualValidationReport:
    generated_at: str
    provenance: str
    business_lab_url: str
    atlas_bridge_url: str
    passed: bool
    total_steps: int
    passed_steps: int
    failed_steps: int
    total_elapsed_ms: float
    average_elapsed_ms: float
    median_elapsed_ms: float
    steps: tuple[VisualValidationStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JsonHttpClient:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def get_json(self, url: str) -> HttpJsonResponse:
        return self._request("GET", url)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> HttpJsonResponse:
        return self._request(
            "POST",
            url,
            payload=payload,
            headers=headers,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpJsonResponse:
        started = perf_counter()
        body = None
        request_headers = {
            "Accept": "application/json",
        }

        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        if headers:
            request_headers.update(headers)

        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                decoded = json.loads(raw) if raw else {}
                if not isinstance(decoded, dict):
                    decoded = {"value": decoded}
                elapsed_ms = (perf_counter() - started) * 1000
                return HttpJsonResponse(
                    ok=200 <= response.status < 300,
                    status_code=response.status,
                    data=decoded,
                    elapsed_ms=elapsed_ms,
                )
        except urllib.error.HTTPError as error:
            elapsed_ms = (perf_counter() - started) * 1000
            raw = error.read().decode("utf-8")
            decoded = _decode_json_object(raw)
            return HttpJsonResponse(
                ok=False,
                status_code=error.code,
                data=decoded,
                elapsed_ms=elapsed_ms,
                error=_error_message(decoded) or str(error),
            )
        except urllib.error.URLError as error:
            elapsed_ms = (perf_counter() - started) * 1000
            return HttpJsonResponse(
                ok=False,
                status_code=0,
                data={},
                elapsed_ms=elapsed_ms,
                error=str(error.reason),
            )
        except OSError as error:
            elapsed_ms = (perf_counter() - started) * 1000
            return HttpJsonResponse(
                ok=False,
                status_code=0,
                data={},
                elapsed_ms=elapsed_ms,
                error=str(error),
            )


class AtlasCopilotVisualValidator:
    def __init__(
        self,
        *,
        business_lab_url: str = DEFAULT_BUSINESS_LAB_URL,
        atlas_bridge_url: str = DEFAULT_ATLAS_BRIDGE_URL,
        copilot_token: str = "",
        lead_code: str = "SIM-00001",
        user_email: str = "consultor@nexyra.lab",
        client: JsonHttpClient | None = None,
    ) -> None:
        self.business_lab_url = business_lab_url.rstrip("/")
        self.atlas_bridge_url = atlas_bridge_url.rstrip("/")
        self.copilot_token = copilot_token
        self.lead_code = lead_code
        self.user_email = user_email
        self.client = client or JsonHttpClient()

    def run(self) -> VisualValidationReport:
        steps: list[VisualValidationStep] = []
        steps.append(self._check_business_lab())
        steps.append(self._check_atlas_bridge())

        if all(step.ok for step in steps):
            steps.extend(self._run_copilot_checks())
        else:
            steps.append(
                VisualValidationStep(
                    step_id="VIS-000",
                    name="Validação interrompida",
                    ok=False,
                    elapsed_ms=0.0,
                    error=(
                        "Business Lab ou Atlas Copilot Bridge está offline. "
                        "Abra os dois serviços e rode novamente."
                    ),
                )
            )

        return self._build_report(tuple(steps))

    def _check_business_lab(self) -> VisualValidationStep:
        endpoint = f"{self.business_lab_url}/health"
        response = self.client.get_json(endpoint)
        return VisualValidationStep(
            step_id="VIS-001",
            name="Business Lab online",
            ok=response.ok,
            elapsed_ms=response.elapsed_ms,
            status_code=response.status_code,
            endpoint=endpoint,
            error=response.error,
            data=response.data,
        )

    def _check_atlas_bridge(self) -> VisualValidationStep:
        endpoint = f"{self.atlas_bridge_url}/health"
        response = self.client.get_json(endpoint)
        return VisualValidationStep(
            step_id="VIS-002",
            name="Atlas Copilot Bridge online",
            ok=response.ok,
            elapsed_ms=response.elapsed_ms,
            status_code=response.status_code,
            endpoint=endpoint,
            error=response.error,
            data=response.data,
        )

    def _run_copilot_checks(self) -> tuple[VisualValidationStep, ...]:
        checks = (
            (
                "VIS-003",
                "Resumo do lead aberto",
                "Resuma esse lead",
                False,
            ),
            (
                "VIS-004",
                "Sugestão de próxima ação",
                "Qual a próxima ação desse lead?",
                False,
            ),
            (
                "VIS-005",
                "Consulta de cursos",
                "Liste os cursos disponíveis",
                False,
            ),
            (
                "VIS-006",
                "Consulta de dashboard",
                "Resumo do dashboard",
                False,
            ),
            (
                "VIS-007",
                "Simulação de atendimento",
                "Registre atendimento dizendo que teste visual final foi executado",
                True,
            ),
            (
                "VIS-008",
                "Simulação de retorno",
                "Crie retorno amanhã às 15h",
                True,
            ),
        )
        return tuple(
            self._send_copilot_message(
                step_id=step_id,
                name=name,
                message=message,
                dry_run=dry_run,
            )
            for step_id, name, message, dry_run in checks
        )

    def _send_copilot_message(
        self,
        *,
        step_id: str,
        name: str,
        message: str,
        dry_run: bool,
    ) -> VisualValidationStep:
        endpoint = f"{self.atlas_bridge_url}/api/copilot/message"
        payload = {
            "message": message,
            "dry_run": dry_run,
            "context": {
                "page": "lead_detail",
                "route": "/leads/1",
                "lead_code": self.lead_code,
                "user_email": self.user_email,
                "metadata": {
                    "source": "atlas_visual_validation",
                    "sprint": "28.12",
                },
            },
        }
        headers = {}
        if self.copilot_token:
            headers["X-Atlas-Copilot-Token"] = self.copilot_token

        response = self.client.post_json(endpoint, payload, headers=headers)
        data = response.data
        ok = response.ok and data.get("ok") is True
        answer = str(data.get("answer") or "")
        intent = str(data.get("intent") or "")

        return VisualValidationStep(
            step_id=step_id,
            name=name,
            ok=ok,
            elapsed_ms=response.elapsed_ms,
            status_code=response.status_code,
            endpoint=endpoint,
            intent=intent,
            answer=answer,
            error=response.error or _error_message(data),
            data={
                "dry_run": dry_run,
                "response": data,
            },
        )

    def _build_report(
        self,
        steps: tuple[VisualValidationStep, ...],
    ) -> VisualValidationReport:
        elapsed_values = [step.elapsed_ms for step in steps]
        passed_steps = sum(1 for step in steps if step.ok)
        failed_steps = len(steps) - passed_steps
        total_elapsed_ms = sum(elapsed_values)
        average_elapsed_ms = (
            total_elapsed_ms / len(elapsed_values) if elapsed_values else 0.0
        )
        median_elapsed_ms = statistics.median(elapsed_values) if elapsed_values else 0

        return VisualValidationReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            provenance="MEASURED_IN_LOCAL_ATLAS_BUSINESS_LAB_COPILOT",
            business_lab_url=self.business_lab_url,
            atlas_bridge_url=self.atlas_bridge_url,
            passed=failed_steps == 0,
            total_steps=len(steps),
            passed_steps=passed_steps,
            failed_steps=failed_steps,
            total_elapsed_ms=round(total_elapsed_ms, 2),
            average_elapsed_ms=round(average_elapsed_ms, 2),
            median_elapsed_ms=round(float(median_elapsed_ms), 2),
            steps=steps,
        )


def save_visual_validation_report(
    report: VisualValidationReport,
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = destination / f"atlas_copilot_visual_validation_{stamp}.json"
    md_path = destination / f"atlas_copilot_visual_validation_{stamp}.md"

    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    return json_path, md_path


def _render_markdown(report: VisualValidationReport) -> str:
    status = "APROVADO" if report.passed else "REPROVADO"
    lines = [
        "# Atlas Copilot — Validação final visual",
        "",
        f"**Resultado:** {status}",
        f"**Origem:** {report.provenance}",
        f"**Business Lab:** `{report.business_lab_url}`",
        f"**Atlas Bridge:** `{report.atlas_bridge_url}`",
        f"**Etapas:** {report.passed_steps}/{report.total_steps}",
        f"**Tempo total:** {report.total_elapsed_ms:.2f} ms",
        "",
        "## Etapas",
        "",
        "| ID | Nome | Status | Tempo | Intenção | Observação |",
        "|---|---|---:|---:|---|---|",
    ]

    for step in report.steps:
        step_status = "OK" if step.ok else "FALHOU"
        note = step.answer or step.error
        note = note.replace("|", "/").replace("\n", " ")
        lines.append(
            "| "
            f"{step.step_id} | {step.name} | {step_status} | "
            f"{step.elapsed_ms:.2f} ms | {step.intent} | {note} |"
        )

    lines.extend(
        [
            "",
            "## Leitura comercial",
            "",
            (
                "Esta validação demonstra o fluxo visual integrado: o usuário "
                "opera o Business Lab, o widget envia contexto para o Atlas "
                "Bridge, e o Atlas executa ou simula ações usando o Integration "
                "Framework."
            ),
            "",
            (
                "Os dados usados continuam sendo sintéticos e locais. Este "
                "relatório não deve ser apresentado como resultado real de "
                "cliente, e sim como demonstração técnica/comercial controlada."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _decode_json_object(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return decoded if isinstance(decoded, dict) else {"value": decoded}


def _error_message(payload: dict[str, Any]) -> str:
    raw_error = payload.get("error")
    if isinstance(raw_error, dict):
        return str(raw_error.get("message") or raw_error.get("code") or "")
    return str(raw_error or "")
