from __future__ import annotations

from pathlib import Path

import pytest

from logic_mcp.errors import (
    InstrumentConfigError,
    InstrumentUnavailableError,
    SessionStateError,
    UnimplementedInstrumentError,
)
from logic_mcp.instrument.registry import get_backend, list_instruments, scan_instruments
from logic_mcp.instrument.sigrok import parse_sigrok_scan, parse_sigrok_show
from logic_mcp.instrument.types import build_request
from logic_mcp.session import Session
from logic_mcp.synth import DEFAULT_MAP, build_st7789_blocks_csv


def test_instrument_list_and_scan_mock():
    by_id = {item["id"]: item for item in list_instruments()}
    assert by_id["mock"]["status"] == "implemented"
    assert by_id["mock"]["transport"] == "inprocess"
    assert by_id["ipc"]["status"] == "implemented"
    assert by_id["dsview"]["transport"] == "ipc"
    assert by_id["sigrok_cli"]["status"] == "implemented"
    assert by_id["dslogic"]["status"] == "implemented"
    assert by_id["saleae_live"]["status"] == "unimplemented"
    assert by_id["saleae_live"]["available"] is False
    devices = scan_instruments("mock")
    assert devices[0].id == "mock:virtual"


def test_saleae_live_is_stub():
    backend = get_backend("saleae_live")
    with pytest.raises(UnimplementedInstrumentError):
        backend.scan()
    session = Session()
    with pytest.raises(UnimplementedInstrumentError):
        session.instrument_open("saleae_live")


def test_build_request_validation():
    with pytest.raises(InstrumentConfigError):
        build_request(0, duration_s=0.1)
    with pytest.raises(InstrumentConfigError):
        build_request(1e6)
    with pytest.raises(InstrumentConfigError):
        build_request(1e6, duration_s=0.1, trigger_edge="rising")
    req = build_request(
        1e8,
        duration_s=0.01,
        channels=["D0", "WR"],
        trigger_channel="WR",
        trigger_edge="rising",
    )
    assert req.trigger.sigrok_token() == "WR=r"


def test_mock_configure_capture_decode(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = Session()
    opened = session.instrument_open("mock")
    assert opened["ok"]
    assert opened["capabilities"]["channels"][0]["name"] == "D0"
    configured = session.instrument_configure(100_000_000, duration_s=0.001)
    assert configured["state"] == "configured"
    captured = session.instrument_capture(out_dir=str(tmp_path / "live"))
    assert captured["source"] == "live"
    assert captured["state"] == "captured"
    assert "D0" in [ch["name"] for ch in captured["channels"]]
    decoded = session.decode("i8080", DEFAULT_MAP, job_id="lcd")
    assert decoded["event_count"] > 0
    rebuilt = session.reconstruct("st7789", width=32, height=32, out_dir=str(tmp_path / "out"))
    assert Path(rebuilt["png"]["final"]).is_file()
    status = session.status()
    assert status["instrument"]["backend"] == "mock"
    assert status["source"] == "live"


def test_mock_replay_and_one_shot_capture(tmp_path: Path):
    csv_path = build_st7789_blocks_csv(tmp_path / "cap.csv")
    session = Session()
    session.instrument_open("mock", extra={"replay": str(csv_path)})
    captured = session.instrument_capture(
        sample_rate_hz=50_000_000,
        sample_count=1000,
        out_dir=str(tmp_path / "live"),
    )
    assert captured["path"] == str(csv_path.resolve())
    assert captured["metadata"]["backend"] == "mock"


def test_capture_without_configure_fails():
    session = Session()
    session.instrument_open("mock")
    with pytest.raises(SessionStateError):
        session.instrument_capture()


def test_dslogic_scan_without_sigrok(monkeypatch):
    monkeypatch.delenv("SIGROK_CLI", raising=False)
    monkeypatch.setattr("logic_mcp.instrument.dslogic.find_sigrok_cli", lambda: None)
    monkeypatch.setattr("logic_mcp.instrument.sigrok.find_sigrok_cli", lambda: None)
    with pytest.raises(InstrumentUnavailableError):
        get_backend("dslogic").scan()


SIGROK_SCAN = """
The following devices were found:
demo - Demo device with analog and digital channels
dreamsourcelab-dslogic:conn=1.12 - DSLogic Plus
fx2lafw:conn=3.9 - Cypress FX2 (generic)
"""

SIGROK_SHOW = """
Driver: dreamsourcelab-dslogic
Board: DSLogic Plus
Supported samplerates:
  10 kHz
  1 MHz
  100 MHz
  400 MHz
Logic channels: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15
Analog channels: none
"""


def test_parse_sigrok_scan_and_show():
    devices = parse_sigrok_scan(SIGROK_SCAN, "sigrok_cli")
    ids = [d.id for d in devices]
    assert "demo" in ids
    assert "dreamsourcelab-dslogic:conn=1.12" in ids
    assert "fx2lafw:conn=3.9" in ids
    caps = parse_sigrok_show(SIGROK_SHOW, {})
    assert caps.channels[0].name == "0"
    assert len(caps.channels) == 16
    assert 400_000_000 in caps.sample_rates_hz
    assert caps.min_sample_rate_hz == 10_000
    assert caps.analog is False


def test_ipc_wraps_inprocess_mock(tmp_path: Path):
    from logic_mcp.instrument.dispatch import connected_dispatcher
    from logic_mcp.instrument.ipc_server import InstrumentIpcServer
    from logic_mcp.instrument.mock import MockBackend

    sock = tmp_path / "instrument.sock"
    inner = MockBackend().connect(extra={"out_dir": str(tmp_path / "inner")})
    server = InstrumentIpcServer(
        sock,
        connected_dispatcher(inner, configure=True),
        vendor="logic-mcp",
        product="mock-hub",
        configure=True,
    )
    server.start()
    try:
        session = Session()
        opened = session.instrument_open("ipc", extra={"socket": str(sock)})
        assert opened["ok"]
        assert opened["owns_config"] is True
        assert opened["transport"] == "ipc"
        captured = session.instrument_capture(
            sample_rate_hz=100_000_000,
            duration_s=0.001,
            out_dir=str(tmp_path / "live"),
        )
        assert captured["source"] == "live"
        assert Path(captured["path"]).is_file()
        session.instrument_close()
    finally:
        server.stop()


def test_ipc_gui_owned_start_export(tmp_path: Path):
    from logic_mcp.instrument.dispatch import connected_dispatcher
    from logic_mcp.instrument.ipc_server import InstrumentIpcServer
    from logic_mcp.instrument.mock import MockBackend

    sock = tmp_path / "dsview.sock"
    inner = MockBackend().connect(
        extra={"gui_owned": True, "out_dir": str(tmp_path / "inner")}
    )
    server = InstrumentIpcServer(
        sock,
        connected_dispatcher(inner, configure=False),
        vendor="DreamSourceLab",
        product="DSView",
        configure=False,
    )
    server.start()
    try:
        session = Session()
        opened = session.instrument_open("dsview", extra={"socket": str(sock)})
        assert opened["owns_config"] is False
        started = session.instrument_start()
        assert started["ok"]
        session.instrument_wait(timeout_s=2)
        exported = session.instrument_export(out_dir=str(tmp_path / "live"))
        assert exported["ok"]
        assert Path(exported["path"]).is_file()
        session.instrument_close()
    finally:
        server.stop()


def test_ipc_scan_missing_socket(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOGIC_MCP_INSTRUMENT_SOCK", str(tmp_path / "missing.sock"))
    assert scan_instruments("ipc") == []
