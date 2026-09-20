from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from logic_mcp.bus.registry import get_bus
from logic_mcp.capture.registry import open_capture
from logic_mcp.capture.types import LogicCapture
from logic_mcp.devices.registry import get_driver, load_profile
from logic_mcp.errors import SessionStateError, UnknownJobError, UnimplementedInstrumentError
from logic_mcp.instrument.base import ConnectedInstrument
from logic_mcp.instrument.registry import get_backend, scan_instruments
from logic_mcp.instrument.types import CaptureRequest, InstrumentState, build_request
from logic_mcp.messages import Artifact
from logic_mcp.sinks.framebuffer import FramebufferSink
from logic_mcp.sinks.log import CommandLogSink


def default_out_dir() -> Path:
    override = os.environ.get("LOGIC_MCP_OUT")
    if override:
        return Path(override).expanduser()
    return Path.cwd() / "out"


def _trim_commands(summaries: list[dict], max_commands: int) -> dict:
    return {
        "commands": summaries[:max_commands],
        "commands_truncated": len(summaries) > max_commands,
        "command_count": len(summaries),
    }


@dataclass
class DecodeJob:
    id: str
    protocol: str
    channel_map: dict[str, str | int]
    options: dict[str, Any] = field(default_factory=dict)
    t_min: float | None = None
    t_max: float | None = None
    event_count: int = 0
    event_kinds: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "protocol": self.protocol,
            "channel_map": self.channel_map,
            "options": self.options,
            "t_min": self.t_min,
            "t_max": self.t_max,
            "event_count": self.event_count,
            "by_kind": self.event_kinds,
        }


@dataclass
class InterpretJob:
    id: str
    decode_job_id: str
    decoder_id: str
    profile_id: str | None
    message_count: int = 0
    artifacts: list[Artifact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "decode_job_id": self.decode_job_id,
            "decoder": self.decoder_id,
            "profile": self.profile_id,
            "message_count": self.message_count,
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


@dataclass
class Session:
    capture: LogicCapture | None = None
    capture_id: str | None = None
    decode_jobs: dict[str, DecodeJob] = field(default_factory=dict)
    interpret_jobs: dict[str, InterpretJob] = field(default_factory=dict)
    instrument: ConnectedInstrument | None = None
    instrument_backend_id: str | None = None
    instrument_request: CaptureRequest | None = None
    instrument_state: InstrumentState = "disconnected"
    _decode_seq: int = 0
    _interpret_seq: int = 0
    _latest_decode_id: str | None = None

    def require_capture(self) -> LogicCapture:
        if self.capture is None:
            raise SessionStateError("No capture open. Call capture_open or instrument_capture first.")
        return self.capture

    def require_instrument(self) -> ConnectedInstrument:
        if self.instrument is None:
            raise SessionStateError("No instrument open. Call instrument_open first.")
        return self.instrument

    def _decode_job(self, job_id: str | None = None) -> DecodeJob:
        if not self.decode_jobs:
            raise SessionStateError("No decode job. Call bus_decode first.")
        if job_id is None:
            job_id = self._latest_decode_id
        if job_id is None or job_id not in self.decode_jobs:
            known = ", ".join(self.decode_jobs)
            raise UnknownJobError(f"Unknown decode job {job_id!r}. Known: {known}")
        return self.decode_jobs[job_id]

    def attach_capture(self, cap: LogicCapture, capture_id: str = "cap") -> dict:
        self.capture = cap
        self.capture_id = capture_id
        self.decode_jobs = {}
        self.interpret_jobs = {}
        self._decode_seq = 0
        self._interpret_seq = 0
        self._latest_decode_id = None
        return {
            "ok": True,
            "capture_id": self.capture_id,
            "path": str(cap.path) if cap.path else None,
            "format_id": cap.info.id,
            "vendor": cap.info.vendor,
            "source": cap.source,
            "channels": [
                {"index": ch.index, "name": ch.name, "kind": ch.kind}
                for ch in cap.channels
            ],
            "sample_rate_hz": cap.sample_rate_hz,
            "sample_count": cap.sample_count,
            "metadata": dict(cap.metadata),
        }

    def open(self, path: str, format_id: str | None = None) -> dict:
        return self.attach_capture(open_capture(path, format_id))

    def instrument_scan(self, backend: str | None = None) -> dict:
        devices = scan_instruments(backend)
        return {
            "ok": True,
            "backend": backend,
            "devices": [dev.to_dict() for dev in devices],
        }

    def instrument_open(
        self,
        backend: str,
        device_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict:
        plugin = get_backend(backend)
        if plugin.info.status != "implemented":
            raise UnimplementedInstrumentError(plugin.info.id)
        if self.instrument is not None:
            self.instrument.close()
        self.instrument = plugin.connect(device_id, extra)
        self.instrument_backend_id = plugin.info.id
        self.instrument_request = None
        self.instrument_state = "idle"
        return {
            "ok": True,
            "backend": plugin.info.id,
            "device": self.instrument.device.to_dict(),
            "state": self.instrument_state,
            "capabilities": self.instrument.capabilities().to_dict(),
            "owns_config": self.instrument.owns_config,
            "transport": getattr(plugin, "transport", "inprocess"),
        }

    def instrument_close(self) -> dict:
        if self.instrument is not None:
            self.instrument.close()
        self.instrument = None
        self.instrument_backend_id = None
        self.instrument_request = None
        self.instrument_state = "disconnected"
        return {"ok": True, "state": self.instrument_state}

    def instrument_capabilities(self) -> dict:
        handle = self.require_instrument()
        return {
            "ok": True,
            "backend": self.instrument_backend_id,
            "device": handle.device.to_dict(),
            "capabilities": handle.capabilities().to_dict(),
        }

    def instrument_configure(
        self,
        sample_rate_hz: float,
        *,
        channels: list[str] | None = None,
        duration_s: float | None = None,
        sample_count: int | None = None,
        trigger_channel: str | None = None,
        trigger_edge: str | None = None,
        extra: dict[str, Any] | None = None,
        timeout_s: float = 60.0,
    ) -> dict:
        self.require_instrument()
        self.instrument_request = build_request(
            sample_rate_hz,
            channels=channels,
            duration_s=duration_s,
            sample_count=sample_count,
            trigger_channel=trigger_channel,
            trigger_edge=trigger_edge,
            extra=extra,
            timeout_s=timeout_s,
        )
        self.instrument_state = "configured"
        return {
            "ok": True,
            "state": self.instrument_state,
            "config": self.instrument_request.to_dict(),
        }

    def instrument_capture(
        self,
        sample_rate_hz: float | None = None,
        *,
        channels: list[str] | None = None,
        duration_s: float | None = None,
        sample_count: int | None = None,
        trigger_channel: str | None = None,
        trigger_edge: str | None = None,
        extra: dict[str, Any] | None = None,
        timeout_s: float | None = None,
        out_dir: str | None = None,
    ) -> dict:
        handle = self.require_instrument()
        if sample_rate_hz is not None:
            self.instrument_configure(
                sample_rate_hz,
                channels=channels,
                duration_s=duration_s,
                sample_count=sample_count,
                trigger_channel=trigger_channel,
                trigger_edge=trigger_edge,
                extra=extra,
                timeout_s=60.0 if timeout_s is None else timeout_s,
            )
        elif extra and self.instrument_request is not None:
            self.instrument_request.extra.update(extra)
        if self.instrument_request is None and handle.owns_config:
            raise SessionStateError(
                "No capture config. Call instrument_configure, pass sample_rate_hz, "
                "or use a GUI-owned backend (dsview/ipc) that already has rates set."
            )
        dest = Path(out_dir).expanduser() if out_dir else default_out_dir() / "live"
        self.instrument_state = "capturing"
        try:
            cap = handle.capture(self.instrument_request, dest)
            opened = self.attach_capture(cap)
            self.instrument_state = "captured"
            return {
                **opened,
                "state": self.instrument_state,
                "backend": self.instrument_backend_id,
                "device": handle.device.to_dict(),
                "config": self.instrument_request.to_dict() if self.instrument_request else None,
                "owns_config": handle.owns_config,
            }
        except Exception:
            self.instrument_state = "error"
            raise

    def instrument_start(self) -> dict:
        handle = self.require_instrument()
        self.instrument_state = "capturing"
        result = handle.start(self.instrument_request)
        state = str(result.get("state") or "capturing")
        self.instrument_state = "captured" if state == "complete" else "capturing"
        return {
            "ok": True,
            "state": self.instrument_state,
            "hub_state": state,
            "owns_config": handle.owns_config,
        }

    def instrument_stop(self) -> dict:
        handle = self.require_instrument()
        result = handle.stop()
        self.instrument_state = "idle"
        return {"ok": True, "state": self.instrument_state, "hub_state": result.get("state")}

    def instrument_wait(self, timeout_s: float = 60.0) -> dict:
        handle = self.require_instrument()
        result = handle.wait(timeout_s)
        if result.get("timed_out"):
            self.instrument_state = "capturing"
        elif result.get("state") in ("complete", "idle"):
            self.instrument_state = "captured" if result.get("state") == "complete" else "idle"
        return {"ok": True, "state": self.instrument_state, **result}

    def instrument_export(self, path: str | None = None, format: str = "csv", out_dir: str | None = None) -> dict:
        handle = self.require_instrument()
        dest_dir = Path(out_dir).expanduser() if out_dir else default_out_dir() / "live"
        dest = Path(path).expanduser() if path else dest_dir / f"export.{format}"
        exported = handle.export_capture(dest, format)
        from logic_mcp.capture.registry import open_capture

        cap = open_capture(exported)
        cap.source = "live"
        cap.metadata["backend"] = self.instrument_backend_id or ""
        opened = self.attach_capture(cap)
        self.instrument_state = "captured"
        return {**opened, "state": self.instrument_state}

    def iter_link(self, job: DecodeJob):
        cap = self.require_capture()
        decoder = get_bus(job.protocol)
        return decoder.decode(
            cap,
            job.channel_map,
            options=job.options,
            t_min=job.t_min,
            t_max=job.t_max,
        )

    def decode(
        self,
        protocol: str,
        channel_map: dict[str, str | int],
        *,
        options: dict[str, Any] | None = None,
        t_min: float | None = None,
        t_max: float | None = None,
        job_id: str | None = None,
    ) -> dict:
        cap = self.require_capture()
        decoder = get_bus(protocol)
        self._decode_seq += 1
        job_id = job_id or f"dec_{self._decode_seq}"
        opts = dict(options or {})
        kinds: dict[str, int] = {}
        count = 0
        for event in decoder.decode(
            cap, channel_map, options=opts, t_min=t_min, t_max=t_max
        ):
            count += 1
            label = getattr(event, "strobe", None) or type(event).__name__
            kinds[str(label)] = kinds.get(str(label), 0) + 1
        job = DecodeJob(
            id=job_id,
            protocol=protocol,
            channel_map=dict(channel_map),
            options=opts,
            t_min=t_min,
            t_max=t_max,
            event_count=count,
            event_kinds=kinds,
        )
        self.decode_jobs[job_id] = job
        self._latest_decode_id = job_id
        return {"ok": True, "roles": decoder.roles_dict(), **job.to_dict()}

    def interpret(
        self,
        decoder_id: str = "mipi_dcs",
        *,
        decode_job_id: str | None = None,
        profile_id: str | None = None,
        sinks: list[str] | None = None,
        width: int | None = None,
        height: int | None = None,
        col_offset: int | None = None,
        row_offset: int | None = None,
        save_intermediate_frames: bool = True,
        max_intermediate_frames: int = 32,
        max_commands: int = 200,
        out_dir: str | None = None,
        job_id: str | None = None,
    ) -> dict:
        decode_job = self._decode_job(decode_job_id)
        upper = get_driver(decoder_id)
        context: dict[str, Any] = {}
        profile = None
        if profile_id:
            profile = load_profile(profile_id).override(
                width=width,
                height=height,
                col_offset=col_offset,
                row_offset=row_offset,
            )
            context["commands"] = profile.commands
            if not decoder_id:
                decoder_id = profile.driver
        messages = list(upper.interpret(self.iter_link(decode_job), context=context))
        sink_ids = sinks or ["command_log"]
        self._interpret_seq += 1
        job_id = job_id or f"int_{self._interpret_seq}"
        dest = Path(out_dir).expanduser() if out_dir else default_out_dir()
        cap = self.require_capture()
        stem = cap.path.stem if cap.path else "capture"
        artifacts: list[Artifact] = []
        command_rows: list[dict] = []
        result_extra: dict[str, Any] = {}

        if "command_log" in sink_ids:
            path = dest / f"{stem}.{decode_job.protocol}.{decoder_id}.{job_id}.commands.jsonl"
            command_rows, art = CommandLogSink().write(messages, path, job_id)
            artifacts.append(art)
        if "framebuffer" in sink_ids:
            if profile is None:
                raise SessionStateError("framebuffer sink requires profile_id")
            recon, pngs = FramebufferSink().run(
                messages,
                profile,
                dest,
                f"{stem}.{job_id}",
                job_id,
                save_intermediate_frames=save_intermediate_frames,
                max_intermediate_frames=max_intermediate_frames,
            )
            artifacts.extend(pngs)
            result_extra = {
                "width": recon.width,
                "height": recon.height,
                "pixels_written": recon.pixels_written,
                "pixel_overflow": recon.pixel_overflow,
                "ramwr_count": recon.ramwr_count,
                "colmod": f"0x{recon.colmod:02X}",
                "madctl": f"0x{recon.madctl:02X}",
                "window": {
                    "xs": recon.window[0],
                    "xe": recon.window[1],
                    "ys": recon.window[2],
                    "ye": recon.window[3],
                },
                "frames_capped": save_intermediate_frames
                and len(recon.frames) > max_intermediate_frames,
                "png": {
                    "final": next(
                        (a.path for a in pngs if a.extra.get("role") == "final"), None
                    ),
                    "intermediate": [
                        a.path for a in pngs if a.extra.get("role") == "intermediate"
                    ],
                },
            }

        job = InterpretJob(
            id=job_id,
            decode_job_id=decode_job.id,
            decoder_id=decoder_id,
            profile_id=profile_id,
            message_count=len(messages),
            artifacts=artifacts,
        )
        self.interpret_jobs[job_id] = job
        body = job.to_dict()
        if command_rows:
            body.update(_trim_commands(command_rows, max_commands))
            body["commands_path"] = next(
                (a.path for a in artifacts if a.kind == "jsonl"), None
            )
        body.update(result_extra)
        return {"ok": True, **body}

    def analyze(self, profile_id: str = "st7789", **kwargs) -> dict:
        kwargs.setdefault("sinks", ["command_log"])
        kwargs.setdefault("decoder_id", "mipi_dcs")
        return self.interpret(profile_id=profile_id, **kwargs)

    def reconstruct(self, profile_id: str = "st7789", **kwargs) -> dict:
        kwargs.setdefault("sinks", ["command_log", "framebuffer"])
        kwargs.setdefault("decoder_id", "mipi_dcs")
        return self.interpret(profile_id=profile_id, **kwargs)

    def status(self) -> dict:
        cap = self.capture
        inst = self.instrument
        return {
            "ok": True,
            "capture_id": self.capture_id,
            "has_capture": cap is not None,
            "path": str(cap.path) if cap and cap.path else None,
            "format_id": cap.info.id if cap else None,
            "vendor": cap.info.vendor if cap else None,
            "source": cap.source if cap else None,
            "channels": cap.channel_names if cap else None,
            "instrument": {
                "state": self.instrument_state,
                "backend": self.instrument_backend_id,
                "device": inst.device.to_dict() if inst else None,
                "config": self.instrument_request.to_dict() if self.instrument_request else None,
                "owns_config": inst.owns_config if inst else None,
                "transport": getattr(inst, "transport", None) if inst else None,
            },
            "latest_decode_job_id": self._latest_decode_id,
            "decode_jobs": [job.to_dict() for job in self.decode_jobs.values()],
            "interpret_jobs": [job.to_dict() for job in self.interpret_jobs.values()],
        }


SESSION = Session()
