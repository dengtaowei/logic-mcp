from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from logic_mcp.bus.base import BusDecoder
from logic_mcp.bus.events import ParallelCycle
from logic_mcp.bus.roles import ChannelRole, resolve_channel_map
from logic_mcp.capture.stream import snapshots_in_window
from logic_mcp.capture.types import LogicCapture, Snapshot

I8080_ROLES: tuple[ChannelRole, ...] = (
    ChannelRole("d0", description="Data bit 0"),
    ChannelRole("d1", description="Data bit 1"),
    ChannelRole("d2", description="Data bit 2"),
    ChannelRole("d3", description="Data bit 3"),
    ChannelRole("d4", description="Data bit 4"),
    ChannelRole("d5", description="Data bit 5"),
    ChannelRole("d6", description="Data bit 6"),
    ChannelRole("d7", description="Data bit 7"),
    ChannelRole("wr", aliases=("wrx",), description="Write strobe (active-low pulse, sample rising edge)"),
    ChannelRole("dc", aliases=("rs", "dcx"), description="Data/command: 0=cmd, 1=data"),
    ChannelRole("cs", required=False, aliases=("csx",), description="Chip select, active-low"),
    ChannelRole("rd", required=False, aliases=("rdx",), description="Read strobe (optional)"),
)

I8080_OPTIONS: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "cs_active_low": {
            "type": "boolean",
            "default": True,
            "description": "CS is active-low",
        },
        "wr_rising": {
            "type": "boolean",
            "default": True,
            "description": "Sample data on WR rising edge",
        },
        "rd_rising": {
            "type": "boolean",
            "default": True,
            "description": "Sample data on RD rising edge",
        },
    },
}


def _byte_from_values(values: tuple[int, ...], data_idx: Sequence[int]) -> int:
    byte = 0
    for bit, idx in enumerate(data_idx):
        if values[idx]:
            byte |= 1 << bit
    return byte


def _strobe(prev: int, curr: int, rising: bool) -> bool:
    if rising:
        return prev == 0 and curr == 1
    return prev == 1 and curr == 0


def decode_i8080_snapshots(
    snapshots: Iterator[Snapshot],
    resolved: Mapping[str, int | None],
    *,
    cs_active_low: bool = True,
    wr_rising: bool = True,
    rd_rising: bool = True,
) -> Iterator[ParallelCycle]:
    data_idx = [int(resolved[f"d{i}"]) for i in range(8)]
    wr_i = int(resolved["wr"])
    dc_i = int(resolved["dc"])
    cs_i = resolved["cs"]
    rd_i = resolved["rd"]

    prev: tuple[int, ...] | None = None
    for snap in snapshots:
        values = snap.values
        if prev is None:
            prev = values
            continue
        if cs_i is None:
            cs_active = True
        elif cs_active_low:
            cs_active = values[cs_i] == 0
        else:
            cs_active = values[cs_i] == 1
        wr_edge = _strobe(prev[wr_i], values[wr_i], wr_rising)
        rd_edge = (
            rd_i is not None and _strobe(prev[rd_i], values[rd_i], rd_rising)
        )
        if cs_active and wr_edge:
            yield ParallelCycle(
                t=snap.t,
                data=_byte_from_values(values, data_idx),
                strobe="wr",
                cs_active=True,
                extras={"dc": values[dc_i]},
            )
        elif cs_active and rd_edge:
            yield ParallelCycle(
                t=snap.t,
                data=_byte_from_values(values, data_idx),
                strobe="rd",
                cs_active=True,
                extras={"dc": values[dc_i]},
            )
        prev = values


class I8080Decoder(BusDecoder):
    id = "i8080"
    title = "Intel 8080 / MCU 8-bit parallel (LCD 8080-I)"
    status = "implemented"
    notes = (
        "Link-layer only: emits ParallelCycle on WR/RD strobe while CS is active. "
        "DC/RS is in extras['dc']. Polarity is decode options, not a new decoder."
    )
    roles = I8080_ROLES
    options_schema = I8080_OPTIONS

    def decode(
        self,
        capture: LogicCapture,
        channel_map: Mapping[str, str | int],
        *,
        options: Mapping[str, Any] | None = None,
        t_min: float | None = None,
        t_max: float | None = None,
    ) -> Iterator[ParallelCycle]:
        opts = dict(options or {})
        resolved = resolve_channel_map(self.roles, channel_map, capture.channel_names)
        snaps = snapshots_in_window(capture.iter_snapshots(), t_min, t_max)
        return decode_i8080_snapshots(
            snaps,
            resolved,
            cs_active_low=bool(opts.get("cs_active_low", True)),
            wr_rising=bool(opts.get("wr_rising", True)),
            rd_rising=bool(opts.get("rd_rising", True)),
        )
