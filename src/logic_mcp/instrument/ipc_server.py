from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from logic_mcp.errors import InstrumentError
from logic_mcp.instrument.protocol import (
    OPTIONAL_METHODS,
    PROTOCOL_ID,
    REQUIRED_METHODS,
    encode_error,
    encode_result,
    parse_message,
)

Dispatcher = Callable[[str, dict[str, Any]], dict[str, Any]]


class InstrumentIpcServer:
    """Reference server. Vendors can copy this or speak the same NDJSON in C++/Qt."""

    def __init__(
        self,
        path: Path,
        dispatch: Dispatcher,
        *,
        vendor: str,
        product: str,
        configure: bool,
        formats: tuple[str, ...] = ("csv",),
        serial: str | None = None,
    ):
        self.path = Path(path)
        self.dispatch = dispatch
        self.vendor = vendor
        self.product = product
        self.configure = configure
        self.formats = formats
        self.serial = serial
        self._sock: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def hello_result(self) -> dict[str, Any]:
        methods = list(REQUIRED_METHODS)
        if self.configure:
            methods.extend(OPTIONAL_METHODS)
        else:
            methods.append("capabilities")
        return {
            "protocol": PROTOCOL_ID,
            "vendor": self.vendor,
            "product": self.product,
            "serial": self.serial,
            "methods": methods,
            "configure": self.configure,
            "formats": list(self.formats),
            "transport": "ipc",
        }

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.path))
        sock.listen(4)
        sock.settimeout(0.3)
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="instrument-ipc", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError:
                pass

    def _loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                self._serve_client(conn)
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _serve_client(self, conn: socket.socket) -> None:
        conn.settimeout(0.3)
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = conn.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                if not raw.strip():
                    continue
                conn.sendall(self._handle_line(raw.decode("utf-8")))

    def _handle_line(self, line: str) -> bytes:
        try:
            msg = parse_message(line)
        except (ValueError, TypeError) as exc:
            return encode_error(0, "protocol_error", str(exc))
        msg_id = int(msg.get("id") or 0)
        method = str(msg.get("method") or "")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if method == "hello":
            return encode_result(msg_id, self.hello_result())
        try:
            result = self.dispatch(method, params)
        except InstrumentError as exc:
            return encode_error(msg_id, exc.code, str(exc))
        except Exception as exc:
            return encode_error(msg_id, "instrument_error", str(exc))
        return encode_result(msg_id, result)
