from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from logic_mcp.capture.types import LogicCapture
from logic_mcp.errors import InstrumentError, UnimplementedInstrumentError
from logic_mcp.instrument.types import (
    CaptureRequest,
    InstrumentCapabilities,
    InstrumentDevice,
    InstrumentInfo,
)


class ConnectedInstrument(ABC):
    """One open handle on a scanned device. Capture always returns LogicCapture.

    In-process vendors implement capture() (and optionally start/stop/wait/export).
    IPC vendors implement the same methods over logic_mcp.instrument.v1.
    If owns_config is False, the vendor UI already has rate/channels; MCP only arms.
    """

    device: InstrumentDevice
    owns_config: bool = True
    hub_state: str = "idle"
    transport: str = "inprocess"

    @abstractmethod
    def capabilities(self) -> InstrumentCapabilities:
        """What this device can do right now (rates, channel names, trigger)."""

    def configure(self, request: CaptureRequest) -> dict[str, Any]:
        if not self.owns_config:
            return {"ok": True, "configure": False, "state": self.hub_state}
        raise InstrumentError("configure is not implemented on this backend")

    def start(self, request: CaptureRequest | None = None) -> dict[str, Any]:
        raise InstrumentError("start is not implemented on this backend")

    def stop(self) -> dict[str, Any]:
        raise InstrumentError("stop is not implemented on this backend")

    def wait(self, timeout_s: float = 60.0) -> dict[str, Any]:
        raise InstrumentError("wait is not implemented on this backend")

    def export_capture(self, path: Path, format: str = "csv") -> Path:
        raise InstrumentError("export is not implemented on this backend")

    def capture(self, request: CaptureRequest | None, out_dir: Path) -> LogicCapture:
        """Default: configure? → start → wait → export → LogicCapture."""
        from logic_mcp.capture.registry import open_capture

        if request is not None and self.owns_config:
            self.configure(request)
        self.start(request)
        timeout = request.timeout_s if request is not None else 60.0
        waited = self.wait(timeout)
        if waited.get("timed_out"):
            raise InstrumentError("Capture wait timed out")
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / "capture.csv"
        exported = self.export_capture(dest)
        cap = open_capture(exported)
        if request is not None:
            return mark_live(
                cap,
                backend=self.device.backend,
                device_id=self.device.id,
                request=request,
            )
        cap.source = "live"
        cap.metadata["backend"] = self.device.backend
        cap.metadata["device_id"] = self.device.id
        return cap

    def close(self) -> None:
        return None


class InstrumentBackend(ABC):
    """Vendor plugin. Register via entry point group logic_mcp.instruments."""

    info: InstrumentInfo
    options_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }

    def available(self) -> bool:
        """True if the local runtime can actually talk to this backend (CLI/SDK present)."""
        return self.info.status == "implemented"

    @abstractmethod
    def scan(self) -> list[InstrumentDevice]:
        """Discover devices. Empty list is OK; missing runtime should raise unavailable."""

    @abstractmethod
    def connect(
        self,
        device_id: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> ConnectedInstrument:
        """Claim a device. device_id None means 'first scanned' if the backend allows it."""

    transport: str = "inprocess"

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.info.id,
            "vendor": self.info.vendor,
            "title": self.info.title,
            "status": self.info.status,
            "available": self.available(),
            "transport": self.transport,
            "notes": self.info.notes,
            "options_schema": self.options_schema,
        }


class UnimplementedInstrument(InstrumentBackend):
    def available(self) -> bool:
        return False

    def scan(self) -> list[InstrumentDevice]:
        raise UnimplementedInstrumentError(self.info.id)

    def connect(
        self,
        device_id: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> ConnectedInstrument:
        raise UnimplementedInstrumentError(self.info.id)


def mark_live(
    capture: LogicCapture,
    *,
    backend: str,
    device_id: str,
    request: CaptureRequest,
) -> LogicCapture:
    capture.source = "live"
    capture.metadata["backend"] = backend
    capture.metadata["device_id"] = device_id
    capture.metadata["requested_sample_rate_hz"] = str(request.sample_rate_hz)
    if capture.sample_rate_hz is None:
        capture.sample_rate_hz = request.sample_rate_hz
    return capture
