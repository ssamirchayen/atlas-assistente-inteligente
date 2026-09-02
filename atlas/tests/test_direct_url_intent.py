from atlas.automation.url_intent import extract_direct_url_command


def test_extracts_local_lab_url_without_losing_punctuation() -> None:
    request = extract_direct_url_command(
        "abra http://127.0.0.1:8765/tools/vision_form_lab.html"
    )

    assert request is not None
    assert request.url == "http://127.0.0.1:8765/tools/vision_form_lab.html"


def test_accepts_https_query_and_fragment() -> None:
    request = extract_direct_url_command(
        "acesse https://example.com/a_b?q=atlas-10#teste"
    )

    assert request is not None
    assert request.url == "https://example.com/a_b?q=atlas-10#teste"


def test_rejects_non_http_schemes() -> None:
    assert extract_direct_url_command("abra file:///C:/Windows") is None
    assert extract_direct_url_command("abra javascript:alert(1)") is None


def test_does_not_swallow_a_multi_step_command() -> None:
    assert (
        extract_direct_url_command(
            "abra https://example.com e depois clique em entrar"
        )
        is None
    )
