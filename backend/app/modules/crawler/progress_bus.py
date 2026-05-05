"""TaskProgressBus：进程内事件总线，向 WebSocket 订阅者广播任务进度。"""
import json
import logging
from dataclasses import dataclass, asdict
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    task_id: str
    status: str
    completed: int = 0
    failed: int = 0
    total: int = 0
    current_url: str | None = None
    message: str | None = None


class TaskProgressBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, task_id: str, callback: Callable[[str], None]):
        self._subscribers.setdefault(task_id, []).append(callback)

    def unsubscribe(self, task_id: str, callback: Callable[[str], None]):
        subs = self._subscribers.get(task_id, [])
        if callback in subs:
            subs.remove(callback)
        if not subs:
            self._subscribers.pop(task_id, None)

    def emit(self, event: ProgressEvent):
        subs = self._subscribers.get(event.task_id, [])
        if not subs:
            return
        data = json.dumps(asdict(event))
        for cb in subs:
            try:
                cb(data)
            except Exception:
                logger.warning("progress bus callback failed", exc_info=True)


progress_bus = TaskProgressBus()
