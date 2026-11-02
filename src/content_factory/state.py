"""Durable engine state, so a restart loses no queued work."""

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .tasks import Task


@dataclass
class EngineState:
    offset: Optional[int] = None
    queue: list = field(default_factory=list)
    active: Optional[Task] = None


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> EngineState:
        if not self.path.exists():
            return EngineState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        queue = [Task.from_dict(item) for item in data.get("queue", [])]
        # A task that was running when the process stopped has no result, so run it again.
        if data.get("active"):
            queue.insert(0, Task.from_dict(data["active"]))
        return EngineState(offset=data.get("offset"), queue=queue)

    def save(self, state: EngineState) -> None:
        payload = {
            "offset": state.offset,
            "queue": [task.to_dict() for task in state.queue],
            "active": state.active.to_dict() if state.active else None,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write and rename, so a crash cannot leave a half-written state file.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
