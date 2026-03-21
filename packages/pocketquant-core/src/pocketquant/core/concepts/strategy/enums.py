"""Strategy enums - trading direction."""

from enum import Enum


class Direction(Enum):
    """Trading direction for signals."""

    LONG = "long"
    SHORT = "short"
    EXIT = "exit"
    FLAT = "flat"
