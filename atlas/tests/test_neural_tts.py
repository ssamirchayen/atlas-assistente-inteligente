from __future__ import annotations

import base64
import sys
from pathlib import Path

from atlas.voice.tts import EdgeTTSProvider, WindowsSapiProvider


def test_edge_tts_builds_neural_synthesis_command() -> None:
    provider = EdgeTTSProvider(
        voice="pt-BR-AntonioNeural",
        rate="+5%",
        volume="+0%",
        pitch="-2Hz",
    )
    media_path = Path("voz-atlas.mp3")

    command = provider.synthesis_command(
        "Olá, Ssamir",
        media_path,
        executable="python-atlas.exe",
    )

    assert command == [
        "python-atlas.exe",
        "-m",
        "edge_tts",
        "--voice",
        "pt-BR-AntonioNeural",
        "--rate=+5%",
        "--volume=+0%",
        "--pitch=-2Hz",
        "--write-media=voz-atlas.mp3",
        "--text",
        "Olá, Ssamir",
    ]


def test_edge_tts_uses_same_python_for_interruptible_playback() -> None:
    command = EdgeTTSProvider.playback_command(Path("voz-atlas.mp3"))

    assert command == [
        sys.executable,
        "-m",
        "atlas.voice.playback",
        "voz-atlas.mp3",
    ]


def test_windows_fallback_encodes_unicode_message_safely() -> None:
    message = "Operação concluída, Ssamir."
    command = WindowsSapiProvider.command(message)
    encoded = base64.b64encode(message.encode("utf-8")).decode("ascii")

    assert command[:5] == [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
    ]
    assert encoded in command[-1]
    assert message not in command[-1]
