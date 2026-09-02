from types import MethodType

from atlas.gui.service import AtlasGuiService, GuiCommandResult
from atlas.vision.option_select_intent import (
    StructuredContextualFormRequest,
    StructuredOptionSelectionRequest,
)
from atlas.vision.text_input_intent import StructuredTextInputRequest


def test_contextual_flow_reuses_context_for_fill_and_select() -> None:
    service = object.__new__(AtlasGuiService)
    required_tokens: list[str | None] = []
    turns: list[tuple[str, str]] = []

    request = StructuredContextualFormRequest(
        fields=(StructuredTextInputRequest(target="campo nome", text="Ssamir"),),
        selections=(
            StructuredOptionSelectionRequest(
                target="campo estado",
                option="Amazonas",
            ),
        ),
    )

    def fake_fill(
        self,
        clean_command,
        operation,
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

    def fake_select(
        self,
        clean_command,
        operation,
        *,
        record_turn=True,
        required_context_token=None,
    ):
        required_tokens.append(required_context_token)
        return GuiCommandResult(
            message="ok",
            source="vision_select_dom",
            success=True,
            action_count=1,
            context_token="dom:123",
        )

    service._execute_structured_text_input = MethodType(fake_fill, service)
    service._execute_structured_option_selection = MethodType(fake_select, service)
    service._add_turn = MethodType(
        lambda self, user, assistant: turns.append((user, assistant)),
        service,
    )

    result = service._execute_contextual_form("teste", request)

    assert result.success is True
    assert result.action_count == 2
    assert required_tokens == [None, "dom:123"]
    assert len(turns) == 1
    assert "Nenhum envio" in result.message
