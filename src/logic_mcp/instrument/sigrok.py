from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from logic_mcp.capture.registry import open_capture
from logic_mcp.capture.types import Channel, LogicCapture
from logic_mcp.errors import InstrumentError, InstrumentUnavailableError
from logic_mcp.instrument.base import ConnectedInstrument, InstrumentBackend, mark_live
from logic_mcp.instrument.types import (
    CaptureRequest,
    InstrumentCapabilities,
    InstrumentDevice,
    InstrumentInfo,
    find_hz_values,
)


def find_sigrok_cli() -> Path | None:
    override = os.environ.get("SIGROK_CLI")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    found = shutil.which("sigrok-cli")
    return Path(found) if found else None


def parse_sigrok_scan(text: str, backend_id: str) -> list[InstrumentDevice]:
    devices: list[InstrumentDevice] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or " - " not in line:
            continue
        lower = line.lower()
        if lower.startswith("the following") or lower.startswith("no devices"):
            continue
        ident, desc = line.split(" - ", 1)
        ident = ident.strip()
        desc = desc.strip()
        if not ident or " " in ident:
            continue
        driver = ident.split(":", 1)[0]
        devices.append(
            InstrumentDevice(
                id=ident,
                backend=backend_id,
                vendor=driver,
                model=desc,
                extra={"driver": driver, "sigrok_id": ident},
            )
        )
    return devices


def parse_sigrok_show(text: str, options_schema: dict[str, Any]) -> InstrumentCapabilities:
    rates = find_hz_values(text)
    names: list[str] = []
    logic = re.search(r"Logic channels:\s*(.+)", text, re.I)
    if logic:
        names = [tok for tok in re.split(r"[,\s]+", logic.group(1).strip()) if tok]
    if not names:
        for match in re.finditer(r"Channel\s+(\d+)\s*:\s*(\S+)", text, re.I):
            names.append(match.group(2))
    if not names:
        grouped = re.search(r"channels?\s+(\d+)\s*[-–]\s*(\d+)", text, re.I)
        if grouped:
            start, end = int(grouped.group(1)), int(grouped.group(2))
            names = [str(i) for i in range(start, end + 1)]
    analog = bool(re.search(r"Analog channels:\s*(?!none\b)\S", text, re.I))
    channels = [Channel(index=i, name=name) for i, name in enumerate(names)]
    return InstrumentCapabilities(
        channels=channels,
        sample_rates_hz=rates or None,
        min_sample_rate_hz=min(rates) if rates else None,
        max_sample_rate_hz=max(rates) if rates else None,
        supports_trigger=True,
        supports_duration=True,
        supports_sample_count=True,
        analog=analog,
        streaming=False,
        options_schema=options_schema,
    )


def _run_sigrok(args: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
    binary = find_sigrok_cli()
    if binary is None:
        raise InstrumentUnavailableError(
            "sigrok-cli not found. Install sigrok-cli (with the DSLogic driver) "
            "or set SIGROK_CLI to the binary."
        )
    try:
        proc = subprocess.run(
            [str(binary), *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise InstrumentError(f"sigrok-cli timed out after {timeout_s:g}s") from exc
    except OSError as exc:
        raise InstrumentUnavailableError(f"Failed to exec sigrok-cli: {exc}") from exc
    return proc


def _require_ok(proc: subprocess.CompletedProcess[str], what: str) -> str:
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        hint = ""
        low = err.lower()
        if "resource busy" in low or "access denied" in low or "claim" in low:
            hint = " Close DSView/PulseView; USB is exclusive."
        raise InstrumentError(f"{what} failed: {err}.{hint}")
    return proc.stdout or ""


class SigrokConnected(ConnectedInstrument):
    def __init__(self, backend: "SigrokCliBackend", device: InstrumentDevice, extra: Mapping[str, Any] | None):
        self.backend = backend
        self.device = device
        self.connect_extra = dict(extra or {})
        self._caps: InstrumentCapabilities | None = None

    def _driver(self) -> str:
        extra = self.connect_extra
        if extra.get("driver"):
            driver = str(extra["driver"])
            conn = extra.get("conn")
            return f"{driver}:conn={conn}" if conn else driver
        return self.device.id

    def capabilities(self) -> InstrumentCapabilities:
        if self._caps is None:
            proc = _run_sigrok(["-d", self._driver(), "--show"], timeout_s=20)
            text = _require_ok(proc, "sigrok-cli --show")
            self._caps = parse_sigrok_show(text, self.backend.options_schema)
        return self._caps

    def capture(self, request: CaptureRequest, out_dir: Path) -> LogicCapture:
        extra = {**self.connect_extra, **request.extra}
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / "sigrok-capture.csv"
        args = ["-d", self._driver(), "--config", f"samplerate={int(request.sample_rate_hz)}"]
        for key, value in (extra.get("config") or {}).items():
            args.extend(["--config", f"{key}={value}"])
        if request.channels:
            args.extend(["--channels", ",".join(request.channels)])
        if request.trigger:
            args.extend(["--triggers", request.trigger.sigrok_token()])
        if request.sample_count is not None:
            args.extend(["--samples", str(int(request.sample_count))])
        elif request.duration_s is not None:
            ms = max(1, int(round(request.duration_s * 1000)))
            args.extend(["--time", str(ms)])
        args.extend(["-O", "csv", "-o", str(dest)])
        proc = _run_sigrok(args, timeout_s=request.timeout_s)
        _require_ok(proc, "sigrok-cli capture")
        if not dest.is_file() or dest.stat().st_size == 0:
            raise InstrumentError(f"sigrok-cli produced no CSV at {dest}")
        return mark_live(
            open_capture(dest),
            backend=self.device.backend,
            device_id=self.device.id,
            request=request,
        )


class SigrokCliBackend(InstrumentBackend):
    info = InstrumentInfo(
        id="sigrok_cli",
        vendor="sigrok",
        title="sigrok-cli (DSLogic, FX2, Saleae clones, demo, …)",
        status="implemented",
        notes=(
            "Portable live-capture backend. Device id is the sigrok driver string "
            "from instrument_scan, e.g. dreamsourcelab-dslogic:conn=1.4 or demo. "
            "Does not remote-control the DSView GUI."
        ),
    )
    options_schema = {
        "type": "object",
        "properties": {
            "driver": {"type": "string", "description": "Override sigrok driver name"},
            "conn": {"type": "string", "description": "USB conn appended as driver:conn="},
            "config": {
                "type": "object",
                "additionalProperties": True,
                "description": "Extra sigrok --config key=value pairs",
            },
        },
        "additionalProperties": True,
    }

    def available(self) -> bool:
        return find_sigrok_cli() is not None

    def scan(self) -> list[InstrumentDevice]:
        proc = _run_sigrok(["--scan"], timeout_s=20)
        text = _require_ok(proc, "sigrok-cli --scan")
        return parse_sigrok_scan(text, self.info.id)

    def connect(
        self,
        device_id: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> ConnectedInstrument:
        if not self.available():
            raise InstrumentUnavailableError(
                "sigrok-cli not found. Install it or set SIGROK_CLI."
            )
        extra = dict(extra or {})
        if device_id is None:
            found = self.scan()
            if not found:
                raise InstrumentUnavailableError(
                    "sigrok-cli --scan found no devices. Plug in an analyzer or use backend='mock'."
                )
            device_id = found[0].id
            device = found[0]
        else:
            device = InstrumentDevice(
                id=device_id,
                backend=self.info.id,
                vendor=device_id.split(":", 1)[0],
                model=device_id,
                extra={"sigrok_id": device_id},
            )
        return SigrokConnected(self, device, extra)
