from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from logic_mcp.errors import InstrumentError, InstrumentUnavailableError
from logic_mcp.instrument.protocol import PROTOCOL_ID, encode_request, parse_message


class InstrumentIpcClient:
    """Talk logic_mcp.instrument.v1 to a vendor process."""

    def __init__(self, path: Path, timeout_s: float = 5.0):
        self.path = Path(path)
        self.timeout_s = timeout_s
        self._sock: socket.socket | None = None
        self._buf = b""
        self._next_id = 1
        self.hello: dict[str, Any] = {}

    def connect(self) -> dict[str, Any]:
        if not self.path.exists():
            raise InstrumentUnavailableError(
                f"Instrument socket not found: {self.path}. "
                "Start the vendor app (DSView) or logic-mcp-instrument."
            )
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout_s)
        try:
            sock.connect(str(self.path))
        except OSError as exc:
            sock.close()
            raise InstrumentUnavailableError(
                f"Cannot connect to instrument socket {self.path}: {exc}"
            ) from exc
        self._sock = sock
        self._buf = b""
        self.hello = self.call("hello")
        proto = self.hello.get("protocol")
        if proto != PROTOCOL_ID:
            self.close()
            raise InstrumentError(
                f"Unsupported instrument protocol {proto!r}, expected {PROTOCOL_ID}"
            )
        return self.hello

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def call(self, method: str, params: dict[str, Any] | None = None, timeout_s: float | None = None) -> dict[str, Any]:
        if self._sock is None:
            raise InstrumentUnavailableError("Instrument IPC is not connected")
        msg_id = self._next_id
        self._next_id += 1
        payload = encode_request(msg_id, method, params)
        try:
            self._sock.sendall(payload)
            if timeout_s is not None:
                self._sock.settimeout(timeout_s)
            line = self._readline()
        except (TimeoutError, socket.timeout) as exc:
            raise InstrumentError(f"IPC {method} timed out") from exc
        except OSError as exc:
            raise InstrumentError(f"IPC {method} failed: {exc}") from exc
        finally:
            if timeout_s is not None and self._sock is not None:
                self._sock.settimeout(self.timeout_s)
        msg = parse_message(line)
        if msg.get("id") != msg_id:
            raise InstrumentError(f"IPC id mismatch: sent {msg_id}, got {msg.get('id')!r}")
        if msg.get("ok") is False:
            err = msg.get("error") or {}
            raise InstrumentError(err.get("message") or f"{method} failed")
        result = msg.get("result")
        if not isinstance(result, dict):
            raise InstrumentError(f"IPC {method} returned no result object")
        return result

    def _readline(self) -> str:
        assert self._sock is not None
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise InstrumentError("Instrument IPC connection closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("utf-8")
