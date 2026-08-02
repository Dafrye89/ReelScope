from __future__ import annotations

import io
import hmac
import json
import math
import os
import re
import secrets
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Literal
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, g, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from auth_store import AuthStore, User
from elevenlabs_transcriber import available_models as available_elevenlabs_models
from elevenlabs_transcriber import default_settings as default_elevenlabs_settings
from elevenlabs_transcriber import transcribe_to_srt as transcribe_with_elevenlabs
from elevenlabs_transcriber import validate_api_key as validate_elevenlabs_api_key
from elevenlabs_transcriber import validate_settings as validate_elevenlabs_settings
from frame_extractor import ExtractResult, extract_frames
from transcriber import MODELS as TRANSCRIPTION_MODELS
from transcriber import available_models, transcribe_to_srt
from transcript_store import read_srt, update_cue_text, write_srt


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
MODEL_CACHE_DIR = DATA_DIR / "models"


def _load_or_create_credential_cipher() -> Fernet:
    configured = os.environ.get("REELSCOPE_CREDENTIAL_KEY", "").strip()
    if configured:
        return Fernet(configured.encode("ascii"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_path = DATA_DIR / ".credential_key"
    if key_path.is_file():
        return Fernet(key_path.read_bytes().strip())
    generated = Fernet.generate_key()
    key_path.write_bytes(generated)
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return Fernet(generated)


auth_store = AuthStore(DATA_DIR / "reelscope.sqlite3")
credential_cipher = _load_or_create_credential_cipher()


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
transcription_executor = ThreadPoolExecutor(max_workers=int(os.environ.get("REELSCOPE_TRANSCRIPTION_WORKERS", "1")))
AUTO_TRANSCRIPTION_MODEL = os.environ.get("REELSCOPE_AUTO_TRANSCRIBE_MODEL", "whisper-turbo")
jobs: dict[str, Job] = {}
jobs_lock = threading.Lock()


app = Flask(
    __name__,
    template_folder=str(RESOURCE_DIR / "templates"),
    static_folder=str(RESOURCE_DIR / "assets"),
    static_url_path="/assets",
)


def _load_or_create_session_key() -> str:
    configured = os.environ.get("REELSCOPE_SESSION_SECRET", "").strip()
    if configured:
        return configured
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_path = DATA_DIR / ".session_key"
    if key_path.is_file():
        existing = key_path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    generated = secrets.token_urlsafe(48)
    key_path.write_text(generated, encoding="utf-8")
    return generated


app.secret_key = _load_or_create_session_key()
if MAX_UPLOAD_MB is not None:
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("REELSCOPE_SECURE_COOKIES", "0") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 14
app.jinja_env.auto_reload = True


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = _csrf_token


@app.before_request
def load_user_and_validate_request():
    user_id = session.get("user_id")
    g.user = auth_store.get_user(int(user_id)) if isinstance(user_id, int) else None
    if g.user is None and user_id is not None:
        session.clear()

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not isinstance(supplied, str) or not isinstance(expected, str) or not hmac.compare_digest(supplied, expected):
            if request.path.startswith("/api/"):
                return jsonify({"error": "invalid request token; refresh the page and try again"}), 400
            return "invalid request token; refresh the page and try again", 400
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/") or request.path.startswith("/jobs/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
        return view(*args, **kwargs)

    return wrapped


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _frames_dir(job_id: str) -> Path:
    return _job_dir(job_id) / "frames"


def _meta_path(job_id: str) -> Path:
    return _job_dir(job_id) / "meta.json"


def _video_path(job_id: str) -> Path | None:
    job_dir = _job_dir(job_id)
    if not job_dir.is_dir():
        return None
    for path in job_dir.iterdir():
        if path.is_file() and path.stem == "upload" and path.suffix.lower() in ALLOWED_VIDEO_EXTS:
            return path
    return None


def _transcription_status_path(job_id: str) -> Path:
    return _job_dir(job_id) / "transcription.json"


def _transcript_path(job_id: str) -> Path:
    return _job_dir(job_id) / "transcript.srt"


def _default_account_transcription_settings() -> dict:
    return {
        "provider": "local",
        "local": {"model": "whisper-turbo", "language": "auto"},
        "elevenlabs": default_elevenlabs_settings(),
    }


def _account_transcription_settings(user_id: int, *, include_key: bool = False) -> dict:
    defaults = _default_account_transcription_settings()
    stored = auth_store.get_transcription_settings(user_id)
    if stored is None:
        result = {**defaults, "api_key_configured": False, "api_key_suffix": ""}
        if include_key:
            result["api_key"] = None
        return result
    try:
        decoded = json.loads(stored["settings_json"])
    except (TypeError, json.JSONDecodeError):
        decoded = {}
    if not isinstance(decoded, dict):
        decoded = {}
    provider = str(stored.get("provider") or decoded.get("provider") or "local")
    if provider not in {"local", "elevenlabs"}:
        provider = "local"
    local = decoded.get("local") if isinstance(decoded.get("local"), dict) else {}
    local_model = str(local.get("model") or "whisper-turbo")
    if local_model not in TRANSCRIPTION_MODELS:
        local_model = "whisper-turbo"
    local_language = str(local.get("language") or "auto").strip().lower() or "auto"
    try:
        elevenlabs = validate_elevenlabs_settings(decoded.get("elevenlabs"))
    except ValueError:
        elevenlabs = default_elevenlabs_settings()

    api_key = None
    encrypted = stored.get("elevenlabs_api_key_encrypted")
    if encrypted:
        try:
            api_key = credential_cipher.decrypt(bytes(encrypted)).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError):
            api_key = None
    result = {
        "provider": provider,
        "local": {"model": local_model, "language": local_language},
        "elevenlabs": elevenlabs,
        "api_key_configured": bool(api_key),
        "api_key_suffix": api_key[-4:] if api_key else "",
        "updated_utc": stored.get("updated_utc"),
    }
    if include_key:
        result["api_key"] = api_key
    return result


def _save_account_transcription_settings(
    user_id: int,
    payload: dict,
    *,
    new_api_key: str | None = None,
) -> dict:
    current = _account_transcription_settings(user_id, include_key=True)
    provider = str(payload.get("provider") or current["provider"])
    if provider not in {"local", "elevenlabs"}:
        raise ValueError("unknown transcription provider")

    raw_local = payload.get("local") if isinstance(payload.get("local"), dict) else current["local"]
    local_model = str(raw_local.get("model") or "whisper-turbo")
    if local_model not in TRANSCRIPTION_MODELS:
        raise ValueError("unknown local transcription model")
    local_language = str(raw_local.get("language") or "auto").strip().lower() or "auto"
    elevenlabs = validate_elevenlabs_settings(payload.get("elevenlabs", current["elevenlabs"]))

    api_key = new_api_key.strip() if isinstance(new_api_key, str) and new_api_key.strip() else current.get("api_key")
    if provider == "elevenlabs" and not api_key:
        raise ValueError("save an ElevenLabs API key before selecting the cloud provider")
    encrypted = credential_cipher.encrypt(api_key.encode("utf-8")) if api_key else None
    saved_settings = {
        "provider": provider,
        "local": {"model": local_model, "language": local_language},
        "elevenlabs": elevenlabs,
    }
    auth_store.save_transcription_settings(
        user_id,
        provider,
        json.dumps(saved_settings, separators=(",", ":"), sort_keys=True),
        encrypted,
        _utc_now_iso(),
    )
    return _account_transcription_settings(user_id)


def _read_transcription_status(job_id: str) -> dict:
    path = _transcription_status_path(job_id)
    if not path.is_file():
        return {"state": "idle"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "error", "error": "transcription status is unreadable"}
    return payload if isinstance(payload, dict) else {"state": "error", "error": "invalid transcription status"}


def _write_transcription_status(job_id: str, payload: dict) -> None:
    path = _transcription_status_path(job_id)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _owned_job(job_id: str) -> Job | None:
    if g.user is None or not _validate_job_id(job_id):
        return None
    if not auth_store.user_owns_job(g.user.id, job_id):
        return None
    return _get_job(job_id)


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
    video_path = _video_path(job.id)
    payload["video_available"] = video_path is not None
    payload["video_url"] = f"/jobs/{job.id}/video" if video_path is not None else None
    transcription = _read_transcription_status(job.id)
    transcription["download_url"] = f"/api/jobs/{job.id}/transcript.srt" if transcription.get("state") == "done" else None
    if transcription.get("state") == "done" and isinstance(transcription.get("additional_formats"), list):
        transcription["additional_formats"] = [
            {
                **item,
                "download_url": f"/api/jobs/{job.id}/transcript-export/{item['filename']}",
            }
            for item in transcription["additional_formats"]
            if isinstance(item, dict) and isinstance(item.get("filename"), str)
        ]
    payload["transcription"] = transcription
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


def _transcribe_job(job_id: str, user_id: int, settings: dict) -> None:
    provider = settings["provider"]
    local_settings = settings["local"]
    elevenlabs_settings = settings["elevenlabs"]
    model_key = local_settings["model"] if provider == "local" else elevenlabs_settings["model_id"]
    model_label = (
        TRANSCRIPTION_MODELS[model_key].label
        if provider == "local"
        else f"ElevenLabs {'Scribe v2' if model_key == 'scribe_v2' else 'Scribe v1'}"
    )
    language = local_settings["language"] if provider == "local" else elevenlabs_settings["language_code"]
    queued_status = _read_transcription_status(job_id)
    base_status = {
        "state": "running",
        "provider": provider,
        "model": model_key,
        "model_label": model_label,
        "language_requested": language or "auto",
        "automatic": bool(queued_status.get("automatic")),
        "started_utc": _utc_now_iso(),
        "progress_seconds": 0.0,
    }
    _write_transcription_status(job_id, base_status)

    def on_progress(seconds: float) -> None:
        _write_transcription_status(job_id, {**base_status, "progress_seconds": round(seconds, 3)})

    try:
        video_path = _video_path(job_id)
        if video_path is None:
            raise RuntimeError("the original video is unavailable")
        if provider == "elevenlabs":
            account = _account_transcription_settings(user_id, include_key=True)
            api_key = account.get("api_key")
            if not api_key:
                raise RuntimeError("the saved ElevenLabs API key is unavailable")
            result = transcribe_with_elevenlabs(
                video_path,
                _transcript_path(job_id),
                api_key=api_key,
                settings=elevenlabs_settings,
            )
        else:
            selected_language = None if language in {"", "auto"} else language
            result = transcribe_to_srt(
                video_path,
                _transcript_path(job_id),
                model_key=model_key,
                language=selected_language,
                cache_dir=MODEL_CACHE_DIR,
                on_progress=on_progress,
            )
        _write_transcription_status(
            job_id,
            {
                **base_status,
                **result,
                "state": "done",
                "completed_utc": _utc_now_iso(),
                "progress_seconds": result.get("duration_seconds", 0.0),
            },
        )
    except Exception as exc:  # noqa: BLE001
        _write_transcription_status(
            job_id,
            {
                **base_status,
                "state": "error",
                "completed_utc": _utc_now_iso(),
                "error": str(exc),
            },
        )


def _queue_transcription(job_id: str, user_id: int, settings: dict, *, automatic: bool) -> dict:
    provider = settings["provider"]
    if provider == "local":
        model_key = settings["local"]["model"]
        if model_key not in TRANSCRIPTION_MODELS:
            raise ValueError("unknown transcription model")
        model_label = TRANSCRIPTION_MODELS[model_key].label
        language = settings["local"]["language"]
    elif provider == "elevenlabs":
        model_key = settings["elevenlabs"]["model_id"]
        model_label = f"ElevenLabs {'Scribe v2' if model_key == 'scribe_v2' else 'Scribe v1'}"
        language = settings["elevenlabs"]["language_code"]
        if not _account_transcription_settings(user_id, include_key=True).get("api_key"):
            raise ValueError("save an ElevenLabs API key before using cloud transcription")
    else:
        raise ValueError("unknown transcription provider")
    queued = {
        "state": "queued",
        "provider": provider,
        "model": model_key,
        "model_label": model_label,
        "language_requested": language or "auto",
        "automatic": automatic,
        "queued_utc": _utc_now_iso(),
        "progress_seconds": 0.0,
    }
    _write_transcription_status(job_id, queued)
    transcription_executor.submit(_transcribe_job, job_id, user_id, settings)
    return queued


def _auto_transcribe_after_extraction(job_id: str) -> None:
    job = _get_job(job_id)
    if job is None or job.state != "done" or _video_path(job_id) is None:
        return
    if _read_transcription_status(job_id).get("state") != "idle":
        return
    user_id = auth_store.job_owner_id(job_id)
    if user_id is None:
        return
    settings = _account_transcription_settings(user_id, include_key=True)
    if auth_store.get_transcription_settings(user_id) is None:
        model_key = AUTO_TRANSCRIPTION_MODEL if AUTO_TRANSCRIPTION_MODEL in TRANSCRIPTION_MODELS else "whisper-turbo"
        settings["local"]["model"] = model_key
    try:
        _queue_transcription(job_id, user_id, settings, automatic=True)
    except ValueError as exc:
        _write_transcription_status(
            job_id,
            {
                "state": "error",
                "provider": settings.get("provider", "local"),
                "automatic": True,
                "completed_utc": _utc_now_iso(),
                "error": str(exc),
            },
        )


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("index"))
    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = auth_store.authenticate(username, password)
        if user is None:
            error = "The username or password is incorrect."
        else:
            requested_next = request.form.get("next", "")
            destination = requested_next if requested_next.startswith("/") and not requested_next.startswith("//") else url_for("index")
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            _csrf_token()
            return redirect(destination)
    return render_template("login.html", error=error, username=username, next=request.args.get("next", ""))


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("index"))
    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            user = auth_store.create_user(username, password, _utc_now_iso())
        except ValueError as exc:
            error = str(exc)
        else:
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            _csrf_token()
            return redirect(url_for("index"))
    return render_template("register.html", error=error, username=username)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    return render_template(
        "index.html",
        max_upload_label=MAX_UPLOAD_LABEL,
        engine_label=os.environ.get("VIDEO_FRAMES_ENGINE", "CPU").upper(),
        user=g.user,
        transcription_models=available_models(),
        elevenlabs_models=available_elevenlabs_models(),
    )


@app.route("/api/account/transcription-settings", methods=["GET", "PUT", "DELETE"])
@login_required
def account_transcription_settings():
    if request.method == "GET":
        return jsonify(_account_transcription_settings(g.user.id))
    if request.method == "DELETE":
        auth_store.delete_elevenlabs_api_key(g.user.id, _utc_now_iso())
        return jsonify(_account_transcription_settings(g.user.id))

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid transcription settings"}), 400
    new_api_key = str(payload.get("api_key") or "").strip()
    key_details = None
    try:
        if new_api_key:
            key_details = validate_elevenlabs_api_key(new_api_key)
        saved = _save_account_transcription_settings(
            g.user.id,
            payload,
            new_api_key=new_api_key or None,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    if key_details:
        saved["elevenlabs_tier"] = key_details.get("tier")
        saved["key_validated"] = True
    return jsonify(saved)


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
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.post("/api/jobs")
@login_required
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
    auth_store.assign_job(g.user.id, job_id, created)

    try:
        video_path, original_name = _save_upload(file, job_id)
        _update_job(job_id, filename=original_name)
    except Exception as e:  # noqa: BLE001
        _update_job(job_id, state="error", error=str(e))
        return jsonify({"error": str(e)}), 400

    extraction_future = executor.submit(_extract_job, job_id, video_path, original_name, image_ext, sample_fps)
    extraction_future.add_done_callback(lambda _future: _auto_transcribe_after_extraction(job_id))
    return jsonify({"job_id": job_id})


@app.get("/api/jobs")
@login_required
def list_jobs():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    allowed_ids = auth_store.job_ids_for_user(g.user.id)
    restored: list[Job] = []
    for job_id in allowed_ids:
        path = JOBS_DIR / job_id
        if not path.is_dir() or not _validate_job_id(job_id):
            continue
        job = _get_job(job_id)
        if job is not None:
            restored.append(job)

    with jobs_lock:
        active = [job for job in jobs.values() if job.id in allowed_ids]
    by_id = {job.id: job for job in [*restored, *active]}
    ordered = sorted(by_id.values(), key=lambda item: item.created_utc, reverse=True)
    return jsonify({"jobs": [_job_payload(job, include_frames=False) for job in ordered]})


@app.get("/api/jobs/<job_id>")
@login_required
def get_job(job_id: str):
    job = _owned_job(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404

    return jsonify(_job_payload(job, include_frames=job.state == "done"))


@app.get("/api/jobs/<job_id>/debug")
@login_required
def get_job_debug(job_id: str):
    job = _owned_job(job_id)
    if job is None or not g.user.is_admin:
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
@login_required
def serve_frame(job_id: str, filename: str):
    job = _owned_job(job_id)
    if job is None:
        return "not found", 404
    frames_dir = _frames_dir(job_id)
    return send_from_directory(frames_dir, filename, conditional=True)


@app.get("/jobs/<job_id>/video")
@login_required
def serve_original_video(job_id: str):
    job = _owned_job(job_id)
    video_path = _video_path(job_id) if job is not None else None
    if job is None or video_path is None:
        return "not found", 404
    return send_file(video_path, conditional=True, as_attachment=False, download_name=job.filename)


@app.get("/api/jobs/<job_id>/frame/<int:index>/download.png")
@login_required
def download_frame_png(job_id: str, index: int):
    job = _owned_job(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404
    if job.state != "done":
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
@login_required
def download_all_zip(job_id: str):
    job = _owned_job(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404
    if job.state != "done":
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


@app.post("/api/jobs/<job_id>/download-selected.zip")
@login_required
def download_selected_zip(job_id: str):
    job = _owned_job(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404
    if job.state != "done":
        return jsonify({"error": "job not ready"}), 400

    payload = request.get_json(silent=True) or {}
    requested = payload.get("indices")
    if not isinstance(requested, list) or not requested:
        return jsonify({"error": "select at least one frame"}), 400
    if len(requested) > 1000:
        return jsonify({"error": "select no more than 1,000 frames at a time"}), 400

    frames = _list_frames(job_id)
    selected_indices: list[int] = []
    for value in requested:
        if isinstance(value, bool) or not isinstance(value, int):
            return jsonify({"error": "frame indices must be integers"}), 400
        if value < 0 or value >= len(frames):
            return jsonify({"error": "frame index out of range"}), 400
        if value not in selected_indices:
            selected_indices.append(value)
    selected_indices.sort()

    zip_buf = io.BytesIO()
    base = Path(job.filename).stem if job.filename else job_id
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for index in selected_indices:
            filename = frames[index]
            bundle.write(_frames_dir(job_id) / filename, arcname=f"{base}/frames/{filename}")

    zip_buf.seek(0)
    zip_name = f"{base}_{len(selected_indices)}_selected_frames.zip"
    return send_file(zip_buf, mimetype="application/zip", as_attachment=True, download_name=zip_name)


@app.get("/api/transcription/models")
@login_required
def transcription_models():
    return jsonify({"models": available_models()})


@app.get("/api/jobs/<job_id>/transcription")
@login_required
def get_transcription(job_id: str):
    if _owned_job(job_id) is None:
        return jsonify({"error": "job not found"}), 404
    payload = _read_transcription_status(job_id)
    payload["download_url"] = f"/api/jobs/{job_id}/transcript.srt" if payload.get("state") == "done" else None
    if payload.get("state") == "done" and isinstance(payload.get("additional_formats"), list):
        payload["additional_formats"] = [
            {
                **item,
                "download_url": f"/api/jobs/{job_id}/transcript-export/{item['filename']}",
            }
            for item in payload["additional_formats"]
            if isinstance(item, dict) and isinstance(item.get("filename"), str)
        ]
    return jsonify(payload)


@app.post("/api/jobs/<job_id>/transcribe")
@login_required
def start_transcription(job_id: str):
    job = _owned_job(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404
    if _video_path(job_id) is None:
        return jsonify({"error": "the original video is unavailable"}), 400
    current = _read_transcription_status(job_id)
    if current.get("state") in {"queued", "running"}:
        return jsonify({"error": "transcription is already running"}), 409
    payload = request.get_json(silent=True) or {}
    settings = _account_transcription_settings(g.user.id, include_key=True)
    # Preserve the original local-model request shape for older clients.
    if isinstance(payload, dict) and payload.get("model"):
        settings["provider"] = "local"
        settings["local"] = {
            "model": str(payload.get("model") or "whisper-turbo"),
            "language": str(payload.get("language") or "auto").strip().lower() or "auto",
        }
    try:
        queued = _queue_transcription(job_id, g.user.id, settings, automatic=False)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(queued), 202


@app.get("/api/jobs/<job_id>/transcript-export/<filename>")
@login_required
def download_transcript_export(job_id: str, filename: str):
    job = _owned_job(job_id)
    status = _read_transcription_status(job_id)
    allowed = {
        str(item.get("filename"))
        for item in status.get("additional_formats") or []
        if isinstance(item, dict) and isinstance(item.get("filename"), str)
    }
    if job is None or status.get("state") != "done" or filename not in allowed:
        return jsonify({"error": "transcript export not found"}), 404
    export_path = _job_dir(job_id) / filename
    if not export_path.is_file() or export_path.parent != _job_dir(job_id):
        return jsonify({"error": "transcript export not found"}), 404
    download_name = f"{Path(job.filename).stem or 'transcript'}-{filename}"
    return send_file(export_path, as_attachment=True, download_name=download_name)


@app.route("/api/jobs/<job_id>/transcript", methods=["GET", "PUT"])
@login_required
def transcript_data(job_id: str):
    job = _owned_job(job_id)
    transcript_path = _transcript_path(job_id)
    if job is None or not transcript_path.is_file() or _read_transcription_status(job_id).get("state") != "done":
        return jsonify({"error": "transcript is not ready"}), 404

    cues = read_srt(transcript_path)
    if not cues:
        return jsonify({"error": "transcript has no readable cues"}), 422
    if request.method == "GET":
        return jsonify({"cues": cues, "filename": f"{Path(job.filename).stem or 'transcript'}.srt"})

    payload = request.get_json(silent=True) or {}
    try:
        cues = update_cue_text(cues, payload.get("cues"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    write_srt(transcript_path, cues)
    status = _read_transcription_status(job_id)
    status["edited_utc"] = _utc_now_iso()
    _write_transcription_status(job_id, status)
    return jsonify({"cues": cues, "saved": True, "edited_utc": status["edited_utc"]})


@app.get("/api/jobs/<job_id>/transcript.srt")
@login_required
def download_transcript(job_id: str):
    job = _owned_job(job_id)
    transcript_path = _transcript_path(job_id)
    if job is None or not transcript_path.is_file() or _read_transcription_status(job_id).get("state") != "done":
        return jsonify({"error": "transcript is not ready"}), 404
    download_name = f"{Path(job.filename).stem or 'transcript'}.srt"
    return send_file(transcript_path, mimetype="application/x-subrip", as_attachment=True, download_name=download_name)


def main() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=8002, debug=False, threaded=True)


if __name__ == "__main__":
    main()
