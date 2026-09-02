from atlas.vision.post_action import verify_text_fill_post_action


def test_confirms_dom_normalized_text_value() -> None:
    result = verify_text_fill_post_action(
        {"target": {"value": ""}},
        {"target": {"value": "atlas vision 10"}},
        expected_text="Atlas Vision 10",
    )

    assert result.verified is True
    assert result.reason_code == "text_fill_value_confirmed"


def test_does_not_confirm_different_final_value() -> None:
    result = verify_text_fill_post_action(
        {"target": {"value": "antes"}},
        {"target": {"value": "outro valor"}},
        expected_text="valor esperado",
    )

    assert result.verified is False
    assert result.reason_code == "text_fill_value_changed_but_not_confirmed"
