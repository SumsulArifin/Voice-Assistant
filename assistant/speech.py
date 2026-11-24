"""Speech input (speech_recognition) and output (pyttsx3), plus a text-mode stand-in."""
from __future__ import annotations

import sys
import threading
from typing import Optional


class NoSpeech(Exception):
    """Nothing was said before the timeout."""


class NotUnderstood(Exception):
    """Audio was captured but could not be turned into text."""


class SpeechServiceError(Exception):
    """The recognition service could not be reached."""


def beep() -> None:
    """Audible alert for reminders (winsound on Windows, terminal bell elsewhere)."""
    try:
        import winsound  # type: ignore
        winsound.Beep(880, 350)
        winsound.Beep(1100, 350)
    except ImportError:
        sys.stdout.write("\a\a\a")
        sys.stdout.flush()


class Speaker:
    """Prints every reply and speaks it with pyttsx3 when available."""

    def __init__(self, enabled: bool = True, rate: int = 175):
        self._engine = None
        self._lock = threading.Lock()
        if enabled:
            try:
                import pyttsx3
                self._engine = pyttsx3.init()
                self._engine.setProperty("rate", rate)
            except Exception as exc:  # missing package or no TTS backend
                print(f"[warning] Text-to-speech unavailable ({exc}); replies will be printed only.")

    def speak(self, text: str) -> None:
        print(f"Assistant: {text}")
        if self._engine:
            with self._lock:
                self._engine.say(text)
                self._engine.runAndWait()


class MicListener:
    """Microphone input via the speech_recognition library."""

    def __init__(self, language: str = "en-US", engine: str = "google",
                 timeout: float = 6, phrase_limit: float = 12):
        import speech_recognition as sr  # imported lazily so tests/--text work without it
        self._sr = sr
        self.language, self.engine = language, engine
        self.timeout, self.phrase_limit = timeout, phrase_limit
        self._recognizer = sr.Recognizer()
        self._recognizer.dynamic_energy_threshold = True
        self._mic = sr.Microphone()          # raises if no microphone / PyAudio
        with self._mic as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=1)

    def listen(self) -> str:
        sr = self._sr
        print("(listening...)")
        with self._mic as source:
            try:
                audio = self._recognizer.listen(source, timeout=self.timeout,
                                                phrase_time_limit=self.phrase_limit)
            except sr.WaitTimeoutError:
                raise NoSpeech()
        try:
            if self.engine == "sphinx":
                text = self._recognizer.recognize_sphinx(audio, language=self.language)
            else:
                text = self._recognizer.recognize_google(audio, language=self.language)
        except sr.UnknownValueError:
            raise NotUnderstood()
        except sr.RequestError as exc:
            raise SpeechServiceError(str(exc))
        print(f"You: {text}")
        return text


class TextListener:
    """Keyboard stand-in for the microphone (--text mode)."""

    def listen(self) -> str:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "goodbye"
        if not text:
            raise NoSpeech()
        return text
