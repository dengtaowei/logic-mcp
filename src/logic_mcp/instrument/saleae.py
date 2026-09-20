from logic_mcp.instrument.base import UnimplementedInstrument
from logic_mcp.instrument.types import InstrumentInfo


class SaleaeLiveBackend(UnimplementedInstrument):
    info = InstrumentInfo(
        id="saleae_live",
        vendor="Saleae",
        title="Saleae Logic 2 Automation API",
        status="unimplemented",
        notes=(
            "Placeholder for saleae.automation (Logic 2). Same CaptureRequest / LogicCapture "
            "contract as mock and sigrok_cli. Do not implement as a DSView-shaped API."
        ),
    )
    options_schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "default": "127.0.0.1"},
            "port": {"type": "integer", "default": 10430},
        },
        "additionalProperties": True,
    }
