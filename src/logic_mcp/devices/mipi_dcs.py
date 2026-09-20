"""Shared MIPI DCS opcodes used by ST7789, ILI9341, ST7735, and similar panels."""

from __future__ import annotations

# opcode -> (name, expected param bytes; None means variable / pixel stream)
DCS_COMMANDS: dict[int, tuple[str, int | None]] = {
    0x00: ("NOP", 0),
    0x01: ("SWRESET", 0),
    0x04: ("RDDID", 3),
    0x09: ("RDDST", 4),
    0x10: ("SLPIN", 0),
    0x11: ("SLPOUT", 0),
    0x12: ("PTLON", 0),
    0x13: ("NORON", 0),
    0x20: ("INVOFF", 0),
    0x21: ("INVON", 0),
    0x26: ("GAMSET", 1),
    0x28: ("DISPOFF", 0),
    0x29: ("DISPON", 0),
    0x2A: ("CASET", 4),
    0x2B: ("RASET", 4),
    0x2C: ("RAMWR", None),
    0x2E: ("RAMRD", None),
    0x30: ("PTLAR", 4),
    0x33: ("VSCRDEF", 6),
    0x34: ("TEOFF", 0),
    0x35: ("TEON", 1),
    0x36: ("MADCTL", 1),
    0x37: ("VSCSAD", 2),
    0x38: ("IDMOFF", 0),
    0x39: ("IDMON", 0),
    0x3A: ("COLMOD", 1),
    0x3C: ("WRMEMC", None),
    0x3E: ("RDMEMC", None),
    0x44: ("STE", 2),
    0x51: ("WRDISBV", 1),
    0x53: ("WRCTRLD", 1),
    0x55: ("WRCACE", 1),
}

PIXEL_OPCODES = {0x2C, 0x3C}


def command_name(opcode: int, extra: dict[int, str] | None = None) -> str:
    if extra and opcode in extra:
        return extra[opcode]
    if opcode in DCS_COMMANDS:
        return DCS_COMMANDS[opcode][0]
    return f"CMD_{opcode:02X}"


def is_pixel_opcode(opcode: int) -> bool:
    return opcode in PIXEL_OPCODES
