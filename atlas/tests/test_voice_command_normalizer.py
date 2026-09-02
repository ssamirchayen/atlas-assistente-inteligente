from __future__ import annotations

from atlas.voice.command_normalizer import normalize_voice_command


def test_repairs_quick_as_click_only_at_command_start() -> None:
    assert (
        normalize_voice_command(
            "quick no campo de texto e depois digite teste 10 no campo de texto"
        )
        == "clique no campo de texto e depois digite teste 10 no campo de texto"
    )


def test_repairs_common_structural_voice_aliases() -> None:
    assert normalize_voice_command("abre o menu arquivo") == "abra o menu arquivo"
    assert (
        normalize_voice_command("digita atlas vision 10 na barra pesquisa")
        == "digite atlas vision 10 na barra de pesquisa"
    )
    assert normalize_voice_command("clica no campo texto") == "clique no campo de texto"


def test_does_not_invent_missing_target() -> None:
    assert normalize_voice_command("digite atlas vision 10 na barra") == (
        "digite atlas vision 10 na barra"
    )


def test_explicit_self_correction_cancels_same_utterance() -> None:
    assert (
        normalize_voice_command(
            "clique no campo de texto desculpa errei nao era isso"
        )
        == ""
    )


def test_does_not_rewrite_quick_inside_free_text() -> None:
    assert normalize_voice_command("digite quick sort no campo") == (
        "digite quick sort no campo"
    )
