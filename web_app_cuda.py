from __future__ import annotations

import os
from pathlib import Path

import web_app as base

from frame_extractor_cuda import extract_frames_cuda


def _extract_job_cuda(job_id: str, video_path: Path, original_filename: str, image_ext: str, sample_fps: float | None) -> None:
    base._update_job(job_id, state="running", image_ext=image_ext, sample_fps=sample_fps)

    def on_progress(written: int, expected: int | None) -> None:
        base._update_job(job_id, frames_written=written, expected_frames=expected)

    try:
        result = extract_frames_cuda(
            video_path=video_path,
            frames_dir=base._frames_dir(job_id),
            image_ext=image_ext,  # type: ignore[arg-type]
            jpeg_quality=95,
            sample_fps=sample_fps,
            include_timestamps_in_filenames=True,
            overwrite=True,
            on_progress=on_progress,
        )
        if not result.ok:
            base._update_job(job_id, state="error", error=result.message)
            return

        base._write_meta(job_id, result, original_filename)
        base._update_job(
            job_id,
            state="done",
            frames_written=result.frames_written,
            expected_frames=result.expected_frames,
        )
    except Exception as e:  # noqa: BLE001
        base._update_job(job_id, state="error", error=str(e))


base._extract_job = _extract_job_cuda


def main() -> None:
    base.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("VIDEO_FRAMES_PORT", "8003"))
    base.app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
