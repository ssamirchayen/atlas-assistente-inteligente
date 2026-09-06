from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.copilot.visual_validation import (
    AtlasCopilotVisualValidator,
    HttpJsonResponse,
    save_visual_validation_report,
)


class FakeClient:
    def __init__(self, *, bridge_online: bool = True) -> None:
        self.bridge_online = bridge_online
        self.posts: list[dict[str, Any]] = []

    def get_json(self, url: str) -> HttpJsonResponse:
        if url.endswith(":8765/health") and not self.bridge_online:
            return HttpJsonResponse(
                ok=False,
                status_code=0,
                data={},
                elapsed_ms=1.0,
                error="offline",
            )
        return HttpJsonResponse(
            ok=True,
            status_code=200,
            data={"ok": True, "data": {"status": "ok"}},
            elapsed_ms=2.0,
        )

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> HttpJsonResponse:
        self.posts.append(
            {
                "url": url,
                "payload": payload,
                "headers": headers or {},
            }
        )
        return HttpJsonResponse(
            ok=True,
            status_code=200,
            data={
                "ok": True,
                "intent": "fake_intent",
                "answer": "Resposta simulada do Atlas.",
            },
            elapsed_ms=3.0,
        )


def test_visual_validator_builds_success_report() -> None:
    fake_client = FakeClient()
    validator = AtlasCopilotVisualValidator(client=fake_client)

    report = validator.run()

    assert report.passed is True
    assert report.total_steps == 8
    assert report.passed_steps == 8
    assert len(fake_client.posts) == 6


def test_visual_validator_sends_page_context_and_dry_run_actions() -> None:
    fake_client = FakeClient()
    validator = AtlasCopilotVisualValidator(
        client=fake_client,
        lead_code="SIM-00001",
        user_email="consultor@nexyra.lab",
        copilot_token="local-token",
    )

    report = validator.run()

    assert report.passed is True
    assert fake_client.posts[0]["payload"]["context"]["lead_code"] == "SIM-00001"
    assert fake_client.posts[0]["headers"]["X-Atlas-Copilot-Token"] == "local-token"
    assert fake_client.posts[-2]["payload"]["dry_run"] is True
    assert fake_client.posts[-1]["payload"]["dry_run"] is True


def test_visual_validator_stops_when_bridge_is_offline() -> None:
    fake_client = FakeClient(bridge_online=False)
    validator = AtlasCopilotVisualValidator(client=fake_client)

    report = validator.run()

    assert report.passed is False
    assert report.failed_steps >= 1
    assert fake_client.posts == []


def test_save_visual_validation_report_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    fake_client = FakeClient()
    validator = AtlasCopilotVisualValidator(client=fake_client)
    report = validator.run()

    json_path, md_path = save_visual_validation_report(report, output_dir=tmp_path)

    assert json_path.exists()
    assert md_path.exists()
    assert "APROVADO" in md_path.read_text(encoding="utf-8")
    assert "MEASURED_IN_LOCAL_ATLAS_BUSINESS_LAB_COPILOT" in json_path.read_text(
        encoding="utf-8"
    )
