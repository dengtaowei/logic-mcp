from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from logic_mcp.errors import InstrumentError
from logic_mcp.instrument.base import ConnectedInstrument
from logic_mcp.instrument.protocol import OPTIONAL_METHODS, REQUIRED_METHODS
from logic_mcp.instrument.types import CaptureRequest


def connected_dispatcher(connected: ConnectedInstrument, *, configure: bool) -> Any:
    """Map protocol methods onto a ConnectedInstrument (in-process vendor)."""

    allowed = set(REQUIRED_METHODS) | {"status"}
    if configure:
        allowed.update(OPTIONAL_METHODS)
    else:
        allowed.add("capabilities")

    def dispatch(method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method not in allowed:
            raise InstrumentError(f"Method {method!r} is not advertised by this hub")
        if method == "status":
            return {
                "state": getattr(connected, "hub_state", "idle"),
                "configure": configure,
            }
        if method == "capabilities":
            return connected.capabilities().to_dict()
        if method == "configure":
            request = CaptureRequest(
                sample_rate_hz=float(params["sample_rate_hz"]),
                channels=tuple(params["channels"]) if params.get("channels") else None,
                duration_s=params.get("duration_s"),
                sample_count=params.get("sample_count"),
                extra=dict(params.get("extra") or {}),
                timeout_s=float(params.get("timeout_s") or 60),
            )
            return connected.configure(request)
        if method == "start":
            request = None
            if params.get("sample_rate_hz"):
                request = CaptureRequest(
                    sample_rate_hz=float(params["sample_rate_hz"]),
                    channels=tuple(params["channels"]) if params.get("channels") else None,
                    duration_s=params.get("duration_s"),
                    sample_count=params.get("sample_count"),
                    extra=dict(params.get("extra") or {}),
                    timeout_s=float(params.get("timeout_s") or 60),
                )
            return connected.start(request)
        if method == "stop":
            return connected.stop()
        if method == "wait":
            return connected.wait(float(params.get("timeout_s") or 60))
        if method == "export":
            path = Path(str(params.get("path") or "capture.csv"))
            fmt = str(params.get("format") or "csv")
            exported = connected.export_capture(path, fmt)
            return {"path": str(exported), "format": fmt}
        raise InstrumentError(f"Unknown method {method!r}")

    return dispatch
