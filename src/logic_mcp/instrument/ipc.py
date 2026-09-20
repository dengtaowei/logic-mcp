from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from logic_mcp.capture.registry import open_capture
from logic_mcp.capture.types import Channel, LogicCapture
from logic_mcp.errors import InstrumentError, InstrumentUnavailableError
from logic_mcp.instrument.base import ConnectedInstrument, InstrumentBackend, mark_live
from logic_mcp.instrument.ipc_client import InstrumentIpcClient
from logic_mcp.instrument.protocol import default_socket_path
from logic_mcp.instrument.types import (
    CaptureRequest,
    InstrumentCapabilities,
    InstrumentDevice,
    InstrumentInfo,
)


class IpcConnected(ConnectedInstrument):
    owns_config = False

    def __init__(self, client: InstrumentIpcClient, device: InstrumentDevice):
        self.client = client
        self.device = device
        self.owns_config = bool(client.hello.get("configure"))
        self.transport = "ipc"

    def capabilities(self) -> InstrumentCapabilities:
        methods = self.client.hello.get("methods") or []
        if "capabilities" in methods:
            raw = self.client.call("capabilities")
            channels = [
                Channel(
                    index=int(ch.get("index", i)),
                    name=str(ch.get("name", i)),
                    kind="analog" if ch.get("kind") == "analog" else "digital",
                )
                for i, ch in enumerate(raw.get("channels") or [])
            ]
            return InstrumentCapabilities(
                channels=channels,
                sample_rates_hz=raw.get("sample_rates_hz"),
                min_sample_rate_hz=raw.get("min_sample_rate_hz"),
                max_sample_rate_hz=raw.get("max_sample_rate_hz"),
                supports_trigger=bool(raw.get("supports_trigger", True)),
                supports_duration=bool(raw.get("supports_duration", True)),
                supports_sample_count=bool(raw.get("supports_sample_count", True)),
                analog=bool(raw.get("analog", False)),
                streaming=bool(raw.get("streaming", False)),
                options_schema=raw.get("options_schema") or {},
            )
        return InstrumentCapabilities(channels=[], options_schema=IpcBackend.options_schema)

    def configure(self, request: CaptureRequest) -> dict[str, Any]:
        if not self.owns_config:
            return {"ok": True, "configure": False, "note": "config owned by vendor UI"}
        return self.client.call("configure", request.to_dict())

    def start(self, request: CaptureRequest | None = None) -> dict[str, Any]:
        params = request.to_dict() if request is not None else {}
        return self.client.call("start", params)

    def stop(self) -> dict[str, Any]:
        return self.client.call("stop")

    def wait(self, timeout_s: float = 60.0) -> dict[str, Any]:
        return self.client.call("wait", {"timeout_s": timeout_s}, timeout_s=timeout_s + 5)

    def export_capture(self, path: Path, format: str = "csv") -> Path:
        result = self.client.call("export", {"path": str(path), "format": format})
        exported = Path(str(result.get("path") or path))
        if not exported.is_file():
            raise InstrumentError(f"Vendor export did not create {exported}")
        return exported

    def capture(self, request: CaptureRequest | None, out_dir: Path) -> LogicCapture:
        if request is not None and self.owns_config:
            self.configure(request)
        started = self.start(request)
        timeout = request.timeout_s if request is not None else 60.0
        waited = self.wait(timeout)
        if waited.get("timed_out"):
            raise InstrumentError("Capture wait timed out")
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / "ipc-capture.csv"
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
        cap.metadata["ipc_start"] = str(started.get("state", ""))
        return cap

    def close(self) -> None:
        self.client.close()


class IpcBackend(InstrumentBackend):
    """Connect to any process speaking logic_mcp.instrument.v1."""

    transport = "ipc"
    socket_name = "instrument"
    info = InstrumentInfo(
        id="ipc",
        vendor="logic-mcp",
        title="External instrument hub (logic_mcp.instrument.v1)",
        status="implemented",
        notes=(
            "Vendor process owns USB. Default socket $XDG_RUNTIME_DIR/logic-mcp/instrument.sock. "
            "Override with extra.socket or LOGIC_MCP_INSTRUMENT_SOCK. "
            "hello.configure=false means rates/channels stay in the vendor UI; MCP only start/stop/export."
        ),
    )
    options_schema = {
        "type": "object",
        "properties": {
            "socket": {"type": "string", "description": "Unix socket path"},
        },
        "additionalProperties": True,
    }

    def _path(self, extra: Mapping[str, Any] | None = None) -> Path:
        extra = extra or {}
        if extra.get("socket"):
            return Path(str(extra["socket"])).expanduser()
        return default_socket_path(self.socket_name)

    def available(self) -> bool:
        return self._path().exists()

    def scan(self) -> list[InstrumentDevice]:
        path = self._path()
        if not path.exists():
            return []
        client = InstrumentIpcClient(path)
        try:
            hello = client.connect()
        except (InstrumentUnavailableError, InstrumentError):
            return []
        finally:
            client.close()
        return [
            InstrumentDevice(
                id=f"{self.info.id}:{hello.get('product') or path.name}",
                backend=self.info.id,
                vendor=str(hello.get("vendor") or "unknown"),
                model=str(hello.get("product") or self.info.id),
                serial=hello.get("serial"),
                present=True,
                extra={"socket": str(path), "configure": str(bool(hello.get("configure")))},
            )
        ]

    def connect(
        self,
        device_id: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> ConnectedInstrument:
        path = self._path(extra)
        client = InstrumentIpcClient(path)
        hello = client.connect()
        device = InstrumentDevice(
            id=device_id or f"{self.info.id}:{hello.get('product') or path.name}",
            backend=self.info.id,
            vendor=str(hello.get("vendor") or "unknown"),
            model=str(hello.get("product") or self.info.id),
            serial=hello.get("serial"),
            present=True,
            extra={"socket": str(path)},
        )
        return IpcConnected(client, device)


class DsviewIpcBackend(IpcBackend):
    socket_name = "dsview"
    info = InstrumentInfo(
        id="dsview",
        vendor="DreamSourceLab",
        title="DSView GUI via logic_mcp.instrument.v1",
        status="implemented",
        notes=(
            "Patched DSView listens on $XDG_RUNTIME_DIR/logic-mcp/dsview.sock. "
            "Configure channels/rate/trigger in the GUI; MCP calls start/stop/wait/export. "
            "Do not open DSView and sigrok_cli at the same time."
        ),
    )
