# logic-mcp

Vendor-neutral [MCP](https://modelcontextprotocol.io/) server for logic analyzers. Cursor (or any MCP client) can capture from hardware, open a trace file, decode a bus, and reconstruct a display framebuffer.

DreamSourceLab / DSView, Saleae, and VCD are **plugins**, not the product name.

```text
Cursor ── stdio MCP ── logic-mcp
                         ├─ in-process: mock / sigrok_cli / dslogic
                         └─ ipc / dsview ── Unix socket ── vendor process
                              └─ LogicCapture → bus decode → interpret / PNG
```

## What it does

- **Live instrument control** — scan, configure, start/stop/wait, export.
- **Offline files** — open a capture (DSView CSV today; Saleae CSV / VCD are stubs).
- **Bus decode** — Intel 8080 / MCU 8080 parallel is implemented; SPI, I2C, UART are stubs with roles reserved.
- **Upper decode** — MIPI DCS / ST7789 command log + optional PNG reconstruction.

Vendors attach in **either** way:

1. **In-process** — Python `InstrumentBackend` registered on `logic_mcp.instruments`.
2. **IPC** — a long-lived process speaking [`logic_mcp.instrument.v1`](src/logic_mcp/instrument/PROTOCOL.md) on a Unix socket (patched DSView, or the reference hub `logic-mcp-instrument`).

MCP tool names stay vendor-neutral. Do not add `dsview_set_rate`-style tools.

## Status

| Layer | Implemented | Stub / placeholder |
|---|---|---|
| Instruments | `mock`, `ipc`, `dsview`, `sigrok_cli`, `dslogic` | `saleae_live` |
| Capture files | DSView / libsigrok4DSL CSV | Saleae CSV, VCD |
| Buses | `i8080` | `spi`, `i2c`, `uart` |
| Devices | `mipi_dcs` + `st7789` profile | other panels via extra YAML |

`dslogic` drives hardware through **sigrok-cli**, not the DSView GUI. USB is exclusive: close DSView before using `dslogic`. The stable DSView path is the patch in [`vendor/dsview`](vendor/dsview) (`backend=dsview`).

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Optional: `sigrok-cli` on `PATH` (or `SIGROK_CLI`) for live `sigrok_cli` / `dslogic`
- Optional: DSView rebuilt with the patch in [`vendor/dsview`](vendor/dsview) (listens on `$XDG_RUNTIME_DIR/logic-mcp/dsview.sock`)

## Install

```bash
git clone https://github.com/dengtaowei/logic-mcp.git
cd logic-mcp
uv sync --extra dev
uv run pytest
```

## Cursor MCP

Add to Cursor MCP settings. Point `--directory` at your clone:

```json
{
  "mcpServers": {
    "logic": {
      "command": "uv",
      "args": ["--directory", "/path/to/logic-mcp", "run", "logic-mcp"]
    }
  }
}
```

The server speaks MCP over stdio. It returns JSON summaries, not raw sample dumps.

## Workflows

### Offline CSV

```text
capture_open(path) → bus_decode(protocol, channel_map) → interpret / display_reconstruct
```

Pin maps are explicit. Column names or 0-based indices:

```json
{
  "protocol": "i8080",
  "channel_map": {
    "d0": "0", "d1": "1", "d2": "2", "d3": "3",
    "d4": "4", "d5": "5", "d6": "6", "d7": "7",
    "wr": "WR", "dc": "DC", "cs": "CS"
  }
}
```

`display_reconstruct` (profile `st7789`) writes a command log and PNG frames under `out/` (or `LOGIC_MCP_OUT`).

### Full config in MCP (mock / sigrok)

```text
instrument_open(backend) → instrument_configure → instrument_capture
→ bus_decode → interpret
```

`CaptureRequest` fields: `sample_rate_hz`, `channels`, `duration_s` **xor** `sample_count`, optional trigger, `extra`. There is no `channel_count`; pass the channel name list.

### Config in the vendor GUI (DSView)

Human sets rate, channels, and trigger in DSView. MCP only arms:

```text
instrument_open("dsview") → instrument_start → instrument_wait → instrument_export
```

`hello.configure=false` means the GUI owns sample rate and channels. `instrument_capture` without `sample_rate_hz` is valid on those backends.

## Instrument backends

| id | Transport | Config owner | Notes |
|---|---|---|---|
| `mock` | in-process | MCP | Always available; for tests and the reference hub |
| `sigrok_cli` | in-process subprocess | MCP | Portable probe via `sigrok-cli` |
| `dslogic` | in-process subprocess | MCP | `sigrok_cli` filtered to DreamSourceLab drivers |
| `ipc` | Unix socket | advertised by hub | Default `$XDG_RUNTIME_DIR/logic-mcp/instrument.sock` |
| `dsview` | Unix socket | GUI | Default `$XDG_RUNTIME_DIR/logic-mcp/dsview.sock` |
| `saleae_live` | — | — | Unimplemented (Logic 2 Automation API) |

Reference hub (wraps an in-process backend behind the socket):

```bash
uv run logic-mcp-instrument --socket "$XDG_RUNTIME_DIR/logic-mcp/instrument.sock"
# optional: --backend mock --gui-owned
```

IPC methods, framing, and states: [`src/logic_mcp/instrument/PROTOCOL.md`](src/logic_mcp/instrument/PROTOCOL.md).

## MCP tools

Inventory: `protocol_list`, `session_status`.

Instrument: `instrument_list`, `instrument_scan`, `instrument_open`, `instrument_close`, `instrument_capabilities`, `instrument_configure`, `instrument_capture`, `instrument_start`, `instrument_stop`, `instrument_wait`, `instrument_export`.

Decode: `capture_open`, `protocol_roles`, `bus_decode`, `interpret`, `display_analyze`, `display_reconstruct`.

## Extending

Entry points in `pyproject.toml`:

| Group | What to implement |
|---|---|
| `logic_mcp.instruments` | `InstrumentBackend` + `ConnectedInstrument` |
| `logic_mcp.captures` | `CaptureFormat` → `LogicCapture` |
| `logic_mcp.buses` | `BusDecoder` + channel roles |
| `logic_mcp.devices` | upper decoder (e.g. MIPI DCS) |

Out of process: listen on the Unix socket and implement `hello` / `status` / `start` / `stop` / `wait` / `export` (and `configure` / `capabilities` if you own config). Python reference: `logic-mcp-instrument`.

When a vendor’s own GUI/SDK must be patched, put a unified diff under [`vendor/<id>/`](vendor/README.md) (pinned upstream commit + `series`). Do not copy their whole tree. First example: [`vendor/dsview`](vendor/dsview).

Panel YAML (`profiles/st7789.yaml`, or `LOGIC_MCP_PROFILES`): `width`, `height`, offsets, extra DCS opcodes.

## Environment

| Variable | Purpose |
|---|---|
| `LOGIC_MCP_OUT` | Artifact directory (default `./out`) |
| `LOGIC_MCP_PROFILES` | Extra panel YAML directory |
| `LOGIC_MCP_INSTRUMENT_SOCK` | Default `ipc` socket |
| `LOGIC_MCP_DSVIEW_SOCK` | Default `dsview` socket |
| `SIGROK_CLI` | Path to `sigrok-cli` if not on `PATH` |

## License

[MIT](LICENSE) for logic-mcp.

Patches under [`vendor/`](vendor/README.md) are against other projects and keep **that** project’s license. [`vendor/dsview`](vendor/dsview) is GPLv3+ (DreamSourceLab DSView).
