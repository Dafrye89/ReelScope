from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from shutil import which
from typing import Callable

from frame_extractor import ExtractMeta, ExtractResult, ImageExt


@dataclass(frozen=True)
class ProbeInfo:
    codec_name: str | None
    fps: float | None
    width: int | None
    height: int | None
    source_frame_count: int | None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _format_timestamp_label(timestamp_seconds: float) -> str:
    total_ms = max(0, int(round(timestamp_seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}-{minutes:02d}-{seconds:02d}.{milliseconds:03d}"


def _parse_ratio(value: str | None) -> float | None:
    if not value:
        return None
    if "/" in value:
        num_s, den_s = value.split("/", 1)
        num = float(num_s)
        den = float(den_s)
        if den == 0:
            return None
        return num / den
    parsed = float(value)
    return parsed if parsed > 0 else None


def _expected_output_frames(
    source_frame_count: int | None,
    source_fps: float | None,
    sample_fps: float | None,
) -> int | None:
    if source_frame_count is None or source_frame_count <= 0:
        return None
    if sample_fps is None or source_fps is None or source_fps <= 0 or sample_fps >= source_fps:
        return source_frame_count
    duration_seconds = max(0.0, source_frame_count / source_fps)
    return max(1, int(math.floor(duration_seconds * sample_fps + 1e-9)))


def _jpeg_quality_to_qscale(jpeg_quality: int) -> int:
    quality = max(1, min(100, int(jpeg_quality)))
    return max(2, min(31, round(31 - ((quality - 1) / 99.0) * 29)))


def _source_frame_number_for_output(output_index: int, source_fps: float | None, sample_fps: float | None) -> int:
    if output_index <= 1:
        return 1
    if sample_fps is None or source_fps is None or source_fps <= 0:
        return output_index
    return max(1, round((output_index - 1) * source_fps / sample_fps) + 1)


def _timestamp_seconds_for_output(output_index: int, source_fps: float | None, sample_fps: float | None) -> float:
    if sample_fps is not None and sample_fps > 0:
        return (output_index - 1) / sample_fps
    if source_fps is not None and source_fps > 0:
        return (output_index - 1) / source_fps
    return float(output_index - 1)


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def _stderr_tail(text: str, max_lines: int = 6) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "no details from ffmpeg"
    return " | ".join(lines[-max_lines:])


def _resolve_executable(env_name: str, executable_name: str) -> str:
    configured = os.environ.get(env_name)
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_file():
            raise RuntimeError(f"{env_name} points to a missing file: {configured_path}")
        return str(configured_path)

    discovered = which(executable_name)
    if discovered is None:
        raise RuntimeError(f"{executable_name} must be installed and available on PATH")
    return discovered


def _ensure_ffmpeg_support() -> tuple[str, str]:
    ffmpeg_bin = _resolve_executable("VIDEO_FRAMES_FFMPEG", "ffmpeg")
    ffprobe_bin = _resolve_executable("VIDEO_FRAMES_FFPROBE", "ffprobe")

    hwaccels = _run_command([ffmpeg_bin, "-hide_banner", "-hwaccels"])
    if hwaccels.returncode != 0:
        raise RuntimeError(f"failed to query ffmpeg hardware accelerators: {_stderr_tail(hwaccels.stderr)}")
    if "cuda" not in hwaccels.stdout.lower():
        raise RuntimeError("this ffmpeg build does not report CUDA hardware acceleration")

    return ffmpeg_bin, ffprobe_bin


def _cuda_decoder_for_codec(codec_name: str | None) -> str:
    decoders = {
        "av1": "av1_cuvid",
        "h264": "h264_cuvid",
        "hevc": "hevc_cuvid",
        "mjpeg": "mjpeg_cuvid",
        "mpeg1video": "mpeg1_cuvid",
        "mpeg2video": "mpeg2_cuvid",
        "mpeg4": "mpeg4_cuvid",
        "vc1": "vc1_cuvid",
        "vp8": "vp8_cuvid",
        "vp9": "vp9_cuvid",
    }
    decoder = decoders.get((codec_name or "").lower())
    if decoder is None:
        raise RuntimeError(f"no NVIDIA CUVID decoder is configured for codec: {codec_name or 'unknown'}")
    return decoder


def _probe_video(ffprobe_bin: str, video_path: Path) -> ProbeInfo:
    cmd = [
        ffprobe_bin,
        "-hide_banner",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,avg_frame_rate,r_frame_rate,width,height,nb_frames",
        "-of",
        "json",
        str(video_path),
    ]
    completed = _run_command(cmd)
    if completed.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {_stderr_tail(completed.stderr)}")

    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise RuntimeError("ffprobe found no video stream")
    stream = streams[0]

    fps = _parse_ratio(stream.get("avg_frame_rate")) or _parse_ratio(stream.get("r_frame_rate"))
    width = int(stream.get("width") or 0) or None
    height = int(stream.get("height") or 0) or None
    source_frame_count = int(stream.get("nb_frames") or 0) or None
    return ProbeInfo(
        codec_name=stream.get("codec_name"),
        fps=fps,
        width=width,
        height=height,
        source_frame_count=source_frame_count,
    )


def extract_frames_cuda(
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
    done_marker = frames_dir / ".done"
    if done_marker.exists() and not overwrite:
        return ExtractResult(ok=True, message="already processed (.done exists)", frames_written=0)

    if frames_dir.exists() and overwrite:
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    raw_dir = frames_dir / ".ffmpeg_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    try:
        ffmpeg_bin, ffprobe_bin = _ensure_ffmpeg_support()
        probe = _probe_video(ffprobe_bin, video_path)
        cuda_decoder = _cuda_decoder_for_codec(probe.codec_name)
        applied_sample_fps = sample_fps
        if applied_sample_fps is not None and (probe.fps is None or probe.fps <= 0 or applied_sample_fps >= probe.fps):
            applied_sample_fps = None
        expected_frames = _expected_output_frames(probe.source_frame_count, probe.fps, applied_sample_fps)

        if on_progress is not None:
            on_progress(0, expected_frames)

        filters: list[str] = []
        if applied_sample_fps is not None:
            filters.append(f"fps={applied_sample_fps:g}")

        output_pattern = raw_dir / f"%06d{image_ext}"
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-c:v",
            cuda_decoder,
            "-i",
            str(video_path),
            "-an",
            "-sn",
            "-dn",
            "-start_number",
            "1",
        ]
        if filters:
            cmd.extend(["-vf", ",".join(filters)])
        if image_ext.lower() in {".jpg", ".jpeg"}:
            cmd.extend(["-q:v", str(_jpeg_quality_to_qscale(jpeg_quality))])
        cmd.append(str(output_pattern))

        completed = _run_command(cmd)
        if completed.returncode != 0:
            return ExtractResult(ok=False, message=f"ffmpeg CUDA extract failed: {_stderr_tail(completed.stderr)}")

        raw_files = sorted(p for p in raw_dir.iterdir() if p.is_file() and p.suffix.lower() == image_ext.lower())
        if not raw_files:
            return ExtractResult(ok=False, message="ffmpeg produced no frames", expected_frames=expected_frames)

        frames_written = 0
        for output_index, raw_path in enumerate(raw_files, start=1):
            source_frame_number = _source_frame_number_for_output(output_index, probe.fps, applied_sample_fps)
            if include_timestamps_in_filenames:
                timestamp_label = _format_timestamp_label(
                    _timestamp_seconds_for_output(output_index, probe.fps, applied_sample_fps)
                )
                target_name = f"{source_frame_number:06d}_{timestamp_label}{image_ext}"
            else:
                target_name = f"{source_frame_number:06d}{image_ext}"
            raw_path.rename(frames_dir / target_name)
            frames_written += 1
            if on_progress is not None and frames_written % 10 == 0:
                on_progress(frames_written, expected_frames)

        if on_progress is not None:
            on_progress(frames_written, expected_frames)

        if frames_written == 0:
            return ExtractResult(ok=False, message="no frames read", frames_written=0, expected_frames=expected_frames)

        meta = ExtractMeta(
            source=str(video_path),
            source_size_bytes=video_path.stat().st_size,
            source_mtime_utc=datetime.fromtimestamp(video_path.stat().st_mtime, tz=timezone.utc).isoformat(
                timespec="seconds"
            ),
            processed_utc=_utc_now_iso(),
            fps=probe.fps,
            source_frame_count=probe.source_frame_count,
            width=probe.width,
            height=probe.height,
            expected_frames=expected_frames if expected_frames is not None else frames_written,
            frames_written=frames_written,
            image_ext=image_ext,
            jpeg_quality=jpeg_quality if image_ext.lower() in {".jpg", ".jpeg"} else None,
            requested_sample_fps=applied_sample_fps,
        )
        done_marker.write_text("ok\n", encoding="utf-8")
        return ExtractResult(
            ok=True,
            message="processed with ffmpeg cuda",
            frames_written=frames_written,
            expected_frames=meta.expected_frames,
            meta=meta,
        )
    except Exception as e:  # noqa: BLE001
        return ExtractResult(ok=False, message=str(e))
    finally:
        if raw_dir.exists():
            shutil.rmtree(raw_dir, ignore_errors=True)
