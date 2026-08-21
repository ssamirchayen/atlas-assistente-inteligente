from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Generic, Iterable, TypeVar


T = TypeVar("T")


@dataclass(slots=True)
class PrefetchItem(Generic[T]):
    text: str
    future: Future[T]


class TTSPrefetchPipeline(Generic[T]):
    """Pipeline simples de TTS com 1 item de look-ahead.

    Enquanto o trecho atual é reproduzido, o próximo já é sintetizado
    em background. A ordem de reprodução continua determinística.
    """

    def __init__(
        self,
        synthesize: Callable[[str], T],
        *,
        max_workers: int = 1,
    ) -> None:
        self._synthesize = synthesize
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="atlas-tts-prefetch",
        )

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _submit(self, text: str) -> PrefetchItem[T]:
        return PrefetchItem(
            text=text,
            future=self._executor.submit(self._synthesize, text),
        )

    def iter_prefetched(
        self,
        chunks: Iterable[str],
    ):
        iterator = iter(chunks)

        try:
            first = next(iterator)
        except StopIteration:
            return

        current = self._submit(first)

        for next_text in iterator:
            following = self._submit(next_text)
            yield current.text, current.future.result()
            current = following

        yield current.text, current.future.result()
