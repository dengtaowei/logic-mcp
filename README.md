# logic-mcp

Multi-vendor logic-analyzer MCP for Cursor. DreamSourceLab/DSView, Saleae, and VCD are **plugins**, not the product name.

Vendors attach in **either** way:

1. **In-process** — Python `InstrumentBackend` in this repo.
2. **IPC** — external process speaking [`logic_mcp.instrument.v1`](src/logic_mcp/instrument/PROTOCOL.md) on a Unix socket (patched DSView, or `logic-mcp-instrument`).

```text
Cursor ── logic-mcp
            ├─ in-process: mock / sigrok_cli / dslogic
            └─ ipc/dsview ── socket ── vendor (DSView GUI, …)
                 └─ LogicCapture → DecodeJob → interpret / PNG
```

## Instrument MCP

Same tools for both transports:

- Full config in MCP: `instrument_open` → `instrument_configure` → `instrument_capture`
- Config in vendor UI (DSView): `instrument_open("dsview")` → `instrument_start` → `instrument_wait` → `instrument_export` (or just `instrument_capture` with no rate)

Do not add vendor-named tools. `hello.configure` tells the client who owns sample rate and channels.

## Setup

```bash
cd /home/adminpc/m9s/logic-mcp
uv sync --extra dev
uv run pytest
```

Reference hub (wraps the in-process `mock` behind the socket):

```bash
uv run logic-mcp-instrument --socket $XDG_RUNTIME_DIR/logic-mcp/instrument.sock
```

Patched DSView listens on `$XDG_RUNTIME_DIR/logic-mcp/dsview.sock`.

Cursor:

```json
{
  "mcpServers": {
    "logic": {
      "command": "uv",
      "args": ["--directory", "/home/adminpc/m9s/logic-mcp", "run", "logic-mcp"]
    }
  }
}
```

Env: `LOGIC_MCP_PROFILES`, `LOGIC_MCP_OUT`, `LOGIC_MCP_INSTRUMENT_SOCK`, `LOGIC_MCP_DSVIEW_SOCK`, `SIGROK_CLI`.
