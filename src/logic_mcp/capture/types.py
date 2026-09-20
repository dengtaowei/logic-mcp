from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Status = Literal["implemented", "unimplemented"]
SourceKind = Literal["file", "live", "memory"]
ChannelKind = Literal["digital", "analog"]
SnapshotIter = Callable[[], Iterator["Snapshot"]]
EdgeIter = Callable[[], Iterator["Edge"]]


@dataclass(frozen=True)
class FormatInfo:
    id: str
    vendor: str
    title: str
    status: Status
    extensions: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class Channel:
    index: int
    name: str
    kind: ChannelKind = "digital"


@dataclass(frozen=True)
class Edge:
    """One digital channel changing to 0 or 1 at time t (seconds)."""

    t: float
    channel: int
    value: int


@dataclass(frozen=True)
class Snapshot:
    """Full digital vector after a change. Prefer building this from Edge streams."""

    t: float
    values: tuple[int, ...]


@dataclass
class LogicCapture:
    """Vendor-agnostic capture. Adapters fill this; bus decoders only see this.

    Edge stream is the native interchange. Snapshots are reconstructed levels so
    parallel-bus decoders can sample the whole vector on a strobe edge.
    """

    info: FormatInfo
    channels: list[Channel]
    source: SourceKind = "file"
    path: Path | None = None
    sample_rate_hz: float | None = None
    sample_count: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    _iter_snapshots: SnapshotIter | None = field(default=None, repr=False, compare=False)
    _iter_edges: EdgeIter | None = field(default=None, repr=False, compare=False)

    @property
    def channel_names(self) -> list[str]:
        return [ch.name for ch in self.channels]

    def iter_edges(self) -> Iterator[Edge]:
        from logic_mcp.capture.stream import edges_from_snapshots

        if self._iter_edges is not None:
            return self._iter_edges()
        if self._iter_snapshots is not None:
            return edges_from_snapshots(self._iter_snapshots())
        raise RuntimeError("Capture has no edge or snapshot iterator")

    def iter_snapshots(self) -> Iterator[Snapshot]:
        from logic_mcp.capture.stream import snapshots_from_edges

        if self._iter_snapshots is not None:
            return self._iter_snapshots()
        if self._iter_edges is not None:
            return snapshots_from_edges(len(self.channels), self._iter_edges())
        raise RuntimeError("Capture has no edge or snapshot iterator")


class CaptureFormat(ABC):
    """One capture file family from one vendor (or a shared interchange format)."""

    info: FormatInfo

    @abstractmethod
    def sniff(self, path: Path) -> float:
        """Confidence 0.0–1.0 that this adapter should open the file."""

    @abstractmethod
    def open(self, path: Path) -> LogicCapture:
        """Parse headers and return a capture that can stream edges/snapshots."""
