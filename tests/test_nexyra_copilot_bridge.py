from __future__ import annotations

from concurrent.futures import Future

from atlas.copilot.nexyra_bridge import NexyraCopilotBridge
from atlas.gui.service import GuiCommandResult


def _future(result: GuiCommandResult) -> Future[GuiCommandResult]:
    future: Future[GuiCommandResult] = Future()
    future.set_result(result)
    return future


def test_nexyra_copilot_bridge_returns_atlas_result() -> None:
    seen: list[str] = []

    def submit(command: str) -> Future[GuiCommandResult]:
        seen.append(command)
        return _future(
            GuiCommandResult(
                message="Existem 3 leads com SLA estourada.",
                source="nexyra_crm",
                action_count=1,
            )
        )

    bridge = NexyraCopilotBridge(submit)
    response = bridge.handle(
        {
            "message": "Quais leads estão com SLA estourada?",
            "context": {"page": "atlas-copilot", "route": "/atlas-copilot"},
        }
    )

    assert seen == ["Quais leads estão com SLA estourada?"]
    assert response.ok is True
    assert response.answer == "Existem 3 leads com SLA estourada."
    assert response.context is not None
    assert response.context.page == "atlas-copilot"
    assert response.data["source"] == "nexyra_crm"
    assert response.requires_human_review is False


def test_nexyra_copilot_bridge_preserves_confirmation_state() -> None:
    bridge = NexyraCopilotBridge(
        lambda _command: _future(
            GuiCommandResult(
                message="Prévia pronta. Confirme com sim.",
                source="nexyra_crm",
                requires_confirmation=True,
                confirmation_token="confirm-123",
            )
        )
    )

    response = bridge.handle({"message": "Nexyra prévia distribuir 10"})

    assert response.ok is True
    assert response.requires_human_review is True
    assert response.data["requires_confirmation"] is True
    assert response.data["confirmation_token"] == "confirm-123"


def test_nexyra_copilot_bridge_rejects_empty_message() -> None:
    bridge = NexyraCopilotBridge(
        lambda _command: _future(
            GuiCommandResult(message="não deveria executar", source="test")
        )
    )

    response = bridge.handle({"message": "  "})

    assert response.ok is False
    assert response.intent == "empty_message"
