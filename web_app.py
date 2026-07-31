from __future__ import annotations

import io
import json
import math
import os
import re
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from frame_extractor import ExtractResult, extract_frames


JobState = Literal["queued", "running", "done", "error"]


@dataclass
class Job:
    id: str
    state: JobState
    created_utc: str
    filename: str
    error: str | None = None
    frames_written: int = 0
    expected_frames: int | None = None
    image_ext: str = ".jpg"
    sample_fps: float | None = None


APP_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
DATA_DIR = Path(os.environ.get("VIDEO_FRAMES_DATA_DIR", str(APP_DIR / "web_data"))).resolve()
JOBS_DIR = DATA_DIR / "jobs"


def _read_max_upload_mb() -> int | None:
    raw = os.environ.get("VIDEO_FRAMES_MAX_UPLOAD_MB", "").strip()
    if not raw:
        return None
    value = int(raw)
    return value if value > 0 else None


MAX_UPLOAD_MB = _read_max_upload_mb()
MAX_UPLOAD_LABEL = "Unlimited" if MAX_UPLOAD_MB is None else f"{MAX_UPLOAD_MB} MB"

ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".webm", ".mpeg", ".mpg"}
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")

executor = ThreadPoolExecutor(max_workers=int(os.environ.get("VIDEO_FRAMES_WORKERS", "1")))
jobs: dict[str, Job] = {}
jobs_lock = threading.Lock()


app = Flask(
    __name__,
    template_folder=str(RESOURCE_DIR / "templates"),
    static_folder=str(RESOURCE_DIR / "assets"),
    static_url_path="/assets",
)
if MAX_UPLOAD_MB is not None:
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _frames_dir(job_id: str) -> Path:
    return _job_dir(job_id) / "frames"


def _meta_path(job_id: str) -> Path:
    return _job_dir(job_id) / "meta.json"


def _set_job(job: Job) -> None:
    with jobs_lock:
        jobs[job.id] = job


def _get_job(job_id: str) -> Job | None:
    with jobs_lock:
        cached = jobs.get(job_id)
    if cached is not None:
        return cached

    restored = _job_from_disk(job_id)
    if restored is not None:
        _set_job(restored)
    return restored


def _update_job(job_id: str, **kwargs) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)


def _validate_job_id(job_id: str) -> bool:
    return bool(JOB_ID_RE.match(job_id))


def _save_upload(file: FileStorage, job_id: str) -> tuple[Path, str]:
    original_name = secure_filename(file.filename or "upload")
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        raise ValueError(f"unsupported file type: {ext}")
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / f"upload{ext}"
    file.save(dest)
    return dest, original_name


def _list_frames(job_id: str) -> list[str]:
    frames_dir = _frames_dir(job_id)
    if not frames_dir.exists():
        return []
    allowed = {".jpg", ".jpeg", ".png"}
    files: list[Path] = [p for p in frames_dir.iterdir() if p.is_file() and p.suffix.lower() in allowed]
    files.sort(key=lambda p: p.name)
    return [p.name for p in files]


def _representative_frame(job_id: str) -> str | None:
    frames_dir = _frames_dir(job_id)
    if not frames_dir.exists():
        return None
    allowed = {".jpg", ".jpeg", ".png"}
    for path in frames_dir.iterdir():
        if path.is_file() and path.suffix.lower() in allowed:
            return path.name
    return None


def _write_meta(job_id: str, result: ExtractResult, original_filename: str) -> None:
    meta = {
        "job_id": job_id,
        "original_filename": original_filename,
        "created_utc": _get_job(job_id).created_utc if _get_job(job_id) else _utc_now_iso(),
        "result": asdict(result.meta) if result.meta is not None else None,
    }
    _meta_path(job_id).write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")


def _read_meta(job_id: str) -> dict | None:
    meta_path = _meta_path(job_id)
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _job_from_disk(job_id: str) -> Job | None:
    if not _validate_job_id(job_id):
        return None
    meta = _read_meta(job_id)
    if not isinstance(meta, dict):
        return None
    result = meta.get("result")
    if not isinstance(result, dict):
        return None

    raw_frames_written = result.get("frames_written")
    try:
        frames_written = int(raw_frames_written)
    except (TypeError, ValueError):
        frames_written = 0
    if frames_written <= 0:
        frames_written = len(_list_frames(job_id))
    if frames_written == 0:
        return None
    expected = result.get("expected_frames")
    try:
        expected_frames = int(expected) if expected is not None else frames_written
    except (TypeError, ValueError):
        expected_frames = frames_written
    sample_fps = result.get("requested_sample_fps")
    try:
        parsed_sample_fps = float(sample_fps) if sample_fps is not None else None
    except (TypeError, ValueError):
        parsed_sample_fps = None

    return Job(
        id=job_id,
        state="done",
        created_utc=str(meta.get("created_utc") or result.get("processed_utc") or _utc_now_iso()),
        filename=str(meta.get("original_filename") or "video"),
        frames_written=frames_written,
        expected_frames=expected_frames,
        image_ext=str(result.get("image_ext") or ".jpg"),
        sample_fps=parsed_sample_fps,
    )


def _job_payload(job: Job, *, include_frames: bool) -> dict:
    payload = asdict(job)
    frames = _list_frames(job.id) if include_frames and job.state == "done" else []
    payload["frames_count"] = len(frames) if include_frames else job.frames_written
    payload["source_fps"] = _source_fps(job.id)
    result = _meta_result(job.id) or {}
    payload["width"] = result.get("width")
    payload["height"] = result.get("height")
    payload["source_frame_count"] = result.get("source_frame_count")
    payload["source_size_bytes"] = result.get("source_size_bytes")
    payload["processed_utc"] = result.get("processed_utc")
    if include_frames and frames:
        payload["thumbnail"] = frames[min(len(frames) - 1, len(frames) // 2)]
    elif job.state == "done":
        payload["thumbnail"] = _representative_frame(job.id)
    if include_frames:
        payload["frames"] = frames
    return payload


def _meta_result(job_id: str) -> dict | None:
    meta = _read_meta(job_id)
    if not isinstance(meta, dict):
        return None
    result = meta.get("result")
    return result if isinstance(result, dict) else None


def _source_fps(job_id: str) -> float | None:
    result = _meta_result(job_id)
    if result is None:
        return None
    fps = result.get("fps")
    try:
        value = float(fps)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _requested_sample_fps(job_id: str) -> float | None:
    result = _meta_result(job_id)
    if result is None:
        return None
    sample_fps = result.get("requested_sample_fps")
    try:
        value = float(sample_fps)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _frame_source_number(filename: str) -> int | None:
    match = re.match(r"^(\d+)", Path(filename).stem)
    if match is None:
        return None
    return int(match.group(1))


def _parse_sample_fps(value: str | None) -> float | None:
    if value is None:
        return None
    raw = value.strip().lower()
    if not raw or raw == "all":
        return None
    parsed = float(raw)
    if parsed <= 0:
        raise ValueError("sample_fps must be greater than 0")
    return parsed


def _select_sampled_frames(
    frames: list[str],
    source_fps: float | None,
    sample_fps: float | None,
    extracted_sample_fps: float | None,
) -> list[str]:
    if not frames or sample_fps is None:
        return frames
    if source_fps is None or source_fps <= 0:
        raise ValueError("source fps is unavailable for sampled downloads")
    if extracted_sample_fps is not None and sample_fps >= extracted_sample_fps:
        return frames
    if extracted_sample_fps is None and sample_fps >= source_fps:
        return frames

    indexed_frames: list[tuple[str, int]] = []
    for fname in frames:
        source_number = _frame_source_number(fname)
        if source_number is None:
            raise ValueError("frame filenames do not contain source frame numbers")
        indexed_frames.append((fname, max(0, source_number - 1)))

    indexed_frames.sort(key=lambda item: item[1])
    duration_seconds = indexed_frames[-1][1] / source_fps
    sample_count = int(math.floor(duration_seconds * sample_fps + 1e-9)) + 1

    selected: list[str] = []
    cursor = 0
    for sample_index in range(sample_count):
        target_source_index = max(0, round((sample_index / sample_fps) * source_fps))
        while cursor + 1 < len(indexed_frames) and indexed_frames[cursor + 1][1] <= target_source_index:
            cursor += 1

        best_index = cursor
        if cursor + 1 < len(indexed_frames):
            prev_distance = abs(indexed_frames[cursor][1] - target_source_index)
            next_distance = abs(indexed_frames[cursor + 1][1] - target_source_index)
            if next_distance < prev_distance:
                best_index = cursor + 1

        selected_name = indexed_frames[best_index][0]
        if selected and selected[-1] == selected_name:
            continue
        selected.append(selected_name)
    return selected


def _extract_job(job_id: str, video_path: Path, original_filename: str, image_ext: str, sample_fps: float | None) -> None:
    _update_job(job_id, state="running", image_ext=image_ext, sample_fps=sample_fps)

    def on_progress(written: int, expected: int | None) -> None:
        _update_job(job_id, frames_written=written, expected_frames=expected)

    try:
        result = extract_frames(
            video_path=video_path,
            frames_dir=_frames_dir(job_id),
            image_ext=image_ext,  # type: ignore[arg-type]
            jpeg_quality=95,
            sample_fps=sample_fps,
            include_timestamps_in_filenames=True,
            overwrite=True,
            on_progress=on_progress,
        )
        if not result.ok:
            _update_job(job_id, state="error", error=result.message)
            return

        _write_meta(job_id, result, original_filename)
        _update_job(
            job_id,
            state="done",
            frames_written=result.frames_written,
            expected_frames=result.expected_frames,
        )
    except Exception as e:  # noqa: BLE001
        _update_job(job_id, state="error", error=str(e))


@app.get("/")
def index():
    return render_template(
        "index.html",
        max_upload_label=MAX_UPLOAD_LABEL,
        engine_label=os.environ.get("VIDEO_FRAMES_ENGINE", "CPU").upper(),
    )


@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(_error: RequestEntityTooLarge):
    message = f"upload too large; current limit is {MAX_UPLOAD_LABEL}"
    if request.path.startswith("/api/"):
        return jsonify({"error": message}), 413
    return message, 413


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.post("/api/jobs")
def create_job():
    file = request.files.get("video")
    if file is None or not isinstance(file, FileStorage) or not file.filename:
        return jsonify({"error": "missing file field 'video'"}), 400

    image_ext = request.form.get("image_ext", ".jpg").lower()
    if image_ext not in {".jpg", ".jpeg", ".png"}:
        return jsonify({"error": "image_ext must be .jpg, .jpeg, or .png"}), 400
    try:
        sample_fps = _parse_sample_fps(request.form.get("sample_fps"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    job_id = uuid4().hex
    created = _utc_now_iso()
    _set_job(Job(id=job_id, state="queued", created_utc=created, filename="", image_ext=image_ext, sample_fps=sample_fps))

    try:
        video_path, original_name = _save_upload(file, job_id)
        _update_job(job_id, filename=original_name)
    except Exception as e:  # noqa: BLE001
        _update_job(job_id, state="error", error=str(e))
        return jsonify({"error": str(e)}), 400

    executor.submit(_extract_job, job_id, video_path, original_name, image_ext, sample_fps)
    return jsonify({"job_id": job_id})


@app.get("/api/jobs")
def list_jobs():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    restored: list[Job] = []
    for path in JOBS_DIR.iterdir():
        if not path.is_dir() or not _validate_job_id(path.name):
            continue
        job = _get_job(path.name)
        if job is not None:
            restored.append(job)

    with jobs_lock:
        active = list(jobs.values())
    by_id = {job.id: job for job in [*restored, *active]}
    ordered = sorted(by_id.values(), key=lambda item: item.created_utc, reverse=True)
    return jsonify({"jobs": [_job_payload(job, include_frames=False) for job in ordered]})


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    if not _validate_job_id(job_id):
        return jsonify({"error": "invalid job id"}), 404
    job = _get_job(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404

    return jsonify(_job_payload(job, include_frames=job.state == "done"))


@app.get("/api/jobs/<job_id>/debug")
def get_job_debug(job_id: str):
    if not _validate_job_id(job_id):
        return jsonify({"error": "invalid job id"}), 404
    job = _get_job(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404
    frames = _list_frames(job_id)
    sample = {"first": frames[0] if frames else None, "last": frames[-1] if frames else None}
    return jsonify(
        {
            "job": asdict(job),
            "job_dir": str(_job_dir(job_id)),
            "frames_dir": str(_frames_dir(job_id)),
            "frames_listed": len(frames),
            "sample": sample,
            "meta_exists": _meta_path(job_id).exists(),
        }
    )


@app.get("/jobs/<job_id>/frames/<path:filename>")
def serve_frame(job_id: str, filename: str):
    if not _validate_job_id(job_id):
        return "not found", 404
    job = _get_job(job_id)
    if job is None:
        return "not found", 404
    frames_dir = _frames_dir(job_id)
    return send_from_directory(frames_dir, filename, conditional=True)


@app.get("/api/jobs/<job_id>/frame/<int:index>/download.png")
def download_frame_png(job_id: str, index: int):
    if not _validate_job_id(job_id):
        return jsonify({"error": "invalid job id"}), 404
    job = _get_job(job_id)
    if job is None or job.state != "done":
        return jsonify({"error": "job not ready"}), 400

    frames = _list_frames(job_id)
    if index < 0 or index >= len(frames):
        return jsonify({"error": "frame index out of range"}), 400

    src = _frames_dir(job_id) / frames[index]

    try:
        from PIL import Image
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"missing dependency: pillow ({e})"}), 500

    with Image.open(src) as im:
        out = io.BytesIO()
        im.save(out, format="PNG", optimize=True)
        out.seek(0)

    base = Path(job.filename).stem if job.filename else "frame"
    download_name = f"{base}_{Path(frames[index]).stem}.png"
    return send_file(out, mimetype="image/png", as_attachment=True, download_name=download_name)


@app.get("/api/jobs/<job_id>/download.zip")
def download_all_zip(job_id: str):
    if not _validate_job_id(job_id):
        return jsonify({"error": "invalid job id"}), 404
    job = _get_job(job_id)
    if job is None or job.state != "done":
        return jsonify({"error": "job not ready"}), 400

    fmt = request.args.get("format", "jpg").lower()
    if fmt not in {"jpg", "png"}:
        return jsonify({"error": "format must be jpg or png"}), 400
    try:
        sample_fps = _parse_sample_fps(request.args.get("sample_fps"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    frames = _list_frames(job_id)
    if not frames:
        return jsonify({"error": "no frames"}), 400
    try:
        selected_frames = _select_sampled_frames(
            frames,
            _source_fps(job_id),
            sample_fps,
            _requested_sample_fps(job_id),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    zip_buf = io.BytesIO()
    base = Path(job.filename).stem if job.filename else job_id
    rate_label = "all" if sample_fps is None else f"{sample_fps:g}fps"
    zip_name = f"{base}_{rate_label}_frames.zip"

    pil = None
    if fmt == "png":
        try:
            from PIL import Image
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": f"missing dependency: pillow ({e})"}), 500
        pil = Image

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        meta = _meta_path(job_id)
        if meta.exists():
            z.write(meta, arcname=f"{base}/meta.json")

        for fname in selected_frames:
            src = _frames_dir(job_id) / fname
            if fmt == "jpg":
                z.write(src, arcname=f"{base}/frames/{fname}")
                continue

            with pil.open(src) as im:  # type: ignore[union-attr]
                out = io.BytesIO()
                im.save(out, format="PNG", optimize=True)
                z.writestr(f"{base}/frames/{Path(fname).stem}.png", out.getvalue())

    zip_buf.seek(0)
    return send_file(zip_buf, mimetype="application/zip", as_attachment=True, download_name=zip_name)


def main() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=8002, debug=False, threaded=True)


if __name__ == "__main__":
    main()
