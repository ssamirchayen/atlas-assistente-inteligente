from atlas.vision.uia_grounding import (
    _set_structural_uia_text,
    _target_state,
)


class _ElementInfo:
    control_type = "Edit"
    is_password = False
    name = "Campo Nome"


class _EditWrapper:
    element_info = _ElementInfo()

    def is_enabled(self) -> bool:
        return True

    def has_keyboard_focus(self) -> bool:
        return True

    def get_value(self) -> str:
        return "Atlas"

    def set_edit_text(self, text: str) -> None:
        self.value = text


class _PasswordElementInfo(_ElementInfo):
    is_password = True


class _PasswordWrapper(_EditWrapper):
    element_info = _PasswordElementInfo()


def test_sets_text_with_structural_edit_pattern() -> None:
    wrapper = _EditWrapper()

    assert _set_structural_uia_text(wrapper, "Atlas 10") is True
    assert wrapper.value == "Atlas 10"


def test_password_field_is_blocked_and_hidden_from_state() -> None:
    wrapper = _PasswordWrapper()

    assert _set_structural_uia_text(wrapper, "segredo") is False
    state = _target_state(wrapper)
    assert state["is_password"] is True
    assert state["value"] == ""
