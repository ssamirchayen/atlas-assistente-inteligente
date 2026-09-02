"""Grounding estrutural para aplicações Windows via UI Automation.

A Etapa 8 usa UIA como terceira camada estrutural do Atlas Vision:

    Qt próprio -> DOM/Playwright -> Windows UI Automation -> Vision/Qwen

Ações UIA são deliberadamente conservadoras. O módulo nunca usa coordenadas
para clicar e nunca usa ``pyautogui``. Elementos são re-resolvidos por uma
impressão digital estrutural imediatamente antes de qualquer ação.
"""

from __future__ import annotations

import os
import re
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from difflib import SequenceMatcher
from time import sleep
from typing import Any, Iterator, Mapping

from atlas.vision.models import (
    VisionBoundingBox,
    VisionGroundingResult,
    VisionUIElement,
)


@dataclass(frozen=True, slots=True)
class WindowsUIAMatch:
    """Elemento Windows localizado estruturalmente via Microsoft UIA."""

    grounding: VisionGroundingResult
    confidence: float
    fingerprint: dict[str, str]
    semantic_kind: str = ""
    window_title: str = ""
    process_id: int = 0
    window_handle: int = 0

    def action_fingerprint(self) -> dict[str, str]:
        return dict(self.fingerprint)


@dataclass(frozen=True, slots=True)
class WindowsUIAActionResult:
    """Resultado de uma única ação UIA estrutural da Etapa 9."""

    executed: bool
    already_satisfied: bool = False
    reason_code: str = ""


_STOPWORDS = {
    "a",
    "ao",
    "botao",
    "campo",
    "caixa",
    "da",
    "de",
    "do",
    "em",
    "esta",
    "fica",
    "menu",
    "na",
    "no",
    "o",
    "onde",
}

_SEARCH_WORDS = {
    "busca",
    "buscar",
    "pesquisa",
    "pesquisar",
    "search",
}

_SEARCH_CONTAINER_WORDS = {
    "barra",
    "campo",
    "caixa",
    "entrada",
    "input",
}

_TEXT_CONTROL_TYPES = {
    "combobox",
    "document",
    "edit",
}

_BUTTON_CONTROL_TYPES = {
    "button",
    "checkbox",
    "hyperlink",
    "menuitem",
    "radiobutton",
    "splitbutton",
    "tabitem",
}


@contextmanager
def _com_scope() -> Iterator[None]:
    """Inicializa COM quando pywin32 estiver disponível.

    O comando da GUI roda em uma thread de worker persistente. Inicializar COM
    explicitamente evita depender do estado COM de outra thread do processo.
    """

    pythoncom = None
    try:
        import pythoncom as _pythoncom  # type: ignore[import-not-found]

        pythoncom = _pythoncom
        pythoncom.CoInitialize()
    except (ImportError, OSError):
        pythoncom = None

    try:
        yield
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except OSError:
                pass


def is_windows_uia_available() -> bool:
    """Retorna ``True`` somente quando UIA pode ser usada neste runtime."""

    if os.name != "nt":
        return False

    try:
        import pywinauto  # noqa: F401
    except (ImportError, OSError):
        return False

    return True


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(
        char for char in text if not unicodedata.combining(char)
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _tokens(value: object) -> list[str]:
    return [
        token
        for token in _normalize(value).split()
        if token not in _STOPWORDS
    ]


def _is_search_entry_request(query: str) -> bool:
    raw = _normalize(query)
    words = set(raw.split())

    direct = bool(words & _SEARCH_WORDS) and bool(
        words & _SEARCH_CONTAINER_WORDS
    )
    typing_language = any(
        phrase in raw
        for phrase in (
            "onde eu digito",
            "onde digito",
            "onde escrever",
            "onde eu escrevo",
            "onde pesquisar",
            "onde buscar",
        )
    )
    return direct or typing_language


def _semantic_kind(query: str) -> str:
    if _is_search_entry_request(query):
        return "search_input"

    raw = _normalize(query)

    if any(term in raw for term in ("caixa de selecao", "checkbox")):
        return "checkbox"
    if any(term in raw for term in ("botao de opcao", "radio button", "radiobutton")):
        return "radio_button"
    if any(term in raw for term in ("caixa de combinacao", "combobox", "combo box")):
        return "combo_box"
    if "aba" in raw or "tab" in raw:
        return "tab"
    if "menu" in raw:
        return "menu"
    if any(term in raw for term in ("item da lista", "item de lista", "lista")):
        return "list_item"
    if "botao" in raw:
        return "button"
    if any(
        term in raw
        for term in (
            "campo",
            "caixa",
            "barra",
            "texto",
            "digito",
            "escrevo",
        )
    ):
        return "text_input"
    return ""


def _candidate_text(candidate: Mapping[str, Any]) -> str:
    return " ".join(
        str(candidate.get(key, "") or "")
        for key in (
            "name",
            "automation_id",
            "control_type",
            "class_name",
            "help_text",
            "access_key",
            "window_title",
        )
    )


def _is_text_control(candidate: Mapping[str, Any]) -> bool:
    return _normalize(candidate.get("control_type")) in _TEXT_CONTROL_TYPES


def _base_similarity(query: str, candidate: Mapping[str, Any]) -> float:
    query_tokens = _tokens(query)
    candidate_tokens = _tokens(_candidate_text(candidate))

    if not query_tokens or not candidate_tokens:
        return 0.0

    token_scores: list[float] = []
    for query_token in query_tokens:
        token_scores.append(
            max(
                SequenceMatcher(None, query_token, candidate_token).ratio()
                for candidate_token in candidate_tokens
            )
        )

    token_score = sum(token_scores) / len(token_scores)
    phrase_score = SequenceMatcher(
        None,
        " ".join(query_tokens),
        " ".join(candidate_tokens),
    ).ratio()
    return max(token_score, phrase_score)


def _score_uia_candidate(query: str, candidate: Mapping[str, Any]) -> float:
    """Pontuação pura e testável de um candidato UIA."""

    semantic_kind = _semantic_kind(query)
    control_type = _normalize(candidate.get("control_type"))
    candidate_norm = _normalize(_candidate_text(candidate))
    query_tokens = _tokens(query)
    candidate_tokens = set(_tokens(candidate_norm))

    base = _base_similarity(query, candidate)
    score = base * 0.72

    if query_tokens and all(token in candidate_tokens for token in query_tokens):
        score += 0.18

    query_norm = _normalize(query)
    if query_norm and query_norm in candidate_norm:
        score += 0.20

    if semantic_kind == "search_input":
        if control_type in _TEXT_CONTROL_TYPES:
            score = max(score, 0.66)
            score += 0.12

        if any(
            term in candidate_norm
            for term in (
                "pesquisa",
                "pesquisar",
                "busca",
                "buscar",
                "search",
            )
        ):
            score += 0.28

    elif semantic_kind == "text_input":
        if control_type in _TEXT_CONTROL_TYPES:
            score = max(score, 0.72)

    elif semantic_kind == "button":
        if control_type in _BUTTON_CONTROL_TYPES:
            score += 0.16
        else:
            score -= 0.20

    elif semantic_kind == "checkbox":
        if control_type == "checkbox":
            score = max(score, 0.84)
            score += 0.10
        else:
            score -= 0.22

    elif semantic_kind == "radio_button":
        if control_type == "radiobutton":
            score = max(score, 0.84)
            score += 0.10
        else:
            score -= 0.22

    elif semantic_kind == "tab":
        if control_type == "tabitem":
            score = max(score, 0.84)
            score += 0.10
        else:
            score -= 0.20

    elif semantic_kind == "menu":
        # Aplicativos WinUI modernos (incluindo o Bloco de Notas atual)
        # podem expor cabeçalhos de menu como Button/SplitButton em vez de
        # MenuItem. Continuamos exigindo correspondência textual forte e
        # usamos somente padrões UIA para a ação.
        if control_type in {"menu", "menuitem", "button", "splitbutton"}:
            score = max(score, 0.80)
            score += 0.10
        else:
            score -= 0.18

    elif semantic_kind == "list_item":
        if control_type in {"listitem", "treeitem", "dataitem"}:
            score = max(score, 0.80)
            score += 0.10
        else:
            score -= 0.16

    elif semantic_kind == "combo_box":
        if control_type == "combobox":
            score = max(score, 0.86)
            score += 0.08
        else:
            score -= 0.20

    if not bool(candidate.get("enabled", True)):
        score -= 0.25

    return max(0.0, min(score, 1.0))


def _active_window(desktop: Any) -> Any | None:
    get_active = getattr(desktop, "get_active", None)
    if callable(get_active):
        try:
            return get_active()
        except Exception:  # pywinauto raises backend-specific errors
            pass

    windows = getattr(desktop, "windows", None)
    if callable(windows):
        try:
            active = windows(active_only=True)
        except Exception:
            active = []
        if active:
            return active[0]

    return None


def _safe_attr(value: Any, attribute: str, default: Any = None) -> Any:
    try:
        return getattr(value, attribute, default)
    except Exception:
        return default


def _wrapper_value(wrapper: Any, method: str, default: Any = "") -> Any:
    value = _safe_attr(wrapper, method, None)
    if callable(value):
        try:
            return value()
        except Exception:
            return default
    return default


def _element_info_value(wrapper: Any, attribute: str, default: Any = "") -> Any:
    info = _safe_attr(wrapper, "element_info", None)
    if info is None:
        return default
    value = _safe_attr(info, attribute, default)
    return value if value is not None else default


def _rect_payload(wrapper: Any) -> tuple[float, float, float, float] | None:
    rectangle = getattr(wrapper, "rectangle", None)
    if not callable(rectangle):
        return None

    try:
        rect = rectangle()
        left = float(rect.left)
        top = float(rect.top)
        right = float(rect.right)
        bottom = float(rect.bottom)
    except Exception:
        return None

    if right <= left or bottom <= top:
        return None

    return left, top, right, bottom


def _candidate_from_wrapper(
    wrapper: Any,
    *,
    window_title: str,
    process_id: int,
    window_handle: int = 0,
) -> dict[str, Any] | None:
    rect = _rect_payload(wrapper)
    if rect is None:
        return None

    visible = bool(_wrapper_value(wrapper, "is_visible", True))
    if not visible:
        return None

    enabled = bool(_wrapper_value(wrapper, "is_enabled", True))

    return {
        "name": str(_element_info_value(wrapper, "name", "") or "").strip(),
        "automation_id": str(
            _element_info_value(wrapper, "automation_id", "") or ""
        ).strip(),
        "control_type": str(
            _element_info_value(wrapper, "control_type", "") or ""
        ).strip(),
        "class_name": str(
            _element_info_value(wrapper, "class_name", "") or ""
        ).strip(),
        "help_text": str(
            _element_info_value(wrapper, "help_text", "") or ""
        ).strip(),
        "access_key": str(
            _element_info_value(wrapper, "access_key", "") or ""
        ).strip(),
        "window_title": window_title,
        "process_id": process_id,
        "window_handle": window_handle,
        "enabled": enabled,
        "is_password": bool(
            _element_info_value(wrapper, "is_password", False)
        ),
        "left": rect[0],
        "top": rect[1],
        "right": rect[2],
        "bottom": rect[3],
    }


def _window_handle(wrapper: Any) -> int:
    handle = _safe_attr(wrapper, "handle", 0)
    try:
        return int(handle or 0)
    except (TypeError, ValueError):
        return 0


def _window_title(wrapper: Any) -> str:
    return str(
        _wrapper_value(wrapper, "window_text", "")
        or _element_info_value(wrapper, "name", "")
        or ""
    ).strip()


def _foreground_window_handle() -> int:
    """Retorna o HWND realmente em primeiro plano no Windows."""

    if os.name != "nt":
        return 0

    try:
        import ctypes

        handle = ctypes.windll.user32.GetForegroundWindow()
        return int(handle or 0)
    except (AttributeError, OSError, TypeError, ValueError):
        return 0


def _set_native_foreground_window(window_handle: int) -> bool:
    """Traz um HWND validado ao foreground sem usar mouse/coordenadas."""

    if os.name != "nt" or window_handle <= 0:
        return False

    try:
        import ctypes

        user32 = ctypes.windll.user32
        sw_restore = 9
        user32.ShowWindow(window_handle, sw_restore)
        user32.BringWindowToTop(window_handle)
        user32.SetForegroundWindow(window_handle)
    except (AttributeError, OSError, TypeError, ValueError):
        return False

    for _ in range(6):
        if _foreground_window_handle() == window_handle:
            return True
        sleep(0.04)
    return False


def _bring_window_to_foreground(window: Any) -> bool:
    """Faz o handoff de foco Atlas -> app externo e confirma o foreground.

    ``pywinauto`` pode conseguir focar um controle UIA sem promover a janela
    top-level visualmente. Por isso a Etapa 8.2 confirma o HWND real do
    foreground antes de permitir a ação estrutural.
    """

    window_handle = _window_handle(window)
    if window_handle <= 0:
        return False

    if _foreground_window_handle() == window_handle:
        return True

    is_minimized = getattr(window, "is_minimized", None)
    restore = getattr(window, "restore", None)
    if callable(is_minimized) and callable(restore):
        try:
            if bool(is_minimized()):
                restore()
        except Exception:
            pass

    set_focus = getattr(window, "set_focus", None)
    if callable(set_focus):
        try:
            set_focus()
        except Exception:
            pass

    if _foreground_window_handle() == window_handle:
        return True

    return _set_native_foreground_window(window_handle)


def _is_external_top_window(window: Any) -> bool:
    process_id = int(_element_info_value(window, "process_id", 0) or 0)
    if not process_id or process_id == os.getpid():
        return False
    if not bool(_wrapper_value(window, "is_visible", True)):
        return False
    if not _window_title(window):
        return False

    class_name = _normalize(_element_info_value(window, "class_name", ""))
    if class_name in {"progman", "workerw", "shell traywnd"}:
        return False
    return True


def _external_target_window(desktop: Any) -> Any | None:
    """Escolhe com segurança a janela externa relevante.

    Se um aplicativo externo está em primeiro plano, ele continua sendo a
    origem oficial. Quando a própria GUI do Atlas ganhou foco apenas para o
    usuário digitar o comando, escolhemos a primeira janela externa visível
    na ordem Z do Desktop (normalmente a aplicação logo atrás do Atlas).
    """

    active = _active_window(desktop)
    if active is not None and _is_external_top_window(active):
        return active

    windows = getattr(desktop, "windows", None)
    if not callable(windows):
        return None

    try:
        top_windows = windows()
    except Exception:
        return None

    for window in top_windows:
        if _is_external_top_window(window):
            return window
    return None


def inspect_foreground_uia_elements(*, limit: int = 240) -> list[dict[str, Any]]:
    """Inspeciona o aplicativo Windows externo alvo.

    O processo do Atlas continua excluído. Quando o Atlas está em primeiro
    plano porque o comando foi digitado na GUI, a Etapa 8.1 pode inspecionar
    a primeira aplicação externa visível imediatamente abaixo dele, sem usar
    coordenadas nem clicar na tela.
    """

    if not is_windows_uia_available():
        return []

    with _com_scope():
        try:
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            window = _external_target_window(desktop)
        except Exception:
            return []

        if window is None:
            return []

        process_id = int(_element_info_value(window, "process_id", 0) or 0)
        window_title = _window_title(window)
        window_handle = _window_handle(window)

        wrappers: list[Any] = [window]
        descendants = getattr(window, "descendants", None)
        if callable(descendants):
            try:
                wrappers.extend(descendants())
            except Exception:
                pass

        candidates: list[dict[str, Any]] = []
        for wrapper in wrappers[: max(1, limit)]:
            candidate = _candidate_from_wrapper(
                wrapper,
                window_title=window_title,
                process_id=process_id,
                window_handle=window_handle,
            )
            if candidate is not None:
                candidates.append(candidate)

        return candidates


def _fingerprint(candidate: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: str(candidate.get(key, "") or "").strip()
        for key in (
            "name",
            "automation_id",
            "control_type",
            "class_name",
            "help_text",
            "access_key",
        )
    }


def _normalized_bbox(
    candidate: Mapping[str, Any],
    *,
    screen_width: int,
    screen_height: int,
) -> VisionBoundingBox | None:
    try:
        left = float(candidate["left"])
        top = float(candidate["top"])
        right = float(candidate["right"])
        bottom = float(candidate["bottom"])
    except (KeyError, TypeError, ValueError):
        return None

    if screen_width <= 0 or screen_height <= 0:
        return None

    left = max(0.0, min(left, float(screen_width - 1)))
    top = max(0.0, min(top, float(screen_height - 1)))
    right = max(0.0, min(right, float(screen_width)))
    bottom = max(0.0, min(bottom, float(screen_height)))

    if right <= left or bottom <= top:
        return None

    try:
        return VisionBoundingBox(
            round(left * 1000 / screen_width),
            round(top * 1000 / screen_height),
            round(right * 1000 / screen_width),
            round(bottom * 1000 / screen_height),
        )
    except ValueError:
        return None


def find_windows_uia_match(
    query: str,
    *,
    screen_width: int,
    screen_height: int,
) -> WindowsUIAMatch | None:
    """Localiza o melhor elemento na aplicação Windows em primeiro plano."""

    candidates = inspect_foreground_uia_elements()
    if not candidates:
        return None

    semantic_kind = _semantic_kind(query)
    ranked = sorted(
        ((_score_uia_candidate(query, candidate), candidate) for candidate in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked:
        return None

    confidence, best = ranked[0]

    # Um único campo de texto visível pode ser resolvido por intenção mesmo
    # quando a aplicação não fornece um nome acessível útil.
    if semantic_kind in {"text_input", "search_input"}:
        text_candidates = [
            (score, candidate)
            for score, candidate in ranked
            if _is_text_control(candidate)
        ]
        if len(text_candidates) == 1 and text_candidates[0][0] >= 0.72:
            confidence = max(text_candidates[0][0], 0.88)
            best = text_candidates[0][1]

    semantic_control_types = {
        "checkbox": {"checkbox"},
        "radio_button": {"radiobutton"},
        "tab": {"tabitem"},
        "menu": {"menu", "menuitem", "button", "splitbutton"},
        "list_item": {"listitem", "treeitem", "dataitem"},
        "combo_box": {"combobox"},
    }
    expected_types = semantic_control_types.get(semantic_kind)
    if expected_types:
        typed_candidates = [
            (score, candidate)
            for score, candidate in ranked
            if _normalize(candidate.get("control_type")) in expected_types
        ]
        if len(typed_candidates) == 1 and typed_candidates[0][0] >= 0.68:
            confidence = max(typed_candidates[0][0], 0.88)
            best = typed_candidates[0][1]

    if confidence < 0.63:
        return None

    bbox = _normalized_bbox(
        best,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    if bbox is None:
        return None

    label = (
        str(best.get("name", "") or "").strip()
        or str(best.get("automation_id", "") or "").strip()
        or query
    )
    control_type = str(best.get("control_type", "") or "").strip() or "uia"
    window_title = str(best.get("window_title", "") or "").strip()
    process_id = int(best.get("process_id", 0) or 0)
    window_handle = int(best.get("window_handle", 0) or 0)

    grounding = VisionGroundingResult(
        query=query,
        found=True,
        element=VisionUIElement(
            label=label,
            kind=control_type,
            description=(
                "Elemento localizado estruturalmente pelo Windows UI Automation"
                + (f" em '{window_title}'." if window_title else ".")
            ),
            bbox=bbox,
            confidence=confidence,
        ),
        message=f"Localizei '{label}' pelo Windows UI Automation.",
    )

    return WindowsUIAMatch(
        grounding=grounding,
        confidence=confidence,
        fingerprint=_fingerprint(best),
        semantic_kind=semantic_kind,
        window_title=window_title,
        process_id=process_id,
        window_handle=window_handle,
    )


def locate_windows_uia_element(
    query: str,
    *,
    screen_width: int,
    screen_height: int,
) -> VisionGroundingResult | None:
    """API read-only usada pelo pipeline híbrido de grounding."""

    match = find_windows_uia_match(
        query,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    return None if match is None else match.grounding


def _fingerprint_score(wrapper: Any, fingerprint: Mapping[str, str]) -> float:
    candidate = {
        "name": _element_info_value(wrapper, "name", ""),
        "automation_id": _element_info_value(wrapper, "automation_id", ""),
        "control_type": _element_info_value(wrapper, "control_type", ""),
        "class_name": _element_info_value(wrapper, "class_name", ""),
        "help_text": _element_info_value(wrapper, "help_text", ""),
        "access_key": _element_info_value(wrapper, "access_key", ""),
    }

    weights = {
        "automation_id": 0.34,
        "name": 0.28,
        "control_type": 0.16,
        "class_name": 0.10,
        "help_text": 0.07,
        "access_key": 0.05,
    }

    available_weight = 0.0
    matched_weight = 0.0
    for key, weight in weights.items():
        expected = _normalize(fingerprint.get(key, ""))
        if not expected:
            continue
        available_weight += weight
        actual = _normalize(candidate.get(key, ""))
        if actual == expected:
            matched_weight += weight
        elif actual and SequenceMatcher(None, actual, expected).ratio() >= 0.92:
            matched_weight += weight * 0.75

    if available_weight <= 0.0:
        return 0.0
    return matched_weight / available_weight


def _resolve_target_window(desktop: Any, match: WindowsUIAMatch) -> Any | None:
    """Reencontra a mesma janela externa mesmo após a GUI ganhar foco."""

    windows = getattr(desktop, "windows", None)
    try:
        top_windows = windows() if callable(windows) else []
    except Exception:
        top_windows = []

    active = _active_window(desktop)
    if active is not None:
        top_windows = [active, *top_windows]

    seen: set[int] = set()
    ranked: list[tuple[float, Any]] = []
    for window in top_windows:
        handle = _window_handle(window)
        if handle and handle in seen:
            continue
        if handle:
            seen.add(handle)

        process_id = int(_element_info_value(window, "process_id", 0) or 0)
        if not process_id or process_id == os.getpid():
            continue
        if match.window_handle and handle == match.window_handle:
            return window
        if match.process_id and process_id != match.process_id:
            continue

        title = _window_title(window)
        if match.window_title and title:
            score = SequenceMatcher(
                None,
                _normalize(match.window_title),
                _normalize(title),
            ).ratio()
        else:
            score = 0.75
        ranked.append((score, window))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked and ranked[0][0] >= 0.55:
        return ranked[0][1]
    return None


def _resolve_active_wrapper(match: WindowsUIAMatch) -> Any | None:
    """Nome histórico: revalida o wrapper na janela externa registrada."""

    if not is_windows_uia_available():
        return None

    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        window = _resolve_target_window(desktop, match)
    except Exception:
        return None

    if window is None:
        return None

    process_id = int(_element_info_value(window, "process_id", 0) or 0)
    if match.process_id and process_id and process_id != match.process_id:
        return None
    if process_id and process_id == os.getpid():
        return None

    wrappers: list[Any] = [window]
    descendants = getattr(window, "descendants", None)
    if callable(descendants):
        try:
            wrappers.extend(descendants())
        except Exception:
            pass

    ranked = sorted(
        ((_fingerprint_score(wrapper, match.fingerprint), wrapper) for wrapper in wrappers),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < 0.72:
        return None

    wrapper = ranked[0][1]
    if not bool(_wrapper_value(wrapper, "is_visible", True)):
        return None
    if not bool(_wrapper_value(wrapper, "is_enabled", True)):
        return None
    return wrapper


def _coerce_state_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raw = _normalize(value)
        aliases = {
            "off": 0,
            "collapsed": 0,
            "on": 1,
            "expanded": 1,
            "indeterminate": 2,
            "partially expanded": 2,
            "leaf node": 3,
        }
        return aliases.get(raw)


def _read_toggle_state(wrapper: Any) -> int | None:
    toggle_state = getattr(wrapper, "get_toggle_state", None)
    if callable(toggle_state):
        try:
            return _coerce_state_int(toggle_state())
        except Exception:
            pass

    iface_toggle = _safe_attr(wrapper, "iface_toggle", None)
    current = _safe_attr(iface_toggle, "CurrentToggleState", None)
    return _coerce_state_int(current)


def _read_expand_state(wrapper: Any) -> int | None:
    get_expand_state = getattr(wrapper, "get_expand_state", None)
    if callable(get_expand_state):
        try:
            return _coerce_state_int(get_expand_state())
        except Exception:
            pass

    iface_expand = _safe_attr(wrapper, "iface_expand_collapse", None)
    current = _safe_attr(iface_expand, "CurrentExpandCollapseState", None)
    return _coerce_state_int(current)


def _read_text_value(wrapper: Any) -> str:
    """Lê o valor textual exposto por UIA sem recorrer a OCR."""

    if bool(_element_info_value(wrapper, "is_password", False)):
        return ""

    for method_name in ("get_value", "window_text"):
        method = getattr(wrapper, method_name, None)
        if not callable(method):
            continue
        try:
            value = method()
        except Exception:
            continue
        if value is not None:
            return str(value)

    iface_value = _safe_attr(wrapper, "iface_value", None)
    current_value = _safe_attr(iface_value, "CurrentValue", None)
    if current_value is not None:
        try:
            return str(current_value)
        except Exception:
            return ""

    return ""


def _target_state(wrapper: Any | None) -> dict[str, Any]:
    if wrapper is None:
        return {"exists": False}

    focused = bool(_wrapper_value(wrapper, "has_keyboard_focus", False))
    checked = _read_toggle_state(wrapper)
    expanded = _read_expand_state(wrapper)
    selected: Any = None

    is_selected = getattr(wrapper, "is_selected", None)
    if callable(is_selected):
        try:
            selected = bool(is_selected())
        except Exception:
            selected = None

    if selected is None:
        iface_selection = _safe_attr(wrapper, "iface_selection_item", None)
        current_selected = _safe_attr(iface_selection, "CurrentIsSelected", None)
        if current_selected is not None:
            try:
                selected = bool(current_selected)
            except Exception:
                selected = None

    return {
        "exists": True,
        "focused": focused,
        "checked": checked,
        "selected": selected,
        "expanded": expanded,
        "enabled": bool(_wrapper_value(wrapper, "is_enabled", True)),
        "is_password": bool(
            _element_info_value(wrapper, "is_password", False)
        ),
        "value": _read_text_value(wrapper),
        "name": str(_element_info_value(wrapper, "name", "") or "").strip(),
        "control_type": str(
            _element_info_value(wrapper, "control_type", "") or ""
        ).strip(),
    }


def _visible_menu_surface_count(desktop: Any, process_id: int) -> int:
    """Conta superfícies/itens de menu visíveis do mesmo processo.

    Alguns apps WinUI não publicam ExpandCollapse no cabeçalho do menu.
    Nesses casos, o aumento de Menu/MenuItem visíveis após Invoke é uma
    evidência estrutural de que o menu foi aberto, sem usar pixels.
    """

    if process_id <= 0:
        return 0

    windows = getattr(desktop, "windows", None)
    if not callable(windows):
        return 0

    try:
        top_windows = windows()
    except Exception:
        return 0

    count = 0
    seen: set[tuple[int, str, str]] = set()
    for window in top_windows:
        window_pid = int(_element_info_value(window, "process_id", 0) or 0)
        if window_pid != process_id:
            continue

        wrappers: list[Any] = [window]
        descendants = getattr(window, "descendants", None)
        if callable(descendants):
            try:
                wrappers.extend(descendants())
            except Exception:
                pass

        for wrapper in wrappers:
            if not bool(_wrapper_value(wrapper, "is_visible", True)):
                continue
            control_type = _normalize(
                _element_info_value(wrapper, "control_type", "")
            )
            if control_type not in {"menu", "menuitem"}:
                continue
            key = (
                int(_element_info_value(wrapper, "handle", 0) or 0),
                str(_element_info_value(wrapper, "automation_id", "") or ""),
                str(_element_info_value(wrapper, "name", "") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            count += 1

    return count


def inspect_uia_interaction_state(
    match: WindowsUIAMatch,
) -> dict[str, Any] | None:
    """Observa estado UIA sem executar qualquer ação."""

    if not is_windows_uia_available():
        return None

    with _com_scope():
        wrapper = _resolve_active_wrapper(match)
        window_title = match.window_title
        menu_surface_count = 0
        try:
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            window = _resolve_target_window(desktop, match)
            if window is not None:
                window_title = _window_title(window) or window_title
            menu_surface_count = _visible_menu_surface_count(
                desktop,
                match.process_id,
            )
        except Exception:
            pass

        return {
            "window_title": window_title,
            "menu_surface_count": menu_surface_count,
            "target": _target_state(wrapper),
        }



def _call_wrapper_or_pattern(
    wrapper: Any,
    *,
    wrapper_method: str,
    iface_name: str,
    pattern_method: str,
) -> bool:
    method = _safe_attr(wrapper, wrapper_method, None)
    if callable(method):
        try:
            method()
            return True
        except Exception:
            pass

    iface = _safe_attr(wrapper, iface_name, None)
    pattern = _safe_attr(iface, pattern_method, None)
    if callable(pattern):
        try:
            pattern()
            return True
        except Exception:
            pass
    return False


def _perform_structural_uia_action(
    wrapper: Any,
    action: str,
    semantic_kind: str = "",
) -> WindowsUIAActionResult:
    """Executa uma ação UIA explícita sem qualquer fallback físico."""

    if action == "focus":
        if bool(_wrapper_value(wrapper, "has_keyboard_focus", False)):
            return WindowsUIAActionResult(
                executed=False,
                already_satisfied=True,
                reason_code="uia_focus_already_satisfied",
            )
        executed = _call_wrapper_or_pattern(
            wrapper,
            wrapper_method="set_focus",
            iface_name="iface_keyboard_input",
            pattern_method="SetFocus",
        )
        return WindowsUIAActionResult(
            executed=executed,
            reason_code="uia_focus_executed" if executed else "uia_focus_unsupported",
        )

    if action in {"check", "uncheck"}:
        current = _read_toggle_state(wrapper)
        desired = 1 if action == "check" else 0
        if current == desired:
            return WindowsUIAActionResult(
                executed=False,
                already_satisfied=True,
                reason_code=f"uia_{action}_already_satisfied",
            )
        executed = _call_wrapper_or_pattern(
            wrapper,
            wrapper_method="toggle",
            iface_name="iface_toggle",
            pattern_method="Toggle",
        )
        reason_code = (
            f"uia_{action}_executed"
            if executed
            else f"uia_{action}_unsupported"
        )
        return WindowsUIAActionResult(
            executed=executed,
            reason_code=reason_code,
        )

    if action == "select":
        state = _target_state(wrapper)
        if state.get("selected") is True:
            return WindowsUIAActionResult(
                executed=False,
                already_satisfied=True,
                reason_code="uia_select_already_satisfied",
            )
        executed = _call_wrapper_or_pattern(
            wrapper,
            wrapper_method="select",
            iface_name="iface_selection_item",
            pattern_method="Select",
        )
        return WindowsUIAActionResult(
            executed=executed,
            reason_code="uia_select_executed" if executed else "uia_select_unsupported",
        )

    if action in {"expand", "collapse"}:
        current = _read_expand_state(wrapper)
        desired = 1 if action == "expand" else 0
        if current == desired:
            return WindowsUIAActionResult(
                executed=False,
                already_satisfied=True,
                reason_code=f"uia_{action}_already_satisfied",
            )
        executed = _call_wrapper_or_pattern(
            wrapper,
            wrapper_method=action,
            iface_name="iface_expand_collapse",
            pattern_method="Expand" if action == "expand" else "Collapse",
        )

        # WinUI moderno pode expor o cabeçalho Arquivo/Editar como Button
        # com Invoke, sem ExpandCollapse. Para abrir menu, Invoke continua
        # sendo UI Automation estrutural e não envolve coordenadas físicas.
        invoked_menu = False
        if not executed and action == "expand" and semantic_kind == "menu":
            invoked_menu = _call_wrapper_or_pattern(
                wrapper,
                wrapper_method="invoke",
                iface_name="iface_invoke",
                pattern_method="Invoke",
            )
            executed = invoked_menu

        if invoked_menu:
            reason_code = "uia_expand_invoked"
        else:
            reason_code = (
                f"uia_{action}_executed"
                if executed
                else f"uia_{action}_unsupported"
            )
        return WindowsUIAActionResult(
            executed=executed,
            reason_code=reason_code,
        )

    return WindowsUIAActionResult(
        executed=False,
        reason_code="uia_action_not_supported",
    )

def _invoke_structural_action(wrapper: Any, semantic_kind: str) -> bool:
    """Executa apenas padrões UIA; nunca clique por coordenadas."""

    control_type = _normalize(_element_info_value(wrapper, "control_type", ""))

    if semantic_kind in {"search_input", "text_input"} or control_type in {
        "document",
        "edit",
    }:
        set_focus = getattr(wrapper, "set_focus", None)
        if callable(set_focus):
            try:
                set_focus()
                return True
            except Exception:
                return False

    invoke_method = _safe_attr(wrapper, "invoke", None)
    if callable(invoke_method):
        try:
            invoke_method()
            return True
        except Exception:
            pass

    iface_invoke = _safe_attr(wrapper, "iface_invoke", None)
    invoke = _safe_attr(iface_invoke, "Invoke", None)
    if callable(invoke):
        try:
            invoke()
            return True
        except Exception:
            pass

    iface_toggle = _safe_attr(wrapper, "iface_toggle", None)
    toggle = _safe_attr(iface_toggle, "Toggle", None)
    if callable(toggle):
        try:
            toggle()
            return True
        except Exception:
            pass

    iface_selection = _safe_attr(wrapper, "iface_selection_item", None)
    select = _safe_attr(iface_selection, "Select", None)
    if callable(select):
        try:
            select()
            return True
        except Exception:
            pass

    return False


def activate_windows_uia_match(match: WindowsUIAMatch) -> bool:
    """Revalida e ativa um elemento via padrão UIA direto.

    Segurança: não existe fallback para clique físico, coordenadas ou Vision.
    """

    if not is_windows_uia_available():
        return False

    with _com_scope():
        try:
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            window = _resolve_target_window(desktop, match)
        except Exception:
            return False

        if window is None:
            return False

        # A ação foi pedida explicitamente. Fazemos um handoff confirmado do
        # foreground para a janela estrutural já revalidada. Não existe clique
        # por coordenadas nem fallback visual para executar a ação.
        if not _bring_window_to_foreground(window):
            return False

        wrapper = _resolve_active_wrapper(match)
        if wrapper is None:
            return False
        return _invoke_structural_action(wrapper, match.semantic_kind)


def _set_structural_uia_text(wrapper: Any, text: str) -> bool:
    """Define texto via Value/Edit UIA; nunca envia teclas físicas."""

    if not text or bool(_element_info_value(wrapper, "is_password", False)):
        return False

    control_type = _normalize(
        _element_info_value(wrapper, "control_type", "")
    )
    if control_type not in _TEXT_CONTROL_TYPES:
        return False

    for method_name in ("set_edit_text", "set_text"):
        method = getattr(wrapper, method_name, None)
        if not callable(method):
            continue
        try:
            method(text)
            return True
        except Exception:
            continue

    iface_value = _safe_attr(wrapper, "iface_value", None)
    set_value = _safe_attr(iface_value, "SetValue", None)
    if callable(set_value):
        try:
            set_value(text)
            return True
        except Exception:
            return False

    return False


def perform_windows_uia_text_fill(
    match: WindowsUIAMatch,
    text: str,
) -> WindowsUIAActionResult:
    """Preenche um campo Windows revalidado usando somente padrões UIA."""

    if not is_windows_uia_available():
        return WindowsUIAActionResult(
            executed=False,
            reason_code="uia_runtime_unavailable",
        )

    with _com_scope():
        try:
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            window = _resolve_target_window(desktop, match)
        except Exception:
            return WindowsUIAActionResult(
                executed=False,
                reason_code="uia_window_unavailable",
            )

        if window is None:
            return WindowsUIAActionResult(
                executed=False,
                reason_code="uia_window_unavailable",
            )

        if not _bring_window_to_foreground(window):
            return WindowsUIAActionResult(
                executed=False,
                reason_code="uia_foreground_handoff_failed",
            )

        wrapper = _resolve_active_wrapper(match)
        if wrapper is None:
            return WindowsUIAActionResult(
                executed=False,
                reason_code="uia_target_revalidation_failed",
            )

        if bool(_element_info_value(wrapper, "is_password", False)):
            return WindowsUIAActionResult(
                executed=False,
                reason_code="uia_password_field_blocked",
            )

        if _set_structural_uia_text(wrapper, text):
            return WindowsUIAActionResult(
                executed=True,
                reason_code="uia_text_filled",
            )

        return WindowsUIAActionResult(
            executed=False,
            reason_code="uia_text_fill_unsupported",
        )


def perform_windows_uia_action(
    match: WindowsUIAMatch,
    action: str,
) -> WindowsUIAActionResult:
    """Executa uma ação Windows da Etapa 9 após revalidação estrutural.

    A janela é promovida ao foreground por HWND validado, o elemento é
    reencontrado por fingerprint e apenas padrões UIA são usados.
    """

    if not is_windows_uia_available():
        return WindowsUIAActionResult(
            executed=False,
            reason_code="uia_runtime_unavailable",
        )

    with _com_scope():
        try:
            from pywinauto import Desktop

            desktop = Desktop(backend="uia")
            window = _resolve_target_window(desktop, match)
        except Exception:
            return WindowsUIAActionResult(
                executed=False,
                reason_code="uia_window_unavailable",
            )

        if window is None:
            return WindowsUIAActionResult(
                executed=False,
                reason_code="uia_window_unavailable",
            )

        if not _bring_window_to_foreground(window):
            return WindowsUIAActionResult(
                executed=False,
                reason_code="uia_foreground_handoff_failed",
            )

        wrapper = _resolve_active_wrapper(match)
        if wrapper is None:
            return WindowsUIAActionResult(
                executed=False,
                reason_code="uia_target_revalidation_failed",
            )

        return _perform_structural_uia_action(
            wrapper,
            action,
            semantic_kind=match.semantic_kind,
        )

