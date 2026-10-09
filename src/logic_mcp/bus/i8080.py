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
        "min_strobe_ns": {
            "type": "number",
            "default": 0,
            "minimum": 0,
            "description": (
                "Drop WR/RD pulses shorter than this many nanoseconds "
                "(probe ringing). 0 keeps every strobe edge. "
                "A pulse still high/low at the end of the capture is kept."
            ),
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


def _min_strobe_s(options: Mapping[str, Any] | None) -> float:
    """0 disables filtering. Non-positive, NaN, and non-numeric values disable it too."""
    if not options:
        return 0.0
    raw = options.get("min_strobe_ns", 0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if value != value or value <= 0:  # NaN or disabled
        return 0.0
    return value * 1e-9


class _StrobePulse:
    """One WR/RD line. A sample edge is emitted only if that pulse lasts long enough.

    The pending event is built at the sample edge (data/DC/CS from that snapshot,
    timestamp of that edge). It is dropped if the opposite edge arrives before
    min_strobe_s. A pulse that never returns before the capture ends is kept,
    matching an unfiltered trailing edge.
    """

    def __init__(self, level: int, since: float) -> None:
        self.level = level
        self.since = since
        self.pending: ParallelCycle | None = None

    def transition(
        self,
        level: int,
        t: float,
        *,
        sample_level: int,
        min_strobe_s: float,
        pending: ParallelCycle | None,
    ) -> ParallelCycle | None:
        if level == self.level:
            return None
        confirmed: ParallelCycle | None = None
        if self.level == sample_level and self.pending is not None:
            if t - self.since >= min_strobe_s:
                confirmed = self.pending
            self.pending = None
        self.level = level
        self.since = t
        if level == sample_level:
            self.pending = pending
        return confirmed

    def finish(self, sample_level: int) -> ParallelCycle | None:
        if self.level == sample_level and self.pending is not None:
            return self.pending
        return None


def decode_i8080_snapshots(
    snapshots: Iterator[Snapshot],
    resolved: Mapping[str, int | None],
    *,
    cs_active_low: bool = True,
    wr_rising: bool = True,
    rd_rising: bool = True,
    min_strobe_s: float = 0.0,
) -> Iterator[ParallelCycle]:
    if min_strobe_s > 0:
        return _decode_i8080_min_strobe(
            snapshots,
            resolved,
            cs_active_low=cs_active_low,
            wr_rising=wr_rising,
            rd_rising=rd_rising,
            min_strobe_s=min_strobe_s,
        )
    return _decode_i8080_edges(
        snapshots,
        resolved,
        cs_active_low=cs_active_low,
        wr_rising=wr_rising,
        rd_rising=rd_rising,
    )


def _cs_active(
    values: tuple[int, ...],
    cs_i: int | None,
    cs_active_low: bool,
) -> bool:
    if cs_i is None:
        return True
    if cs_active_low:
        return values[cs_i] == 0
    return values[cs_i] == 1


def _cycle(
    snap: Snapshot,
    data_idx: Sequence[int],
    dc_i: int,
    strobe: str,
) -> ParallelCycle:
    return ParallelCycle(
        t=snap.t,
        data=_byte_from_values(snap.values, data_idx),
        strobe=strobe,
        cs_active=True,
        extras={"dc": snap.values[dc_i]},
    )


def _decode_i8080_edges(
    snapshots: Iterator[Snapshot],
    resolved: Mapping[str, int | None],
    *,
    cs_active_low: bool,
    wr_rising: bool,
    rd_rising: bool,
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
        cs_active = _cs_active(values, cs_i, cs_active_low)
        wr_edge = _strobe(prev[wr_i], values[wr_i], wr_rising)
        rd_edge = (
            rd_i is not None and _strobe(prev[rd_i], values[rd_i], rd_rising)
        )
        if cs_active and wr_edge:
            yield _cycle(snap, data_idx, dc_i, "wr")
        elif cs_active and rd_edge:
            yield _cycle(snap, data_idx, dc_i, "rd")
        prev = values


def _decode_i8080_min_strobe(
    snapshots: Iterator[Snapshot],
    resolved: Mapping[str, int | None],
    *,
    cs_active_low: bool,
    wr_rising: bool,
    rd_rising: bool,
    min_strobe_s: float,
) -> Iterator[ParallelCycle]:
    data_idx = [int(resolved[f"d{i}"]) for i in range(8)]
    wr_i = int(resolved["wr"])
    dc_i = int(resolved["dc"])
    cs_i = resolved["cs"]
    rd_i = resolved["rd"]
    wr_sample = 1 if wr_rising else 0
    rd_sample = 1 if rd_rising else 0

    first = next(snapshots, None)
    if first is None:
        return
    wr = _StrobePulse(first.values[wr_i], first.t)
    rd = (
        _StrobePulse(first.values[rd_i], first.t)
        if rd_i is not None
        else None
    )

    for snap in snapshots:
        values = snap.values
        cs_active = _cs_active(values, cs_i, cs_active_low)
        wr_edge = None
        if values[wr_i] != wr.level:
            wr_edge = wr.transition(
                values[wr_i],
                snap.t,
                sample_level=wr_sample,
                min_strobe_s=min_strobe_s,
                pending=_cycle(snap, data_idx, dc_i, "wr") if cs_active else None,
            )
        if wr_edge is not None:
            yield wr_edge
        # Same snapshot: a WR sample edge suppresses a new RD sample, matching
        # the unfiltered if/elif. RD level still tracks so a later edge is real.
        wr_took_edge = (
            wr.pending is not None
            and wr.pending.t == snap.t
            and wr.level == wr_sample
        )
        if rd is not None and rd_i is not None and values[rd_i] != rd.level:
            rd_edge = rd.transition(
                values[rd_i],
                snap.t,
                sample_level=rd_sample,
                min_strobe_s=min_strobe_s,
                pending=None
                if wr_took_edge or not cs_active
                else _cycle(snap, data_idx, dc_i, "rd"),
            )
            if rd_edge is not None:
                yield rd_edge

    done = wr.finish(wr_sample)
    if done is not None:
        yield done
    if rd is not None:
        done = rd.finish(rd_sample)
        if done is not None:
            yield done


class I8080Decoder(BusDecoder):
    id = "i8080"
    title = "Intel 8080 / MCU 8-bit parallel (LCD 8080-I)"
    status = "implemented"
    notes = (
        "Link-layer only: emits ParallelCycle on WR/RD strobe while CS is active. "
        "DC/RS is in extras['dc']. Polarity is decode options, not a new decoder. "
        "min_strobe_ns is optional; 0 (default) does not filter edges."
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
            min_strobe_s=_min_strobe_s(opts),
        )
