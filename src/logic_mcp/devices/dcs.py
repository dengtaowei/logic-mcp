from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from logic_mcp.bus.events import LinkEvent, ParallelCycle
from logic_mcp.devices.base import UpperDecoder
from logic_mcp.devices.mipi_dcs import command_name, is_pixel_opcode
from logic_mcp.messages import COMMANDS_SCHEMA, Message


def parallel_wr_cycles(events: Iterable[LinkEvent]) -> Iterator[ParallelCycle]:
    for event in events:
        if isinstance(event, ParallelCycle) and event.strobe == "wr":
            yield event


def interpret_dcs(
    events: Iterable[LinkEvent],
    extra_names: dict[int, str] | None = None,
) -> Iterator[Message]:
    """Lift 8080 WR cycles (extras['dc']) into dcs.command / dcs.data messages."""
    in_pixel = False
    for cycle in parallel_wr_cycles(events):
        dc = cycle.extras.get("dc", 1)
        if dc == 0:
            opcode = cycle.data
            in_pixel = is_pixel_opcode(opcode)
            yield Message(
                t=cycle.t,
                type="dcs.command",
                fields={
                    "opcode": opcode,
                    "name": command_name(opcode, extra_names),
                    "pixel": in_pixel,
                },
            )
            continue
        yield Message(
            t=cycle.t,
            type="dcs.data",
            fields={"byte": cycle.data, "pixel": in_pixel},
        )


def aggregate_dcs_commands(messages: Iterable[Message]) -> list[dict]:
    rows: list[dict] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            rows.append(current)
            current = None

    for msg in messages:
        if msg.type == "dcs.command":
            flush()
            current = {
                "schema": COMMANDS_SCHEMA,
                "t": msg.t,
                "opcode": f"0x{msg.fields['opcode']:02X}",
                "name": msg.fields["name"],
                "data_len": 0,
                "is_pixel": bool(msg.fields.get("pixel")),
                "params": None if msg.fields.get("pixel") else [],
            }
            continue
        if msg.type != "dcs.data" or current is None:
            continue
        current["data_len"] += 1
        if not current["is_pixel"] and isinstance(current.get("params"), list):
            current["params"].append(f"0x{msg.fields['byte']:02X}")
    flush()
    return rows


class MipiDcsDriver(UpperDecoder):
    id = "mipi_dcs"
    title = "MIPI DCS (ST7789, ILI9341, ST7735, ...)"
    notes = "Emits dcs.command / dcs.data messages. Framebuffer is a sink, not this decoder."

    def interpret(
        self,
        events: Iterable[LinkEvent],
        context: dict[str, Any] | None = None,
    ) -> Iterator[Message]:
        extra = (context or {}).get("commands")
        return interpret_dcs(events, extra)
