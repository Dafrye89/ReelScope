from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal


ImageExt = Literal[".jpg", ".jpeg", ".png"]


@dataclass(frozen=True)
class ExtractMeta:
    source: str
    source_size_bytes: int
    source_mtime_utc: str
    processed_utc: str
    fps: float | None
    source_frame_count: int | None
    width: int | None
    height: int | None
    expected_frames: int | None
    frames_written: int
    image_ext: str
    jpeg_quality: int | None
    requested_sample_fps: float | None


@dataclass(frozen=True)
class ExtractResult:
    ok: bool
    message: str
    frames_written: int = 0
    expected_frames: int | None = None
    meta: ExtractMeta | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _format_timestamp_label(timestamp_seconds: float) -> str:
    total_ms = max(0, int(round(timestamp_seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}-{minutes:02d}-{seconds:02d}.{milliseconds:03d}"


def _frame_filename(frame_number: int, image_ext: str, fps: float | None, include_timestamp: bool) -> str:
    if not include_timestamp or fps is None or fps <= 0:
        return f"{frame_number:06d}{image_ext}"
    timestamp_seconds = (frame_number - 1) / fps
    timestamp_label = _format_timestamp_label(timestamp_seconds)
    return f"{frame_number:06d}_{timestamp_label}{image_ext}"


def _expected_output_frames(
    source_frame_count: int | None,
    source_fps: float | None,
    sample_fps: float | None,
) -> int | None:
    if source_frame_count is None or source_frame_count <= 0:
        return None
    if sample_fps is None or source_fps is None or source_fps <= 0 or sample_fps >= source_fps:
        return source_frame_count
    duration_seconds = max(0.0, (source_frame_count - 1) / source_fps)
    return int(math.floor(duration_seconds * sample_fps + 1e-9)) + 1


def extract_frames(
    *,
    video_path: Path,
    frames_dir: Path,
    image_ext: ImageExt = ".jpg",
    jpeg_quality: int = 95,
    sample_fps: float | None = None,
    include_timestamps_in_filenames: bool = False,
    overwrite: bool = False,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> ExtractResult:
    """
    Extracts frames into `frames_dir` as 000001.jpg/png etc.

    If `overwrite` is False and `.done` exists in `frames_dir`, returns early.
    """
    try:
        import cv2  # type: ignore
    except Exception as e:  # noqa: BLE001
        return ExtractResult(ok=False, message=f"missing dependency: opencv-python ({e})")

    done_marker = frames_dir / ".done"
    if done_marker.exists() and not overwrite:
        return ExtractResult(ok=True, message="already processed (.done exists)", frames_written=0)

    if frames_dir.exists() and overwrite:
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return ExtractResult(ok=False, message="could not open video")

    fps = cap.get(cv2.CAP_PROP_FPS) or None
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or None
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or None
    source_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) or None
    source_fps = float(fps) if fps is not None else None
    expected_frames = _expected_output_frames(source_frame_count, source_fps, sample_fps)

    frames_written = 0
    encode_params: list[int] = []
    if image_ext.lower() in {".jpg", ".jpeg"}:
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)]

    save_all_frames = sample_fps is None or source_fps is None or source_fps <= 0 or sample_fps >= source_fps
    sample_interval_seconds = None if save_all_frames else 1.0 / sample_fps
    half_frame_seconds = None if save_all_frames else 0.5 / source_fps

    def report() -> None:
        if on_progress is not None:
            on_progress(frames_written, expected_frames)

    try:
        source_frame_number = 1
        next_target_seconds = 0.0
        report()
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            should_write = save_all_frames
            if not save_all_frames:
                current_seconds = (source_frame_number - 1) / source_fps
                threshold_seconds = current_seconds + half_frame_seconds
                if threshold_seconds >= next_target_seconds:
                    should_write = True
                    while threshold_seconds >= next_target_seconds:
                        next_target_seconds += sample_interval_seconds

            if should_write:
                filename = _frame_filename(
                    source_frame_number,
                    image_ext,
                    source_fps,
                    include_timestamps_in_filenames,
                )
                out_path = frames_dir / filename

                if image_ext.lower() in {".jpg", ".jpeg"}:
                    ok2, buf = cv2.imencode(image_ext, frame, encode_params)
                else:
                    ok2, buf = cv2.imencode(image_ext, frame)
                if not ok2:
                    return ExtractResult(ok=False, message="failed to encode frame", frames_written=frames_written)
                out_path.write_bytes(buf.tobytes())

                frames_written += 1
                report()
            elif source_frame_number % 30 == 0:
                report()
            source_frame_number += 1
        report()
    finally:
        cap.release()

    if frames_written == 0:
        return ExtractResult(ok=False, message="no frames read", frames_written=0, expected_frames=expected_frames)

    meta = ExtractMeta(
        source=str(video_path),
        source_size_bytes=video_path.stat().st_size,
        source_mtime_utc=datetime.fromtimestamp(video_path.stat().st_mtime, tz=timezone.utc).isoformat(
            timespec="seconds"
        ),
        processed_utc=_utc_now_iso(),
        fps=source_fps,
        source_frame_count=source_frame_count,
        width=width,
        height=height,
        expected_frames=expected_frames,
        frames_written=frames_written,
        image_ext=image_ext,
        jpeg_quality=jpeg_quality if image_ext.lower() in {".jpg", ".jpeg"} else None,
        requested_sample_fps=sample_fps,
    )
    done_marker.write_text("ok\n", encoding="utf-8")

    return ExtractResult(
        ok=True,
        message="processed",
        frames_written=frames_written,
        expected_frames=expected_frames,
        meta=meta,
    )
