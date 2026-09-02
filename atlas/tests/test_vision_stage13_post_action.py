from atlas.vision.post_action import verify_control_state_post_action


def test_confirms_checked_and_unchecked_state() -> None:
    checked = verify_control_state_post_action(
        {"target": {"checked": True}},
        desired_state=True,
    )
    unchecked = verify_control_state_post_action(
        {"target": {"checked": False}},
        desired_state=False,
    )

    assert checked.verified is True
    assert checked.reason_code == "control_checked_confirmed"
    assert unchecked.verified is True
    assert unchecked.reason_code == "control_unchecked_confirmed"


def test_rejects_missing_or_different_final_state() -> None:
    missing = verify_control_state_post_action(None, desired_state=True)
    different = verify_control_state_post_action(
        {"target": {"checked": False}},
        desired_state=True,
    )

    assert missing.verified is False
    assert different.verified is False
    assert different.reason_code == "control_state_not_confirmed"

