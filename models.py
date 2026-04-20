from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ScreenTemplate:
    name: str
    path: str
    threshold: float = 0.8
    min_scale: float = 0.6
    max_scale: float = 1.0
    scale_step: float = 0.05
    image: Any = None


@dataclass
class RunStatistics:
    loop_count: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    last_step: str = ""

    def restart(self) -> None:
        self.loop_count = 0
        self.start_time = datetime.now()
        self.last_step = ""
