from atlas.vision.formatter import format_analysis_for_user
from atlas.vision.models import VisionAnalysis


def test_formatter_mentions_visible_errors() -> None:
    analysis = VisionAnalysis(
        summary="Vejo um terminal aberto.",
        errors=("PermissionError no terminal",),
    )

    text = format_analysis_for_user(analysis)

    assert "terminal aberto" in text
    assert "PermissionError" in text
