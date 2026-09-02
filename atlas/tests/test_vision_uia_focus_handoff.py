from dataclasses import dataclass
from pathlib import Path

from atlas.vision.uia_grounding import _external_target_window


@dataclass
class _Info:
    process_id: int
    class_name: str
    name: str


class _Window:
    def __init__(
        self,
        *,
        process_id: int,
        title: str,
        handle: int,
        class_name: str = "Window",
        visible: bool = True,
    ) -> None:
        self.element_info = _Info(process_id, class_name, title)
        self._title = title
        self.handle = handle
        self._visible = visible

    def window_text(self) -> str:
        return self._title

    def is_visible(self) -> bool:
        return self._visible


class _Desktop:
    def __init__(self, active: _Window, windows: list[_Window]) -> None:
        self._active = active
        self._windows = windows

    def get_active(self) -> _Window:
        return self._active

    def windows(self, **_kwargs) -> list[_Window]:
        return self._windows


def test_uia_uses_external_window_when_atlas_has_focus(monkeypatch) -> None:
    import atlas.vision.uia_grounding as uia

    current_pid = 900
    monkeypatch.setattr(uia.os, "getpid", lambda: current_pid)

    atlas = _Window(process_id=current_pid, title="Atlas", handle=10)
    notepad = _Window(process_id=901, title="Sem título - Bloco de Notas", handle=20)
    desktop = _Desktop(atlas, [atlas, notepad])

    assert _external_target_window(desktop) is notepad


def test_uia_keeps_external_foreground_when_it_is_active(monkeypatch) -> None:
    import atlas.vision.uia_grounding as uia

    monkeypatch.setattr(uia.os, "getpid", lambda: 900)

    atlas = _Window(process_id=900, title="Atlas", handle=10)
    notepad = _Window(process_id=901, title="Sem título - Bloco de Notas", handle=20)
    desktop = _Desktop(notepad, [notepad, atlas])

    assert _external_target_window(desktop) is notepad


def test_gui_external_structural_grounding_wins_over_generic_qt_match() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    start = source.index("selected_grounding = None")
    end = source.index("if selected_grounding is not None", start)
    selection = source[start:end]

    assert selection.index("dom_grounding") < selection.index("uia_grounding")
    assert selection.index("uia_grounding") < selection.rindex("qt_grounding")
