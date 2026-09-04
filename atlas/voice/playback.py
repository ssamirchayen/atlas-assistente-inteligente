from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path
from threading import RLock


class AudioPlaybackError(RuntimeError):
    """Falha ao reproduzir o áudio neural no Windows."""


def _short_windows_path(path: Path) -> str:
    get_short_path = ctypes.windll.kernel32.GetShortPathNameW
    get_short_path.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    get_short_path.restype = wintypes.DWORD

    size = 0

    while True:
        output = ctypes.create_unicode_buffer(size)
        needed = get_short_path(str(path), output, size)

        if needed == 0:
            raise AudioPlaybackError(
                f"Não foi possível localizar o áudio: {path}"
            )
        if size >= needed:
            return output.value

        size = needed


def _mci_send(command: str, *, raise_on_error: bool = True) -> int:
    result = ctypes.windll.winmm.mciSendStringW(command, None, 0, None)

    if result != 0 and raise_on_error:
        raise AudioPlaybackError(
            f"Falha MCI {result} ao executar: {command}"
        )

    return int(result)


class WindowsMciPlayer:
    """Player MP3 nativo, síncrono e interrompível.

    O player roda dentro do próprio Atlas.exe. Isso evita depender do padrão
    ``sys.executable -m atlas.voice.playback``, que não funciona quando
    ``sys.executable`` é o executável congelado do PyInstaller.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._alias = f"atlasNeuralVoice{id(self):x}"
        self._opened = False
        self._stop_requested = False

    def play(self, path: Path) -> None:
        if sys.platform != "win32":
            raise AudioPlaybackError(
                "A reprodução neural atual requer o Windows."
            )

        media_path = path.expanduser().resolve()

        if not media_path.is_file():
            raise AudioPlaybackError(f"Áudio não encontrado: {media_path}")

        short_path = _short_windows_path(media_path)

        with self._lock:
            self._stop_requested = False
            self._opened = False

        try:
            _mci_send(
                f'Open "{short_path}" Type MPEGVideo Alias {self._alias}'
            )
            with self._lock:
                self._opened = True
                stopped_before_play = self._stop_requested

            if stopped_before_play:
                return

            _mci_send(f"Play {self._alias} Wait")
        finally:
            with self._lock:
                opened = self._opened
                self._opened = False

            if opened:
                _mci_send(
                    f"Close {self._alias}",
                    raise_on_error=False,
                )

    def stop(self) -> bool:
        with self._lock:
            self._stop_requested = True
            opened = self._opened

        if not opened or sys.platform != "win32":
            return False

        return _mci_send(
            f"Stop {self._alias}",
            raise_on_error=False,
        ) == 0


def play_mp3(path: Path) -> None:
    """Reproduz MP3 usando a API multimídia nativa do Windows."""

    WindowsMciPlayer().play(path)


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: python -m atlas.voice.playback <arquivo.mp3>")
        return 2

    try:
        play_mp3(Path(sys.argv[1]))
    except AudioPlaybackError as exc:
        print(f"[ERRO NA REPRODUÇÃO] {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
