"""Pós-verificação segura de ações controladas do Atlas Vision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class PostActionVerification:
    """Resultado da verificação de efeito após uma ação de interface."""

    verified: bool
    reason_code: str
    evidence: tuple[str, ...] = ()

    @property
    def user_summary(self) -> str:
        if self.evidence:
            return "; ".join(self.evidence)
        return "nenhuma evidência pós-ação confiável foi observada"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalized_text(value: object) -> str:
    return " ".join(_text(value).casefold().split())


def _target(state: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not state:
        return {}
    return _mapping(state.get("target"))


def _page_value(state: Mapping[str, Any] | None, key: str) -> object:
    if not state:
        return None
    return state.get(key)


def _changed_nonempty(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    key: str,
) -> bool:
    before_value = _text(_page_value(before, key))
    after_value = _text(_page_value(after, key))
    return bool(before_value and after_value and before_value != after_value)


def _target_state_change(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> tuple[str, str] | None:
    before_target = _target(before)
    after_target = _target(after)

    if not before_target or not after_target:
        return None

    labels = {
        "checked": "o estado marcado/desmarcado do elemento mudou",
        "aria_pressed": "o estado pressionado do elemento mudou",
        "aria_expanded": "o estado expandido do elemento mudou",
        "aria_selected": "o estado selecionado do elemento mudou",
    }

    for key, message in labels.items():
        before_value = before_target.get(key)
        after_value = after_target.get(key)

        if (
            before_value is not None
            and after_value is not None
            and before_value != after_value
        ):
            return key, message

    return None


def verify_click_post_action(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    semantic_kind: str = "",
) -> PostActionVerification:
    """Verifica evidências observáveis depois de um clique DOM.

    A função é deliberadamente conservadora. Ela nunca executa ou repete
    ações; apenas compara observações feitas antes e depois do clique.
    """

    if not after:
        return PostActionVerification(
            verified=False,
            reason_code="post_state_unavailable",
            evidence=("não foi possível ler o estado da página após o clique",),
        )

    if _changed_nonempty(before, after, "url"):
        return PostActionVerification(
            verified=True,
            reason_code="navigation_changed",
            evidence=("a página navegou para outro endereço",),
        )

    after_target = _target(after)
    before_target = _target(before)
    target_focused = bool(after_target.get("focused"))
    was_focused = bool(before_target.get("focused"))

    if target_focused and (
        semantic_kind in {"search_input", "text_input"}
        or not was_focused
        or not before_target
    ):
        return PostActionVerification(
            verified=True,
            reason_code="target_focused",
            evidence=("o elemento alvo está com foco após o clique",),
        )

    target_change = _target_state_change(before, after)
    if target_change is not None:
        _, message = target_change
        return PostActionVerification(
            verified=True,
            reason_code="target_state_changed",
            evidence=(message,),
        )

    before_dialogs = _page_value(before, "dialog_count")
    after_dialogs = _page_value(after, "dialog_count")
    if (
        before_dialogs is not None
        and after_dialogs is not None
        and before_dialogs != after_dialogs
    ):
        return PostActionVerification(
            verified=True,
            reason_code="dialog_state_changed",
            evidence=("a quantidade de diálogos visíveis mudou",),
        )

    before_expanded = _page_value(before, "expanded_count")
    after_expanded = _page_value(after, "expanded_count")
    if (
        before_expanded is not None
        and after_expanded is not None
        and before_expanded != after_expanded
    ):
        return PostActionVerification(
            verified=True,
            reason_code="expanded_state_changed",
            evidence=("o estado expandido da interface mudou",),
        )

    if _changed_nonempty(before, after, "title"):
        return PostActionVerification(
            verified=True,
            reason_code="title_changed",
            evidence=("o título da página mudou após o clique",),
        )

    before_exists = bool(before_target.get("exists"))
    after_exists = bool(after_target.get("exists"))
    before_count = _page_value(before, "interactive_count")
    after_count = _page_value(after, "interactive_count")
    if (
        before_exists
        and not after_exists
        and before_count is not None
        and after_count is not None
        and before_count != after_count
    ):
        return PostActionVerification(
            verified=True,
            reason_code="target_replaced",
            evidence=("o elemento alvo foi substituído e a interface mudou",),
        )

    return PostActionVerification(
        verified=False,
        reason_code="post_action_inconclusive",
        evidence=("não houve mudança observável suficiente para confirmar o efeito",),
    )


def verify_uia_post_action(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    semantic_kind: str = "",
    expected_action: str = "",
) -> PostActionVerification:
    """Verifica efeitos observáveis de uma ação estrutural Windows UIA."""

    if not after:
        return PostActionVerification(
            verified=False,
            reason_code="uia_post_state_unavailable",
            evidence=("não foi possível ler o estado UIA após a ação",),
        )

    before_target = _target(before)
    after_target = _target(after)

    if not after_target:
        return PostActionVerification(
            verified=False,
            reason_code="uia_target_unavailable",
            evidence=("o elemento alvo não pôde ser revalidado após a ação",),
        )

    if expected_action == "check" and after_target.get("checked") == 1:
        return PostActionVerification(
            verified=True,
            reason_code="uia_target_checked",
            evidence=("o controle Windows ficou marcado",),
        )

    if expected_action == "uncheck" and after_target.get("checked") == 0:
        return PostActionVerification(
            verified=True,
            reason_code="uia_target_unchecked",
            evidence=("o controle Windows ficou desmarcado",),
        )

    if expected_action == "select" and after_target.get("selected") is True:
        return PostActionVerification(
            verified=True,
            reason_code="uia_target_selected",
            evidence=("o item Windows ficou selecionado",),
        )

    if expected_action == "expand" and after_target.get("expanded") == 1:
        return PostActionVerification(
            verified=True,
            reason_code="uia_target_expanded",
            evidence=("o controle Windows ficou expandido",),
        )

    if expected_action == "collapse" and after_target.get("expanded") == 0:
        return PostActionVerification(
            verified=True,
            reason_code="uia_target_collapsed",
            evidence=("o controle Windows ficou recolhido",),
        )

    if semantic_kind == "menu" and expected_action in {"expand", "collapse"}:
        before_menu_count = _page_value(before, "menu_surface_count")
        after_menu_count = _page_value(after, "menu_surface_count")
        if isinstance(before_menu_count, int) and isinstance(after_menu_count, int):
            if expected_action == "expand" and after_menu_count > before_menu_count:
                return PostActionVerification(
                    verified=True,
                    reason_code="uia_menu_surface_opened",
                    evidence=("novos itens de menu ficaram visíveis via UIA",),
                )
            if expected_action == "collapse" and after_menu_count < before_menu_count:
                return PostActionVerification(
                    verified=True,
                    reason_code="uia_menu_surface_closed",
                    evidence=("os itens do menu deixaram de ficar visíveis via UIA",),
                )

    focused = bool(after_target.get("focused"))
    was_focused = bool(before_target.get("focused"))
    if focused and (
        semantic_kind in {"search_input", "text_input"}
        or not was_focused
        or not before_target
    ):
        return PostActionVerification(
            verified=True,
            reason_code="uia_target_focused",
            evidence=("o elemento Windows alvo está com foco após a ação",),
        )

    for key, message in (
        ("checked", "o estado marcado/desmarcado do controle Windows mudou"),
        ("selected", "o estado selecionado do controle Windows mudou"),
    ):
        before_value = before_target.get(key)
        after_value = after_target.get(key)
        if (
            before_value is not None
            and after_value is not None
            and before_value != after_value
        ):
            return PostActionVerification(
                verified=True,
                reason_code="uia_target_state_changed",
                evidence=(message,),
            )

    before_title = _text(_page_value(before, "window_title"))
    after_title = _text(_page_value(after, "window_title"))
    if before_title and after_title and before_title != after_title:
        return PostActionVerification(
            verified=True,
            reason_code="uia_window_changed",
            evidence=("a janela ativa mudou após a ação",),
        )

    return PostActionVerification(
        verified=False,
        reason_code="uia_post_action_inconclusive",
        evidence=(
            "não houve mudança UIA suficiente para confirmar o efeito da ação",
        ),
    )


def verify_text_fill_post_action(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    expected_text: str,
) -> PostActionVerification:
    """Confirma preenchimento estrutural comparando o valor final do alvo."""

    if not after:
        return PostActionVerification(
            verified=False,
            reason_code="text_fill_post_state_unavailable",
            evidence=("não foi possível ler o campo após o preenchimento",),
        )

    after_target = _target(after)
    if not after_target:
        return PostActionVerification(
            verified=False,
            reason_code="text_fill_target_unavailable",
            evidence=("o campo não pôde ser revalidado após o preenchimento",),
        )

    expected = _normalized_text(expected_text)
    final_value = _normalized_text(after_target.get("value"))
    if not final_value:
        final_value = _normalized_text(after_target.get("text"))

    if expected and final_value == expected:
        return PostActionVerification(
            verified=True,
            reason_code="text_fill_value_confirmed",
            evidence=("o valor final do campo corresponde ao texto solicitado",),
        )

    before_target = _target(before)
    before_value = _normalized_text(before_target.get("value"))
    if not before_value:
        before_value = _normalized_text(before_target.get("text"))

    if final_value and final_value != before_value:
        return PostActionVerification(
            verified=False,
            reason_code="text_fill_value_changed_but_not_confirmed",
            evidence=(
                "o campo mudou, mas o valor final não corresponde exatamente ao solicitado",
            ),
        )

    return PostActionVerification(
        verified=False,
        reason_code="text_fill_post_action_inconclusive",
        evidence=("não houve evidência estrutural suficiente do texto preenchido",),
    )


def verify_control_state_post_action(
    after: Mapping[str, Any] | None,
    *,
    desired_state: bool,
) -> PostActionVerification:
    """Confirma checkbox/radio/switch pelo estado estrutural final."""

    if not after:
        return PostActionVerification(
            verified=False,
            reason_code="control_post_state_unavailable",
            evidence=("não foi possível ler o controle após a alteração",),
        )

    after_target = _target(after)
    if not after_target:
        return PostActionVerification(
            verified=False,
            reason_code="control_target_unavailable",
            evidence=("o controle não pôde ser revalidado",),
        )

    checked = after_target.get("checked")
    if isinstance(checked, bool) and checked is desired_state:
        return PostActionVerification(
            verified=True,
            reason_code=(
                "control_checked_confirmed"
                if desired_state
                else "control_unchecked_confirmed"
            ),
            evidence=(
                "o estado final do controle corresponde ao solicitado",
            ),
        )

    return PostActionVerification(
        verified=False,
        reason_code="control_state_not_confirmed",
        evidence=("o estado final do controle não corresponde ao solicitado",),
    )
