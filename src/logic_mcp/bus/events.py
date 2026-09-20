from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Strobe = Literal["wr", "rd"]


@dataclass
class LinkEvent:
    """Physical / link-layer event. Protocol-specific subclasses add fields."""

    t: float
    protocol: str

    def to_dict(self) -> dict:
        return {"t": self.t, "protocol": self.protocol, "type": type(self).__name__}


@dataclass
class ParallelCycle(LinkEvent):
    """One MCU-parallel (8080/6800-style) strobe with a data byte and extra GPIOs."""

    protocol: str = "i8080"
    data: int = 0
    strobe: Strobe = "wr"
    cs_active: bool = True
    extras: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        body = super().to_dict()
        body.update(
            {
                "data": self.data,
                "strobe": self.strobe,
                "cs_active": self.cs_active,
                "extras": self.extras,
            }
        )
        return body
