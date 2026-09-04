from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_window_exposes_admin_console_button() -> None:
    source = (ROOT / "atlas" / "gui" / "window.py").read_text(encoding="utf-8")
    assert 'QPushButton("Admin Console")' in source
    assert "self.show_admin_console" in source


def test_window_uses_same_kernel_through_admin_service() -> None:
    source = (ROOT / "atlas" / "gui" / "window.py").read_text(encoding="utf-8")
    assert "AdminConsoleService(self.service.kernel)" in source


def test_console_has_no_mutating_controls() -> None:
    source = (ROOT / "atlas" / "gui" / "admin_console.py").read_text(
        encoding="utf-8"
    )
    forbidden = ("terminate", "kill", "install", "delete", "reset_failure")
    assert not any(item in source.casefold() for item in forbidden)


def test_console_does_not_use_threads_to_touch_widgets() -> None:
    source = (ROOT / "atlas" / "gui" / "admin_console.py").read_text(
        encoding="utf-8"
    )
    assert "threading" not in source
    assert "QTimer" in source


def test_admin_service_does_not_load_lazy_brain() -> None:
    source = (ROOT / "atlas" / "admin" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "_brain_component.peek()" in source
    assert "_brain_component.get()" not in source


def test_admin_service_does_not_read_environment_or_secrets() -> None:
    source = (ROOT / "atlas" / "admin" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "os.environ" not in source
    assert ".env" not in source
    assert "API_ADMIN_KEY" not in source


def test_admin_console_is_not_exposed_as_public_api() -> None:
    source = (ROOT / "atlas" / "api" / "app.py").read_text(encoding="utf-8")
    assert '"/admin"' not in source
    assert '"/admin/' not in source

