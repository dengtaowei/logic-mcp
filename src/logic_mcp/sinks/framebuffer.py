from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from logic_mcp.devices.profile import PanelProfile
from logic_mcp.messages import FRAMEBUFFER_SCHEMA, Artifact, Message
from logic_mcp.reconstruct.framebuffer import ReconstructResult, reconstruct


class FramebufferSink:
    id = "framebuffer"
    schema = FRAMEBUFFER_SCHEMA

    def run(
        self,
        messages: Iterable[Message],
        profile: PanelProfile,
        dest: Path,
        stem: str,
        job_id: str,
        save_intermediate_frames: bool = True,
        max_intermediate_frames: int = 32,
    ) -> tuple[ReconstructResult, list[Artifact]]:
        from PIL import Image

        result = reconstruct(messages, profile)
        dest.mkdir(parents=True, exist_ok=True)

        def write_png(name: str, blob: bytes) -> str:
            image = Image.frombytes("RGB", (result.width, result.height), blob)
            path = dest / name
            image.save(path)
            return str(path.resolve())

        artifacts = [
            Artifact(
                kind="png",
                path=write_png(f"{stem}_frame_final.png", result.final),
                schema=self.schema,
                job_id=job_id,
                extra={"role": "final", "width": result.width, "height": result.height},
            )
        ]
        if save_intermediate_frames:
            for i, blob in enumerate(result.frames[:max_intermediate_frames]):
                artifacts.append(
                    Artifact(
                        kind="png",
                        path=write_png(f"{stem}_frame_{i:03d}.png", blob),
                        schema=self.schema,
                        job_id=job_id,
                        extra={"role": "intermediate", "index": i},
                    )
                )
        return result, artifacts
