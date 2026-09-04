"""Valida uma distribuição simulada sem construir ou instalar programas."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.packaging.release import ReleaseValidator, load_release_policy


def main() -> None:
    project_root = Path(__file__).resolve().parent
    policy = load_release_policy(project_root / "packaging" / "release_manifest.json")
    with TemporaryDirectory(prefix="atlas-installer-pilot-") as directory:
        release = Path(directory) / "Atlas"
        assets = release / "atlas" / "gui" / "assets"
        assets.mkdir(parents=True)
        (release / "Atlas.exe").write_bytes(b"MZ-atlas-pilot")
        (release / ".env.example").write_text(
            "ATLAS_MODEL=atlas\n",
            encoding="utf-8",
        )
        (assets / "atlas_mark.svg").write_text(
            "<svg xmlns='http://www.w3.org/2000/svg'/>",
            encoding="utf-8",
        )
        report = ReleaseValidator(policy).validate(release)
        if not report.valid:
            raise SystemExit("A distribuição simulada foi rejeitada.")
        print("Sprint 25 — Etapa 6: instalador Windows")
        print(f"Arquivos simulados: {report.file_count}")
        print("Manifesto: aprovado")
        print("Segredos e dados locais: ausentes")
        print("Nenhum programa foi instalado e nenhum arquivo do usuário foi alterado.")


if __name__ == "__main__":
    main()

