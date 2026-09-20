from pathlib import Path

from logic_mcp.capture.registry import list_formats, sniff_format
from logic_mcp.devices.registry import list_profiles
from logic_mcp.instrument.registry import list_instruments
from logic_mcp.session import Session
from tests.synth import DEFAULT_MAP, build_st7789_blocks_csv


def test_protocol_list_includes_stubs():
    captures = {info.id: info for info in list_formats()}
    assert captures["dsview_csv"].status == "implemented"
    assert captures["saleae_csv"].status == "unimplemented"
    assert captures["vcd"].status == "unimplemented"
    instruments = {item["id"]: item for item in list_instruments()}
    assert instruments["mock"]["status"] == "implemented"
    assert instruments["saleae_live"]["status"] == "unimplemented"
    assert instruments["ipc"]["transport"] == "ipc"
    assert instruments["dsview"]["status"] == "implemented"
    profiles = {p["id"] for p in list_profiles()}
    assert "st7789" in profiles


def test_sniff_dsview(tmp_path: Path):
    path = build_st7789_blocks_csv(tmp_path / "cap.csv")
    fmt = sniff_format(path)
    assert fmt.info.id == "dsview_csv"


def test_session_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = build_st7789_blocks_csv(tmp_path / "cap.csv")
    session = Session()
    opened = session.open(str(csv_path))
    assert opened["ok"]
    assert opened["capture_id"] == "cap"
    decoded = session.decode("i8080", DEFAULT_MAP)
    assert decoded["event_count"] > 0
    assert decoded["by_kind"]["wr"] > 0
    assert decoded["job_id"] == "dec_1"
    analyzed = session.analyze("st7789", width=32, height=32)
    assert analyzed["command_count"] >= 8
    assert Path(analyzed["commands_path"]).is_file()
    rebuilt = session.reconstruct(
        "st7789",
        width=32,
        height=32,
        save_intermediate_frames=True,
        out_dir=str(tmp_path / "out"),
    )
    assert Path(rebuilt["png"]["final"]).is_file()
    assert len(rebuilt["png"]["intermediate"]) == 2
    status = session.status()
    assert status["latest_decode_job_id"] == "dec_1"
    assert status["decode_jobs"][0]["event_count"] == decoded["event_count"]
    assert status["decode_jobs"][0]["channel_map"]["wr"] == "WR"


def test_two_decode_jobs_and_time_window(tmp_path: Path):
    csv_path = build_st7789_blocks_csv(tmp_path / "cap.csv")
    session = Session()
    session.open(str(csv_path))
    full = session.decode("i8080", DEFAULT_MAP, job_id="lcd")
    early = session.decode("i8080", DEFAULT_MAP, job_id="early", t_max=5e-6)
    assert full["job_id"] == "lcd"
    assert early["event_count"] < full["event_count"]
    assert set(session.decode_jobs) == {"lcd", "early"}
    late_cmds = session.analyze("st7789", width=32, height=32, decode_job_id="lcd")
    early_cmds = session.analyze("st7789", width=32, height=32, decode_job_id="early")
    assert early_cmds["command_count"] < late_cmds["command_count"]


def test_cs_active_high_option_skips_active_low_bus(tmp_path: Path):
    csv_path = build_st7789_blocks_csv(tmp_path / "cap.csv")
    session = Session()
    session.open(str(csv_path))
    inverted = session.decode(
        "i8080", DEFAULT_MAP, options={"cs_active_low": False}, job_id="inv"
    )
    assert inverted["event_count"] == 0
