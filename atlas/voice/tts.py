from __future__ import annotations

import base64
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EdgeTTSProvider:
    """Configuração da voz neural online usada pelo Atlas."""

    voice: str = "pt-BR-AntonioNeural"
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"

    def synthesis_command(
        self,
        message: str,
        media_path: Path,
        *,
        executable: str | None = None,
    ) -> list[str]:
        return [
            executable or sys.executable,
            "-m",
            "edge_tts",
            "--voice",
            self.voice,
            f"--rate={self.rate}",
            f"--volume={self.volume}",
            f"--pitch={self.pitch}",
            f"--write-media={media_path}",
            "--text",
            message,
        ]

    @staticmethod
    def playback_command(
        media_path: Path,
        *,
        executable: str | None = None,
    ) -> list[str]:
        return [
            executable or sys.executable,
            "-m",
            "atlas.voice.playback",
            str(media_path),
        ]


class WindowsSapiProvider:
    """Voz local do Windows mantida como fallback operacional."""

    @staticmethod
    def command(message: str) -> list[str]:
        encoded_text = base64.b64encode(
            message.encode("utf-8")
        ).decode("ascii")

        powershell_command = f"""
Add-Type -AssemblyName System.Speech

$texto = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String('{encoded_text}')
)

$voz = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voz.Volume = 100
$voz.Rate = 0

$vozes = $voz.GetInstalledVoices()

foreach ($item in $vozes) {{
    $info = $item.VoiceInfo
    $nome = $info.Name.ToLower()
    $cultura = $info.Culture.Name.ToLower()

    if (
        $cultura -like "pt-*" -or
        $nome -like "*maria*" -or
        $nome -like "*francisca*"
    ) {{
        try {{
            $voz.SelectVoice($info.Name)
            break
        }} catch {{
        }}
    }}
}}

$voz.Speak($texto)
$voz.Dispose()
"""

        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            powershell_command,
        ]
