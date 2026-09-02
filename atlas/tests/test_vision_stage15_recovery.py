from atlas.vision.recovery import decide_recovery


def test_allows_one_retry_only_before_action_is_sent() -> None:
    first = decide_recovery(
        action_performed=False,
        verified=False,
        reversible=False,
        attempts=0,
    )
    exhausted = decide_recovery(
        action_performed=False,
        verified=False,
        reversible=False,
        attempts=1,
    )

    assert first.retry_allowed is True
    assert exhausted.retry_allowed is False


def test_never_retries_sent_action_and_rolls_back_only_reversible_state() -> None:
    reversible = decide_recovery(
        action_performed=True,
        verified=False,
        reversible=True,
        attempts=1,
    )
    irreversible = decide_recovery(
        action_performed=True,
        verified=False,
        reversible=False,
        attempts=1,
    )

    assert reversible.retry_allowed is False
    assert reversible.rollback_allowed is True
    assert irreversible.retry_allowed is False
    assert irreversible.rollback_allowed is False
    assert irreversible.reason_code == "action_sent_no_retry"


def test_verified_action_needs_no_recovery() -> None:
    decision = decide_recovery(
        action_performed=True,
        verified=True,
        reversible=True,
        attempts=1,
    )

    assert decision.reason_code == "recovery_not_needed"
    assert decision.retry_allowed is False
    assert decision.rollback_allowed is False

