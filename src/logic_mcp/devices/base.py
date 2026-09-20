from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from typing import Any

from logic_mcp.bus.events import LinkEvent
from logic_mcp.messages import Message


class UpperDecoder(ABC):
    """Link events → namespaced Message stream. Not a display, not a PNG writer."""

    id: str
    title: str
    notes: str = ""

    @abstractmethod
    def interpret(
        self,
        events: Iterable[LinkEvent],
        context: dict[str, Any] | None = None,
    ) -> Iterator[Message]:
        """context may include command-name maps; geometry belongs to sinks."""


DeviceDriver = UpperDecoder
