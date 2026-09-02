from pathlib import Path


def test_browser_exposes_read_only_interaction_state() -> None:
    source = Path(
        "atlas/automation/browser.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "def inspect_interaction_state("
    )
    end = source.index(
        "# INTERAÇÃO",
        start,
    )
    method = source[start:end]

    assert "document.activeElement" in method
    assert "dialog_count" in method
    assert "expanded_count" in method
    assert ".click(" not in method
    assert ".fill(" not in method


def test_service_verifies_after_click_without_second_post_action_click() -> None:
    source = Path(
        "atlas/gui/service.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "click_target = extract_click_target("
    )
    end = source.index(
        "priority_result =",
        start,
    )
    flow = source[start:end]

    assert "before_state = self._inspect_click_state" in flow
    assert "self._verify_click_post_action(" in flow
    assert "verification.verified" in flow
    assert "action_performed" in flow
    assert "Não repeti o clique" in flow
    assert "duplicada." in flow


def test_validation_lab_promotes_stage_7_to_manual_e2e() -> None:
    source = Path(
        "validation/scenarios/vision.json"
    ).read_text(encoding="utf-8")

    assert '"id": "VISION-004"' in source
    assert '"phase": "vision-stage-7"' in source
