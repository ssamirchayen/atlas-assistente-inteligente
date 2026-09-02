from dataclasses import dataclass

from atlas.vision.uia_grounding import (
    _perform_structural_uia_action,
    _score_uia_candidate,
    _target_state,
)


@dataclass
class _Info:
    name: str = ""
    automation_id: str = ""
    control_type: str = ""
    class_name: str = ""
    help_text: str = ""
    access_key: str = ""


class _Checkbox:
    def __init__(self, checked: int = 0) -> None:
        self.element_info = _Info(name="Modo escuro", control_type="CheckBox")
        self.checked = checked

    def get_toggle_state(self) -> int:
        return self.checked

    def toggle(self) -> None:
        self.checked = 0 if self.checked == 1 else 1

    def is_enabled(self) -> bool:
        return True

    def has_keyboard_focus(self) -> bool:
        return False


class _Selectable:
    def __init__(self) -> None:
        self.element_info = _Info(name="Exibir", control_type="TabItem")
        self.selected = False

    def is_selected(self) -> bool:
        return self.selected

    def select(self) -> None:
        self.selected = True

    def is_enabled(self) -> bool:
        return True

    def has_keyboard_focus(self) -> bool:
        return False


class _Expandable:
    def __init__(self) -> None:
        self.element_info = _Info(name="Arquivo", control_type="MenuItem")
        self.expanded = 0

    def get_expand_state(self) -> int:
        return self.expanded

    def expand(self) -> None:
        self.expanded = 1

    def collapse(self) -> None:
        self.expanded = 0

    def is_enabled(self) -> bool:
        return True

    def has_keyboard_focus(self) -> bool:
        return False


def test_checkbox_semantics_receive_strong_type_bonus() -> None:
    candidate = {
        "name": "Modo escuro",
        "control_type": "CheckBox",
        "enabled": True,
    }

    assert _score_uia_candidate(
        "caixa de seleção modo escuro", candidate
    ) >= 0.85


def test_tab_semantics_receive_strong_type_bonus() -> None:
    candidate = {
        "name": "Exibir",
        "control_type": "TabItem",
        "enabled": True,
    }

    assert _score_uia_candidate("aba Exibir", candidate) >= 0.85


def test_check_action_is_idempotent() -> None:
    wrapper = _Checkbox(checked=0)

    first = _perform_structural_uia_action(wrapper, "check")
    second = _perform_structural_uia_action(wrapper, "check")

    assert first.executed is True
    assert wrapper.checked == 1
    assert second.executed is False
    assert second.already_satisfied is True


def test_select_action_uses_selection_pattern() -> None:
    wrapper = _Selectable()

    result = _perform_structural_uia_action(wrapper, "select")

    assert result.executed is True
    assert wrapper.selected is True
    assert _target_state(wrapper)["selected"] is True


def test_expand_and_collapse_are_structural() -> None:
    wrapper = _Expandable()

    expanded = _perform_structural_uia_action(wrapper, "expand")
    state_after_expand = _target_state(wrapper)
    collapsed = _perform_structural_uia_action(wrapper, "collapse")

    assert expanded.executed is True
    assert state_after_expand["expanded"] == 1
    assert collapsed.executed is True
    assert wrapper.expanded == 0


class _ModernMenuButton:
    def __init__(self) -> None:
        self.element_info = _Info(name="Arquivo", control_type="Button")
        self.invoked = False

    def invoke(self) -> None:
        self.invoked = True

    def is_enabled(self) -> bool:
        return True

    def has_keyboard_focus(self) -> bool:
        return False


def test_modern_menu_button_can_open_with_structural_invoke() -> None:
    wrapper = _ModernMenuButton()

    result = _perform_structural_uia_action(
        wrapper,
        "expand",
        semantic_kind="menu",
    )

    assert result.executed is True
    assert result.reason_code == "uia_expand_invoked"
    assert wrapper.invoked is True


def test_modern_menu_button_receives_menu_semantic_bonus() -> None:
    candidate = {
        "name": "Arquivo",
        "control_type": "Button",
        "enabled": True,
    }

    assert _score_uia_candidate("menu Arquivo", candidate) >= 0.85
