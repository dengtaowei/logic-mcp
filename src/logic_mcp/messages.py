from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MESSAGES_SCHEMA = "logic_mcp.messages.v1"
COMMANDS_SCHEMA = "logic_mcp.commands.v1"
FRAMEBUFFER_SCHEMA = "logic_mcp.framebuffer.v1"


@dataclass
class Message:
    """Upper-layer event. type is namespaced (dcs.command, eeprom.write, ...)."""

    t: float
    type: str
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"t": self.t, "type": self.type, **self.fields}


@dataclass
class Artifact:
    kind: str
    path: str
    schema: str
    job_id: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        body = {
            "kind": self.kind,
            "path": self.path,
            "schema": self.schema,
            "job_id": self.job_id,
        }
        body.update(self.extra)
        return body
