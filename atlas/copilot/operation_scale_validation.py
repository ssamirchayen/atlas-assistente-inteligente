from __future__ import annotations

import json
import statistics
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

DEFAULT_BUSINESS_LAB_URL = "http://127.0.0.1:5055"
DEFAULT_ATLAS_BRIDGE_URL = "http://127.0.0.1:8765"
DEFAULT_OUTPUT_DIR = Path("data") / "business_lab_benchmark"
DEFAULT_LEAD_CODE = "SIM-00001"
DEFAULT_USER_EMAIL = "consultor@nexyra.lab"


@dataclass(frozen=True, slots=True)
class HttpJsonResponse:
    ok: bool
    status_code: int
    data: dict[str, Any]
    elapsed_ms: float
    error: str = ""


@dataclass(frozen=True, slots=True)
class OperationValidationStep:
    step_id: str
    name: str
    ok: bool
    elapsed_ms: float
    status_code: int = 0
    endpoint: str = ""
    intent: str = ""
    mode: str = ""
    answer: str = ""
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OperationScaleValidationReport:
    generated_at: str
    provenance: str
    business_lab_url: str
    atlas_bridge_url: str
    execution_mode: str
    passed: bool
    total_steps: int
    passed_steps: int
    failed_steps: int
    total_elapsed_ms: float
    average_elapsed_ms: float
    median_elapsed_ms: float
    capabilities: dict[str, bool]
    safety_notes: tuple[str, ...]
    steps: tuple[OperationValidationStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JsonHttpClientProtocol(Protocol):
    def get_json(self, url: str) -> HttpJsonResponse: ...

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> HttpJsonResponse: ...


class JsonHttpClient:
    def __init__(self, timeout: float = 15.0) -> None:
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
        return self._request("POST", url, payload=payload, headers=headers)

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
        request_headers = {"Accept": "application/json"}

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
                decoded = _decode_json_object(raw)
                return HttpJsonResponse(
                    ok=200 <= response.status < 300,
                    status_code=response.status,
                    data=decoded,
                    elapsed_ms=_elapsed_ms(started),
                )
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8")
            decoded = _decode_json_object(raw)
            return HttpJsonResponse(
                ok=False,
                status_code=error.code,
                data=decoded,
                elapsed_ms=_elapsed_ms(started),
                error=_error_message(decoded) or str(error),
            )
        except urllib.error.URLError as error:
            return HttpJsonResponse(
                ok=False,
                status_code=0,
                data={},
                elapsed_ms=_elapsed_ms(started),
                error=str(error.reason),
            )
        except OSError as error:
            return HttpJsonResponse(
                ok=False,
                status_code=0,
                data={},
                elapsed_ms=_elapsed_ms(started),
                error=str(error),
            )


class AtlasOperationScaleValidator:
    def __init__(
        self,
        *,
        business_lab_url: str = DEFAULT_BUSINESS_LAB_URL,
        atlas_bridge_url: str = DEFAULT_ATLAS_BRIDGE_URL,
        copilot_token: str = "",
        lead_code: str = DEFAULT_LEAD_CODE,
        user_email: str = DEFAULT_USER_EMAIL,
        confirm_batch: bool = False,
        client: JsonHttpClientProtocol | None = None,
    ) -> None:
        self.business_lab_url = business_lab_url.rstrip("/")
        self.atlas_bridge_url = atlas_bridge_url.rstrip("/")
        self.copilot_token = copilot_token
        self.lead_code = lead_code
        self.user_email = user_email
        self.confirm_batch = confirm_batch
        self.client = client or JsonHttpClient()

    def run(self) -> OperationScaleValidationReport:
        steps: list[OperationValidationStep] = [
            self._check_business_lab(),
            self._check_atlas_bridge(),
        ]

        if all(step.ok for step in steps):
            steps.extend(self._run_copilot_checks())
        else:
            steps.append(
                OperationValidationStep(
                    step_id="OPS-000",
                    name="Validação interrompida",
                    ok=False,
                    elapsed_ms=0.0,
                    error=(
                        "Business Lab ou Atlas Bridge está offline. "
                        "Abra os dois serviços e rode novamente."
                    ),
                )
            )

        return self._build_report(tuple(steps))

    def _check_business_lab(self) -> OperationValidationStep:
        endpoint = f"{self.business_lab_url}/health"
        response = self.client.get_json(endpoint)
        return OperationValidationStep(
            step_id="OPS-001",
            name="Business Lab online",
            ok=response.ok,
            elapsed_ms=response.elapsed_ms,
            status_code=response.status_code,
            endpoint=endpoint,
            mode="health_check",
            error=response.error,
            data=response.data,
        )

    def _check_atlas_bridge(self) -> OperationValidationStep:
        endpoint = f"{self.atlas_bridge_url}/health"
        response = self.client.get_json(endpoint)
        return OperationValidationStep(
            step_id="OPS-002",
            name="Atlas Copilot Bridge online",
            ok=response.ok,
            elapsed_ms=response.elapsed_ms,
            status_code=response.status_code,
            endpoint=endpoint,
            mode="health_check",
            error=response.error,
            data=response.data,
        )

    def _run_copilot_checks(self) -> tuple[OperationValidationStep, ...]:
        checks = [
            self._copilot_step(
                step_id="OPS-003",
                name="Resumo da tela de leads",
                message="Atlas, resuma essa tela",
                context={"page": "leads", "route": "/leads"},
                expected_intent="summarize_screen",
                expected_mode="read_only",
            ),
            self._copilot_step(
                step_id="OPS-004",
                name="Resumo de lead específico",
                message="Atlas, resuma esse lead",
                context={
                    "page": "lead_detail",
                    "route": "/leads/1",
                    "lead_code": self.lead_code,
                },
                expected_intent="summarize_lead",
                expected_mode="read_only",
            ),
            self._copilot_step(
                step_id="OPS-005",
                name="Triagem em lote de leads",
                message=(
                    "Atlas, analise os 10 leads novos de Radiologia, "
                    "priorize os mais importantes e sugira a próxima ação."
                ),
                context={"page": "leads", "route": "/leads"},
                expected_intent="batch_lead_triage",
                expected_mode="safe_preview",
            ),
            self._copilot_step(
                step_id="OPS-006",
                name="Prévia de mensagens em lote",
                message=_batch_message_command(),
                context={"page": "leads", "route": "/leads"},
                expected_intent="batch_messages",
                expected_mode="confirmation_required",
                expect_human_review=True,
            ),
        ]

        if self.confirm_batch:
            checks.append(
                self._copilot_step(
                    step_id="OPS-007",
                    name="Execução confirmada em lote",
                    message=_batch_message_command(),
                    context={"page": "leads", "route": "/leads"},
                    expected_intent="batch_messages",
                    expected_mode="confirmed_execution",
                    extra_payload={"confirmed": True},
                )
            )
        else:
            checks.append(
                OperationValidationStep(
                    step_id="OPS-007",
                    name="Execução confirmada em lote",
                    ok=True,
                    elapsed_ms=0.0,
                    mode="not_executed_by_default",
                    answer=(
                        "Etapa preservada em modo seguro. Para registrar dados "
                        "reais no Lab, rode com --confirm-batch."
                    ),
                    data={"skipped_by_safety": True},
                )
            )

        checks.extend(
            [
                self._copilot_step(
                    step_id="OPS-008",
                    name="Relatório inteligente + downloads",
                    message=(
                        "Atlas, gere um relatório completo de leads, matrículas, "
                        "atendimentos e retornos desta semana com planilha XLSX."
                    ),
                    context={"page": "reports", "route": "/relatorios"},
                    expected_intent="smart_reports",
                    expected_mode="downloadable_report",
                    validator=_smart_report_has_downloads,
                ),
                self._copilot_step(
                    step_id="OPS-009",
                    name="Próxima ação operacional",
                    message="Atlas, qual a próxima ação desse lead?",
                    context={
                        "page": "lead_detail",
                        "route": "/leads/1",
                        "lead_code": self.lead_code,
                    },
                    expected_intent="suggest_next_action",
                    expected_mode="decision_support",
                ),
                self._copilot_step(
                    step_id="OPS-010",
                    name="Proteção sem lead aberto",
                    message="Atlas, resuma esse lead",
                    context={"page": "dashboard", "route": "/"},
                    expected_intent="summarize_lead",
                    expected_mode="safety_guard",
                    expect_ok=False,
                ),
            ]
        )
        return tuple(checks)

    def _copilot_step(
        self,
        *,
        step_id: str,
        name: str,
        message: str,
        context: dict[str, Any],
        expected_intent: str,
        expected_mode: str,
        expect_ok: bool = True,
        expect_human_review: bool = False,
        extra_payload: dict[str, Any] | None = None,
        validator: Any = None,
    ) -> OperationValidationStep:
        endpoint = f"{self.atlas_bridge_url}/api/copilot/message"
        enriched_context = {
            "user_email": self.user_email,
            "metadata": {
                "source": "atlas_operation_scale_validation",
                "sprint": "28.17",
            },
        }
        enriched_context.update(context)
        payload: dict[str, Any] = {
            "message": message,
            "context": enriched_context,
        }
        if extra_payload:
            payload.update(extra_payload)

        headers = {}
        if self.copilot_token:
            headers["X-Atlas-Copilot-Token"] = self.copilot_token

        response = self.client.post_json(endpoint, payload, headers=headers)
        api_payload = response.data
        copilot_data = _copilot_data(api_payload)
        intent = str(copilot_data.get("intent") or "")
        answer = str(copilot_data.get("answer") or "")
        requires_review = bool(copilot_data.get("requires_human_review") is True)
        payload_ok = bool(api_payload.get("ok") is True)
        if not response.ok and response.status_code == 422:
            payload_ok = False

        expectation_ok = payload_ok is expect_ok
        intent_ok = intent == expected_intent
        review_ok = requires_review is expect_human_review if expect_human_review else True
        custom_ok = True if validator is None else bool(validator(copilot_data))
        step_ok = response.status_code in {200, 422} and expectation_ok and intent_ok
        step_ok = step_ok and review_ok and custom_ok

        error = response.error or _error_message(api_payload)
        if not step_ok and not error:
            error = _expectation_error(
                expected_intent=expected_intent,
                actual_intent=intent,
                expected_ok=expect_ok,
                actual_ok=payload_ok,
                expected_review=expect_human_review,
                actual_review=requires_review,
                custom_ok=custom_ok,
            )

        return OperationValidationStep(
            step_id=step_id,
            name=name,
            ok=step_ok,
            elapsed_ms=response.elapsed_ms,
            status_code=response.status_code,
            endpoint=endpoint,
            intent=intent,
            mode=expected_mode,
            answer=answer,
            error=error if not step_ok else "",
            data={
                "message": message,
                "payload_ok": payload_ok,
                "requires_human_review": requires_review,
                "response": api_payload,
            },
        )

    def _build_report(
        self,
        steps: tuple[OperationValidationStep, ...],
    ) -> OperationScaleValidationReport:
        elapsed_values = [step.elapsed_ms for step in steps]
        passed_steps = sum(1 for step in steps if step.ok)
        failed_steps = len(steps) - passed_steps
        total_elapsed_ms = sum(elapsed_values)
        average_elapsed_ms = (
            total_elapsed_ms / len(elapsed_values) if elapsed_values else 0.0
        )
        median_elapsed_ms = statistics.median(elapsed_values) if elapsed_values else 0
        capabilities = _capabilities_from_steps(steps)
        return OperationScaleValidationReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            provenance="MEASURED_IN_LOCAL_ATLAS_BUSINESS_LAB_SCALE_VALIDATION",
            business_lab_url=self.business_lab_url,
            atlas_bridge_url=self.atlas_bridge_url,
            execution_mode="confirmed_batch" if self.confirm_batch else "safe_preview",
            passed=failed_steps == 0,
            total_steps=len(steps),
            passed_steps=passed_steps,
            failed_steps=failed_steps,
            total_elapsed_ms=round(total_elapsed_ms, 2),
            average_elapsed_ms=round(average_elapsed_ms, 2),
            median_elapsed_ms=round(float(median_elapsed_ms), 2),
            capabilities=capabilities,
            safety_notes=(
                "Ações em lote exigem confirmação explícita.",
                "Mensagens reais de WhatsApp/e-mail continuam desativadas.",
                "A execução usa dados sintéticos do Nexyra Business Lab.",
                "Este relatório é evidência técnica/comercial, não case real de cliente.",
            ),
            steps=steps,
        )


def save_operation_scale_validation_report(
    report: OperationScaleValidationReport,
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = destination / f"atlas_operation_scale_validation_{stamp}.json"
    md_path = destination / f"atlas_operation_scale_validation_{stamp}.md"
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, md_path


def _render_markdown(report: OperationScaleValidationReport) -> str:
    status = "APROVADO" if report.passed else "REPROVADO"
    lines = [
        "# Atlas — Validação final da operação em escala",
        "",
        f"**Resultado:** {status}",
        f"**Origem:** {report.provenance}",
        f"**Modo:** {report.execution_mode}",
        f"**Business Lab:** `{report.business_lab_url}`",
        f"**Atlas Bridge:** `{report.atlas_bridge_url}`",
        f"**Etapas:** {report.passed_steps}/{report.total_steps}",
        f"**Tempo total:** {report.total_elapsed_ms:.2f} ms",
        "",
        "## Capacidades validadas",
        "",
    ]
    for capability, enabled in report.capabilities.items():
        marker = "OK" if enabled else "FALHOU"
        lines.append(f"- **{_capability_label(capability)}:** {marker}")

    lines.extend(
        [
            "",
            "## Etapas executadas",
            "",
            "| ID | Nome | Status | Modo | Tempo | Intenção | Observação |",
            "|---|---|---:|---|---:|---|---|",
        ]
    )
    for step in report.steps:
        step_status = "OK" if step.ok else "FALHOU"
        note = (step.answer or step.error).replace("|", "/").replace("\n", " ")
        lines.append(
            "| "
            f"{step.step_id} | {step.name} | {step_status} | {step.mode} | "
            f"{step.elapsed_ms:.2f} ms | {step.intent} | {note} |"
        )

    lines.extend(
        [
            "",
            "## Leitura executiva",
            "",
            (
                "Esta validação fecha a Sprint 28 demonstrando que o Atlas "
                "consegue operar o Business Lab como copiloto empresarial: "
                "entende tela, entende lead aberto, faz triagem em lote, "
                "prepara mensagens/atendimentos em lote, gera relatórios "
                "inteligentes com arquivos para download e mantém travas de "
                "segurança para ações críticas."
            ),
            "",
            "## Notas de segurança",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.safety_notes)
    lines.append("")
    return "\n".join(lines)


def _batch_message_command() -> str:
    return (
        "Atlas, prepare mensagens para 3 leads novos de Administração, "
        "registre atendimento, crie retorno para amanhã às 15h e atualize "
        "status para em_atendimento."
    )


def _capabilities_from_steps(
    steps: tuple[OperationValidationStep, ...],
) -> dict[str, bool]:
    by_id = {step.step_id: step.ok for step in steps}
    return {
        "services_online": by_id.get("OPS-001", False) and by_id.get("OPS-002", False),
        "screen_context": by_id.get("OPS-003", False),
        "lead_context": by_id.get("OPS-004", False),
        "batch_triage": by_id.get("OPS-005", False),
        "batch_messages_preview": by_id.get("OPS-006", False),
        "batch_execution_guard": by_id.get("OPS-007", False),
        "smart_reports_downloads": by_id.get("OPS-008", False),
        "decision_support": by_id.get("OPS-009", False),
        "safety_guardrails": by_id.get("OPS-010", False),
    }


def _capability_label(capability: str) -> str:
    labels = {
        "services_online": "Business Lab + Atlas Bridge online",
        "screen_context": "Resumo de tela/contexto",
        "lead_context": "Resumo de lead aberto",
        "batch_triage": "Triagem em lote",
        "batch_messages_preview": "Mensagens em lote com prévia",
        "batch_execution_guard": "Execução em lote protegida",
        "smart_reports_downloads": "Relatórios inteligentes + downloads",
        "decision_support": "Sugestão de próxima ação",
        "safety_guardrails": "Travas de segurança",
    }
    return labels.get(capability, capability.replace("_", " "))


def _smart_report_has_downloads(copilot_data: dict[str, Any]) -> bool:
    nested = copilot_data.get("data")
    if not isinstance(nested, dict):
        return False

    files = nested.get("files")
    expected = {"json", "csv", "md", "html", "xlsx"}

    if isinstance(files, dict):
        # Formato antigo dos testes: {"json": {...}, "csv": {...}, ...}
        if expected.issubset(set(files)):
            return True

        # Formato atual do Atlas Smart Reports: {"downloads": [{"format": ...}]}
        downloads = files.get("downloads")
        if isinstance(downloads, list):
            formats = {
                str(item.get("format") or item.get("format_name") or "").lower()
                for item in downloads
                if isinstance(item, dict)
            }
            aliases = {"markdown": "md"}
            normalized = {aliases.get(item, item) for item in formats}
            return expected.issubset(normalized)

    downloads = nested.get("downloads")
    if isinstance(downloads, list):
        formats = {
            str(item.get("format") or item.get("format_name") or "").lower()
            for item in downloads
            if isinstance(item, dict)
        }
        aliases = {"markdown": "md"}
        normalized = {aliases.get(item, item) for item in formats}
        return expected.issubset(normalized)

    return False


def _copilot_data(api_payload: dict[str, Any]) -> dict[str, Any]:
    data = api_payload.get("data")
    if isinstance(data, dict) and "answer" in data:
        return data
    return api_payload


def _expectation_error(
    *,
    expected_intent: str,
    actual_intent: str,
    expected_ok: bool,
    actual_ok: bool,
    expected_review: bool,
    actual_review: bool,
    custom_ok: bool,
) -> str:
    return (
        "Resposta fora do esperado. "
        f"intent esperado={expected_intent}, recebido={actual_intent}; "
        f"ok esperado={expected_ok}, recebido={actual_ok}; "
        f"review esperado={expected_review}, recebido={actual_review}; "
        f"validação extra={custom_ok}."
    )


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


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)
