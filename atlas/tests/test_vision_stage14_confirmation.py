from datetime import datetime, timedelta, timezone

import pytest

from atlas.vision.final_action import (
    VisionConfirmationError,
    VisionConfirmationStore,
    extract_final_action_confirmation,
    extract_final_action_request,
)


def test_extracts_submit_and_confirmation_commands() -> None:
    request = extract_final_action_request("enviar o formulário")

    assert request is not None
    assert request.target == "botão enviar"
    assert extract_final_action_confirmation(
        "CONFIRMAR VISÃO TOKEN123"
    ) == "TOKEN123"


@pytest.mark.parametrize(
    "command",
    ["pagar compra", "excluir cadastro", "confirmar transferência"],
)
def test_does_not_prepare_high_risk_final_actions(command: str) -> None:
    assert extract_final_action_request(command) is None


def test_confirmation_is_bound_and_single_use() -> None:
    store = VisionConfirmationStore(token_factory=lambda: "TOKEN123")
    pending = store.prepare(
        target="botão enviar",
        action="submit",
        context_token="dom:1",
        dom_index=4,
        fingerprint={"tag": "button", "text": "Enviar"},
    )

    consumed = store.consume("TOKEN123")

    assert consumed == pending
    assert consumed.fingerprint_dict()["text"] == "Enviar"
    with pytest.raises(VisionConfirmationError):
        store.consume("TOKEN123")


def test_expired_confirmation_is_rejected() -> None:
    now = [datetime(2026, 8, 30, tzinfo=timezone.utc)]
    store = VisionConfirmationStore(
        ttl_seconds=10,
        clock=lambda: now[0],
        token_factory=lambda: "TOKEN123",
    )
    store.prepare(
        target="botão enviar",
        action="submit",
        context_token="dom:1",
        dom_index=1,
        fingerprint={},
    )
    now[0] += timedelta(seconds=10)

    with pytest.raises(VisionConfirmationError, match="expirou"):
        store.consume("TOKEN123")

