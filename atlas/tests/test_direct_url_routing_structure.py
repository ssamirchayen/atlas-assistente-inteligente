from pathlib import Path


def test_direct_url_is_routed_before_controller_and_skill_router() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    execute_start = source.index("def execute(self, command: str)")
    url_pos = source.index("extract_direct_url_command(", execute_start)
    controller_pos = source.index("self.controller.execute(", execute_start)
    priority_pos = source.index("self.kernel.router.route_priority(", execute_start)

    assert url_pos < priority_pos < controller_pos


def test_direct_url_uses_controlled_browser_not_os_shell() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    start = source.index("direct_url = extract_direct_url_command")
    end = source.index("form_request = extract_structured_form", start)
    region = source[start:end]

    assert "self.kernel.automation.browser.open_url" in region
    assert "subprocess" not in region
    assert "os.system" not in region
    assert "shell=True" not in region
