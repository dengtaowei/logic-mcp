# logic_mcp.instrument.v1

Vendors plug in **either** way. MCP tools stay the same.

1. **In-process** — Python `InstrumentBackend` in this repo (`logic_mcp.instruments` entry point).
2. **IPC** — a long-lived process (DSView, Saleae wrapper, …) speaks this protocol on a Unix socket.

```text
Cursor ── stdio MCP ── logic-mcp
                         ├─ mock / sigrok_cli / dslogic     (in-process)
                         └─ backend=ipc|dsview  ── socket ── vendor process
```

## Transport

- Unix domain stream socket.
- Default paths:
  - `ipc`: `$XDG_RUNTIME_DIR/logic-mcp/instrument.sock` (`LOGIC_MCP_INSTRUMENT_SOCK`)
  - `dsview`: `$XDG_RUNTIME_DIR/logic-mcp/dsview.sock` (`LOGIC_MCP_DSVIEW_SOCK`)
- Framing: **one JSON object per line**, UTF-8, `\n` terminated.

Request:

```json
{"id":1,"method":"start","params":{}}
```

Success:

```json
{"id":1,"ok":true,"result":{"state":"capturing"}}
```

Error:

```json
{"id":1,"ok":false,"error":{"code":"busy","message":"already capturing"}}
```

`protocol` string in `hello` **must** be `logic_mcp.instrument.v1`.

## Methods

| Method | Required | Params | Result |
|---|---|---|---|
| `hello` | yes | `{}` | `protocol`, `vendor`, `product`, `serial?`, `methods[]`, `configure` (bool), `formats[]` |
| `status` | yes | `{}` | `state`: `idle` \| `capturing` \| `complete` \| `error` |
| `start` | yes | optional CaptureRequest fields | `state` |
| `stop` | yes | `{}` | `state` |
| `wait` | yes | `{timeout_s}` | `state`, `timed_out` |
| `export` | yes | `{path, format}` | `{path, format}` — file the MCP can `capture_open` |
| `capabilities` | if you have them | `{}` | rates, channel names |
| `configure` | only if `hello.configure=true` | CaptureRequest | `state` |

`configure=false` (DSView): human sets rate/channels/trigger in the GUI. MCP only `start` / `stop` / `wait` / `export`.

`configure=true` (in-process mock, or a headless hub): MCP may `configure` then `start`.

States: after `start`, `wait` until `complete`, then `export`. Instant backends may return `complete` from `start`.

## Adding a vendor

**This repo:** subclass `InstrumentBackend` + `ConnectedInstrument`, register `logic_mcp.instruments`.

**Out of process:** listen on the socket, implement the table above. Python reference: `logic-mcp-instrument`. DSView: `LogicMcpIpc` in the DSView tree.

Do not add `dsview_set_rate`-style MCP tools. Decode stays in `logic-mcp`.
