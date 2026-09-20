from __future__ import annotations

from importlib.metadata import entry_points
from pathlib import Path

from logic_mcp.capture.types import CaptureFormat, FormatInfo, LogicCapture
from logic_mcp.errors import CaptureOpenError, UnimplementedCaptureError

_FORMATS: dict[str, CaptureFormat] | None = None
_LOAD_ERRORS: list[str] = []


def _builtin_formats() -> list[CaptureFormat]:
    from logic_mcp.capture.dsview_csv import DsviewCsvFormat
    from logic_mcp.capture.saleae_csv import SaleaeCsvFormat
    from logic_mcp.capture.vcd import VcdFormat

    return [DsviewCsvFormat(), SaleaeCsvFormat(), VcdFormat()]


def load_formats() -> dict[str, CaptureFormat]:
    global _FORMATS
    if _FORMATS is not None:
        return _FORMATS
    found: dict[str, CaptureFormat] = {}
    for fmt in _builtin_formats():
        found[fmt.info.id] = fmt
    try:
        eps = entry_points(group="logic_mcp.captures")
    except Exception as exc:
        _LOAD_ERRORS.append(f"logic_mcp.captures: {exc}")
        eps = []
    for ep in eps:
        try:
            cls = ep.load()
            inst = cls() if isinstance(cls, type) else cls
        except Exception as exc:
            _LOAD_ERRORS.append(f"{ep.name}: {exc}")
            continue
        if not isinstance(inst, CaptureFormat):
            _LOAD_ERRORS.append(f"{ep.name}: not a CaptureFormat")
            continue
        found[inst.info.id] = inst
    _FORMATS = found
    return found


def plugin_load_errors() -> list[str]:
    load_formats()
    return list(_LOAD_ERRORS)


def list_formats() -> list[FormatInfo]:
    return [fmt.info for fmt in load_formats().values()]


def get_format(format_id: str) -> CaptureFormat:
    formats = load_formats()
    if format_id not in formats:
        known = ", ".join(sorted(formats)) or "(none)"
        raise CaptureOpenError(f"Unknown capture format '{format_id}'. Known: {known}")
    return formats[format_id]


def sniff_format(path: Path) -> CaptureFormat:
    ranked: list[tuple[float, CaptureFormat]] = []
    for fmt in load_formats().values():
        try:
            score = fmt.sniff(path)
        except Exception:
            continue
        if score > 0:
            ranked.append((score, fmt))
    if not ranked:
        raise CaptureOpenError(
            f"No capture adapter recognized {path}. "
            "Pass format_id explicitly (dsview_csv, saleae_csv, vcd, ...)."
        )
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def open_capture(path: str | Path, format_id: str | None = None) -> LogicCapture:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise CaptureOpenError(f"Capture file not found: {file_path}")
    fmt = get_format(format_id) if format_id else sniff_format(file_path)
    if fmt.info.status != "implemented":
        raise UnimplementedCaptureError(fmt.info.id, fmt.info.vendor)
    return fmt.open(file_path)
