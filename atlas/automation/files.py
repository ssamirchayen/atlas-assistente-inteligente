from __future__ import annotations

import shutil
from pathlib import Path


class FileAutomation:
    def create_folder(self, path: str) -> str:
        try:
            folder = Path(path).expanduser()

            folder.mkdir(parents=True, exist_ok=True)

            return f"Pasta criada: {folder}"

        except Exception as error:
            return f"Erro ao criar pasta: {error}"

    def create_file(self, path: str) -> str:
        try:
            file = Path(path).expanduser()

            file.parent.mkdir(parents=True, exist_ok=True)

            file.touch(exist_ok=True)

            return f"Arquivo criado: {file}"

        except Exception as error:
            return f"Erro ao criar arquivo: {error}"

    def delete(self, path: str) -> str:
        try:
            target = Path(path).expanduser()

            if not target.exists():
                return "Arquivo ou pasta não encontrado."

            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

            return f"Removido: {target}"

        except Exception as error:
            return f"Erro ao remover: {error}"

    def copy(self, source: str, destination: str) -> str:
        try:
            source_path = Path(source).expanduser()
            destination_path = Path(destination).expanduser()

            if source_path.is_dir():
                shutil.copytree(
                    source_path,
                    destination_path,
                    dirs_exist_ok=True,
                )
            else:
                destination_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                shutil.copy2(
                    source_path,
                    destination_path,
                )

            return "Cópia concluída."

        except Exception as error:
            return f"Erro ao copiar: {error}"

    def move(self, source: str, destination: str) -> str:
        try:
            shutil.move(source, destination)

            return "Movido com sucesso."

        except Exception as error:
            return f"Erro ao mover: {error}"

    def rename(self, source: str, destination: str) -> str:
        try:
            Path(source).rename(destination)

            return "Renomeado com sucesso."

        except Exception as error:
            return f"Erro ao renomear: {error}"