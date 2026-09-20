from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class PanelProfile:
    id: str
    controller: str
    title: str
    width: int
    height: int
    col_offset: int = 0
    row_offset: int = 0
    default_colmod: int = 0x05
    default_madctl: int = 0x00
    driver: str = "mipi_dcs"
    commands: dict[int, str] = field(default_factory=dict)
    notes: str = ""

    def override(
        self,
        width: int | None = None,
        height: int | None = None,
        col_offset: int | None = None,
        row_offset: int | None = None,
        default_colmod: int | None = None,
        default_madctl: int | None = None,
    ) -> "PanelProfile":
        clone = deepcopy(self)
        if width is not None:
            clone.width = width
        if height is not None:
            clone.height = height
        if col_offset is not None:
            clone.col_offset = col_offset
        if row_offset is not None:
            clone.row_offset = row_offset
        if default_colmod is not None:
            clone.default_colmod = default_colmod
        if default_madctl is not None:
            clone.default_madctl = default_madctl
        return clone
