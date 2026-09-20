from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from logic_mcp.capture.types import Channel, Status
from logic_mcp.errors import InstrumentConfigError

TriggerEdge = Literal["rising", "falling", "either", "high", "low"]
InstrumentState = Literal["disconnected", "idle", "configured", "capturing", "captured", "error"]
VALID_EDGES: tuple[TriggerEdge, ...] = ("rising", "falling", "either", "high", "low")

_HZ_RE = re.compile(r"([0-9.]+)\s*([kKmMgG])?\s*[Hh]z")
_SI = {"": 1.0, "k": 1e3, "m": 1e6, "g": 1e9}


def parse_hz(text: str) -> float:
    match = _HZ_RE.search(text.replace(",", ""))
    if not match:
        raise InstrumentConfigError(f"Cannot parse sample rate from {text!r}")
    return float(match.group(1)) * _SI[match.group(2).lower() if match.group(2) else ""]


def find_hz_values(text: str) -> list[float]:
    found: list[float] = []
    for match in _HZ_RE.finditer(text.replace(",", "")):
        found.append(float(match.group(1)) * _SI[match.group(2).lower() if match.group(2) else ""])
    return found


@dataclass(frozen=True)
class InstrumentInfo:
    id: str
    vendor: str
    title: str
    status: Status
    notes: str = ""


@dataclass(frozen=True)
class TriggerSpec:
    channel: str
    edge: TriggerEdge = "rising"

    def to_dict(self) -> dict[str, str]:
        return {"channel": self.channel, "edge": self.edge}

    def sigrok_token(self) -> str:
        letter = {"rising": "r", "falling": "f", "either": "e", "high": "1", "low": "0"}[self.edge]
        return f"{self.channel}={letter}"


@dataclass
class CaptureRequest:
    """Vendor-neutral live-capture request. Backends map this onto their CLI/API."""

    sample_rate_hz: float
    channels: tuple[str, ...] | None = None
    duration_s: float | None = None
    sample_count: int | None = None
    trigger: TriggerSpec | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_rate_hz": self.sample_rate_hz,
            "channels": list(self.channels) if self.channels else None,
            "duration_s": self.duration_s,
            "sample_count": self.sample_count,
            "trigger": self.trigger.to_dict() if self.trigger else None,
            "extra": dict(self.extra),
            "timeout_s": self.timeout_s,
        }


@dataclass(frozen=True)
class InstrumentDevice:
    id: str
    backend: str
    vendor: str
    model: str
    serial: str | None = None
    present: bool = True
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "backend": self.backend,
            "vendor": self.vendor,
            "model": self.model,
            "serial": self.serial,
            "present": self.present,
            "extra": dict(self.extra),
        }


@dataclass
class InstrumentCapabilities:
    channels: list[Channel]
    sample_rates_hz: list[float] | None = None
    min_sample_rate_hz: float | None = None
    max_sample_rate_hz: float | None = None
    supports_trigger: bool = True
    supports_duration: bool = True
    supports_sample_count: bool = True
    analog: bool = False
    streaming: bool = False
    options_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channels": [{"index": ch.index, "name": ch.name, "kind": ch.kind} for ch in self.channels],
            "sample_rates_hz": self.sample_rates_hz,
            "min_sample_rate_hz": self.min_sample_rate_hz,
            "max_sample_rate_hz": self.max_sample_rate_hz,
            "supports_trigger": self.supports_trigger,
            "supports_duration": self.supports_duration,
            "supports_sample_count": self.supports_sample_count,
            "analog": self.analog,
            "streaming": self.streaming,
            "options_schema": self.options_schema,
        }


def build_request(
    sample_rate_hz: float,
    *,
    channels: list[str] | None = None,
    duration_s: float | None = None,
    sample_count: int | None = None,
    trigger_channel: str | None = None,
    trigger_edge: str | None = None,
    extra: dict[str, Any] | None = None,
    timeout_s: float = 60.0,
) -> CaptureRequest:
    if sample_rate_hz <= 0:
        raise InstrumentConfigError("sample_rate_hz must be > 0")
    if duration_s is None and sample_count is None:
        raise InstrumentConfigError("Provide duration_s or sample_count")
    if duration_s is not None and duration_s <= 0:
        raise InstrumentConfigError("duration_s must be > 0")
    if sample_count is not None and sample_count <= 0:
        raise InstrumentConfigError("sample_count must be > 0")
    if timeout_s <= 0:
        raise InstrumentConfigError("timeout_s must be > 0")
    trigger = None
    if trigger_channel:
        edge = trigger_edge or "rising"
        if edge not in VALID_EDGES:
            known = ", ".join(VALID_EDGES)
            raise InstrumentConfigError(f"Unknown trigger edge {edge!r}. Use: {known}")
        trigger = TriggerSpec(trigger_channel, edge)  # type: ignore[arg-type]
    elif trigger_edge:
        raise InstrumentConfigError("trigger_edge requires trigger_channel")
    return CaptureRequest(
        sample_rate_hz=float(sample_rate_hz),
        channels=tuple(channels) if channels else None,
        duration_s=duration_s,
        sample_count=sample_count,
        trigger=trigger,
        extra=dict(extra or {}),
        timeout_s=float(timeout_s),
    )
