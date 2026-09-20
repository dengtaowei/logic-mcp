# DSView patch (`logic_mcp.instrument.v1`)

Adds a `QLocalServer` hub so patched DSView can be started/stopped/exported from logic-mcp without going through `sigrok-cli`.

Rate, channels, and trigger stay in the DSView GUI (`hello.configure=false`). MCP tools: `instrument_open("dsview")` → `start` → `wait` → `export`.

Socket: `$XDG_RUNTIME_DIR/logic-mcp/dsview.sock` (override `LOGIC_MCP_DSVIEW_SOCK`).

## Upstream

| | |
|---|---|
| Tree | https://github.com/DreamSourceLab/DSView |
| Commit | `2e9e2c8e726df4ef5687d39b83d4f797cc44b574` (`v1.3.2-53-g2e9e2c8e`) |
| License | GPLv3+ (see upstream README) |

This directory is a **patch against GPLv3+ source**. Those files stay GPLv3+. logic-mcp itself is MIT and does not relicense DSView.

## What the patch changes

- New `DSView/pv/logicmcpipc.{h,cpp}` — NDJSON IPC (`hello`, `status`, `capabilities`, `start`, `stop`, `wait`, `export`).
- `MainWindow` starts the server after `setup_ui`.
- Qt Network on Qt5/Qt6.
- `StoreSession::SetExportFile` plus a fix so a bad export format does not clear `_error`.

## Apply

```bash
git clone https://github.com/DreamSourceLab/DSView.git
cd DSView
git checkout 2e9e2c8e726df4ef5687d39b83d4f797cc44b574

PATCH_DIR=/path/to/logic-mcp/vendor/dsview
while IFS= read -r p; do
  [ -z "$p" ] || [ "${p#\#}" != "$p" ] && continue
  git apply "$PATCH_DIR/$p"
done < "$PATCH_DIR/series"
```

Then build DSView as upstream documents. Rebuild after applying; the stock binary has no socket.

If a later DSView release does not apply cleanly, rebase the patch on the new commit and update `upstream.yaml`.
