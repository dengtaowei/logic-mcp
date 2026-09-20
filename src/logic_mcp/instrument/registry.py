from __future__ import annotations

from importlib.metadata import entry_points

from logic_mcp.errors import (
    InstrumentUnavailableError,
    UnimplementedInstrumentError,
    UnknownInstrumentError,
)
from logic_mcp.instrument.base import InstrumentBackend
from logic_mcp.instrument.types import InstrumentDevice

_BACKENDS: dict[str, InstrumentBackend] | None = None
_LOAD_ERRORS: list[str] = []


def _builtin() -> list[InstrumentBackend]:
    from logic_mcp.instrument.dslogic import DslogicBackend
    from logic_mcp.instrument.ipc import DsviewIpcBackend, IpcBackend
    from logic_mcp.instrument.mock import MockBackend
    from logic_mcp.instrument.saleae import SaleaeLiveBackend
    from logic_mcp.instrument.sigrok import SigrokCliBackend

    return [
        MockBackend(),
        IpcBackend(),
        DsviewIpcBackend(),
        SigrokCliBackend(),
        DslogicBackend(),
        SaleaeLiveBackend(),
    ]


def load_backends() -> dict[str, InstrumentBackend]:
    global _BACKENDS
    if _BACKENDS is not None:
        return _BACKENDS
    found: dict[str, InstrumentBackend] = {}
    for backend in _builtin():
        found[backend.info.id] = backend
    try:
        eps = entry_points(group="logic_mcp.instruments")
    except Exception as exc:
        _LOAD_ERRORS.append(f"logic_mcp.instruments: {exc}")
        eps = []
    for ep in eps:
        try:
            cls = ep.load()
            inst = cls() if isinstance(cls, type) else cls
        except Exception as exc:
            _LOAD_ERRORS.append(f"{ep.name}: {exc}")
            continue
        if isinstance(inst, InstrumentBackend):
            found[inst.info.id] = inst
        else:
            _LOAD_ERRORS.append(f"{ep.name}: not an InstrumentBackend")
    _BACKENDS = found
    return found


def plugin_load_errors() -> list[str]:
    load_backends()
    return list(_LOAD_ERRORS)


def list_instruments() -> list[dict]:
    return [backend.to_summary() for backend in load_backends().values()]


def get_backend(backend_id: str) -> InstrumentBackend:
    backends = load_backends()
    if backend_id not in backends:
        known = ", ".join(sorted(backends)) or "(none)"
        raise UnknownInstrumentError(
            f"Unknown instrument backend '{backend_id}'. Known: {known}"
        )
    return backends[backend_id]


def scan_instruments(backend_id: str | None = None) -> list[InstrumentDevice]:
    if backend_id:
        backend = get_backend(backend_id)
        if backend.info.status != "implemented":
            raise UnimplementedInstrumentError(backend.info.id)
        return backend.scan()
    devices: list[InstrumentDevice] = []
    errors: list[str] = []
    for backend in load_backends().values():
        if backend.info.status != "implemented" or not backend.available():
            continue
        try:
            devices.extend(backend.scan())
        except (InstrumentUnavailableError, UnimplementedInstrumentError) as exc:
            errors.append(f"{backend.info.id}: {exc}")
        except Exception as exc:
            errors.append(f"{backend.info.id}: {exc}")
    if errors:
        _LOAD_ERRORS.extend(errors)
    return devices
