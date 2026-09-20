from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from logic_mcp.capture.registry import open_capture
from logic_mcp.capture.types import Channel, LogicCapture
from logic_mcp.errors import CaptureOpenError, InstrumentConfigError, InstrumentError
from logic_mcp.instrument.base import ConnectedInstrument, InstrumentBackend, mark_live
from logic_mcp.instrument.types import (
    CaptureRequest,
    InstrumentCapabilities,
    InstrumentDevice,
    InstrumentInfo,
)
from logic_mcp.synth import HEADER, build_idle_csv, build_st7789_blocks_csv

MOCK_RATES = [
    1e3,
    10e3,
    100e3,
    1e6,
    10e6,
    25e6,
    50e6,
    100e6,
    200e6,
    400e6,
]
MOCK_CHANNEL_NAMES = list(HEADER[1:]) + [f"CH{i}" for i in range(12, 16)]


def _default_request() -> CaptureRequest:
    return CaptureRequest(sample_rate_hz=100_000_000, duration_s=0.001)


class MockConnected(ConnectedInstrument):
    def __init__(self, device: InstrumentDevice, extra: Mapping[str, Any] | None = None):
        self.device = device
        self.connect_extra = dict(extra or {})
        self.owns_config = not bool(self.connect_extra.get("gui_owned"))
        self.hub_state = "idle"
        self._request: CaptureRequest | None = None
        self._artifact: Path | None = None

    def capabilities(self) -> InstrumentCapabilities:
        channels = [Channel(index=i, name=name) for i, name in enumerate(MOCK_CHANNEL_NAMES)]
        return InstrumentCapabilities(
            channels=channels,
            sample_rates_hz=list(MOCK_RATES),
            min_sample_rate_hz=MOCK_RATES[0],
            max_sample_rate_hz=MOCK_RATES[-1],
            supports_trigger=True,
            supports_duration=True,
            supports_sample_count=True,
            analog=False,
            streaming=False,
            options_schema=MockBackend.options_schema,
        )

    def configure(self, request: CaptureRequest) -> dict[str, Any]:
        self._request = request
        self.hub_state = "configured"
        return {"ok": True, "state": self.hub_state, "configure": True}

    def start(self, request: CaptureRequest | None = None) -> dict[str, Any]:
        req = request or self._request or _default_request()
        extra_dir = self.connect_extra.get("out_dir") or req.extra.get("out_dir")
        if extra_dir:
            out = Path(str(extra_dir))
        else:
            import tempfile

            out = Path(tempfile.mkdtemp(prefix="logic-mcp-mock-"))
        cap = self._write_capture(req, out)
        self._artifact = cap.path
        self._request = req
        self.hub_state = "complete"
        return {"state": self.hub_state}

    def stop(self) -> dict[str, Any]:
        self.hub_state = "idle"
        return {"state": self.hub_state}

    def wait(self, timeout_s: float = 60.0) -> dict[str, Any]:
        return {"state": self.hub_state, "timed_out": False}

    def export_capture(self, path: Path, format: str = "csv") -> Path:
        if self._artifact is None or not self._artifact.is_file():
            raise InstrumentError("No capture to export. Call start first.")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.resolve() != self._artifact.resolve():
            shutil.copyfile(self._artifact, path)
            return path
        return self._artifact

    def capture(self, request: CaptureRequest | None, out_dir: Path) -> LogicCapture:
        req = request or self._request or _default_request()
        cap = self._write_capture(req, out_dir)
        self._artifact = cap.path
        self._request = req
        self.hub_state = "complete"
        return cap

    def _write_capture(self, request: CaptureRequest, out_dir: Path) -> LogicCapture:
        extra = {**self.connect_extra, **request.extra}
        out_dir.mkdir(parents=True, exist_ok=True)
        replay = extra.get("replay")
        if replay:
            path = Path(str(replay)).expanduser()
            if not path.is_file():
                raise CaptureOpenError(f"Mock replay file not found: {path}")
            return mark_live(
                open_capture(path),
                backend=self.device.backend,
                device_id=self.device.id,
                request=request,
            )
        pattern = str(extra.get("pattern") or "st7789_blocks")
        dest = out_dir / f"mock-{pattern}.csv"
        if pattern == "st7789_blocks":
            build_st7789_blocks_csv(dest, sample_rate_hz=request.sample_rate_hz)
        elif pattern == "idle":
            names = list(request.channels) if request.channels else MOCK_CHANNEL_NAMES[:12]
            duration = request.duration_s
            if duration is None:
                count = request.sample_count or 2
                duration = count / request.sample_rate_hz
            build_idle_csv(dest, names, request.sample_rate_hz, duration)
        else:
            raise InstrumentConfigError(
                f"Unknown mock pattern {pattern!r}. Use st7789_blocks, idle, or extra.replay"
            )
        return mark_live(
            open_capture(dest, format_id="dsview_csv"),
            backend=self.device.backend,
            device_id=self.device.id,
            request=request,
        )


class MockBackend(InstrumentBackend):
    info = InstrumentInfo(
        id="mock",
        vendor="logic-mcp",
        title="Virtual logic analyzer (no hardware)",
        status="implemented",
        notes=(
            "Always present. Default pattern extra.pattern=st7789_blocks so the "
            "instrument → decode → reconstruct loop can be tested without a LA. "
            "Use extra.replay to feed a real CSV as if it were live."
        ),
    )
    options_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "enum": ["st7789_blocks", "idle"],
                "default": "st7789_blocks",
            },
            "replay": {
                "type": "string",
                "description": "Existing capture file treated as the live result",
            },
        },
        "additionalProperties": True,
    }

    def available(self) -> bool:
        return True

    def scan(self) -> list[InstrumentDevice]:
        return [
            InstrumentDevice(
                id="mock:virtual",
                backend=self.info.id,
                vendor="logic-mcp",
                model="Virtual 16-ch logic analyzer",
                serial=None,
                present=True,
            )
        ]

    def connect(
        self,
        device_id: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> ConnectedInstrument:
        device = self.scan()[0]
        if device_id and device_id not in (device.id, "mock", "virtual"):
            device = InstrumentDevice(
                id=device_id,
                backend=self.info.id,
                vendor="logic-mcp",
                model="Virtual 16-ch logic analyzer",
                present=True,
            )
        return MockConnected(device, extra)
