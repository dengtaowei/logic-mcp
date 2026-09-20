from pathlib import Path

from logic_mcp.capture.types import CaptureFormat, FormatInfo, LogicCapture
from logic_mcp.errors import UnimplementedCaptureError


class SaleaeCsvFormat(CaptureFormat):
    info = FormatInfo(
        id="saleae_csv",
        vendor="Saleae",
        title="Saleae Logic CSV export",
        status="unimplemented",
        extensions=(".csv",),
        notes="Placeholder for Saleae Logic 1/2 CSV. Implement as Edge stream into LogicCapture.",
    )

    def sniff(self, path: Path) -> float:
        if path.suffix.lower() != ".csv":
            return 0.0
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                head = "".join(fh.readline() for _ in range(6)).lower()
        except OSError:
            return 0.0
        if "saleae" in head or "logic software" in head:
            return 0.9
        return 0.0

    def open(self, path: Path) -> LogicCapture:
        raise UnimplementedCaptureError(self.info.id, self.info.vendor)
