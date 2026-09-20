from __future__ import annotations

import argparse
import time

from pathlib import Path

from logic_mcp.instrument.dispatch import connected_dispatcher
from logic_mcp.instrument.ipc_server import InstrumentIpcServer
from logic_mcp.instrument.mock import MockBackend
from logic_mcp.instrument.protocol import default_socket_path
from logic_mcp.instrument.registry import get_backend


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Reference logic_mcp.instrument.v1 server (in-process backend behind a socket)."
    )
    parser.add_argument("--backend", default="mock", help="In-process backend to wrap (default: mock)")
    parser.add_argument("--socket", default=None, help="Unix socket path")
    parser.add_argument(
        "--gui-owned",
        action="store_true",
        help="Advertise configure=false (vendor UI owns rate/channels)",
    )
    args = parser.parse_args(argv)
    backend = MockBackend() if args.backend == "mock" else get_backend(args.backend)
    extra = {"gui_owned": True} if args.gui_owned else {}
    connected = backend.connect(extra=extra)
    path = Path(args.socket).expanduser() if args.socket else default_socket_path("instrument")
    server = InstrumentIpcServer(
        path,
        connected_dispatcher(connected, configure=not args.gui_owned),
        vendor=backend.info.vendor,
        product=backend.info.title,
        configure=not args.gui_owned,
    )
    server.start()
    print(f"logic_mcp.instrument.v1 on {path} backend={backend.info.id} configure={not args.gui_owned}")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
