from __future__ import annotations

import json

from atlas.copilot.operation_scale_validation import (
    AtlasOperationScaleValidator,
    HttpJsonResponse,
    OperationScaleValidationReport,
    save_operation_scale_validation_report,
)


class FakeClient:
    def __init__(self) -> None:
        self.posts: list[dict] = []

    def get_json(self, url: str) -> HttpJsonResponse:
        return HttpJsonResponse(
            ok=True,
            status_code=200,
            data={"ok": True, "data": {"status": "ok"}},
            elapsed_ms=1.0,
        )

    def post_json(
        self,
        url: str,
        payload: dict,
        *,
        headers: dict[str, str] | None = None,
    ) -> HttpJsonResponse:
        self.posts.append(payload)
        message = str(payload.get("message") or "").lower()
        intent = "help"
        data = {}
        requires_human_review = False
        payload_ok = True
        answer = "OK"

        if "resuma essa tela" in message:
            intent = "summarize_screen"
            answer = "Resumo da tela de leads."
        elif "resuma esse lead" in message and payload["context"].get("lead_code"):
            intent = "summarize_lead"
            answer = "Resumo do lead SIM-00001."
        elif "resuma esse lead" in message:
            intent = "summarize_lead"
            payload_ok = False
            answer = "Nenhum lead aberto."
        elif "triagem" in message or "analise os" in message:
            intent = "batch_lead_triage"
            answer = "Triagem em lote gerada."
        elif "prepare mensagens" in message:
            intent = "batch_messages"
            if payload.get("confirmed") is True:
                answer = "Execução em lote concluída."
                data = {"execution": {"interaction_success": 3}}
            else:
                answer = "Prévia de mensagens em lote."
                requires_human_review = True
                data = {"confirmation_required": True}
        elif "relatório" in message or "relatorio" in message:
            intent = "smart_reports"
            answer = "Relatório inteligente gerado."
            data = {
                "files": {
                    "json": {"url": "/api/copilot/reports/a.json"},
                    "csv": {"url": "/api/copilot/reports/a.csv"},
                    "md": {"url": "/api/copilot/reports/a.md"},
                    "html": {"url": "/api/copilot/reports/a.html"},
                    "xlsx": {"url": "/api/copilot/reports/a.xlsx"},
                }
            }
        elif "próxima ação" in message or "proxima acao" in message:
            intent = "suggest_next_action"
            answer = "Próxima ação recomendada."

        return HttpJsonResponse(
            ok=payload_ok,
            status_code=200 if payload_ok else 422,
            data={
                "ok": payload_ok,
                "data": {
                    "answer": answer,
                    "intent": intent,
                    "data": data,
                    "requires_human_review": requires_human_review,
                },
            },
            elapsed_ms=2.0,
        )


def test_operation_scale_validation_safe_preview_passes() -> None:
    client = FakeClient()
    validator = AtlasOperationScaleValidator(client=client)

    report = validator.run()

    assert report.passed is True
    assert report.execution_mode == "safe_preview"
    assert report.passed_steps == report.total_steps
    assert report.capabilities["batch_triage"] is True
    assert report.capabilities["smart_reports_downloads"] is True
    assert all(post.get("confirmed") is not True for post in client.posts)


def test_operation_scale_validation_can_confirm_batch_when_requested() -> None:
    client = FakeClient()
    validator = AtlasOperationScaleValidator(client=client, confirm_batch=True)

    report = validator.run()

    assert report.passed is True
    assert report.execution_mode == "confirmed_batch"
    assert any(post.get("confirmed") is True for post in client.posts)


def test_operation_scale_validation_reports_offline_services() -> None:
    class OfflineClient(FakeClient):
        def get_json(self, url: str) -> HttpJsonResponse:
            return HttpJsonResponse(
                ok=False,
                status_code=0,
                data={},
                elapsed_ms=1.0,
                error="offline",
            )

    report = AtlasOperationScaleValidator(client=OfflineClient()).run()

    assert report.passed is False
    assert report.failed_steps >= 1
    assert any(step.step_id == "OPS-000" for step in report.steps)


def test_save_operation_scale_validation_report(tmp_path) -> None:
    report = AtlasOperationScaleValidator(client=FakeClient()).run()

    json_path, md_path = save_operation_scale_validation_report(
        report,
        output_dir=tmp_path,
    )

    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["provenance"] == (
        "MEASURED_IN_LOCAL_ATLAS_BUSINESS_LAB_SCALE_VALIDATION"
    )
    assert "Validação final da operação em escala" in md_path.read_text(
        encoding="utf-8"
    )


def test_report_type_is_structured() -> None:
    report = AtlasOperationScaleValidator(client=FakeClient()).run()

    assert isinstance(report, OperationScaleValidationReport)
    assert report.capabilities["safety_guardrails"] is True
    assert "WhatsApp/e-mail" in " ".join(report.safety_notes)
