from __future__ import annotations

from atlas.vision.models import VisionAnalysis


def format_analysis_for_user(analysis: VisionAnalysis) -> str:
    """Transforma a análise estruturada em resposta curta para o usuário."""

    parts = [analysis.summary.strip()]

    if analysis.errors:
        parts.append(
            "Também identifiquei: "
            + "; ".join(analysis.errors[:3])
            + "."
        )

    return " ".join(part for part in parts if part).strip()



def describe_grounding(
    result,
    *,
    width: int,
    height: int,
) -> str:
    if not result.found or result.element is None:
        return (
            result.message
            or "Não consegui localizar esse elemento."
        )

    center = result.center_pixels(width, height)
    if center is None:
        return result.message

    x, y = center
    label = result.element.label

    horizontal = (
        "lado esquerdo"
        if x < width * 0.33
        else "lado direito"
        if x > width * 0.66
        else "região central"
    )
    vertical = (
        "parte superior"
        if y < height * 0.33
        else "parte inferior"
        if y > height * 0.66
        else "região central"
    )

    return (
        f"Localizei {label} no {horizontal}, na {vertical} da tela. "
        f"Posição aproximada: X={x}, Y={y}."
    )
