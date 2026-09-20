from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from logic_mcp.bus.registry import get_bus, list_buses, plugin_load_errors as bus_plugin_errors
from logic_mcp.capture.registry import list_formats, plugin_load_errors as capture_plugin_errors
from logic_mcp.devices.registry import list_drivers, list_profiles, plugin_load_errors as device_plugin_errors
from logic_mcp.errors import LogicMcpError
from logic_mcp.instrument.registry import (
    list_instruments,
    plugin_load_errors as instrument_plugin_errors,
)
from logic_mcp.session import SESSION

mcp = FastMCP(
    name="logic-mcp",
    instructions=(
        "Instrument MCP. Two vendor paths: in-process plugins (mock, sigrok_cli) or "
        "IPC logic_mcp.instrument.v1 (backend=ipc|dsview). "
        "GUI-owned config (DSView): instrument_open → start → wait → export/capture, then bus_decode. "
        "Full MCP config: configure → capture. Offline: capture_open a CSV. "
        "display_* is sugar for ST7789 / MIPI DCS."
    ),
)


def _ok_or_error(fn, **kwargs) -> dict[str, Any]:
    try:
        return fn(**kwargs)
    except LogicMcpError as exc:
        return exc.to_dict()
    except Exception as exc:
        return {"ok": False, "error": "internal", "message": str(exc)}


@mcp.tool
def protocol_list() -> dict[str, Any]:
    """List instrument backends, capture adapters, bus decoders, upper decoders, profiles, sinks."""
    return {
        "ok": True,
        "instruments": list_instruments(),
        "captures": [
            {
                "id": info.id,
                "vendor": info.vendor,
                "title": info.title,
                "status": info.status,
                "extensions": list(info.extensions),
                "notes": info.notes,
            }
            for info in list_formats()
        ],
        "buses": list_buses(),
        "decoders": list_drivers(),
        "sinks": [
            {"id": "command_log", "schema": "logic_mcp.commands.v1"},
            {"id": "framebuffer", "schema": "logic_mcp.framebuffer.v1"},
        ],
        "profiles": list_profiles(),
        "plugin_errors": (
            capture_plugin_errors()
            + bus_plugin_errors()
            + device_plugin_errors()
            + instrument_plugin_errors()
        ),
    }


@mcp.tool
def capture_open(path: str, format_id: str | None = None) -> dict[str, Any]:
    """Load a capture/trace file. Returns capture_id and channels. Pin maps belong on bus_decode."""
    return _ok_or_error(SESSION.open, path=path, format_id=format_id)


@mcp.tool
def instrument_list() -> dict[str, Any]:
    """List live-capture backends (id, vendor, status, available, options_schema)."""
    return {"ok": True, "instruments": list_instruments(), "plugin_errors": instrument_plugin_errors()}


@mcp.tool
def instrument_scan(backend: str | None = None) -> dict[str, Any]:
    """Discover analyzers. Omit backend to scan every implemented backend that is available."""
    return _ok_or_error(SESSION.instrument_scan, backend=backend)


@mcp.tool
def instrument_open(
    backend: str,
    device_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Open a live backend (mock, dslogic, sigrok_cli, …). Returns device + capabilities."""
    return _ok_or_error(SESSION.instrument_open, backend=backend, device_id=device_id, extra=extra)


@mcp.tool
def instrument_close() -> dict[str, Any]:
    """Release the open instrument. Does not delete the last LogicCapture."""
    return _ok_or_error(SESSION.instrument_close)


@mcp.tool
def instrument_capabilities() -> dict[str, Any]:
    """Sample rates, channel names, trigger support for the open instrument."""
    return _ok_or_error(SESSION.instrument_capabilities)


@mcp.tool
def instrument_configure(
    sample_rate_hz: float,
    channels: list[str] | None = None,
    duration_s: float | None = None,
    sample_count: int | None = None,
    trigger_channel: str | None = None,
    trigger_edge: str | None = None,
    extra: dict[str, Any] | None = None,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """Set live capture params (rate, channels, duration or samples, trigger). Does not start yet."""
    return _ok_or_error(
        SESSION.instrument_configure,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        duration_s=duration_s,
        sample_count=sample_count,
        trigger_channel=trigger_channel,
        trigger_edge=trigger_edge,
        extra=extra,
        timeout_s=timeout_s,
    )


@mcp.tool
def instrument_capture(
    sample_rate_hz: float | None = None,
    channels: list[str] | None = None,
    duration_s: float | None = None,
    sample_count: int | None = None,
    trigger_channel: str | None = None,
    trigger_edge: str | None = None,
    extra: dict[str, Any] | None = None,
    timeout_s: float | None = None,
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Run a blocking capture into the session. GUI-owned backends (dsview) do not need sample_rate_hz."""
    return _ok_or_error(
        SESSION.instrument_capture,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        duration_s=duration_s,
        sample_count=sample_count,
        trigger_channel=trigger_channel,
        trigger_edge=trigger_edge,
        extra=extra,
        timeout_s=timeout_s,
        out_dir=out_dir,
    )


@mcp.tool
def instrument_start() -> dict[str, Any]:
    """Start capture on the open instrument. DSView uses whatever the GUI already configured."""
    return _ok_or_error(SESSION.instrument_start)


@mcp.tool
def instrument_stop() -> dict[str, Any]:
    """Stop an in-progress capture."""
    return _ok_or_error(SESSION.instrument_stop)


@mcp.tool
def instrument_wait(timeout_s: float = 60.0) -> dict[str, Any]:
    """Block until capture completes or timeout_s."""
    return _ok_or_error(SESSION.instrument_wait, timeout_s=timeout_s)


@mcp.tool
def instrument_export(
    path: str | None = None,
    format: str = "csv",
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Ask the vendor hub to export the last capture and load it into the session."""
    return _ok_or_error(SESSION.instrument_export, path=path, format=format, out_dir=out_dir)


@mcp.tool
def bus_decode(
    protocol: str,
    channel_map: dict[str, str],
    options: dict[str, Any] | None = None,
    t_min: float | None = None,
    t_max: float | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Create a DecodeJob on the open capture. Same waveform can have several jobs (e.g. SPI + I2C)."""
    return _ok_or_error(
        SESSION.decode,
        protocol=protocol,
        channel_map=channel_map,
        options=options,
        t_min=t_min,
        t_max=t_max,
        job_id=job_id,
    )


@mcp.tool
def protocol_roles(protocol: str) -> dict[str, Any]:
    """Channel roles and options_schema for a bus decoder."""
    try:
        decoder = get_bus(protocol)
    except LogicMcpError as exc:
        return exc.to_dict()
    return {
        "ok": True,
        "id": decoder.id,
        "status": decoder.status,
        "roles": decoder.roles_dict(),
        "options_schema": decoder.options_schema,
        "notes": decoder.notes,
    }


@mcp.tool
def interpret(
    decoder: str = "mipi_dcs",
    decode_job_id: str | None = None,
    profile: str | None = None,
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
) -> dict[str, Any]:
    """Run an upper decoder on a DecodeJob. Default sink is command_log. Add framebuffer for PNG."""
    return _ok_or_error(
        SESSION.interpret,
        decoder_id=decoder,
        decode_job_id=decode_job_id,
        profile_id=profile,
        sinks=sinks,
        width=width,
        height=height,
        col_offset=col_offset,
        row_offset=row_offset,
        save_intermediate_frames=save_intermediate_frames,
        max_intermediate_frames=max_intermediate_frames,
        max_commands=max_commands,
        out_dir=out_dir,
        job_id=job_id,
    )


@mcp.tool
def display_analyze(
    profile: str = "st7789",
    decode_job_id: str | None = None,
    width: int | None = None,
    height: int | None = None,
    col_offset: int | None = None,
    row_offset: int | None = None,
    max_commands: int = 200,
) -> dict[str, Any]:
    """Sugar: interpret MIPI DCS + command_log sink for a display profile."""
    return _ok_or_error(
        SESSION.analyze,
        profile_id=profile,
        decode_job_id=decode_job_id,
        width=width,
        height=height,
        col_offset=col_offset,
        row_offset=row_offset,
        max_commands=max_commands,
    )


@mcp.tool
def display_reconstruct(
    profile: str = "st7789",
    decode_job_id: str | None = None,
    width: int | None = None,
    height: int | None = None,
    col_offset: int | None = None,
    row_offset: int | None = None,
    save_intermediate_frames: bool = True,
    max_intermediate_frames: int = 32,
    max_commands: int = 200,
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Sugar: interpret MIPI DCS + command_log + framebuffer sinks."""
    return _ok_or_error(
        SESSION.reconstruct,
        profile_id=profile,
        decode_job_id=decode_job_id,
        width=width,
        height=height,
        col_offset=col_offset,
        row_offset=row_offset,
        save_intermediate_frames=save_intermediate_frames,
        max_intermediate_frames=max_intermediate_frames,
        max_commands=max_commands,
        out_dir=out_dir,
    )


@mcp.tool
def session_status() -> dict[str, Any]:
    """Open capture plus all decode/interpret jobs and artifacts."""
    return SESSION.status()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
