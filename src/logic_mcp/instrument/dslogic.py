from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from logic_mcp.errors import InstrumentUnavailableError
from logic_mcp.instrument.base import ConnectedInstrument
from logic_mcp.instrument.sigrok import SigrokCliBackend, find_sigrok_cli
from logic_mcp.instrument.types import InstrumentDevice, InstrumentInfo

_DRIVER_MARKERS = ("dreamsourcelab", "dslogic")


class DslogicBackend(SigrokCliBackend):
    info = InstrumentInfo(
        id="dslogic",
        vendor="DreamSourceLab",
        title="DSLogic via sigrok-cli",
        status="implemented",
        notes=(
            "Live control of DSLogic hardware, not the DSView GUI. "
            "Close DSView before capturing (USB exclusive). "
            "Needs sigrok-cli built with dreamsourcelab-dslogic. "
            "Set SIGROK_CLI if the binary is not on PATH."
        ),
    )

    def _is_ours(self, device: InstrumentDevice) -> bool:
        blob = f"{device.id} {device.vendor} {device.model}".lower()
        return any(marker in blob for marker in _DRIVER_MARKERS)

    def scan(self) -> list[InstrumentDevice]:
        if find_sigrok_cli() is None:
            raise InstrumentUnavailableError(
                "sigrok-cli not found; cannot scan DSLogic. Install sigrok-cli or use backend='mock'."
            )
        devices = [
            InstrumentDevice(
                id=dev.id,
                backend=self.info.id,
                vendor="DreamSourceLab",
                model=dev.model,
                serial=dev.serial,
                present=dev.present,
                extra=dev.extra,
            )
            for dev in super().scan()
            if self._is_ours(dev)
        ]
        return devices

    def connect(
        self,
        device_id: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> ConnectedInstrument:
        if find_sigrok_cli() is None:
            raise InstrumentUnavailableError(
                "sigrok-cli not found; cannot open DSLogic. Install sigrok-cli or use backend='mock'."
            )
        if device_id is None:
            found = self.scan()
            if not found:
                raise InstrumentUnavailableError(
                    "No DSLogic found. Plug it in, close DSView, or use backend='mock'."
                )
            device_id = found[0].id
        connected = super().connect(device_id, extra)
        connected.device = InstrumentDevice(
            id=connected.device.id,
            backend=self.info.id,
            vendor="DreamSourceLab",
            model=connected.device.model,
            serial=connected.device.serial,
            present=True,
            extra=connected.device.extra,
        )
        return connected
