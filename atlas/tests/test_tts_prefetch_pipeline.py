from __future__ import annotations

import threading
import time

from atlas.voice.pipeline import TTSPrefetchPipeline


def test_prefetch_pipeline_preserves_order() -> None:
    def synthesize(text: str) -> str:
        return f"audio:{text}"

    pipeline = TTSPrefetchPipeline(synthesize)

    try:
        result = list(
            pipeline.iter_prefetched(
                ["primeira.", "segunda.", "terceira."]
            )
        )
    finally:
        pipeline.close()

    assert result == [
        ("primeira.", "audio:primeira."),
        ("segunda.", "audio:segunda."),
        ("terceira.", "audio:terceira."),
    ]


def test_prefetch_pipeline_starts_next_synthesis_before_current_playback_finishes() -> None:
    started = []
    lock = threading.Lock()

    def synthesize(text: str) -> str:
        with lock:
            started.append(text)
        time.sleep(0.03)
        return text

    pipeline = TTSPrefetchPipeline(synthesize)

    try:
        iterator = pipeline.iter_prefetched(["um.", "dois."])
        first_text, first_audio = next(iterator)

        # O segundo item já deve ter sido submetido ao executor quando o
        # primeiro é entregue para reprodução.
        deadline = time.time() + 0.25
        while "dois." not in started and time.time() < deadline:
            time.sleep(0.005)

        assert first_text == "um."
        assert first_audio == "um."
        assert "dois." in started

        second_text, second_audio = next(iterator)
        assert second_text == "dois."
        assert second_audio == "dois."
    finally:
        pipeline.close()
