from pathlib import Path

from atlas.vision.storage import VisionStorage


def test_clear_captures_removes_only_vision_screens(
    tmp_path: Path,
) -> None:
    screen_a = tmp_path / "screen_a.png"
    screen_b = tmp_path / "screen_b.png"
    unrelated = tmp_path / "keep.png"

    screen_a.write_bytes(b"a")
    screen_b.write_bytes(b"b")
    unrelated.write_bytes(b"keep")

    removed = VisionStorage(tmp_path).clear_captures()

    assert removed == 2
    assert not screen_a.exists()
    assert not screen_b.exists()
    assert unrelated.exists()
