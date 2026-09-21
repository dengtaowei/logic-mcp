# First session in Cursor

You talk in chat. The agent calls the `logic` MCP tools and answers. You do not click a decoder GUI, paste CSV rows, or write a Python parser.

```text
you  →  Cursor chat  →  logic MCP  →  JSON summary / PNG
              ↓
         agent explains
```

| You | Agent |
|-----|--------|
| Export a compressed DSView CSV; `@`-mention the file | `capture_open` → `bus_decode` → `display_analyze` or `display_reconstruct` |
| Say what you expected (init vs a red screen) | Compare the summary to that |

**Setup** is in the root [README](../README.md) (install + Cursor MCP). The `logic` server must show as connected. Use **Agent** mode. If the model only lectures, tell it to use the `logic` tools.

CSV column names are probe labels, not 8080 roles. The files below use [`channel_maps/i8080_dsview.json`](channel_maps/i8080_dsview.json): **`dc` is `RS`**, not chip select. `DB1` is data bit 1.

There are two exercises. The first uses a **synthetic** file in this repo (Sitronix ST7789 datasheet sequence, not a dump from a particular board). The second needs your own capture (a full-frame CSV is too large to vendor). Do not commit lab captures of product firmware.

---

## 1. Command log — panel init

File: [`captures/panel_init.csv`](captures/panel_init.csv) (`@` it in chat).

**Prompt:**

> Open `@examples/captures/panel_init.csv` with logic-mcp. Map Intel 8080 using `examples/channel_maps/i8080_dsview.json`. Decode the bus, then `display_analyze` as ST7789. Summarize the DCS commands. Note which writes are commands vs parameters, and that the one RD cycle is absent from the DCS log.

The agent should call `capture_open`, then `bus_decode` (`i8080` + that map), then `display_analyze` (`st7789`). It may call `protocol_roles` first. It should not write a decoder.

**A good reply looks like:**

- **17** bus cycles: **16 writes, 1 read**.
- **6** DCS commands: `COLMOD 0x55`, `SLPOUT`, `MADCTL 0x00`, `CASET` (4 bytes, 0..239), `RASET` (4 bytes, 0..319), `DISPON`.
- The **read is not in the command log** — DCS decode only uses write cycles.
- `CASET` / `RASET` here have full 4-byte windows (datasheet). If a later capture shows `data_len` 0 on those opcodes, that is a host-side length error, not a missed edge in the CSV.
- **No `RAMWR` is normal for this file.** Init is register traffic, not a frame.

Optional: *“Reconstruct 240×320 anyway. Were any pixels written?”*

`display_reconstruct` should report `pixels_written: 0`. The frame is unwritten grey (not a failed decode):

![unwritten framebuffer after init](expected/panel_init.png)

---

## 2. Framebuffer — solid fill

Keep a full 240×320 RGB565 `RAMWR` CSV **out of git**. Export your own with the same 12 channels (`RS,CS,RD,WR,DB0–DB7`), compressed, then `@` that path.

**Prompt:**

> Open `<your.csv>` with logic-mcp. Same i8080 map as `examples/channel_maps/i8080_dsview.json`. If this is pixel traffic, reconstruct ST7789 at 240×320. Give window, pixels written, overflow, and the PNG path, then open the PNG.

The agent should `capture_open` → `bus_decode`, then **`display_reconstruct`** (not only `display_analyze`). A full frame is on the order of `2 × 240 × 320` writes plus a few setup cycles.

**A good reply looks like:**

- Commands: `CASET`, `RASET`, `RAMWR` (pixel payload), often `NOP`.
- Window 0..239 × 0..319, **76800** pixels, overflow **0**.
- A PNG under `out/` (or `LOGIC_MCP_OUT`). Solid red matches:

![reconstructed solid red](expected/fill_red.png)

If you only get a four-line command list and no image, ask it to run `display_reconstruct`.

---

## If it goes wrong

| What you see | Likely cause |
|--------------|----------------|
| Model explains MCP but never calls tools | `logic` not connected, or not Agent mode |
| Missing `wr` / `dc` | Map names ≠ `capture_open` channel list |
| `event_count` 0 | Wrong WR column or strobe polarity |
| Every byte is a new command | `dc` mapped to CS or a data line |
| Grey PNG on a fill capture | No `RAMWR`, or reconstruct never ran |

Live instruments (`instrument_open` → `start` → `wait` → `export`) then use the same decode prompts. Maps still go on `bus_decode`.
