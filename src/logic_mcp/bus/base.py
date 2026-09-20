from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from typing import Any, Literal

from logic_mcp.bus.events import LinkEvent
from logic_mcp.bus.roles import ChannelRole
from logic_mcp.capture.types import LogicCapture
from logic_mcp.errors import UnimplementedBusError

BusStatus = Literal["implemented", "unimplemented"]


class BusDecoder(ABC):
    id: str
    title: str
    status: BusStatus
    notes: str = ""
    roles: tuple[ChannelRole, ...] = ()
    options_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }

    @abstractmethod
    def decode(
        self,
        capture: LogicCapture,
        channel_map: Mapping[str, str | int],
        *,
        options: Mapping[str, Any] | None = None,
        t_min: float | None = None,
        t_max: float | None = None,
    ) -> Iterator[LinkEvent]:
        """Stream link-layer events. Does not interpret a panel or high-level protocol."""

    def roles_dict(self) -> list[dict]:
        return [role.to_dict() for role in self.roles]


class UnimplementedBus(BusDecoder):
    status: BusStatus = "unimplemented"

    def decode(
        self,
        capture: LogicCapture,
        channel_map: Mapping[str, str | int],
        *,
        options: Mapping[str, Any] | None = None,
        t_min: float | None = None,
        t_max: float | None = None,
    ) -> Iterator[LinkEvent]:
        raise UnimplementedBusError(self.id)
