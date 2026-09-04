from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

import speech_recognition as sr

from atlas.core.config import (
    ATLAS_NAME,
    DATA_DIR,
    TTS_CACHE_ENABLED,
    TTS_CACHE_MAX_ENTRIES,
    TTS_PREFETCH_ENABLED,
    TTS_PREFETCH_WORKERS,
    TTS_SENTENCE_PAUSE_MS,
    TTS_CHUNK_MAX_CHARS,
    TTS_PITCH,
    TTS_PROVIDER,
    TTS_RATE,
    TTS_VOICE,
    TTS_VOLUME,
    VOICE_PROFILE,
    VOICE_ENABLED,
)
from atlas.voice.latency import VoiceLatencyTracker
from atlas.voice.playback import AudioPlaybackError, WindowsMciPlayer
from atlas.voice.profile import (
    VoicePerformanceProfile,
    resolve_voice_profile,
)
from atlas.voice.response import sentence_pause_seconds, split_for_speech
from atlas.voice.session import (
    VoiceSession,
    VoiceState,
    VoiceTransitionError,
)
from atlas.voice.tts import EdgeTTSProvider, WindowsSapiProvider
from atlas.voice.tts_cache import TTSFileCache
from atlas.voice.pipeline import TTSPrefetchPipeline



@dataclass(slots=True)
class _PreparedVoiceChunk:
    path: Path
    temporary: bool


class SpeechInterface:

    def __init__(
        self,
        microphone_enabled: bool = True,
        session: VoiceSession | None = None,
        *,
        tts_provider: str | None = None,
        performance_profile: str | VoicePerformanceProfile | None = None,
    ) -> None:
        self.microphone_enabled = microphone_enabled
        self.session = session or VoiceSession()
        self.performance_profile = resolve_voice_profile(
            performance_profile or VOICE_PROFILE
        )
        self.latency = VoiceLatencyTracker(self.session)
        self.recognizer = sr.Recognizer()
        self.interruption_recognizer = sr.Recognizer()

        # Sensibilidade do microfone
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 180
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.3

        # Espera mais tempo antes de considerar que você terminou
        self.recognizer.pause_threshold = (
            self.performance_profile.pause_threshold
        )
        self.recognizer.non_speaking_duration = (
            self.performance_profile.non_speaking_duration
        )
        self.recognizer.phrase_threshold = (
            self.performance_profile.phrase_threshold
        )

        # Mantém uma pausa natural entre "Atlas" e "pare" sem deixar
        # a captura de interrupção presa por tempo demais.
        self.interruption_recognizer.dynamic_energy_threshold = True
        self.interruption_recognizer.energy_threshold = 180
        self.interruption_recognizer.pause_threshold = 1.2
        self.interruption_recognizer.non_speaking_duration = 0.6
        self.interruption_recognizer.phrase_threshold = 0.1

        self._microphone_calibrated = False
        self._microphone_lock = Lock()
        self._speech_process_lock = Lock()
        self._speech_process: subprocess.Popen[bytes] | None = None
        self._neural_player = WindowsMciPlayer()
        provider_name = str(tts_provider or TTS_PROVIDER).strip().lower()
        self.tts_provider = (
            provider_name if provider_name in {"edge", "windows"} else "edge"
        )
        self.neural_voice = EdgeTTSProvider(
            voice=TTS_VOICE or "pt-BR-AntonioNeural",
            rate=TTS_RATE or "+0%",
            volume=TTS_VOLUME or "+0%",
            pitch=TTS_PITCH or "+0Hz",
        )
        self.windows_voice = WindowsSapiProvider()
        self.tts_cache = (
            TTSFileCache(
                DATA_DIR / "voice_cache",
                max_entries=TTS_CACHE_MAX_ENTRIES,
            )
            if TTS_CACHE_ENABLED
            else None
        )
        self.tts_chunk_max_chars = TTS_CHUNK_MAX_CHARS

    @classmethod
    def runtime_self_test(cls) -> bool:
        """Valida dependências essenciais sem acessar microfone ou rede."""

        try:
            import edge_tts

            from atlas.voice.continuous import ContinuousVoiceListener
            from atlas.voice.interruption import VoiceInterruptionMonitor
            from atlas.voice.session import VoiceSession

            required = (
                ContinuousVoiceListener,
                VoiceInterruptionMonitor,
                VoiceSession,
            )
            return (
                edge_tts is not None
                and all(item is not None for item in required)
                and EdgeTTSProvider.dependency_available()
                and callable(getattr(EdgeTTSProvider, "synthesize", None))
                and callable(getattr(WindowsMciPlayer, "play", None))
                and callable(getattr(WindowsMciPlayer, "stop", None))
            )
        except ImportError:
            return False

    def performance_snapshot(self) -> dict[str, object]:
        """Retorna configuração e métricas sem conteúdo de fala."""

        return {
            "profile": self.performance_profile.name,
            **self.latency.summary(),
        }

    def say(self, message: str) -> None:
        message = str(message).strip()

        if not message:
            return

        print(f"\n{ATLAS_NAME}: {message}\n")

        if self.session.interruption_requested():
            return

        try:
            self.session.start_speaking()
        except VoiceTransitionError:
            return

        try:
            if not VOICE_ENABLED:
                print("[AVISO] A voz está desativada no arquivo .env.")
                return

            spoken = False

            if self.tts_provider == "edge":
                spoken = self._speak_with_neural_voice(message)

                if self.session.interruption_requested():
                    return

                if not spoken:
                    print(
                        "[AVISO] Voz neural indisponível. "
                        "Usando a voz local do Windows."
                    )

            if not spoken:
                self._speak_with_windows_voice(message)

        except subprocess.TimeoutExpired:
            self._terminate_speech_process()
            print(
                "[AVISO] A voz demorou demais para responder. "
                "O Atlas continuará sem bloquear."
            )

        except Exception as exc:
            print(f"[ERRO AO FALAR] {exc}")

        finally:
            with self._speech_process_lock:
                self._speech_process = None

            if self.session.is_state(VoiceState.SPEAKING):
                self.session.complete()


    def _speak_with_neural_voice(self, message: str) -> bool:
        chunks = split_for_speech(
            message,
            max_chars=self.tts_chunk_max_chars,
        )

        if not chunks:
            return True

        if not TTS_PREFETCH_ENABLED or len(chunks) == 1:
            for chunk in chunks:
                if self.session.interruption_requested():
                    return True

                if not self._speak_neural_chunk(chunk):
                    return False

                self._natural_pause(chunk)

            return True

        pipeline = TTSPrefetchPipeline(
            self._prepare_neural_chunk,
            max_workers=TTS_PREFETCH_WORKERS,
        )

        try:
            for chunk, prepared in pipeline.iter_prefetched(chunks):
                if self.session.interruption_requested():
                    self._cleanup_prepared_chunk(prepared)
                    return True

                if prepared is None:
                    return False

                try:
                    if not self._play_prepared_chunk(prepared):
                        return False
                finally:
                    self._cleanup_prepared_chunk(prepared)

                self._natural_pause(chunk)

            return True

        finally:
            pipeline.close()

    def _prepare_neural_chunk(
        self,
        message: str,
    ) -> _PreparedVoiceChunk | None:
        """Sintetiza um trecho sem bloquear a reprodução do atual."""

        cache_key = self.neural_voice.cache_key(message)
        cached_path = (
            self.tts_cache.get(cache_key)
            if self.tts_cache is not None
            else None
        )

        if cached_path is not None:
            return _PreparedVoiceChunk(
                path=cached_path,
                temporary=False,
            )

        temporary = NamedTemporaryFile(
            prefix="atlas-voice-",
            suffix=".mp3",
            delete=False,
        )
        media_path = Path(temporary.name)
        temporary.close()

        try:
            self.neural_voice.synthesize(
                message,
                media_path,
                timeout=30,
            )

            if (
                not media_path.is_file()
                or media_path.stat().st_size == 0
            ):
                media_path.unlink(missing_ok=True)
                return None

            if self.tts_cache is not None:
                try:
                    cached_path = self.tts_cache.store(
                        cache_key,
                        media_path,
                    )
                    media_path.unlink(missing_ok=True)

                    return _PreparedVoiceChunk(
                        path=cached_path,
                        temporary=False,
                    )

                except (OSError, ValueError):
                    pass

            return _PreparedVoiceChunk(
                path=media_path,
                temporary=True,
            )

        except Exception as exc:
            media_path.unlink(missing_ok=True)
            print(f"[AVISO] Falha na síntese neural: {exc}")
            return None

    def _play_prepared_chunk(
        self,
        prepared: _PreparedVoiceChunk,
    ) -> bool:
        if self.session.interruption_requested():
            return True

        try:
            self._neural_player.play(prepared.path)
        except (AudioPlaybackError, OSError):
            return self.session.interruption_requested()

        return True

    @staticmethod
    def _cleanup_prepared_chunk(
        prepared: _PreparedVoiceChunk | None,
    ) -> None:
        if prepared is not None and prepared.temporary:
            prepared.path.unlink(missing_ok=True)

    def _natural_pause(self, chunk: str) -> None:
        if self.session.interruption_requested():
            return

        delay = sentence_pause_seconds(
            chunk,
            base_ms=TTS_SENTENCE_PAUSE_MS,
        )

        if delay > 0:
            time.sleep(delay)

    def _speak_neural_chunk(self, message: str) -> bool:
        prepared = self._prepare_neural_chunk(message)

        if prepared is None:
            return False

        try:
            return self._play_prepared_chunk(prepared)
        finally:
            self._cleanup_prepared_chunk(prepared)

    def _speak_with_windows_voice(self, message: str) -> bool:
        return (
            self._run_speech_process(
                self.windows_voice.command(message),
                timeout=20,
            )
            == 0
        )

    def _run_speech_process(
        self,
        command: list[str],
        *,
        timeout: float,
    ) -> int:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            ),
        )

        with self._speech_process_lock:
            self._speech_process = process

        try:
            if self.session.interruption_requested():
                self._terminate_speech_process()
                return process.returncode or 1

            return process.wait(timeout=timeout)

        except subprocess.TimeoutExpired:
            self._terminate_speech_process()
            raise

        finally:
            with self._speech_process_lock:
                if self._speech_process is process:
                    self._speech_process = None

    def listen(
        self,
        prompt: str = "Ouvindo...",
        retry_on_failure: bool = False,
        *,
        timeout: float | None = 10,
        phrase_time_limit: float | None = 20,
        verbose: bool = True,
    ) -> str:
        if not self.microphone_enabled:
            return input("Você: ").strip()

        self._validate_listening_limits(timeout, phrase_time_limit)

        try:
            with self._microphone_lock:
                if not self.microphone_enabled:
                    return ""

                self.session.start_listening()

                with sr.Microphone() as source:
                    if verbose and prompt:
                        print(prompt)

                    self._calibrate_microphone(source)

                    audio = self.recognizer.listen(
                        source,
                        timeout=timeout,
                        phrase_time_limit=phrase_time_limit,
                    )

                text = self.recognizer.recognize_google(
                    audio,
                    language="pt-BR",
                    show_all=False,
                )

                text = text.strip()

                if not text:
                    self._complete_listening_cycle()
                    return ""

                if verbose:
                    print(f"Você: {text}")

                self.session.start_processing(text)
                return text

        except sr.WaitTimeoutError:
            if verbose:
                print("[AVISO] Nenhuma fala foi detectada.")

            self._complete_listening_cycle()
            return ""

        except sr.UnknownValueError:
            if verbose:
                print("[AVISO] Não consegui entender o que foi dito.")

            self._complete_listening_cycle()

            if retry_on_failure:
                self.say("Não consegui entender. Pode repetir?")

                time.sleep(0.3)

                return self.listen(
                    prompt="Estou ouvindo novamente...",
                    retry_on_failure=False,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                    verbose=verbose,
                )

            return ""

        except sr.RequestError as exc:
            print(f"[ERRO NO RECONHECIMENTO] {exc}")
            self.session.fail(exc)

            self.say(
                "Não consegui acessar o serviço "
                "de reconhecimento de voz."
            )

            return ""

        except OSError as exc:
            print(f"[ERRO NO MICROFONE] {exc}")
            self.microphone_enabled = False
            self.session.fail(exc)
            return ""

        except Exception as exc:
            print(f"[ERRO INESPERADO] {exc}")
            self.session.fail(exc)
            return ""

    def _calibrate_microphone(
        self,
        source: sr.AudioSource,
    ) -> None:
        if self._microphone_calibrated:
            return

        print("[MICROFONE] Calibrando o ruído do ambiente...")

        self.recognizer.adjust_for_ambient_noise(
            source,
            duration=self.performance_profile.calibration_duration,
        )

        self._microphone_calibrated = True

        print(
            "[MICROFONE] Calibração concluída. "
            f"Sensibilidade: "
            f"{int(self.recognizer.energy_threshold)}"
        )

    def recalibrate_microphone(self) -> bool:
        if not self.microphone_enabled:
            return False

        try:
            with sr.Microphone() as source:
                self._microphone_calibrated = False
                self._calibrate_microphone(source)

            return True

        except Exception as exc:
            print(f"[ERRO NA CALIBRAÇÃO] {exc}")
            return False

    def listen_for_interruption(
        self,
        *,
        timeout: float = 1.25,
        phrase_time_limit: float = 4.0,
    ) -> str:
        """Captura uma frase curta sem alterar a ``VoiceSession``."""

        if not self.microphone_enabled:
            return ""

        self._validate_listening_limits(timeout, phrase_time_limit)

        try:
            with self._microphone_lock:
                if not self.microphone_enabled:
                    return ""

                with sr.Microphone() as source:
                    audio = self.interruption_recognizer.listen(
                        source,
                        timeout=timeout,
                        phrase_time_limit=phrase_time_limit,
                    )

                recognition = self.interruption_recognizer.recognize_google(
                    audio,
                    language="pt-BR",
                    show_all=True,
                )

            return self._format_recognition_alternatives(recognition)

        except (sr.WaitTimeoutError, sr.UnknownValueError):
            return ""

        except sr.RequestError as exc:
            print(f"[ERRO NO MONITOR DE VOZ] {exc}")
            return ""

        except OSError as exc:
            print(f"[ERRO NO MICROFONE] {exc}")
            self.microphone_enabled = False
            return ""

        except Exception as exc:
            print(f"[ERRO NO MONITOR DE VOZ] {exc}")
            return ""

    def enable_microphone(self) -> bool:
        try:
            with sr.Microphone():
                pass

            self.microphone_enabled = True
            self._microphone_calibrated = False
            self.session.reset()

            return True

        except Exception as exc:
            print(f"[ERRO AO ATIVAR MICROFONE] {exc}")
            return False

    def disable_microphone(self) -> None:
        self.microphone_enabled = False

        if self.session.is_state(VoiceState.LISTENING):
            self.session.interrupt("Microfone desativado")

    def request_interruption(
        self,
        reason: str | None = None,
    ) -> bool:
        """Solicita a interrupção cooperativa da escuta ou da fala."""

        try:
            changed = self.session.interrupt(reason)
        except VoiceTransitionError:
            changed = False

        neural_stopped = self._neural_player.stop()
        speech_stopped = self._terminate_speech_process()
        return changed or neural_stopped or speech_stopped

    def _terminate_speech_process(self) -> bool:
        with self._speech_process_lock:
            process = self._speech_process

        if process is None or process.poll() is not None:
            return False

        try:
            process.terminate()
            process.wait(timeout=0.75)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=0.75)
            except Exception:
                return False
        except Exception:
            return False

        return True

    def _complete_listening_cycle(self) -> None:
        if self.session.is_state(VoiceState.LISTENING):
            self.session.complete()

    @staticmethod
    def _format_recognition_alternatives(recognition: object) -> str:
        if isinstance(recognition, str):
            return recognition.strip()

        if not isinstance(recognition, dict):
            return ""

        alternatives = recognition.get("alternative", [])

        if not isinstance(alternatives, list):
            return ""

        transcripts = []

        for alternative in alternatives:
            if not isinstance(alternative, dict):
                continue

            transcript = str(alternative.get("transcript", "")).strip()

            if transcript and transcript not in transcripts:
                transcripts.append(transcript)

        return "\n".join(transcripts)

    @staticmethod
    def _validate_listening_limits(
        timeout: float | None,
        phrase_time_limit: float | None,
    ) -> None:
        if timeout is not None and timeout <= 0:
            raise ValueError("O tempo de escuta deve ser maior que zero.")

        if phrase_time_limit is not None and phrase_time_limit <= 0:
            raise ValueError("O limite da frase deve ser maior que zero.")
