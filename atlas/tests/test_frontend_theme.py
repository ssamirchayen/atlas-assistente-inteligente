from pathlib import Path

from atlas.gui.theme import (
    MESSAGE_PALETTE,
    STATUS_PALETTE,
    VERSION_LABEL,
    application_stylesheet,
)


def test_frontend_theme_exposes_premium_product_identity() -> None:
    assert "ATLAS CORE 1.0" in VERSION_LABEL
    assert "SPRINT 26" in VERSION_LABEL
    assert "PREMIUM UI" in VERSION_LABEL


def test_frontend_theme_has_status_contract() -> None:
    required = {
        "ONLINE",
        "ESCUTA ATIVA",
        "OUVINDO",
        "EXECUTANDO",
        "PROCESSANDO",
        "FALANDO",
        "CONCLUÍDO",
        "ERRO",
        "DEFAULT",
    }
    assert required.issubset(STATUS_PALETTE)


def test_frontend_theme_has_message_roles() -> None:
    assert {"user", "atlas", "system"}.issubset(MESSAGE_PALETTE)


def test_stylesheet_contains_premium_shell() -> None:
    stylesheet = application_stylesheet()
    for selector in (
        "QFrame#sidebar",
        "QFrame#conversationCard",
        "QFrame#heroMetricCard",
        "QLabel#pulseOrb",
        "QLineEdit#commandInput",
        "QPushButton#primaryButton",
        "QPushButton#quickButton",
    ):
        assert selector in stylesheet


def test_theme_is_dark_first() -> None:
    stylesheet = application_stylesheet()
    assert "background: #080D15" in stylesheet
    assert "background: #070B12" in stylesheet
    assert "background: #0A1019" in stylesheet


def test_window_keeps_operational_controls() -> None:
    window_path = Path(__file__).parents[1] / "gui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    for control in (
        "self.history_button",
        "self.admin_button",
        "self.resume_button",
        "self.cancel_button",
        "self.continuous_button",
        "self.send_button",
        "self.workflow_label",
        "self.cpu_bar",
        "self.ram_bar",
    ):
        assert control in source


def test_window_keeps_core_service_integration() -> None:
    window_path = Path(__file__).parents[1] / "gui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    assert "AtlasGuiService" in source
    assert "SerialCommandRunner" in source
    assert "self.service.execute" in source
    assert "self.service.cancel()" in source
