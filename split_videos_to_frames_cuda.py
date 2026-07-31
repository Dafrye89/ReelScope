from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from frame_extractor_cuda import extract_frames_cuda


VIDEO_EXTS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".m4v",
    ".wmv",
    ".flv",
    ".webm",
    ".mpeg",
    ".mpg",
}


def _safe_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[<>:"/\\\\|?*]+', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name or "video"


def _unique_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    for i in range(1, 10_000):
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find a unique destination for: {dest}")


@dataclass(frozen=True)
class ProcessResult:
    ok: bool
    frames_written: int = 0
    message: str = ""


def _iter_videos(input_dir: Path, recursive: bool) -> list[Path]:
    if recursive:
        paths = [p for p in input_dir.rglob("*") if p.is_file()]
    else:
        paths = [p for p in input_dir.glob("*") if p.is_file()]
    return [p for p in paths if p.suffix.lower() in VIDEO_EXTS]


def _output_dir_for_video(
    video_path: Path, input_dir: Path, output_dir: Path, preserve_subdirs: bool
) -> Path:
    rel = video_path.relative_to(input_dir)
    safe_stem = _safe_name(video_path.stem)
    if preserve_subdirs:
        return output_dir / rel.parent / safe_stem
    return output_dir / safe_stem


def _archive_dest_for_video(video_path: Path, input_dir: Path, archive_dir: Path) -> Path:
    rel = video_path.relative_to(input_dir)
    return archive_dir / rel


def _write_meta(meta_path: Path, meta: dict) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")


def _read_video_frames_cuda(
    video_path: Path,
    frames_dir: Path,
    image_ext: str,
    jpeg_quality: int,
    sample_fps: float | None,
    timestamp_names: bool,
    overwrite: bool,
) -> ProcessResult:
    done_marker = frames_dir / ".done"
    meta_path = frames_dir / "meta.json"

    if done_marker.exists() and not overwrite:
        return ProcessResult(ok=True, frames_written=0, message="already processed (.done exists)")

    result = extract_frames_cuda(
        video_path=video_path,
        frames_dir=frames_dir,
        image_ext=image_ext,  # type: ignore[arg-type]
        jpeg_quality=jpeg_quality,
        sample_fps=sample_fps,
        include_timestamps_in_filenames=timestamp_names,
        overwrite=overwrite,
    )
    if not result.ok:
        return ProcessResult(ok=False, frames_written=result.frames_written, message=result.message)

    if result.meta is not None:
        meta = {
            "source": result.meta.source,
            "source_size_bytes": result.meta.source_size_bytes,
            "source_mtime_utc": result.meta.source_mtime_utc,
            "processed_utc": result.meta.processed_utc,
            "fps": result.meta.fps,
            "source_frame_count": result.meta.source_frame_count,
            "width": result.meta.width,
            "height": result.meta.height,
            "expected_frames": result.meta.expected_frames,
            "frames_written": result.meta.frames_written,
            "image_ext": result.meta.image_ext,
            "jpeg_quality": result.meta.jpeg_quality,
            "requested_sample_fps": result.meta.requested_sample_fps,
            "extractor": "ffmpeg-cuda",
        }
        _write_meta(meta_path, meta)

    return ProcessResult(ok=True, frames_written=result.frames_written, message=result.message)


def _archive_video(video_path: Path, dest_path: Path, dry_run: bool) -> tuple[bool, str]:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    final_dest = _unique_path(dest_path)

    if dry_run:
        return True, f"dry-run: would move to {final_dest}"

    try:
        shutil.move(str(video_path), str(final_dest))
        return True, f"moved to {final_dest}"
    except Exception as e:  # noqa: BLE001
        return False, f"failed to archive: {e}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split videos into frames with ffmpeg CUDA decode, then archive processed videos."
    )
    parser.add_argument(
        "-i",
        "--input",
        default="input_cuda",
        help="Input folder containing videos (default: ./input_cuda)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output_cuda",
        help="Output folder for frames (default: ./output_cuda)",
    )
    parser.add_argument(
        "-a",
        "--archive",
        default="archive_cuda",
        help="Archive folder for processed videos (default: ./archive_cuda)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not search input folder recursively",
    )
    parser.add_argument(
        "--no-preserve-subdirs",
        action="store_true",
        help="Do not preserve input subfolders under output; only create per-video folders",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output for a video even if it already exists",
    )
    parser.add_argument(
        "--image-ext",
        default=".jpg",
        choices=[".jpg", ".jpeg", ".png"],
        help="Frame image extension (default: .jpg)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=95,
        help="JPEG quality (1-100). Only used for .jpg/.jpeg (default: 95)",
    )
    parser.add_argument(
        "--sample-fps",
        type=float,
        default=None,
        help="Optional output frame rate, for example 1 for one frame per second",
    )
    parser.add_argument(
        "--timestamp-names",
        action="store_true",
        help="Add video timestamps to output filenames",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write frames or move videos; just report what would happen",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    archive_dir = Path(args.archive).resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"ERROR: input dir not found: {input_dir}", file=sys.stderr)
        return 2

    image_ext = args.image_ext.lower()
    jpeg_quality = int(args.jpeg_quality)
    if image_ext in {".jpg", ".jpeg"} and not (1 <= jpeg_quality <= 100):
        print("ERROR: --jpeg-quality must be 1..100", file=sys.stderr)
        return 2
    if args.sample_fps is not None and args.sample_fps <= 0:
        print("ERROR: --sample-fps must be greater than 0", file=sys.stderr)
        return 2

    videos = _iter_videos(input_dir, recursive=not args.no_recursive)
    videos.sort()
    if not videos:
        print(f"No videos found in {input_dir}")
        return 0

    preserve_subdirs = not args.no_preserve_subdirs
    any_fail = False

    print(f"Found {len(videos)} video(s) under {input_dir}")
    for video_path in videos:
        frames_dir = _output_dir_for_video(video_path, input_dir, output_dir, preserve_subdirs)
        archive_dest = _archive_dest_for_video(video_path, input_dir, archive_dir)

        print(f"\nVideo: {video_path}")
        print(f"Frames: {frames_dir}")
        print(f"Archive: {archive_dest}")

        if args.dry_run:
            print("dry-run: would extract frames with ffmpeg CUDA and archive")
            continue

        result = _read_video_frames_cuda(
            video_path=video_path,
            frames_dir=frames_dir,
            image_ext=image_ext,
            jpeg_quality=jpeg_quality,
            sample_fps=args.sample_fps,
            timestamp_names=args.timestamp_names,
            overwrite=args.overwrite,
        )
        if not result.ok:
            any_fail = True
            print(f"ERROR: {result.message}", file=sys.stderr)
            continue
        print(f"OK: {result.message}; frames_written={result.frames_written}")

        ok, msg = _archive_video(video_path, archive_dest, dry_run=False)
        if not ok:
            any_fail = True
            print(f"ERROR: {msg}", file=sys.stderr)
            continue
        print(f"OK: {msg}")

    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
