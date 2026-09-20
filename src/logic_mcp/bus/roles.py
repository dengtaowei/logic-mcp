from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from logic_mcp.errors import ChannelMapError


@dataclass(frozen=True)
class ChannelRole:
    """A named pin a bus decoder knows how to bind onto a capture channel."""

    name: str
    required: bool = True
    aliases: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "required": self.required,
            "aliases": list(self.aliases),
            "description": self.description,
        }


def resolve_channel(spec: str | int, names: Sequence[str]) -> int:
    if isinstance(spec, int):
        idx = spec
    else:
        text = str(spec).strip()
        if text.isdigit():
            idx = int(text)
        else:
            lowered = {name.lower(): i for i, name in enumerate(names)}
            if text.lower() not in lowered:
                raise ChannelMapError(
                    f"Channel {text!r} not in capture. Available: {list(names)}"
                )
            return lowered[text.lower()]
    if idx < 0 or idx >= len(names):
        raise ChannelMapError(
            f"Channel index {idx} out of range 0..{len(names) - 1} ({list(names)})"
        )
    return idx


def resolve_channel_map(
    roles: Sequence[ChannelRole],
    channel_map: Mapping[str, str | int],
    names: Sequence[str],
) -> dict[str, int | None]:
    alias_to_role: dict[str, str] = {}
    for role in roles:
        alias_to_role[role.name.lower()] = role.name
        for alias in role.aliases:
            alias_to_role[alias.lower()] = role.name

    normalized: dict[str, str | int] = {}
    for key, value in channel_map.items():
        role_name = alias_to_role.get(key.strip().lower())
        if role_name is None:
            continue
        normalized[role_name] = value

    missing = [role.name for role in roles if role.required and role.name not in normalized]
    if missing:
        need = ", ".join(role.name for role in roles)
        raise ChannelMapError(
            f"channel_map missing required roles {missing}. Decoder roles: {need}. "
            "Values are capture column names or 0-based channel indices."
        )

    resolved: dict[str, int | None] = {}
    for role in roles:
        if role.name in normalized:
            resolved[role.name] = resolve_channel(normalized[role.name], names)
        else:
            resolved[role.name] = None
    return resolved
