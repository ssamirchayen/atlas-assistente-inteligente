from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionManager:
    def __init__(self) -> None:
        self.session_file = Path("data") / "last_session.json"

        self.session_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.session_file.exists():
            self.save(self._default_session())

    def _default_session(self) -> dict[str, Any]:
        return {
            "project": None,
            "current_task": None,
            "last_file": None,
            "last_command": None,
            "active_window": None,
            "opened_files": [],
            "browser_tabs": [],
            "notes": [],
            "last_update": datetime.now().isoformat(),
        }

    def load(self) -> dict[str, Any]:
        try:
            with open(
                self.session_file,
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            default_session = self._default_session()

            for key, value in default_session.items():
                data.setdefault(key, value)

            return data

        except (
            FileNotFoundError,
            json.JSONDecodeError,
            OSError,
        ):
            return self._default_session()

    def save(self, data: dict[str, Any]) -> None:
        data["last_update"] = datetime.now().isoformat()

        with open(
            self.session_file,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False,
            )

    def clear(self) -> None:
        self.save(self._default_session())

    def update(self, **values: Any) -> None:
        session = self.load()
        session.update(values)
        self.save(session)

    def save_last_command(
        self,
        command: str,
    ) -> None:
        self.update(last_command=command)

    def save_last_file(
        self,
        filename: str,
    ) -> None:
        self.update(last_file=filename)
        self.add_opened_file(filename)

    def save_project(
        self,
        project: str,
    ) -> None:
        self.update(project=project)

    def save_current_task(
        self,
        task: str,
    ) -> None:
        self.update(current_task=task)

    def save_active_window(
        self,
        window_title: str,
    ) -> None:
        self.update(active_window=window_title)

    def add_opened_file(
        self,
        filename: str,
    ) -> None:
        session = self.load()
        opened_files = session.get("opened_files", [])

        if filename not in opened_files:
            opened_files.append(filename)

        session["opened_files"] = opened_files
        session["last_file"] = filename

        self.save(session)

    def remove_opened_file(
        self,
        filename: str,
    ) -> None:
        session = self.load()
        opened_files = session.get("opened_files", [])

        if filename in opened_files:
            opened_files.remove(filename)

        session["opened_files"] = opened_files
        self.save(session)

    def add_browser_tab(
        self,
        tab_title: str,
    ) -> None:
        session = self.load()
        browser_tabs = session.get("browser_tabs", [])

        if tab_title not in browser_tabs:
            browser_tabs.append(tab_title)

        session["browser_tabs"] = browser_tabs
        self.save(session)

    def remove_browser_tab(
        self,
        tab_title: str,
    ) -> None:
        session = self.load()
        browser_tabs = session.get("browser_tabs", [])

        if tab_title in browser_tabs:
            browser_tabs.remove(tab_title)

        session["browser_tabs"] = browser_tabs
        self.save(session)

    def add_note(
        self,
        note: str,
    ) -> None:
        session = self.load()
        notes = session.get("notes", [])

        if note not in notes:
            notes.append(note)

        session["notes"] = notes
        self.save(session)

    def remove_note(
        self,
        note: str,
    ) -> None:
        session = self.load()
        notes = session.get("notes", [])

        if note in notes:
            notes.remove(note)

        session["notes"] = notes
        self.save(session)

    def get_project(self) -> str | None:
        return self.load().get("project")

    def get_current_task(self) -> str | None:
        return self.load().get("current_task")

    def get_last_file(self) -> str | None:
        return self.load().get("last_file")

    def get_last_command(self) -> str | None:
        return self.load().get("last_command")

    def get_context(self) -> dict[str, Any]:
        return self.load()

    def get_summary(self) -> str:
        session = self.load()

        opened_files = session.get("opened_files", [])
        browser_tabs = session.get("browser_tabs", [])
        notes = session.get("notes", [])

        files_text = (
            ", ".join(opened_files)
            if opened_files
            else "Nenhum"
        )

        tabs_text = (
            ", ".join(browser_tabs)
            if browser_tabs
            else "Nenhuma"
        )

        notes_text = (
            "\n".join(f"- {note}" for note in notes)
            if notes
            else "Nenhuma"
        )

        return (
            f"Projeto: {session.get('project') or 'Desconhecido'}\n"
            f"Tarefa atual: "
            f"{session.get('current_task') or 'Nenhuma'}\n"
            f"Último arquivo: "
            f"{session.get('last_file') or 'Nenhum'}\n"
            f"Último comando: "
            f"{session.get('last_command') or 'Nenhum'}\n"
            f"Janela ativa: "
            f"{session.get('active_window') or 'Desconhecida'}\n"
            f"Arquivos abertos: {files_text}\n"
            f"Abas do navegador: {tabs_text}\n"
            f"Anotações:\n{notes_text}\n"
            f"Última atualização: "
            f"{session.get('last_update') or 'Desconhecida'}"
        )

    def build_prompt_context(self) -> str:
        return (
            "CONTEXTO ATUAL DA SESSÃO DO ATLAS:\n"
            f"{self.get_summary()}\n\n"
            "Use esse contexto para compreender comandos como "
            "'continue', 'volte ao projeto' ou "
            "'abra o último arquivo'."
        )
