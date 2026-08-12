from __future__ import annotations

import os
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path


class WindowsSkill:
    APPS = {
        "chrome": ["cmd", "/c", "start", "", "chrome"],
        "google chrome": ["cmd", "/c", "start", "", "chrome"],
        "spotify": ["cmd", "/c", "start", "", "spotify"],
        "calculadora": ["calc.exe"],
        "calc": ["calc.exe"],
        "bloco de notas": ["notepad.exe"],
        "notepad": ["notepad.exe"],
        "paint": ["mspaint.exe"],
        "explorador": ["explorer.exe"],
        "explorador de arquivos": ["explorer.exe"],
    }

    SITES = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "whatsapp": "https://web.whatsapp.com",
        "whatsapp web": "https://web.whatsapp.com",
        "instagram": "https://www.instagram.com",
    }

    FOLDERS = {
        "downloads": Path.home() / "Downloads",
        "documentos": Path.home() / "Documents",
        "imagens": Path.home() / "Pictures",
        "fotos": Path.home() / "Pictures",
        "desktop": Path.home() / "Desktop",
        "area de trabalho": Path.home() / "Desktop",
    }

    @classmethod
    def open_target(cls, target: str) -> str:
        target = target.strip()

        if target in cls.SITES:
            webbrowser.open(cls.SITES[target])
            return f"Abrindo {target}."

        if target in cls.FOLDERS:
            try:
                os.startfile(cls.FOLDERS[target])
                return f"Abrindo a pasta {target}."
            except OSError as exc:
                return f"Não consegui abrir a pasta {target}: {exc}"

        if target in cls.APPS:
            try:
                subprocess.Popen(cls.APPS[target])
                return f"Abrindo {target}."
            except OSError as exc:
                return f"Não consegui abrir {target}: {exc}"

        return f"Ainda não tenho um atalho configurado para {target}."

    @staticmethod
    def search_web(query: str) -> str:
        webbrowser.open(
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(query)
        )
        return f"Pesquisando por {query}."

    @staticmethod
    def shutdown(seconds: int) -> str:
        subprocess.run(["shutdown", "/s", "/t", str(seconds)], check=False)
        return "Comando de desligamento enviado."

    @staticmethod
    def restart(seconds: int) -> str:
        subprocess.run(["shutdown", "/r", "/t", str(seconds)], check=False)
        return "Comando de reinicialização enviado."

    @staticmethod
    def cancel_shutdown() -> str:
        subprocess.run(["shutdown", "/a"], check=False)
        return "Desligamento ou reinicialização cancelado."
