from pathlib import Path

from atlas.vision.dom_grounding import (
    BrowserDomMatch,
)


def test_browser_dom_match_keeps_fingerprint() -> None:
    fields = BrowserDomMatch.__dataclass_fields__

    assert "fingerprint" in fields
    assert hasattr(
        BrowserDomMatch,
        "click_fingerprint",
    )


def test_click_revalidates_dom_identity() -> None:
    source = Path(
        "atlas/automation/browser.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "def click_interactive_element("
    )
    end = source.index(
        "# INTERAÇÃO",
        start,
    )
    method = source[start:end]

    assert "resolver_script" in method
    assert "aria_label: 10" in method
    assert "name: 9" in method
    assert "bestScore >= 0.62" in method
    assert "trial=True" in method


def test_click_allows_only_bounded_retry() -> None:
    source = Path(
        "atlas/automation/browser.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "def click_interactive_element("
    )
    end = source.index(
        "# INTERAÇÃO",
        start,
    )
    method = source[start:end]

    assert "for attempt in range(2):" in method


def test_service_regrounds_once_after_failed_click() -> None:
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

    assert "retry_match = find_browser_dom_match(" in flow
    assert "retry_match.confidence >= 0.85" in flow
    assert "match.click_fingerprint()" in flow
    assert "retry_match.click_fingerprint()" in flow


def test_click_still_has_no_qwen_coordinate_fallback() -> None:
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

    assert "pyautogui.click" not in flow
    assert "locate_on_screen(" not in flow
