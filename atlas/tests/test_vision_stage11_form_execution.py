from types import MethodType

from atlas.gui.service import AtlasGuiService, GuiCommandResult
from atlas.vision.form_intent import StructuredFormRequest
from atlas.vision.text_input_intent import StructuredTextInputRequest


def _request() -> StructuredFormRequest:
    return StructuredFormRequest(
        fields=(
            StructuredTextInputRequest(target="campo nome", text="Ssamir"),
            StructuredTextInputRequest(target="campo cidade", text="Manaus"),
        )
    )


def test_form_reuses_same_structural_context() -> None:
    service = object.__new__(AtlasGuiService)
    required_tokens: list[str | None] = []
    turns: list[tuple[str, str]] = []

    def fake_fill(
        self,
        clean_command,
        request,
        *,
        record_turn=True,
        required_context_token=None,
    ):
        required_tokens.append(required_context_token)
        return GuiCommandResult(
            message="ok",
            source="vision_fill_dom",
            success=True,
            action_count=1,
            context_token="dom:123",
        )

    def fake_turn(self, user, assistant):
        turns.append((user, assistant))

    service._execute_structured_text_input = MethodType(fake_fill, service)
    service._add_turn = MethodType(fake_turn, service)

    result = service._execute_structured_form("preencha o formulário", _request())

    assert result.success is True
    assert result.action_count == 2
    assert required_tokens == [None, "dom:123"]
    assert len(turns) == 1
    assert "Nenhum envio" in result.message


def test_form_stops_if_context_changes_between_fields() -> None:
    service = object.__new__(AtlasGuiService)
    contexts = iter(("dom:123", "dom:999"))

    def fake_fill(
        self,
        clean_command,
        request,
        *,
        record_turn=True,
        required_context_token=None,
    ):
        return GuiCommandResult(
            message="ok",
            source="vision_fill_dom",
            success=True,
            action_count=1,
            context_token=next(contexts),
        )

    service._execute_structured_text_input = MethodType(fake_fill, service)
    service._add_turn = MethodType(lambda self, user, assistant: None, service)

    result = service._execute_structured_form("preencha o formulário", _request())

    assert result.success is False
    assert result.reason_code == "vision_form_context_changed"
    assert result.action_count == 2
