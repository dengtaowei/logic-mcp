from logic_mcp.bus.base import UnimplementedBus
from logic_mcp.bus.roles import ChannelRole


class UartDecoder(UnimplementedBus):
    id = "uart"
    title = "UART"
    notes = "Link-layer stub. Will emit UART bytes with start/stop/parity, not display PDUs."
    roles = (
        ChannelRole("rx", required=False, description="Receive"),
        ChannelRole("tx", required=False, description="Transmit"),
    )
