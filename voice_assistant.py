"""Opt-in, push-to-talk speech recognition using a local Vosk model only."""

import json
import queue
import threading
from pathlib import Path
from typing import Callable, Optional


class VoiceAssistant:
    def __init__(self, model_path: str, on_command: Callable[[str], None]):
        self.model_path = Path(model_path).expanduser() if model_path else None
        self.on_command = on_command
        self._audio_queue = queue.Queue(maxsize=12)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[str] = None

    @property
    def listening(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def start_push_to_talk(self) -> None:
        if self.listening:
            return
        if self.model_path is None or not self.model_path.is_dir():
            raise RuntimeError("Set VOSK_MODEL_PATH to a downloaded local Vosk model folder before voice use.")
        self._stop_event.clear()
        self.error = None
        self._thread = threading.Thread(target=self._listen, name="local-voice-assistant", daemon=True)
        self._thread.start()

    def stop_push_to_talk(self) -> None:
        self._stop_event.set()

    def _listen(self) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model

            model = Model(str(self.model_path))
            recognizer = KaldiRecognizer(model, 16000)

            def receive_audio(indata, frames, time_info, status):
                if status:
                    self.error = str(status)
                try:
                    self._audio_queue.put_nowait(bytes(indata))
                except queue.Full:
                    try:
                        self._audio_queue.get_nowait()
                        self._audio_queue.put_nowait(bytes(indata))
                    except queue.Empty:
                        pass

            with sd.RawInputStream(
                samplerate=16000,
                blocksize=8000,
                dtype="int16",
                channels=1,
                callback=receive_audio,
            ):
                while not self._stop_event.is_set():
                    try:
                        audio = self._audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if recognizer.AcceptWaveform(audio):
                        command = json.loads(recognizer.Result()).get("text", "").strip()
                        if command:
                            self.on_command(command)
        except Exception as exc:
            self.error = f"Local voice recognition failed: {exc}"
            self._stop_event.set()
