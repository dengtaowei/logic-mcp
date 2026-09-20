from logic_mcp.bus.base import UnimplementedBus
from logic_mcp.bus.roles import ChannelRole


class SpiDecoder(UnimplementedBus):
    id = "spi"
    title = "SPI"
    notes = (
        "Link-layer stub. Will emit SPI transfers, not display messages. "
        "Optional dc role is a side GPIO for 4-wire displays, not part of SPI itself."
    )
    roles = (
        ChannelRole("sck", aliases=("clk", "sclk"), description="SPI clock"),
        ChannelRole("mosi", aliases=("copi", "sdi"), description="Controller out"),
        ChannelRole("cs", required=False, aliases=("ss", "csx"), description="Chip select, active-low"),
        ChannelRole("miso", required=False, aliases=("cipo", "sdo"), description="Controller in"),
        ChannelRole(
            "dc",
            required=False,
            aliases=("rs", "dcx"),
            description="Optional D/C GPIO for 4-wire SPI panels",
        ),
    )
