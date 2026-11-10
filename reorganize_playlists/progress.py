"""Progress lines on stderr: redrawn in place on a terminal, milestone lines when piped."""

from __future__ import annotations

import shutil
import sys
import time
from typing import TextIO


def _duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


class Task:
    def __init__(self, stream: TextIO, tty: bool, label: str, total: int | None) -> None:
        self._stream, self._tty, self.label, self.total = stream, tty, label, total
        self._start = time.monotonic()
        self._last_draw = 0.0
        self._last_bucket = -1
        self.done = 0.0

    def _line(self, detail: str) -> str:
        elapsed = time.monotonic() - self._start
        if self.total is None:
            text = f"{self.label} {self.done:.0f}% ({_duration(elapsed)})"
        else:
            percent = 100 * self.done / self.total if self.total else 100
            text = f"{self.label} {self.done:.0f}/{self.total} ({percent:.0f}%, {_duration(elapsed)}"
            if 0 < self.done < self.total:
                text += f", ~{_duration(elapsed / self.done * (self.total - self.done))} left"
            text += ")"
        return f"{text} {detail}".rstrip()

    def _percent(self) -> float:
        if self.total is None:
            return self.done
        return 100 * self.done / self.total if self.total else 100

    def update(self, done: float, detail: str = "") -> None:
        self.done = done
        if self._tty:
            now = time.monotonic()
            if now - self._last_draw >= 0.1:
                self._last_draw = now
                width = shutil.get_terminal_size().columns - 1
                self._stream.write("\r" + self._line(detail)[:width] + "\x1b[K")
                self._stream.flush()
        elif (bucket := int(self._percent() // 10)) > self._last_bucket and self._percent() < 100:
            self._last_bucket = bucket
            print(self._line(detail), file=self._stream, flush=True)

    def advance(self, detail: str = "") -> None:
        self.update(self.done + 1, detail)

    def finish(self) -> None:
        if self.total is None:
            self.done = 100
        line = self._line("done")
        print(("\r" + line + "\x1b[K") if self._tty else line, file=self._stream, flush=True)


class Progress:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stderr
        self._tty = self._stream.isatty()

    def counter(self, label: str, total: int) -> Task:
        """`label done/total`, with elapsed time and an estimate of what is left."""
        return Task(self._stream, self._tty, label, total)

    def percent(self, label: str) -> Task:
        """`label NN%` for work that reports its own percentage."""
        return Task(self._stream, self._tty, label, None)

    def note(self, message: str) -> None:
        print(message, file=self._stream, flush=True)
