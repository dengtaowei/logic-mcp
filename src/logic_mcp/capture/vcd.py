from pathlib import Path

from logic_mcp.capture.types import CaptureFormat, FormatInfo, LogicCapture
from logic_mcp.errors import UnimplementedCaptureError


class VcdFormat(CaptureFormat):
    info = FormatInfo(
        id="vcd",
        vendor="generic",
        title="Value Change Dump (PulseView, DSView, GTKWave, ...)",
        status="unimplemented",
        extensions=(".vcd",),
        notes="Shared interchange. Implement as Edge stream; many vendors export VCD.",
    )

    def sniff(self, path: Path) -> float:
        if path.suffix.lower() == ".vcd":
            return 0.8
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(256)
        except OSError:
            return 0.0
        if "$timescale" in head or "$var" in head:
            return 0.85
        return 0.0

    def open(self, path: Path) -> LogicCapture:
        raise UnimplementedCaptureError(self.info.id, self.info.vendor)
