from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Callable

from atlas.core.config import (
    MEMORY_CONSOLIDATION_THRESHOLD,
    MEMORY_DECAY_ENABLED,
    MEMORY_DECAY_FLOOR,
    MEMORY_DECAY_HALF_LIFE_DAYS,
    USER_NAME,
)
from atlas.memory.database import MemoryStore
from atlas.memory.models import MemoryRecord
from atlas.utils.text import normalize


@dataclass(frozen=True, slots=True)
class MemoryCommandResult:
    handled: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class MemoryConsolidationGroup:
    keeper_id: int
    duplicate_ids: tuple[int, ...]
    similarity: float


@dataclass(frozen=True, slots=True)
class MemoryConsolidationReport:
    reviewed: int
    groups: tuple[MemoryConsolidationGroup, ...]
    removed_ids: tuple[int, ...]
    dry_run: bool


@dataclass(frozen=True, slots=True)
class MemoryDecayReport:
    reviewed: int
    updated: int
    unchanged: int


@dataclass(frozen=True, slots=True)
class _FactField:
    key: str
    category: str
    importance: float
    aliases: tuple[str, ...]
    formatter: Callable[[str], str]


class MemoryLifecycleManager:
    """Administra correção, restauração, consolidação e decay."""

    def __init__(
        self,
        memory: MemoryStore,
        *,
        user_name: str = USER_NAME,
        decay_enabled: bool = MEMORY_DECAY_ENABLED,
        half_life_days: float = MEMORY_DECAY_HALF_LIFE_DAYS,
        importance_floor: float = MEMORY_DECAY_FLOOR,
        consolidation_threshold: float = MEMORY_CONSOLIDATION_THRESHOLD,
    ) -> None:
        if half_life_days <= 0:
            raise ValueError("A meia-vida deve ser maior que zero.")

        if not 0 <= importance_floor <= 1:
            raise ValueError("O piso de importância deve estar entre 0 e 1.")

        if not 0.5 <= consolidation_threshold <= 1:
            raise ValueError(
                "O limiar de consolidação deve estar entre 0.5 e 1."
            )

        self.memory = memory
        self.user_name = user_name.strip() or "O usuário"
        self.decay_enabled = bool(decay_enabled)
        self.half_life_days = float(half_life_days)
        self.importance_floor = float(importance_floor)
        self.consolidation_threshold = float(consolidation_threshold)
        self._fields = self._build_fields()

    def handle_command(self, raw_text: str) -> MemoryCommandResult:
        text = normalize(raw_text)
        text = re.sub(r"^(?:atlas|atras)\s+", "", text, count=1)

        if not text:
            return MemoryCommandResult(False)

        if self._is_deleted_list_command(text):
            return MemoryCommandResult(
                True,
                self._format_memories(
                    self.memory.list_inactive(limit=20),
                    empty_message="Não há memórias apagadas para restaurar.",
                    title="Memórias apagadas",
                ),
            )

        if self._is_active_list_command(text):
            return MemoryCommandResult(
                True,
                self._format_memories(
                    self.memory.list_records(limit=20),
                    empty_message="Ainda não tenho memórias salvas.",
                    title="Memórias ativas",
                ),
            )

        restore_match = re.fullmatch(
            r"(?:restaura|restaure|restaurar|recupera|recupere|recuperar) "
            r"(?:a )?memoria #?(\d+)",
            text,
        )

        if restore_match:
            memory_id = int(restore_match.group(1))
            restored = self.memory.restore(memory_id)
            message = (
                f"Memória #{memory_id} restaurada."
                if restored
                else f"Não foi possível restaurar a memória #{memory_id}."
            )
            return MemoryCommandResult(True, message)

        delete_match = re.fullmatch(
            r"(?:apaga|apague|apagar|deleta|delete|deletar|"
            r"exclui|exclua|excluir|remove|remova|remover|"
            r"esquece|esqueca|esquecer) (?:a )?memoria #?(\d+)",
            text,
        )

        if delete_match:
            memory_id = int(delete_match.group(1))
            removed = self.memory.forget(memory_id)
            message = (
                f"Memória #{memory_id} removida. Ela ainda pode ser restaurada."
                if removed
                else f"Não encontrei a memória ativa #{memory_id}."
            )
            return MemoryCommandResult(True, message)

        correction = self._handle_correction(raw_text, text)

        if correction.handled:
            return correction

        field_removal = self._handle_field_removal(text)

        if field_removal.handled:
            return field_removal

        forget_fact = re.fullmatch(
            r"(?:esquece|esqueca|apaga|apague|remove|remova) que (.+)",
            text,
        )

        if forget_fact:
            return self._forget_matching_fact(forget_fact.group(1))

        if text in {
            "consolidar memorias",
            "consolide as memorias",
            "remover memorias duplicadas",
            "remova memorias duplicadas",
        }:
            report = self.consolidate()

            if not report.removed_ids:
                return MemoryCommandResult(
                    True,
                    "Não encontrei memórias duplicadas para consolidar.",
                )

            identifiers = ", ".join(
                f"#{memory_id}" for memory_id in report.removed_ids
            )
            return MemoryCommandResult(
                True,
                "Consolidação concluída. As duplicatas "
                f"{identifiers} foram removidas e podem ser restauradas.",
            )

        if text in {
            "otimizar memorias",
            "otimize as memorias",
            "manutencao das memorias",
            "executar manutencao das memorias",
        }:
            decay = self.run_decay()
            consolidation = self.consolidate()
            return MemoryCommandResult(
                True,
                "Manutenção concluída: "
                f"{decay.updated} prioridades atualizadas e "
                f"{len(consolidation.removed_ids)} duplicatas consolidadas.",
            )

        return MemoryCommandResult(False)

    def run_decay(
        self,
        *,
        now: datetime | None = None,
        minimum_interval_days: float = 1.0,
    ) -> MemoryDecayReport:
        if minimum_interval_days < 0:
            raise ValueError("O intervalo mínimo não pode ser negativo.")

        records = self.memory.list_records(limit=10_000)

        if not self.decay_enabled:
            return MemoryDecayReport(
                reviewed=len(records),
                updated=0,
                unchanged=len(records),
            )

        reference_now = self._as_utc(now or datetime.now(UTC))
        updated = 0
        unchanged = 0

        for record in records:
            reference = self._decay_reference(record)
            elapsed_days = max(
                0.0,
                (reference_now - reference).total_seconds() / 86_400,
            )

            if elapsed_days < minimum_interval_days:
                unchanged += 1
                continue

            factor = math.pow(0.5, elapsed_days / self.half_life_days)
            new_importance = max(
                self.importance_floor,
                record.importance * factor,
            )

            self.memory.set_decay_state(
                record.id,
                importance=new_importance,
                decayed_at=reference_now,
            )

            if not math.isclose(
                new_importance,
                record.importance,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                updated += 1
            else:
                unchanged += 1

        return MemoryDecayReport(
            reviewed=len(records),
            updated=updated,
            unchanged=unchanged,
        )

    def consolidate(
        self,
        *,
        dry_run: bool = False,
        limit: int = 500,
    ) -> MemoryConsolidationReport:
        records = self.memory.list_records(limit=limit)
        processed: set[int] = set()
        groups: list[MemoryConsolidationGroup] = []
        removed_ids: list[int] = []

        for index, record in enumerate(records):
            if record.id in processed:
                continue

            matches: list[tuple[MemoryRecord, float]] = []

            for candidate in records[index + 1 :]:
                if candidate.id in processed:
                    continue

                if not self._can_consolidate(record, candidate):
                    continue

                similarity = self._similarity(
                    record.content,
                    candidate.content,
                )

                if similarity >= self.consolidation_threshold:
                    matches.append((candidate, similarity))

            if not matches:
                continue

            group_records = [record, *(item[0] for item in matches)]
            keeper = max(group_records, key=self._keeper_priority)
            duplicates = [
                item for item in group_records if item.id != keeper.id
            ]
            duplicate_ids = tuple(item.id for item in duplicates)
            similarity = min(item[1] for item in matches)

            groups.append(
                MemoryConsolidationGroup(
                    keeper_id=keeper.id,
                    duplicate_ids=duplicate_ids,
                    similarity=similarity,
                )
            )
            processed.update(item.id for item in group_records)

            if dry_run:
                continue

            for duplicate in duplicates:
                if self.memory.forget(duplicate.id):
                    removed_ids.append(duplicate.id)

        return MemoryConsolidationReport(
            reviewed=len(records),
            groups=tuple(groups),
            removed_ids=tuple(removed_ids),
            dry_run=dry_run,
        )

    def _handle_correction(
        self,
        raw_text: str,
        normalized_text: str,
    ) -> MemoryCommandResult:
        id_match = re.fullmatch(
            r"(?:corrige|corrija|corrigir|altera|altere|alterar|"
            r"atualiza|atualize|atualizar|"
            r"mude|mudar) (?:a )?memoria #?(\d+) para (.+)",
            normalized_text,
        )

        if id_match:
            memory_id = int(id_match.group(1))
            value = self._raw_value_after_connector(raw_text)
            updated = self.memory.update(memory_id, content=value)

            if updated is None:
                return MemoryCommandResult(
                    True,
                    f"Não encontrei a memória ativa #{memory_id}.",
                )

            return MemoryCommandResult(
                True,
                f"Memória #{memory_id} corrigida para: {updated.content}.",
            )

        correction_prefixes = (
            "corrige ",
            "corrija ",
            "corrigir ",
            "altera ",
            "altere ",
            "alterar ",
            "atualiza ",
            "atualize ",
            "atualizar ",
            "mude ",
            "mudar ",
        )

        if not normalized_text.startswith(correction_prefixes):
            return MemoryCommandResult(False)

        field = self._resolve_field(normalized_text)

        if field is None or " para " not in normalized_text:
            return MemoryCommandResult(False)

        value = self._raw_value_after_connector(raw_text)
        record, action = self.memory.upsert_keyed_record(
            field.formatter(value),
            memory_key=field.key,
            category=field.category,
            source="user_correction",
            importance=field.importance,
        )
        verb = "criada" if action == "created" else "corrigida"
        return MemoryCommandResult(
            True,
            f"Memória #{record.id} {verb}: {record.content}.",
        )

    def _handle_field_removal(self, text: str) -> MemoryCommandResult:
        prefixes = (
            "esquece ",
            "esqueca ",
            "esquecer ",
            "apaga ",
            "apague ",
            "apagar ",
            "deleta ",
            "delete ",
            "deletar ",
            "remove ",
            "remova ",
            "remover ",
            "exclui ",
            "exclua ",
            "excluir ",
        )

        if not text.startswith(prefixes):
            return MemoryCommandResult(False)

        field = self._resolve_field(text)

        if field is None:
            return MemoryCommandResult(False)

        record = self.memory.get_by_key(field.key)

        if record is None:
            return MemoryCommandResult(
                True,
                "Não encontrei essa informação nas memórias ativas.",
            )

        self.memory.forget(record.id)
        return MemoryCommandResult(
            True,
            f"Memória #{record.id} removida. Ela ainda pode ser restaurada.",
        )

    def _forget_matching_fact(self, query: str) -> MemoryCommandResult:
        matches = self.memory.search_records(query, limit=3)

        if not matches:
            return MemoryCommandResult(
                True,
                "Não encontrei uma memória correspondente.",
            )

        if len(matches) > 1:
            identifiers = ", ".join(f"#{record.id}" for record in matches)
            return MemoryCommandResult(
                True,
                "Encontrei mais de uma possibilidade: "
                f"{identifiers}. Informe o número da memória que deseja apagar.",
            )

        record = matches[0]
        self.memory.forget(record.id)
        return MemoryCommandResult(
            True,
            f"Memória #{record.id} removida. Ela ainda pode ser restaurada.",
        )

    def _resolve_field(self, text: str) -> _FactField | None:
        for field in self._fields:
            if any(alias in text for alias in field.aliases):
                return field

        return None

    def _build_fields(self) -> tuple[_FactField, ...]:
        name = self.user_name
        return (
            _FactField(
                key="profile.location",
                category="profile",
                importance=0.85,
                aliases=("minha cidade", "onde eu moro", "minha localizacao"),
                formatter=lambda value: f"{name} mora em {value}",
            ),
            _FactField(
                key="profile.birthplace",
                category="profile",
                importance=0.75,
                aliases=("onde eu nasci", "minha cidade natal"),
                formatter=lambda value: f"{name} nasceu em {value}",
            ),
            _FactField(
                key="profile.age",
                category="profile",
                importance=0.65,
                aliases=("minha idade",),
                formatter=lambda value: (
                    f"{name} tem {value}"
                    if "ano" in normalize(value)
                    else f"{name} tem {value} anos"
                ),
            ),
            _FactField(
                key="profile.name",
                category="profile",
                importance=0.95,
                aliases=("meu nome",),
                formatter=lambda value: f"O nome do usuário é {value}",
            ),
            _FactField(
                key="work.role",
                category="work",
                importance=0.80,
                aliases=("minha profissao", "meu cargo"),
                formatter=lambda value: f"{name} trabalha como {value}",
            ),
            _FactField(
                key="work.company",
                category="work",
                importance=0.75,
                aliases=("minha empresa", "onde eu trabalho"),
                formatter=lambda value: f"{name} trabalha em {value}",
            ),
            _FactField(
                key="project.current",
                category="project",
                importance=0.90,
                aliases=("meu projeto", "projeto atual"),
                formatter=lambda value: f"O projeto atual de {name} é {value}",
            ),
        )

    @staticmethod
    def _raw_value_after_connector(raw_text: str) -> str:
        match = re.search(r"\bpara\b\s+(.+)$", raw_text, re.IGNORECASE)

        if match is None or not match.group(1).strip():
            raise ValueError("O novo valor da memória não foi informado.")

        return match.group(1).strip(" .")

    @staticmethod
    def _is_active_list_command(text: str) -> bool:
        return text in {
            "listar memoria",
            "listar memorias",
            "listar minha memoria",
            "liste minha memoria",
            "liste as memorias",
            "mostrar memoria",
            "mostrar memorias",
            "mostre minha memoria",
            "mostre minhas memorias",
            "minha memoria",
            "minhas memorias",
            "quais memorias",
            "quais sao minhas memorias",
            "o que voce lembra",
            "o que voce lembra de mim",
            "o que voce lembra sobre mim",
        }

    @staticmethod
    def _is_deleted_list_command(text: str) -> bool:
        has_memory = re.search(r"\bmemorias?\b", text) is not None
        has_deleted_status = (
            re.search(
                r"\b(?:apagadas?|removidas?|excluidas?|deletadas?)\b",
                text,
            )
            is not None
        )
        has_list_intent = (
            re.search(
                r"\b(?:lista|liste|listar|mostra|mostre|mostrar|"
                r"veja|ver|quais)\b",
                text,
            )
            is not None
        )
        starts_with_memory = re.match(r"^memorias?\b", text) is not None

        return (
            has_memory
            and has_deleted_status
            and (has_list_intent or starts_with_memory)
        )

    @staticmethod
    def _format_memories(
        records: list[MemoryRecord],
        *,
        empty_message: str,
        title: str,
    ) -> str:
        if not records:
            return empty_message

        items = "; ".join(
            f"#{record.id} [{record.category}] {record.content}"
            for record in records
        )
        return f"{title}: {items}."

    @staticmethod
    def _can_consolidate(
        left: MemoryRecord,
        right: MemoryRecord,
    ) -> bool:
        if left.category != right.category:
            return False

        if (
            left.memory_key is not None
            and right.memory_key is not None
            and left.memory_key != right.memory_key
        ):
            return False

        return True

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        normalized_left = normalize(left)
        normalized_right = normalize(right)
        sequence = SequenceMatcher(
            None,
            normalized_left,
            normalized_right,
        ).ratio()
        left_tokens = set(normalized_left.split())
        right_tokens = set(normalized_right.split())
        union = left_tokens | right_tokens
        jaccard = (
            len(left_tokens & right_tokens) / len(union)
            if union
            else 0.0
        )
        return max(sequence, jaccard)

    @staticmethod
    def _keeper_priority(record: MemoryRecord) -> tuple[int, float, int, int]:
        return (
            int(record.memory_key is not None),
            record.importance,
            record.access_count,
            record.id,
        )

    @classmethod
    def _decay_reference(cls, record: MemoryRecord) -> datetime:
        candidates = [record.updated_at]

        if record.last_decay_at is not None:
            candidates.append(record.last_decay_at)

        if record.last_accessed_at is not None:
            candidates.append(record.last_accessed_at)

        return max(cls._as_utc(value) for value in candidates)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value.astimezone(UTC)
