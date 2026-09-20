from __future__ import annotations

from collections.abc import Iterable, Iterator

from logic_mcp.capture.types import Edge, Snapshot


def edges_from_snapshots(snapshots: Iterable[Snapshot]) -> Iterator[Edge]:
    """Turn full vectors into per-channel changes (first snapshot emitted as edges)."""
    prev: tuple[int, ...] | None = None
    for snap in snapshots:
        if prev is None:
            for index, value in enumerate(snap.values):
                yield Edge(snap.t, index, value)
        else:
            for index, value in enumerate(snap.values):
                if value != prev[index]:
                    yield Edge(snap.t, index, value)
        prev = snap.values


def snapshots_from_edges(width: int, edges: Iterable[Edge]) -> Iterator[Snapshot]:
    """Hold last known level per channel; yield a snapshot whenever time advances."""
    levels = [0] * width
    current_t: float | None = None
    started = False
    for edge in edges:
        if current_t is None:
            current_t = edge.t
            started = True
        elif edge.t != current_t:
            yield Snapshot(current_t, tuple(levels))
            current_t = edge.t
        if 0 <= edge.channel < width:
            levels[edge.channel] = 1 if edge.value else 0
    if started and current_t is not None:
        yield Snapshot(current_t, tuple(levels))


def snapshots_in_window(
    snapshots: Iterable[Snapshot],
    t_min: float | None = None,
    t_max: float | None = None,
) -> Iterator[Snapshot]:
    """Keep the last snapshot before t_min so strobe-edge decoders still see prior levels."""
    prev: Snapshot | None = None
    started = False
    for snap in snapshots:
        if t_min is not None and snap.t < t_min:
            prev = snap
            continue
        if not started:
            if prev is not None:
                yield prev
            started = True
        if t_max is not None and snap.t > t_max:
            break
        yield snap
