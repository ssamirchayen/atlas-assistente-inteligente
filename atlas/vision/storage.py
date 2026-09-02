from __future__ import annotations

from pathlib import Path


class VisionStorage:
    """Gerencia artefatos visuais temporários do Atlas."""

    def __init__(self, capture_dir: Path) -> None:
        self.capture_dir = Path(capture_dir)

    def clear_captures(self) -> int:
        if not self.capture_dir.exists():
            return 0

        removed = 0
        for path in self.capture_dir.glob("screen_*.png"):
            if path.is_file():
                path.unlink(missing_ok=True)
                removed += 1

        return removed
