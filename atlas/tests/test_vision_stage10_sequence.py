from atlas.vision.interaction_sequence import (
    extract_structured_sequence,
    is_structured_sequence_attempt,
)


def test_extracts_two_verified_structural_steps() -> None:
    request = extract_structured_sequence(
        "clique no campo de texto e depois digite Atlas no campo de texto"
    )

    assert request is not None
    assert request.steps == (
        "clique no campo de texto",
        "digite Atlas no campo de texto",
    )


def test_blocks_sensitive_action_inside_sequence() -> None:
    command = "clique no campo de texto e depois clique em comprar"

    assert extract_structured_sequence(command) is None
    assert is_structured_sequence_attempt(command) is True


def test_rejects_more_than_three_steps() -> None:
    command = (
        "clique no campo A e depois clique no campo B e depois "
        "clique no campo C e depois clique no campo D"
    )

    assert extract_structured_sequence(command) is None
