from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from logic_mcp.devices.dcs import aggregate_dcs_commands
from logic_mcp.messages import COMMANDS_SCHEMA, Artifact, Message


class CommandLogSink:
    id = "command_log"
    schema = COMMANDS_SCHEMA

    def collect(self, messages: Iterable[Message]) -> list[dict]:
        return aggregate_dcs_commands(messages)

    def write(
        self,
        messages: Iterable[Message],
        path: Path,
        job_id: str,
    ) -> tuple[list[dict], Artifact]:
        rows = self.collect(messages)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        return rows, Artifact(
            kind="jsonl",
            path=str(path.resolve()),
            schema=self.schema,
            job_id=job_id,
            extra={"row_count": len(rows)},
        )
