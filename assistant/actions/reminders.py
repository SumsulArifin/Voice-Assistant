"""Timed reminders: a background timer fires an audible alert when due."""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

MAX_SECONDS = 24 * 3600


@dataclass
class Reminder:
    seconds: int
    message: str = ""
    created_at: float = field(default_factory=time.time)
    fired: bool = False

    @property
    def spoken(self) -> str:
        return f"Reminder: {self.message}." if self.message else "Your timer is up."


def humanize_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    parts = []
    for name, size in (("hour", 3600), ("minute", 60), ("second", 1)):
        n, seconds = divmod(seconds, size)
        if n:
            parts.append(f"{n} {name}{'s' if n != 1 else ''}")
    if not parts:
        return "0 seconds"
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


class ReminderManager:
    """The timer thread only raises the alert and queues the reminder; the main
    loop speaks it, because text-to-speech engines are not thread-safe."""

    def __init__(self, alert: Optional[Callable[[Reminder], None]] = None,
                 timer_factory=threading.Timer):
        self._alert = alert
        self._factory = timer_factory
        self._due: "queue.Queue[Reminder]" = queue.Queue()
        self._timers: list = []

    def add(self, seconds: int, message: str = "") -> Reminder:
        if not 0 < seconds <= MAX_SECONDS:
            raise ValueError("Reminders must be between 1 second and 24 hours.")
        reminder = Reminder(int(seconds), message or "")
        timer = self._factory(seconds, self._fire, args=(reminder,))
        timer.daemon = True
        timer.start()
        self._timers.append(timer)
        return reminder

    def _fire(self, reminder: Reminder) -> None:
        reminder.fired = True
        self._due.put(reminder)
        if self._alert:
            self._alert(reminder)

    def pop_due(self) -> List[Reminder]:
        due = []
        while True:
            try:
                due.append(self._due.get_nowait())
            except queue.Empty:
                return due

    def cancel_all(self) -> None:
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()
