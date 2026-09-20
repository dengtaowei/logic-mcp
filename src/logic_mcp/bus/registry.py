from __future__ import annotations

from importlib.metadata import entry_points

from logic_mcp.bus.base import BusDecoder
from logic_mcp.errors import UnknownProtocolError

_DECODERS: dict[str, BusDecoder] | None = None
_LOAD_ERRORS: list[str] = []


def _builtin() -> list[BusDecoder]:
    from logic_mcp.bus.i2c import I2cDecoder
    from logic_mcp.bus.i8080 import I8080Decoder
    from logic_mcp.bus.spi import SpiDecoder
    from logic_mcp.bus.uart import UartDecoder

    return [I8080Decoder(), SpiDecoder(), I2cDecoder(), UartDecoder()]


def load_buses() -> dict[str, BusDecoder]:
    global _DECODERS
    if _DECODERS is not None:
        return _DECODERS
    found: dict[str, BusDecoder] = {}
    for dec in _builtin():
        found[dec.id] = dec
    try:
        eps = entry_points(group="logic_mcp.buses")
    except Exception as exc:
        _LOAD_ERRORS.append(f"logic_mcp.buses: {exc}")
        eps = []
    for ep in eps:
        try:
            cls = ep.load()
            inst = cls() if isinstance(cls, type) else cls
        except Exception as exc:
            _LOAD_ERRORS.append(f"{ep.name}: {exc}")
            continue
        if isinstance(inst, BusDecoder):
            found[inst.id] = inst
        else:
            _LOAD_ERRORS.append(f"{ep.name}: not a BusDecoder")
    _DECODERS = found
    return found


def plugin_load_errors() -> list[str]:
    load_buses()
    return list(_LOAD_ERRORS)


def list_buses() -> list[dict]:
    return [
        {
            "id": decoder.id,
            "title": decoder.title,
            "status": decoder.status,
            "notes": decoder.notes,
            "roles": decoder.roles_dict(),
            "options_schema": decoder.options_schema,
        }
        for decoder in load_buses().values()
    ]


def get_bus(protocol: str) -> BusDecoder:
    buses = load_buses()
    if protocol not in buses:
        known = ", ".join(sorted(buses))
        raise UnknownProtocolError(f"Unknown bus protocol '{protocol}'. Known: {known}")
    return buses[protocol]
