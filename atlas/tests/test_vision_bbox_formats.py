from atlas.vision.analyzer import OllamaVisionAnalyzer


def test_bbox_accepts_zero_to_one_scale() -> None:
    box = OllamaVisionAnalyzer._parse_bbox(
        [0.1, 0.2, 0.3, 0.4]
    )

    assert box is not None
    assert (box.x1, box.y1, box.x2, box.y2) == (
        100,
        200,
        300,
        400,
    )


def test_bbox_accepts_zero_to_hundred_scale() -> None:
    box = OllamaVisionAnalyzer._parse_bbox(
        [10, 20, 30, 40]
    )

    assert box is not None
    assert (box.x1, box.y1, box.x2, box.y2) == (
        100,
        200,
        300,
        400,
    )


def test_bbox_accepts_dict_xywh() -> None:
    box = OllamaVisionAnalyzer._parse_bbox(
        {
            "x": 100,
            "y": 200,
            "w": 100,
            "h": 150,
        }
    )

    assert box is not None
    assert (box.x1, box.y1, box.x2, box.y2) == (
        100,
        200,
        200,
        350,
    )


def test_bbox_accepts_string() -> None:
    box = OllamaVisionAnalyzer._parse_bbox(
        "[100,200,300,400]"
    )

    assert box is not None
    assert (box.x1, box.y1, box.x2, box.y2) == (
        100,
        200,
        300,
        400,
    )
