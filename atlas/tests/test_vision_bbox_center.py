from atlas.vision.models import VisionBoundingBox


def test_bbox_center_normalized() -> None:
    box = VisionBoundingBox(
        915,
        870,
        965,
        910,
    )

    assert box.center == (
        940,
        890,
    )
