from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path


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


def play_mp3(path: Path) -> None:
    """Reproduz MP3 usando a API multimídia nativa do Windows."""

    if sys.platform != "win32":
        raise AudioPlaybackError(
            "A reprodução neural atual requer o Windows."
        )

    media_path = path.expanduser().resolve()

    if not media_path.is_file():
        raise AudioPlaybackError(f"Áudio não encontrado: {media_path}")

    send_command = ctypes.windll.winmm.mciSendStringW

    def send(command: str) -> None:
        result = send_command(command, None, 0, None)

        if result != 0:
            raise AudioPlaybackError(
                f"Falha MCI {result} ao executar: {command}"
            )

    short_path = _short_windows_path(media_path)
    alias = "atlasNeuralVoice"
    opened = False

    try:
        send(f'Open "{short_path}" Type MPEGVideo Alias {alias}')
        opened = True
        send(f"Play {alias} Wait")
    finally:
        if opened:
            send(f"Close {alias}")


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
