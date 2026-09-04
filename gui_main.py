from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    # Self-test sem GUI para a build confirmar que o Edge TTS entrou no EXE.
    if "--voice-selftest" in sys.argv:
        from atlas.voice.speech import SpeechInterface

        return 0 if SpeechInterface.runtime_self_test() else 7

    # Imports pesados ficam dentro de main para preservar freeze_support.
    from PySide6.QtWidgets import QApplication

    from atlas.gui.single_instance import SingleInstanceGuard
    from atlas.gui.window import AtlasWindow

    app = QApplication(sys.argv)
    guard = SingleInstanceGuard("NEXYRA_ATLAS_CORE_GUI")
    if not guard.acquire():
        return 0

    try:
        window = AtlasWindow()
        window.show()
        return app.exec()
    finally:
        guard.release()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
