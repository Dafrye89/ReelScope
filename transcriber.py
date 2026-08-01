from __future__ import annotations

import gc
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class TranscriptionModel:
    key: str
    label: str
    model_id: str
    description: str
    languages: str
    forced_language: str | None = None

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "languages": self.languages,
        }


MODELS = {
    "whisper-turbo": TranscriptionModel(
        key="whisper-turbo",
        label="Whisper Large-v3 Turbo",
        model_id="large-v3-turbo",
        description="Recommended multilingual balance of speed and accuracy.",
        languages="99 languages",
    ),
    "distil-large-v3.5": TranscriptionModel(
        key="distil-large-v3.5",
        label="Distil-Whisper Large-v3.5",
        model_id="distil-whisper/distil-large-v3.5-ct2",
        description="Fastest high-quality English option.",
        languages="English",
        forced_language="en",
    ),
    "whisper-large-v3": TranscriptionModel(
        key="whisper-large-v3",
        label="Whisper Large-v3",
        model_id="large-v3",
        description="Highest-accuracy Whisper option; slower than Turbo.",
        languages="100 languages",
    ),
}


_model_lock = threading.Lock()
_loaded_model = None
_loaded_model_key: str | None = None
_loaded_device: str | None = None


def available_models() -> list[dict]:
    return [model.as_dict() for model in MODELS.values()]


def _format_srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _load_model(model: TranscriptionModel, cache_dir: Path):
    global _loaded_device, _loaded_model, _loaded_model_key

    with _model_lock:
        if _loaded_model is not None and _loaded_model_key == model.key:
            return _loaded_model, _loaded_device or "cpu"

        from faster_whisper import WhisperModel

        _loaded_model = None
        _loaded_model_key = None
        gc.collect()

        preferred = os.environ.get("REELSCOPE_STT_DEVICE", "auto").lower()
        device_order = [preferred] if preferred in {"cuda", "cpu"} else ["cuda", "cpu"]
        last_error: Exception | None = None
        for device in device_order:
            compute_type = "float16" if device == "cuda" else "int8"
            try:
                loaded = WhisperModel(
                    model.model_id,
                    device=device,
                    compute_type=compute_type,
                    download_root=str(cache_dir),
                )
                _loaded_model = loaded
                _loaded_model_key = model.key
                _loaded_device = device
                return loaded, device
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if preferred in {"cuda", "cpu"}:
                    break
        raise RuntimeError(f"could not load {model.label}: {last_error}")


def transcribe_to_srt(
    media_path: Path,
    output_path: Path,
    *,
    model_key: str,
    language: str | None,
    cache_dir: Path,
    on_progress: Callable[[float], None] | None = None,
) -> dict:
    model_info = MODELS.get(model_key)
    if model_info is None:
        raise ValueError("unknown transcription model")
    selected_language = model_info.forced_language or (language.strip().lower() if language else None)
    model, device = _load_model(model_info, cache_dir)
    segments, info = model.transcribe(
        str(media_path),
        beam_size=5,
        language=selected_language,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    count = 0
    last_end = 0.0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for segment in segments:
            text = str(segment.text).strip()
            if not text:
                continue
            count += 1
            start = float(segment.start)
            end = max(start + 0.001, float(segment.end))
            last_end = end
            handle.write(f"{count}\n{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n{text}\n\n")
            if on_progress is not None:
                on_progress(end)
    temporary.replace(output_path)
    if count == 0:
        raise RuntimeError("the model did not detect any speech")

    return {
        "model": model_key,
        "model_label": model_info.label,
        "device": device,
        "language": str(getattr(info, "language", selected_language or "unknown")),
        "language_probability": float(getattr(info, "language_probability", 0.0) or 0.0),
        "duration_seconds": float(getattr(info, "duration", last_end) or last_end),
        "segments": count,
    }
