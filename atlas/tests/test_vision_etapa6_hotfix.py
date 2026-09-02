from pathlib import Path


def test_read_only_dom_inspection_region_has_no_click() -> None:
    source = Path(
        "atlas/automation/browser.py"
    ).read_text(encoding="utf-8")

    inspect_pos = source.index(
        "def inspect_visible_interactive_elements"
    )
    first_interaction = source.index(
        "# INTERAÇÃO",
        inspect_pos,
    )

    inspection = source[
        inspect_pos:first_interaction
    ]

    assert ".click(" not in inspection
    assert ".fill(" not in inspection


def test_click_method_is_bounded_by_interaction_markers() -> None:
    source = Path(
        "atlas/automation/browser.py"
    ).read_text(encoding="utf-8")

    click_pos = source.index(
        "def click_interactive_element("
    )

    interaction_before = source.rfind(
        "# INTERAÇÃO",
        0,
        click_pos,
    )
    interaction_after = source.index(
        "# INTERAÇÃO",
        click_pos,
    )

    assert interaction_before != -1
    assert interaction_after > click_pos


def test_service_checks_runtime_before_dom_click() -> None:
    source = Path(
        "atlas/gui/service.py"
    ).read_text(encoding="utf-8")

    click_pos = source.index(
        "click_target = extract_click_target("
    )
    guard_pos = source.index(
        "self._supports_controlled_dom_click()",
        click_pos,
    )
    router_pos = source.index(
        "priority_result =",
        click_pos,
    )

    assert click_pos < guard_pos < router_pos
    assert "def _supports_controlled_dom_click(" in source
