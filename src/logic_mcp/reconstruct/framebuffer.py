from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from logic_mcp.messages import Message
from logic_mcp.devices.mipi_dcs import is_pixel_opcode
from logic_mcp.devices.profile import PanelProfile

UNWRITTEN = (0x30, 0x30, 0x30)


def rgb565(hi: int, lo: int) -> tuple[int, int, int]:
    value = ((hi & 0xFF) << 8) | (lo & 0xFF)
    red = ((value >> 11) & 0x1F) * 255 // 31
    green = ((value >> 5) & 0x3F) * 255 // 63
    blue = (value & 0x1F) * 255 // 31
    return red, green, blue


def rgb666(b0: int, b1: int, b2: int) -> tuple[int, int, int]:
    red = ((b0 >> 2) & 0x3F) * 255 // 63
    green = ((b1 >> 2) & 0x3F) * 255 // 63
    blue = ((b2 >> 2) & 0x3F) * 255 // 63
    return red, green, blue


def bytes_per_pixel(colmod: int) -> int:
    return 3 if (colmod & 0x0F) == 0x06 else 2


def window_coords(xs: int, xe: int, ys: int, ye: int, madctl: int):
    mx = bool(madctl & 0x40)
    my = bool(madctl & 0x80)
    mv = bool(madctl & 0x20)
    if xe < xs:
        xs, xe = xe, xs
    if ye < ys:
        ys, ye = ye, ys
    cols = range(xe, xs - 1, -1) if mx else range(xs, xe + 1)
    rows = range(ye, ys - 1, -1) if my else range(ys, ye + 1)
    if not mv:
        for y in rows:
            for x in cols:
                yield x, y
    else:
        for x in cols:
            for y in rows:
                yield x, y


@dataclass
class ReconstructResult:
    width: int
    height: int
    pixels_written: int
    pixel_overflow: int
    ramwr_count: int
    invert: bool
    colmod: int
    madctl: int
    window: tuple[int, int, int, int]
    frames: list[bytes] = field(default_factory=list)
    final: bytes = b""


class Framebuffer:
    def __init__(self, profile: PanelProfile):
        self.profile = profile
        self.width = profile.width
        self.height = profile.height
        self.col_offset = profile.col_offset
        self.row_offset = profile.row_offset
        self.colmod = profile.default_colmod
        self.madctl = profile.default_madctl
        self.invert = False
        self.xs = 0
        self.xe = max(self.width - 1, 0)
        self.ys = 0
        self.ye = max(self.height - 1, 0)
        self.pixels = bytearray(UNWRITTEN * self.width * self.height)
        self.pixels_written = 0
        self.pixel_overflow = 0
        self.ramwr_count = 0

    def snapshot(self) -> bytes:
        if not self.invert:
            return bytes(self.pixels)
        inverted = bytearray(self.pixels)
        for i, value in enumerate(inverted):
            inverted[i] = 255 - value
        return bytes(inverted)

    def _put(self, gram_x: int, gram_y: int, color: tuple[int, int, int]) -> None:
        x = gram_x - self.col_offset
        y = gram_y - self.row_offset
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        idx = (y * self.width + x) * 3
        self.pixels[idx : idx + 3] = bytes(color)
        self.pixels_written += 1

    def _apply_window(self, opcode: int, params: list[int]) -> None:
        if len(params) < 4:
            return
        start = (params[0] << 8) | params[1]
        end = (params[2] << 8) | params[3]
        if opcode == 0x2A:
            self.xs, self.xe = start, end
        elif opcode == 0x2B:
            self.ys, self.ye = start, end

    def _write_pixels(self, data: list[int]) -> None:
        bpp = bytes_per_pixel(self.colmod)
        coords = window_coords(self.xs, self.xe, self.ys, self.ye, self.madctl)
        i = 0
        n = len(data)
        while i + bpp <= n:
            try:
                x, y = next(coords)
            except StopIteration:
                self.pixel_overflow += (n - i) // bpp
                return
            if bpp == 2:
                color = rgb565(data[i], data[i + 1])
            else:
                color = rgb666(data[i], data[i + 1], data[i + 2])
            self._put(x, y, color)
            i += bpp

    def replay(self, messages: Iterable[Message]) -> ReconstructResult:
        frames: list[bytes] = []
        params: list[int] = []
        opcode: int | None = None

        def finish_cmd() -> None:
            nonlocal opcode, params
            if opcode is None:
                return
            if opcode == 0x2A:
                self._apply_window(0x2A, params)
            elif opcode == 0x2B:
                self._apply_window(0x2B, params)
            elif opcode == 0x36 and params:
                self.madctl = params[0]
            elif opcode == 0x3A and params:
                self.colmod = params[0]
            elif opcode == 0x21:
                self.invert = True
            elif opcode == 0x20:
                self.invert = False
            elif is_pixel_opcode(opcode):
                self.ramwr_count += 1
                self._write_pixels(params)
                frames.append(self.snapshot())
            opcode = None
            params = []

        for msg in messages:
            if msg.type == "dcs.command":
                finish_cmd()
                opcode = int(msg.fields["opcode"])
                params = []
                continue
            if msg.type == "dcs.data" and opcode is not None:
                params.append(int(msg.fields["byte"]))
        finish_cmd()

        return ReconstructResult(
            width=self.width,
            height=self.height,
            pixels_written=self.pixels_written,
            pixel_overflow=self.pixel_overflow,
            ramwr_count=self.ramwr_count,
            invert=self.invert,
            colmod=self.colmod,
            madctl=self.madctl,
            window=(self.xs, self.xe, self.ys, self.ye),
            frames=frames,
            final=self.snapshot(),
        )


def reconstruct(messages: Iterable[Message], profile: PanelProfile) -> ReconstructResult:
    return Framebuffer(profile).replay(messages)
