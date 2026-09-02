from atlas.vision.analyzer import OllamaVisionAnalyzer


def test_analyzer_has_required_internal_methods() -> None:
    required = (
        "_build_prompt",
        "_parse_content",
        "_parse_bbox",
        "_extract_json_object",
        "locate_target",
    )

    for name in required:
        assert hasattr(OllamaVisionAnalyzer, name)
