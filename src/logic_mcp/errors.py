class LogicMcpError(Exception):
    """Base error for the MCP server and decode pipeline."""

    code = "error"

    def to_dict(self) -> dict:
        return {"ok": False, "error": self.code, "message": str(self)}


class CaptureOpenError(LogicMcpError):
    code = "capture_open_error"


class ChannelMapError(LogicMcpError):
    code = "channel_map_error"


class UnimplementedCaptureError(LogicMcpError):
    code = "not_implemented"

    def __init__(self, format_id: str, vendor: str):
        super().__init__(
            f"Capture format '{format_id}' ({vendor}) is registered but not implemented yet."
        )
        self.format_id = format_id
        self.vendor = vendor


class UnimplementedBusError(LogicMcpError):
    code = "not_implemented"

    def __init__(self, protocol: str):
        super().__init__(
            f"Bus protocol '{protocol}' is registered but not implemented yet."
        )
        self.protocol = protocol


class UnknownProtocolError(LogicMcpError):
    code = "unknown_protocol"


class UnknownJobError(LogicMcpError):
    code = "unknown_job"


class SessionStateError(LogicMcpError):
    code = "session_error"


class ProfileError(LogicMcpError):
    code = "profile_error"


class UnknownInstrumentError(LogicMcpError):
    code = "unknown_instrument"


class InstrumentConfigError(LogicMcpError):
    code = "instrument_config_error"


class InstrumentUnavailableError(LogicMcpError):
    code = "instrument_unavailable"


class InstrumentError(LogicMcpError):
    code = "instrument_error"


class UnimplementedInstrumentError(LogicMcpError):
    code = "not_implemented"

    def __init__(self, backend_id: str):
        super().__init__(
            f"Instrument backend '{backend_id}' is registered but not implemented yet."
        )
        self.backend_id = backend_id
