"""Automation and Vision benchmark executors for Sprint 27 stage 5.

The default suite is intentionally non-destructive. Automation actions are
restricted to the benchmark scratch directory, while live Vision probes are
read-only and opt-in through ``--live``.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .runner import BenchmarkContext, BenchmarkRunner

EngineFactory = Callable[[], Any]


def _is_loopback_http_endpoint(url: str) -> bool:
    parsed = urlparse(str(url).strip())
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    )


def register_automation_vision_executors(
    runner: BenchmarkRunner,
    *,
    live: bool = False,
    vision_timeout_s: float = 120.0,
) -> None:
    """Register safe automation checks and optional live Vision probes."""

    timeout = float(vision_timeout_s)
    if timeout <= 0:
        raise ValueError("vision_timeout_s must be positive")

    runner.register_executor("automation.url_intent", _direct_url_intent)
    runner.register_executor("automation.domain_generators", _domain_generators)
    runner.register_executor("automation.file_sandbox", _automation_file_sandbox)
    runner.register_executor(
        "automation.engine_contract",
        partial(_automation_engine_contract, live=live),
    )
    runner.register_executor("vision.intent_routes", _vision_intent_routes)
    runner.register_executor("vision.structured_intents", _structured_intents)
    runner.register_executor("vision.synthetic_grounding", _synthetic_grounding)
    runner.register_executor("vision.post_action", _post_action_verification)
    runner.register_executor("vision.synthetic_capture", _synthetic_capture)
    runner.register_executor(
        "vision.live_capture",
        partial(_live_capture, live=live),
    )
    runner.register_executor(
        "vision.live_analysis",
        partial(
            _live_analysis,
            live=live,
            timeout_s=timeout,
        ),
    )


def _direct_url_intent(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    from atlas.automation.url_intent import extract_direct_url_command

    raw_samples = case.parameters.get("samples", ())
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("samples parameter must be a non-empty list")

    passed_count = 0
    positives = 0
    true_positives = 0
    negatives = 0
    true_negatives = 0

    for sample in raw_samples:
        if not isinstance(sample, dict):
            continue
        command = str(sample.get("input", ""))
        expected_url = sample.get("expected_url")
        request = extract_direct_url_command(command)
        expected_positive = expected_url is not None
        matched = (
            request is not None
            and request.url == str(expected_url)
            if expected_positive
            else request is None
        )
        passed_count += int(matched)

        if expected_positive:
            positives += 1
            true_positives += int(request is not None)
        else:
            negatives += 1
            true_negatives += int(request is None)

    total = len(raw_samples)
    score = round(passed_count / total * 100.0, 3)
    recall = round(true_positives / positives * 100.0, 3) if positives else 100.0
    specificity = (
        round(true_negatives / negatives * 100.0, 3) if negatives else 100.0
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "samples_total": total,
            "samples_passed": passed_count,
            "intent_accuracy_pct": score,
            "positive_recall_pct": recall,
            "negative_specificity_pct": specificity,
        },
        details=(f"Direct URL intent matched {passed_count}/{total} samples.",),
    )


def _default_engine_factory() -> Any:
    from atlas.automation.engine import AutomationEngine

    return AutomationEngine()


def _domain_generators(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case, context
    from atlas.automation.helpdesk import HelpDeskAutomation
    from atlas.automation.hr import HRAutomation
    from atlas.automation.sales import SalesAutomation

    helpdesk = HelpDeskAutomation().diagnose({"category": "printer"})
    sales = SalesAutomation().compose_message(
        {"style": "follow_up", "offering": "Curso de Radiologia"}
    )
    hr = HRAutomation().generate_document(
        {"document_type": "interview_guide", "role": "Analista de Suporte"}
    )

    checks = {
        "helpdesk": "impressora" in helpdesk.casefold(),
        "sales": "curso de radiologia" in sales.casefold(),
        "hr": "analista de suporte" in hr.casefold(),
    }
    passed_count = sum(checks.values())
    total = len(checks)
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={**checks, "generators_total": total},
        details=(
            f"Safe domain automation generators matched {passed_count}/{total} checks.",
        ),
    )


def _automation_engine_contract(
    case: BenchmarkCase,
    context: BenchmarkContext,
    *,
    live: bool,
    engine_factory: EngineFactory | None = None,
) -> CaseOutcome:
    del case, context
    if not live and engine_factory is None:
        return CaseOutcome(
            status=BenchmarkStatus.SKIP,
            score=0.0,
            metrics={"live": False},
            details=("Live AutomationEngine contract disabled; use --live.",),
        )

    from atlas.planner.actions import Action

    engine = (engine_factory or _default_engine_factory)()
    try:
        unknown = engine.execute(Action(type="benchmark.unknown"))
        missing = engine.execute(Action(type="file.create_file"))
        invalid = engine.execute(
            Action(type="system.wait", parameters={"seconds": -1})
        )
    finally:
        close = getattr(engine, "close", None)
        if callable(close):
            close()

    checks = {
        "unknown_action": (
            not unknown.success and unknown.error_code == "unknown_action"
        ),
        "missing_parameter": (
            not missing.success and missing.error_code == "missing_parameter"
        ),
        "invalid_parameter": (
            not invalid.success and invalid.error_code == "invalid_parameter"
        ),
    }
    passed_count = sum(checks.values())
    score = round(passed_count / len(checks) * 100.0, 3)
    return CaseOutcome(
        status=(
            BenchmarkStatus.PASS
            if passed_count == len(checks)
            else BenchmarkStatus.FAIL
        ),
        score=score,
        metrics={**checks, "contract_checks": len(checks)},
        details=(
            f"Automation engine error contract matched {passed_count}/{len(checks)} checks.",
        ),
    )


def _automation_file_sandbox(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case
    from atlas.automation.files import FileAutomation

    root = context.scratch_dir / "automation"
    source_dir = root / "source"
    archive_dir = root / "archive"
    source = source_dir / "lead.txt"
    copied = root / "lead-copy.txt"
    renamed = root / "lead-renamed.txt"
    moved = archive_dir / "lead-final.txt"

    files = FileAutomation()
    steps: list[bool] = []

    source_dir.mkdir(parents=True, exist_ok=True)
    steps.append(source_dir.is_dir())

    message = files.create_file(str(source))
    steps.append(message.startswith("Arquivo criado:") and source.is_file())
    source.write_text("atlas-benchmark-lead", encoding="utf-8")

    message = files.copy(str(source), str(copied))
    steps.append(message == "Cópia concluída.")
    steps.append(copied.read_text(encoding="utf-8") == "atlas-benchmark-lead")

    message = files.rename(str(copied), str(renamed))
    steps.append(message == "Renomeado com sucesso.")
    steps.append(renamed.is_file() and not copied.exists())

    archive_dir.mkdir(parents=True, exist_ok=True)
    message = files.move(str(renamed), str(moved))
    steps.append(message == "Movido com sucesso.")
    steps.append(moved.is_file() and not renamed.exists())

    message = files.delete(str(moved))
    steps.append(message.startswith("Removido:"))
    steps.append(not moved.exists())

    passed_count = sum(steps)
    total = len(steps)
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "checks_total": total,
            "checks_passed": passed_count,
            "sandbox_only": True,
        },
        details=(
            f"Scratch-only file automation matched {passed_count}/{total} checks.",
        ),
    )


def _vision_intent_routes(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    from atlas.vision.action_intent import extract_click_target
    from atlas.vision.grounding_intent import extract_grounding_query
    from atlas.vision.intent import is_read_only_vision_command

    raw_samples = case.parameters.get("samples", ())
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("samples parameter must be a non-empty list")

    passed_count = 0
    for sample in raw_samples:
        if not isinstance(sample, dict):
            continue
        command = str(sample.get("input", ""))
        expected = str(sample.get("route", "none"))
        expected_value = sample.get("value")

        if is_read_only_vision_command(command):
            route = "read_only"
            value = None
        else:
            click_target = extract_click_target(command)
            grounding_query = extract_grounding_query(command)
            if click_target is not None:
                route = "click"
                value = click_target
            elif grounding_query is not None:
                route = "grounding"
                value = grounding_query
            else:
                route = "none"
                value = None

        matched = route == expected
        if matched and expected_value is not None:
            matched = value == str(expected_value)
        passed_count += int(matched)

    total = len(raw_samples)
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "samples_total": total,
            "samples_passed": passed_count,
            "routing_accuracy_pct": score,
        },
        details=(f"Vision route classification matched {passed_count}/{total} samples.",),
    )


def _structured_intents(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case, context
    from atlas.vision.form_intent import extract_structured_form
    from atlas.vision.interaction_sequence import extract_structured_sequence
    from atlas.vision.option_select_intent import extract_structured_option_selection
    from atlas.vision.text_input_intent import extract_structured_text_input
    from atlas.vision.uia_action_intent import extract_windows_uia_action

    text_input = extract_structured_text_input("digite Ssamir no campo nome")
    form = extract_structured_form(
        "preencha o formulário: nome: Ssamir; cidade: Manaus"
    )
    selection = extract_structured_option_selection(
        "selecione Manaus na lista cidade"
    )
    uia = extract_windows_uia_action("marque a caixa receber novidades")
    sequence = extract_structured_sequence(
        "clique no botão pesquisar e depois digite Atlas no campo pesquisa"
    )
    blocked_sequence = extract_structured_sequence(
        "clique no botão excluir e depois clique no botão confirmar"
    )

    checks = {
        "text_input": bool(
            text_input is not None
            and text_input.target == "campo nome"
            and text_input.text == "Ssamir"
        ),
        "form": bool(form is not None and len(form.fields) == 2),
        "option_selection": bool(
            selection is not None
            and selection.option == "Manaus"
            and selection.target == "lista cidade"
        ),
        "uia_action": bool(
            uia is not None
            and uia.action == "check"
            and uia.target == "caixa receber novidades"
        ),
        "safe_sequence": bool(sequence is not None and len(sequence.steps) == 2),
        "destructive_sequence_blocked": blocked_sequence is None,
    }
    passed_count = sum(checks.values())
    total = len(checks)
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={**checks, "checks_total": total},
        details=(f"Structured Vision intents matched {passed_count}/{total} checks.",),
    )


def _synthetic_grounding(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case, context
    from atlas.vision.grounding import locate_ui_element
    from atlas.vision.models import (
        VisionAnalysis,
        VisionBoundingBox,
        VisionUIElement,
    )

    analysis = VisionAnalysis(
        summary="Synthetic benchmark UI",
        ui_elements=(
            VisionUIElement(
                label="Cancelar",
                kind="button",
                bbox=VisionBoundingBox(620, 800, 760, 920),
                confidence=0.97,
            ),
            VisionUIElement(
                label="Enviar",
                kind="button",
                description="Botão principal de envio",
                bbox=VisionBoundingBox(800, 800, 950, 920),
                confidence=0.98,
            ),
            VisionUIElement(
                label="Pesquisa",
                kind="field",
                bbox=VisionBoundingBox(100, 100, 650, 180),
                confidence=0.96,
            ),
        ),
        confidence=0.98,
        model="synthetic",
    )

    result = locate_ui_element(analysis, "botão enviar")
    center = result.center_pixels(1920, 1080)
    passed = bool(
        result.found
        and result.element is not None
        and result.element.label == "Enviar"
        and center == (1680, 929)
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "target_found": result.found,
            "candidate_count": len(analysis.ui_elements),
            "center_x_px": center[0] if center else -1,
            "center_y_px": center[1] if center else -1,
        },
        details=("Synthetic visual grounding selected the expected UI target.",),
    )


def _post_action_verification(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case, context
    from atlas.vision.post_action import verify_click_post_action

    navigation = verify_click_post_action(
        {"url": "https://example.test/a"},
        {"url": "https://example.test/b"},
    )
    focus = verify_click_post_action(
        {"target": {"exists": True, "focused": False}},
        {"target": {"exists": True, "focused": True}},
        semantic_kind="text_input",
    )
    inconclusive = verify_click_post_action(
        {"url": "https://example.test/a", "target": {"exists": True}},
        {"url": "https://example.test/a", "target": {"exists": True}},
    )

    checks = {
        "navigation_verified": (
            navigation.verified and navigation.reason_code == "navigation_changed"
        ),
        "focus_verified": focus.verified and focus.reason_code == "target_focused",
        "inconclusive_rejected": (
            not inconclusive.verified
            and inconclusive.reason_code == "post_action_inconclusive"
        ),
    }
    passed_count = sum(checks.values())
    total = len(checks)
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={**checks, "checks_total": total},
        details=(
            f"Post-action verification matched {passed_count}/{total} checks.",
        ),
    )


class _SyntheticImage:
    size = (1366, 768)

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(b"atlas-synthetic-screen")


def _synthetic_capture(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case
    from atlas.vision.capture import ScreenCaptureService

    service = ScreenCaptureService(
        context.scratch_dir,
        screenshot_provider=_SyntheticImage,
    )
    capture = service.capture_primary_screen()
    size_bytes = capture.path.stat().st_size
    passed = bool(
        capture.width == 1366
        and capture.height == 768
        and capture.path.is_file()
        and size_bytes > 0
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "width_px": capture.width,
            "height_px": capture.height,
            "capture_bytes": size_bytes,
            "synthetic": True,
        },
        details=("Synthetic screen capture contract is operational.",),
    )


def _live_capture(
    case: BenchmarkCase,
    context: BenchmarkContext,
    *,
    live: bool,
) -> CaseOutcome:
    del case
    if not live:
        return CaseOutcome(
            status=BenchmarkStatus.SKIP,
            score=0.0,
            metrics={"live": False},
            details=("Live screen capture disabled; use --live.",),
        )

    from atlas.vision.capture import ScreenCaptureService

    service = ScreenCaptureService(context.scratch_dir)
    capture = service.capture_primary_screen()
    try:
        size_bytes = capture.path.stat().st_size
        passed = capture.width > 0 and capture.height > 0 and size_bytes > 0
        return CaseOutcome(
            status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
            score=100.0 if passed else 0.0,
            metrics={
                "live": True,
                "width_px": capture.width,
                "height_px": capture.height,
                "capture_bytes": size_bytes,
            },
            details=("Read-only live screen capture completed.",),
        )
    finally:
        capture.path.unlink(missing_ok=True)


def _live_analysis(
    case: BenchmarkCase,
    context: BenchmarkContext,
    *,
    live: bool,
    timeout_s: float,
) -> CaseOutcome:
    if not live:
        return CaseOutcome(
            status=BenchmarkStatus.SKIP,
            score=0.0,
            metrics={"live": False},
            details=("Live Vision analysis disabled; use --live.",),
        )

    from atlas.core.config import OLLAMA_URL, VISION_ENABLED, VISION_MODEL
    from atlas.vision.analyzer import OllamaVisionAnalyzer
    from atlas.vision.capture import ScreenCaptureService
    from atlas.vision.service import VisionService

    if not VISION_ENABLED:
        return CaseOutcome(
            status=BenchmarkStatus.SKIP,
            score=0.0,
            metrics={"live": True, "vision_enabled": False},
            details=("Atlas Vision is disabled by configuration.",),
        )

    if not _is_loopback_http_endpoint(OLLAMA_URL):
        return CaseOutcome(
            status=BenchmarkStatus.SKIP,
            score=0.0,
            metrics={
                "live": True,
                "vision_enabled": True,
                "remote_endpoint_blocked": True,
            },
            details=(
                "Live screen analysis blocked because the configured Ollama "
                "endpoint is not loopback/local.",
            ),
        )

    question = str(
        case.parameters.get(
            "question",
            "Descreva objetivamente a estrutura geral da tela para um benchmark.",
        )
    ).strip()
    if not question:
        raise ValueError("question parameter cannot be empty")

    analyzer = OllamaVisionAnalyzer(
        model=VISION_MODEL,
        url=OLLAMA_URL,
        timeout=timeout_s,
    )
    service = VisionService(
        ScreenCaptureService(context.scratch_dir),
        analyzer,
        keep_captures=False,
    )
    observation = service.observe_screen(question)
    analysis = observation.analysis
    confidence = max(0.0, min(float(analysis.confidence), 1.0))
    summary_present = bool(analysis.summary.strip())
    passed = summary_present

    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "live": True,
            "vision_enabled": True,
            "endpoint_loopback": True,
            "model": VISION_MODEL,
            "summary_present": summary_present,
            "confidence": round(confidence, 4),
            "ui_elements": len(analysis.ui_elements),
            "visible_text_items": len(analysis.visible_text),
            "reported_errors": len(analysis.errors),
            "capture_width_px": observation.capture.width,
            "capture_height_px": observation.capture.height,
        },
        details=(
            "Live local Vision analysis completed; screen content was not stored in metrics.",
        ),
    )
