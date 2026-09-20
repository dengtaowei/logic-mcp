from pathlib import Path

from PIL import Image

from logic_mcp.bus.i8080 import I8080Decoder
from logic_mcp.capture.dsview_csv import DsviewCsvFormat
from logic_mcp.devices.dcs import MipiDcsDriver, aggregate_dcs_commands
from logic_mcp.devices.registry import load_profile
from logic_mcp.reconstruct.framebuffer import UNWRITTEN, reconstruct
from tests.synth import DEFAULT_MAP, build_st7789_blocks_csv


def test_st7789_command_names_and_blocks(tmp_path: Path):
    csv_path = build_st7789_blocks_csv(tmp_path / "cap.csv")
    capture = DsviewCsvFormat().open(csv_path)
    cycles = I8080Decoder().decode(capture, DEFAULT_MAP)
    profile = load_profile("st7789").override(width=32, height=32)
    driver = MipiDcsDriver()
    messages = list(driver.interpret(cycles, context={"commands": profile.commands}))
    events = aggregate_dcs_commands(messages)
    names = [e["name"] for e in events]
    assert names[:4] == ["COLMOD", "MADCTL", "CASET", "RASET"]
    ramwr = [e for e in events if e["name"] == "RAMWR"]
    assert len(ramwr) == 2
    assert ramwr[0]["data_len"] == 128
    assert ramwr[0]["is_pixel"]
    assert ramwr[0]["schema"] == "logic_mcp.commands.v1"

    result = reconstruct(messages, profile)
    assert result.ramwr_count == 2
    assert result.pixel_overflow == 0
    image = Image.frombytes("RGB", (32, 32), result.final)
    assert image.getpixel((2, 2)) == (255, 0, 0)
    assert image.getpixel((9, 9)) == (255, 0, 0)
    assert image.getpixel((12, 12)) == (0, 255, 0)
    assert image.getpixel((19, 19)) == (0, 255, 0)
    assert image.getpixel((0, 0)) == UNWRITTEN
    assert image.getpixel((10, 10)) == UNWRITTEN
