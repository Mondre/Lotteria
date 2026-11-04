from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Draw:
    game: str
    variant: str
    draw_id: str
    occurred_at: datetime
    numbers: tuple[int, ...]
    wheel: str = ""
    extras: dict[str, int] = field(default_factory=dict)
    synthetic: bool = False
    source: str = "manuale"
    date_precision: str = "instant"
