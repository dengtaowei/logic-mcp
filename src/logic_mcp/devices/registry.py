from __future__ import annotations

import os
from pathlib import Path

import yaml

from logic_mcp.devices.base import UpperDecoder
from logic_mcp.devices.profile import PanelProfile
from logic_mcp.errors import ProfileError, UnknownProtocolError

_PACKAGE_PROFILES = Path(__file__).resolve().parent.parent / "profiles"
_DRIVERS: dict[str, UpperDecoder] | None = None
_LOAD_ERRORS: list[str] = []


def _parse_opcode(raw) -> int:
    if isinstance(raw, int):
        return raw
    text = str(raw).strip().lower()
    return int(text, 16) if text.startswith("0x") else int(text)


def profile_from_dict(data: dict, fallback_id: str = "") -> PanelProfile:
    if not data.get("id") and not fallback_id:
        raise ProfileError("Profile YAML missing id")
    extras = {}
    for key, name in (data.get("commands") or {}).items():
        extras[_parse_opcode(key)] = str(name)
    colmod = _parse_opcode(data.get("default_colmod", 0x05))
    madctl = _parse_opcode(data.get("default_madctl", 0x00))
    return PanelProfile(
        id=str(data.get("id") or fallback_id),
        controller=str(data.get("controller") or data.get("id") or fallback_id),
        title=str(data.get("title") or data.get("id") or fallback_id),
        width=int(data["width"]),
        height=int(data["height"]),
        col_offset=int(data.get("col_offset", 0)),
        row_offset=int(data.get("row_offset", 0)),
        default_colmod=colmod,
        default_madctl=madctl,
        driver=str(data.get("driver") or "mipi_dcs"),
        commands=extras,
        notes=str(data.get("notes") or ""),
    )


def _iter_profile_dirs() -> list[Path]:
    dirs: list[Path] = []
    extra = os.environ.get("LOGIC_MCP_PROFILES")
    if extra:
        dirs.append(Path(extra))
    dirs.append(Path.cwd() / "profiles")
    dirs.append(Path(__file__).resolve().parents[3] / "profiles")
    dirs.append(_PACKAGE_PROFILES)
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in dirs:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def load_profile(profile_id: str) -> PanelProfile:
    filename = f"{profile_id}.yaml"
    for directory in _iter_profile_dirs():
        path = directory / filename
        if path.is_file():
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return profile_from_dict(data, fallback_id=profile_id)
    raise ProfileError(
        f"Display profile '{profile_id}' not found. Looked in: "
        + ", ".join(str(p) for p in _iter_profile_dirs())
    )


def list_profiles() -> list[dict]:
    found: dict[str, Path] = {}
    for directory in _iter_profile_dirs():
        if not directory.is_dir():
            continue
        for path in directory.glob("*.yaml"):
            found.setdefault(path.stem, path)
    summaries = []
    for profile_id, path in sorted(found.items()):
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        summaries.append(
            {
                "id": data.get("id", profile_id),
                "controller": data.get("controller", profile_id),
                "title": data.get("title", profile_id),
                "driver": data.get("driver", "mipi_dcs"),
                "width": data.get("width"),
                "height": data.get("height"),
                "path": str(path),
            }
        )
    return summaries


def load_drivers() -> dict[str, UpperDecoder]:
    global _DRIVERS
    if _DRIVERS is not None:
        return _DRIVERS
    from importlib.metadata import entry_points

    from logic_mcp.devices.dcs import MipiDcsDriver

    found: dict[str, UpperDecoder] = {MipiDcsDriver.id: MipiDcsDriver()}
    try:
        eps = entry_points(group="logic_mcp.devices")
    except Exception as exc:
        _LOAD_ERRORS.append(f"logic_mcp.devices: {exc}")
        eps = []
    for ep in eps:
        try:
            cls = ep.load()
            inst = cls() if isinstance(cls, type) else cls
        except Exception as exc:
            _LOAD_ERRORS.append(f"{ep.name}: {exc}")
            continue
        if isinstance(inst, UpperDecoder):
            found[inst.id] = inst
        else:
            _LOAD_ERRORS.append(f"{ep.name}: not an UpperDecoder")
    _DRIVERS = found
    return found


def plugin_load_errors() -> list[str]:
    load_drivers()
    return list(_LOAD_ERRORS)


def list_drivers() -> list[dict]:
    return [
        {"id": driver.id, "title": driver.title, "notes": driver.notes}
        for driver in load_drivers().values()
    ]


def get_driver(driver_id: str) -> UpperDecoder:
    drivers = load_drivers()
    if driver_id not in drivers:
        known = ", ".join(sorted(drivers))
        raise UnknownProtocolError(f"Unknown upper decoder '{driver_id}'. Known: {known}")
    return drivers[driver_id]


def driver_for_profile(profile: PanelProfile) -> UpperDecoder:
    return get_driver(profile.driver)
