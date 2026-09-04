"""Registro central, análise de lacunas e exportação do inventário LGPD."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Callable, Iterable

from atlas.privacy.models import (
    DataNature,
    DataSubject,
    LegalBasisStatus,
    ProcessingRecord,
    RetentionMode,
    RiskLevel,
)


INVENTORY_SCHEMA_VERSION = 1


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class InventoryIssue:
    record_id: str
    code: str
    severity: IssueSeverity
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "record_id": self.record_id,
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class InventoryReport:
    generated_at: datetime
    total_records: int
    counts_by_nature: dict[str, int]
    counts_by_risk: dict[str, int]
    issues: tuple[InventoryIssue, ...]

    @property
    def requires_action(self) -> bool:
        return bool(self.issues)

    @property
    def high_or_critical_issues(self) -> int:
        return sum(
            issue.severity in {IssueSeverity.HIGH, IssueSeverity.CRITICAL}
            for issue in self.issues
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": INVENTORY_SCHEMA_VERSION,
            "generated_at": self.generated_at.isoformat(),
            "total_records": self.total_records,
            "counts_by_nature": dict(sorted(self.counts_by_nature.items())),
            "counts_by_risk": dict(sorted(self.counts_by_risk.items())),
            "requires_action": self.requires_action,
            "high_or_critical_issues": self.high_or_critical_issues,
            "issues": [issue.as_dict() for issue in self.issues],
        }


class ProcessingInventory:
    """Inventário somente de metadados, nunca de conteúdo dos titulares."""

    def __init__(
        self,
        records: Iterable[ProcessingRecord],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        items = tuple(records)
        if not items:
            raise ValueError("O inventário não pode ser vazio.")
        ids = [record.record_id for record in items]
        if len(ids) != len(set(ids)):
            raise ValueError("O inventário possui record_id duplicado.")
        self._records = tuple(sorted(items, key=lambda item: item.record_id))
        self._by_id = {record.record_id: record for record in self._records}
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def records(self) -> tuple[ProcessingRecord, ...]:
        return self._records

    def get(self, record_id: str) -> ProcessingRecord:
        try:
            return self._by_id[record_id]
        except KeyError as error:
            raise KeyError(f"Tratamento não inventariado: {record_id}") from error

    def find_by_component(self, component: str) -> tuple[ProcessingRecord, ...]:
        normalized = component.strip().casefold()
        if not normalized:
            raise ValueError("O componente de busca não pode ser vazio.")
        return tuple(
            record
            for record in self._records
            if normalized in record.component.casefold()
        )

    def analyze(self) -> InventoryReport:
        issues: list[InventoryIssue] = []
        for record in self._records:
            issues.extend(self._issues_for(record))

        counts_by_nature = {
            nature.value: sum(record.nature is nature for record in self._records)
            for nature in DataNature
        }
        counts_by_risk = {
            risk.value: sum(record.risk_level is risk for record in self._records)
            for risk in RiskLevel
        }
        generated_at = self._clock()
        if generated_at.tzinfo is None:
            raise ValueError("O relógio do inventário deve possuir fuso horário.")
        return InventoryReport(
            generated_at=generated_at.astimezone(timezone.utc),
            total_records=len(self._records),
            counts_by_nature=counts_by_nature,
            counts_by_risk=counts_by_risk,
            issues=tuple(
                sorted(
                    issues,
                    key=lambda issue: (
                        issue.record_id,
                        issue.severity.value,
                        issue.code,
                    ),
                )
            ),
        )

    @staticmethod
    def _issues_for(record: ProcessingRecord) -> tuple[InventoryIssue, ...]:
        issues: list[InventoryIssue] = []
        if (
            record.nature is not DataNature.NON_PERSONAL
            and record.legal_basis_status
            is LegalBasisStatus.REQUIRES_CONTROLLER_DEFINITION
        ):
            issues.append(
                InventoryIssue(
                    record_id=record.record_id,
                    code="legal_basis_pending",
                    severity=IssueSeverity.HIGH,
                    message=(
                        "O controlador deve documentar a hipótese legal "
                        "antes do uso em produção."
                    ),
                )
            )
        if record.retention.mode is RetentionMode.UNDEFINED:
            issues.append(
                InventoryIssue(
                    record_id=record.record_id,
                    code="retention_undefined",
                    severity=IssueSeverity.HIGH,
                    message="Ainda não existe prazo técnico de retenção definido.",
                )
            )
        if record.retention.mode is RetentionMode.EXTERNAL_POLICY:
            issues.append(
                InventoryIssue(
                    record_id=record.record_id,
                    code="external_retention_requires_evidence",
                    severity=IssueSeverity.WARNING,
                    message=(
                        "A política externa deve ser registrada e comprovada "
                        "pela organização."
                    ),
                )
            )
        if record.international_transfer:
            issues.append(
                InventoryIssue(
                    record_id=record.record_id,
                    code="international_transfer_review",
                    severity=IssueSeverity.HIGH,
                    message=(
                        "A transferência internacional deve ser avaliada e "
                        "documentada pelo controlador."
                    ),
                )
            )
        if DataSubject.CHILD_OR_ADOLESCENT in record.subjects:
            issues.append(
                InventoryIssue(
                    record_id=record.record_id,
                    code="child_data_specific_review",
                    severity=IssueSeverity.CRITICAL,
                    message=(
                        "O tratamento pode envolver criança ou adolescente e "
                        "exige avaliação específica."
                    ),
                )
            )
        if record.automated_decision:
            issues.append(
                InventoryIssue(
                    record_id=record.record_id,
                    code="automated_decision_review",
                    severity=IssueSeverity.HIGH,
                    message="A decisão automatizada requer governança e revisão.",
                )
            )
        for control in record.unresolved_controls:
            severity = (
                IssueSeverity.CRITICAL
                if record.risk_level is RiskLevel.CRITICAL
                else IssueSeverity.HIGH
            )
            issues.append(
                InventoryIssue(
                    record_id=record.record_id,
                    code=f"control_missing.{control}",
                    severity=severity,
                    message=f"Controle técnico ainda não implementado: {control}.",
                )
            )
        return tuple(issues)

    def as_dict(self) -> dict[str, Any]:
        report = self.analyze()
        return {
            "schema_version": INVENTORY_SCHEMA_VERSION,
            "notice": (
                "Inventário técnico preliminar. Bases legais, prazos e papéis "
                "devem ser confirmados pelo controlador."
            ),
            "report": report.as_dict(),
            "records": [record.as_dict() for record in self._records],
        }

    def export_json(self, path: Path) -> Path:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        payload = json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        try:
            temporary.write_text(payload + "\n", encoding="utf-8")
            temporary.replace(target)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
        return target
