"""Cache local, limitado e sem texto em claro para áudio TTS."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from threading import RLock


class TTSFileCache:
    """Cache LRU simples baseado no horário de modificação dos arquivos."""

    def __init__(self, directory: Path, *, max_entries: int = 64) -> None:
        if max_entries <= 0:
            raise ValueError("O cache TTS deve aceitar ao menos uma entrada.")

        self.directory = Path(directory)
        self.max_entries = int(max_entries)
        self._lock = RLock()

    @staticmethod
    def key_for(
        text: str,
        *,
        voice: str,
        rate: str,
        volume: str,
        pitch: str,
    ) -> str:
        payload = "\x1f".join((voice, rate, volume, pitch, text)).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def get(self, key: str) -> Path | None:
        path = self.directory / f"{key}.mp3"
        with self._lock:
            if not path.is_file() or path.stat().st_size == 0:
                return None
            path.touch()
            return path

    def store(self, key: str, source: Path) -> Path:
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError("O áudio TTS de origem está vazio ou não existe.")

        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / f"{key}.mp3"
            temporary = self.directory / f".{key}.tmp"
            shutil.copyfile(source, temporary)
            temporary.replace(target)
            self._trim_unlocked()
            return target

    def clear(self) -> int:
        with self._lock:
            if not self.directory.exists():
                return 0
            removed = 0
            for path in self.directory.glob("*.mp3"):
                path.unlink(missing_ok=True)
                removed += 1
            return removed

    def _trim_unlocked(self) -> None:
        entries = sorted(
            self.directory.glob("*.mp3"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in entries[self.max_entries :]:
            path.unlink(missing_ok=True)
