"""Runner state enumeration."""

from enum import Enum, auto


class RunnerState(Enum):
    STOPPED = auto()
    RUNNING = auto()
    PAUSED = auto()
