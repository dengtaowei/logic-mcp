from logic_mcp.bus.base import UnimplementedBus
from logic_mcp.bus.roles import ChannelRole


class I2cDecoder(UnimplementedBus):
    id = "i2c"
    title = "I2C"
    notes = "Link-layer stub. Will emit I2C messages (address, rw, payload), not display messages."
    roles = (
        ChannelRole("scl", description="I2C clock"),
        ChannelRole("sda", description="I2C data"),
    )
