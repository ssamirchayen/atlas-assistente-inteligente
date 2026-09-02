from __future__ import annotations

import unicodedata

from atlas.vision.models import (
    VisionBoundingBox,
    VisionGroundingResult,
    VisionUIElement,
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text))
    normalized = "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    )
    return " ".join(normalized.lower().strip().split())


def _candidate_text(widget) -> str:
    parts: list[str] = []

    for attribute in (
        "text",
        "placeholderText",
        "accessibleName",
        "toolTip",
        "objectName",
    ):
        value = getattr(widget, attribute, None)

        if callable(value):
            try:
                result = value()
            except TypeError:
                continue
        else:
            result = value

        if result:
            parts.append(str(result))

    return " ".join(parts)


def locate_qt_widget(
    query: str,
    *,
    screen_width: int,
    screen_height: int,
) -> VisionGroundingResult | None:
    """Localiza widgets visíveis da própria GUI do Atlas."""

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return None

    app = QApplication.instance()
    if app is None:
        return None

    query_norm = _normalize(query)
    query_tokens = {
        token
        for token in query_norm.split()
        if token not in {
            "botao",
            "campo",
            "menu",
            "onde",
            "esta",
            "fica",
            "o",
            "a",
            "de",
            "do",
            "da",
        }
    }

    if not query_tokens:
        return None

    active_window = app.activeWindow()
    if active_window is None or not active_window.isVisible():
        return None

    best_widget = None
    best_text = ""
    best_score = 0.0

    for window in (active_window,):
        widgets = [window]
        widgets.extend(window.findChildren(object))

        for widget in widgets:
            is_visible = getattr(widget, "isVisible", None)
            if callable(is_visible):
                try:
                    if not is_visible():
                        continue
                except RuntimeError:
                    continue

            text = _candidate_text(widget)
            text_norm = _normalize(text)

            if not text_norm:
                continue

            widget_tokens = set(text_norm.split())
            overlap = len(query_tokens & widget_tokens)

            if overlap == 0:
                continue

            score = overlap / len(query_tokens)

            if query_norm and query_norm in text_norm:
                score += 0.5

            if score > best_score:
                best_score = score
                best_widget = widget
                best_text = text

    if best_widget is None or best_score < 0.5:
        return None

    try:
        rect = best_widget.rect()
        top_left = best_widget.mapToGlobal(rect.topLeft())
        bottom_right = best_widget.mapToGlobal(rect.bottomRight())

        x1_px = max(0, min(top_left.x(), screen_width - 1))
        y1_px = max(0, min(top_left.y(), screen_height - 1))
        x2_px = max(0, min(bottom_right.x(), screen_width))
        y2_px = max(0, min(bottom_right.y(), screen_height))
    except (RuntimeError, AttributeError):
        return None

    if x2_px <= x1_px or y2_px <= y1_px:
        return None

    try:
        bbox = VisionBoundingBox(
            round(x1_px * 1000 / screen_width),
            round(y1_px * 1000 / screen_height),
            round(x2_px * 1000 / screen_width),
            round(y2_px * 1000 / screen_height),
        )
    except ValueError:
        return None

    label = best_text.strip().splitlines()[0] or query

    return VisionGroundingResult(
        query=query,
        found=True,
        element=VisionUIElement(
            label=label,
            kind=best_widget.__class__.__name__,
            description=(
                "Elemento localizado pela geometria real "
                "da interface do Atlas."
            ),
            bbox=bbox,
            confidence=min(1.0, best_score),
        ),
        message=f"Localizei '{label}' pela interface do Atlas.",
    )
