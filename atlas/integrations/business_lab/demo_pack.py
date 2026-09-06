from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .benchmark_runner import DEFAULT_OUTPUT_DIR

DEMO_PACK_LABEL = "COMMERCIAL_DEMO_PACK_FROM_MEASURED_BUSINESS_LAB"


@dataclass(frozen=True, slots=True)
class DemoPackResult:
    folder_path: Path
    zip_path: Path
    manifest_path: Path
    included_files: tuple[Path, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "folder_path": str(self.folder_path),
            "zip_path": str(self.zip_path),
            "manifest_path": str(self.manifest_path),
            "included_files": [str(path) for path in self.included_files],
        }


def create_demo_pack(
    *,
    input_dir: Path = DEFAULT_OUTPUT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    company_name: str = "Nexyra",
    product_name: str = "Atlas",
    client_segment: str = "operação comercial educacional",
) -> DemoPackResult:
    """Cria um pacote comercial pronto para demonstração.

    O pacote consolida os relatórios já gerados nas etapas anteriores. Ele não
    executa novos cenários, não consulta gabaritos oficiais e não altera dados
    do Business Lab.
    """

    sources = find_demo_sources(input_dir=input_dir)
    executive_payload = _load_json(sources["executive_json"])
    value_payload = _load_json(sources["value_json"])
    benchmark_payload = _load_json(sources["benchmark_json"])

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    folder_path = output_dir / f"atlas_business_lab_demo_pack_{timestamp}"
    folder_path.mkdir(parents=True, exist_ok=True)

    copied_files = _copy_demo_files(folder_path, sources)
    manifest = build_demo_manifest(
        company_name=company_name,
        product_name=product_name,
        client_segment=client_segment,
        sources=sources,
        executive_payload=executive_payload,
        value_payload=value_payload,
        benchmark_payload=benchmark_payload,
        copied_files=copied_files,
    )

    manifest_path = folder_path / "MANIFESTO_DEMO.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    readme_path = folder_path / "LEIA_ME.md"
    readme_path.write_text(format_demo_readme(manifest), encoding="utf-8")

    zip_path = shutil.make_archive(str(folder_path), "zip", folder_path)
    return DemoPackResult(
        folder_path=folder_path,
        zip_path=Path(zip_path),
        manifest_path=manifest_path,
        included_files=tuple(copied_files.values()) + (manifest_path, readme_path),
    )


def find_demo_sources(*, input_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    return {
        "benchmark_json": _latest_file(input_dir, "business_lab_benchmark_*.json"),
        "value_json": _latest_file(input_dir, "business_lab_value_report_*.json"),
        "value_csv": _latest_file(input_dir, "business_lab_value_report_*.csv"),
        "value_md": _latest_file(input_dir, "business_lab_value_report_*.md"),
        "executive_json": _latest_file(
            input_dir,
            "business_lab_executive_report_*.json",
        ),
        "executive_md": _latest_file(
            input_dir,
            "business_lab_executive_report_*.md",
        ),
        "executive_html": _latest_file(
            input_dir,
            "business_lab_executive_report_*.html",
        ),
    }


def build_demo_manifest(
    *,
    company_name: str,
    product_name: str,
    client_segment: str,
    sources: dict[str, Path],
    executive_payload: dict[str, Any],
    value_payload: dict[str, Any],
    benchmark_payload: dict[str, Any],
    copied_files: dict[str, Path],
) -> dict[str, Any]:
    metrics = _dict(executive_payload.get("metrics"))
    evidence = _dict(executive_payload.get("evidence"))
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provenance": DEMO_PACK_LABEL,
        "company_name": company_name,
        "product_name": product_name,
        "client_segment": client_segment,
        "source_files": {key: str(path) for key, path in sources.items()},
        "pack_files": {key: path.name for key, path in copied_files.items()},
        "metrics": {
            "success_rate_percent": _number(metrics.get("success_rate_percent")),
            "reduction_percent": _number(metrics.get("reduction_percent")),
            "total_saved_minutes": _number(metrics.get("total_saved_minutes")),
            "monthly_saved_hours": _number(metrics.get("monthly_saved_hours")),
            "monthly_estimated_value_brl": _number(
                metrics.get("monthly_estimated_value_brl")
            ),
            "benchmark_total_samples": int(benchmark_payload.get("total") or 0),
            "benchmark_passed": int(benchmark_payload.get("passed") or 0),
            "benchmark_failed": int(benchmark_payload.get("failed") or 0),
            "value_report_scenarios": int(value_payload.get("total_scenarios") or 0),
        },
        "evidence": {
            "atlas_source": evidence.get("atlas_source"),
            "manual_baseline": evidence.get("manual_baseline"),
            "value_report_source": evidence.get("value_report_source"),
            "official_answers_used": False,
            "scenario_endpoint_used": False,
            "customer_claim": False,
        },
        "usage": [
            "Abrir 01_relatorio_executivo.html no navegador.",
            "Usar 02_relatorio_executivo.md como texto editável.",
            "Usar 04_relatorio_valor.csv para planilha e conferência.",
            "Manter os JSONs como rastreabilidade técnica.",
        ],
        "honest_disclaimer": (
            "Este pacote demonstra o Atlas em ambiente local controlado, com dados "
            "sintéticos e métricas reproduzíveis. Não apresentar como resultado "
            "real de cliente sem piloto supervisionado."
        ),
    }


def format_demo_readme(manifest: dict[str, Any]) -> str:
    metrics = _dict(manifest.get("metrics"))
    lines = [
        f"# Demo Pack — {manifest.get('product_name')} Business Lab",
        "",
        f"**Empresa:** {manifest.get('company_name')}",
        f"**Segmento:** {manifest.get('client_segment')}",
        f"**Origem:** `{manifest.get('provenance')}`",
        "",
        "## Como usar",
        "",
        "1. Abra `01_relatorio_executivo.html` no navegador.",
        "2. Use `02_relatorio_executivo.md` para editar o texto comercial.",
        "3. Use `04_relatorio_valor.csv` para conferência em planilha.",
        "4. Guarde os arquivos JSON como evidência técnica.",
        "",
        "## Indicadores do pacote",
        "",
        f"- Sucesso operacional: {_fmt_percent(metrics.get('success_rate_percent'))}",
        f"- Redução estimada: {_fmt_percent(metrics.get('reduction_percent'))}",
        f"- Economia por ciclo: {_fmt_minutes(metrics.get('total_saved_minutes'))}",
        f"- Horas economizadas/mês: {_fmt_hours(metrics.get('monthly_saved_hours'))}",
        f"- Potencial estimado/mês: {_fmt_money(metrics.get('monthly_estimated_value_brl'))}",
        "",
        "## Arquivos incluídos",
        "",
    ]
    pack_files = _dict(manifest.get("pack_files"))
    for key, filename in pack_files.items():
        lines.append(f"- `{filename}` — {key}")
    lines.extend(
        [
            "- `MANIFESTO_DEMO.json` — manifesto de rastreabilidade do pacote",
            "- `LEIA_ME.md` — este guia",
            "",
            "## Aviso de honestidade comercial",
            "",
            str(manifest.get("honest_disclaimer") or ""),
            "",
        ]
    )
    return "\n".join(lines)


def _copy_demo_files(folder_path: Path, sources: dict[str, Path]) -> dict[str, Path]:
    mapping = {
        "executive_html": "01_relatorio_executivo.html",
        "executive_md": "02_relatorio_executivo.md",
        "value_md": "03_relatorio_valor.md",
        "value_csv": "04_relatorio_valor.csv",
        "benchmark_json": "05_benchmark_medido.json",
        "value_json": "06_valor_estruturado.json",
        "executive_json": "07_executivo_estruturado.json",
    }
    copied: dict[str, Path] = {}
    for key, filename in mapping.items():
        destination = folder_path / filename
        shutil.copy2(sources[key], destination)
        copied[key] = destination
    return copied


def _latest_file(input_dir: Path, pattern: str) -> Path:
    candidates = sorted(input_dir.glob(pattern), key=lambda path: (path.name, path.stat().st_mtime))
    if not candidates:
        raise FileNotFoundError(
            f"Nenhum arquivo encontrado em {input_dir} com padrão {pattern}."
        )
    return candidates[-1]


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Arquivo JSON inválido para relatório: {path}")
    return data


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt_percent(value: Any) -> str:
    return f"{_number(value):.2f}%"


def _fmt_minutes(value: Any) -> str:
    return f"{_number(value):.2f} min"


def _fmt_hours(value: Any) -> str:
    return f"{_number(value):.2f} h"


def _fmt_money(value: Any) -> str:
    return f"R$ {_number(value):.2f}"
