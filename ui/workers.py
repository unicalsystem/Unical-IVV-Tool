"""Background execution so the GUI never freezes."""
from __future__ import annotations

import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

log = logging.getLogger(__name__)


class Worker(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., Any], *args: Any, with_progress: bool = False, **kwargs: Any):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.with_progress = with_progress
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def is_cancelled(self) -> bool:
        return self._cancel

    @Slot()
    def run(self) -> None:
        try:
            if self.with_progress:
                result = self.fn(*self.args, progress=lambda p, m="": self.progress.emit(int(p), str(m)),
                                 cancelled=self.is_cancelled, **self.kwargs)
            else:
                result = self.fn(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as exc:  # report every failure to the UI
            log.error("Background task failed: %s\n%s", exc, traceback.format_exc())
            self.failed.emit(str(exc))


def start_worker(parent: QObject, worker: Worker) -> QThread:
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(thread.deleteLater)
    parent._active_threads = getattr(parent, "_active_threads", []) + [(thread, worker)]  # keep references
    thread.start()
    return thread
