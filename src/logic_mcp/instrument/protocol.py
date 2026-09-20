"""logic_mcp.instrument.v1 — newline-delimited JSON over a Unix socket.

Vendors implement this in-process (InstrumentBackend) *or* as an external
process. The MCP client does not care which.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROTOCOL_ID = "logic_mcp.instrument.v1"
REQUIRED_METHODS = ("hello", "status", "start", "stop", "wait", "export")
OPTIONAL_METHODS = ("capabilities", "configure")

# idle → capturing → complete | error  (complete means data is ready to export)
HubState = str


def default_socket_path(name: str = "instrument") -> Path:
    env_key = {
        "dsview": "LOGIC_MCP_DSVIEW_SOCK",
        "instrument": "LOGIC_MCP_INSTRUMENT_SOCK",
    }.get(name, "LOGIC_MCP_INSTRUMENT_SOCK")
    override = os.environ.get(env_key)
    if override:
        return Path(override).expanduser()
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(runtime) / "logic-mcp" / f"{name}.sock"


def encode_request(msg_id: int, method: str, params: dict[str, Any] | None = None) -> bytes:
    body = {"id": msg_id, "method": method, "params": params or {}}
    return (json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def encode_result(msg_id: int, result: dict[str, Any]) -> bytes:
    body = {"id": msg_id, "ok": True, "result": result}
    return (json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def encode_error(msg_id: int, code: str, message: str) -> bytes:
    body = {"id": msg_id, "ok": False, "error": {"code": code, "message": message}}
    return (json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def parse_message(line: str) -> dict[str, Any]:
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError("IPC message must be a JSON object")
    return data
