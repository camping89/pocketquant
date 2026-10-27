from dataclasses import dataclass


@dataclass(frozen=True)
class PnL:
    unrealized: float
    realized: float

    @property
    def total(self) -> float:
        return self.unrealized + self.realized
