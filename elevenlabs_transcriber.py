from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

import requests

from transcript_store import seconds_to_timestamp


API_BASE = "https://api.elevenlabs.io/v1"
MODEL_LABELS = {
    "scribe_v2": "ElevenLabs Scribe v2",
    "scribe_v1": "ElevenLabs Scribe v1",
}
TIMESTAMP_GRANULARITIES = {"word", "character"}
MULTICHANNEL_STYLES = {"separate", "combined"}
REDACTION_MODES = {"redacted", "entity_type", "enumerated_entity_type"}
ADDITIONAL_FORMATS = {"docx", "html", "pdf", "srt", "txt", "segmented_json"}
UNSUPPORTED_KEYTERM_CHARACTERS = set("<>{}[]\\")


def default_settings() -> dict[str, Any]:
    return {
        "model_id": "scribe_v2",
        "language_code": "auto",
        "tag_audio_events": True,
        "timestamps_granularity": "word",
        "diarize": False,
        "num_speakers": None,
        "diarization_threshold": None,
        "no_verbatim": False,
        "use_speaker_library": False,
        "detect_speaker_roles": False,
        "include_speaker_labels": False,
        "temperature": None,
        "seed": None,
        "use_multi_channel": False,
        "multichannel_output_style": "combined",
        "entity_detection": [],
        "entity_redaction": [],
        "entity_redaction_mode": "enumerated_entity_type",
        "keyterms": [],
        "enable_logging": True,
        "additional_formats": [],
        "export_include_speakers": True,
        "export_include_timestamps": True,
        "export_segment_on_silence": None,
        "export_max_segment_duration": None,
        "export_max_segment_chars": None,
        "export_max_characters_per_line": None,
    }


def available_models() -> list[dict[str, str]]:
    return [
        {
            "id": "scribe_v2",
            "label": "Scribe v2",
            "description": "Newest batch model with keyterms, entities, speaker tools, and 90+ languages.",
        },
        {
            "id": "scribe_v1",
            "label": "Scribe v1",
            "description": "Previous-generation batch model for compatibility.",
        },
    ]


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _optional_float(value: Any, name: str, minimum: float, maximum: float) -> float | None:
    if value in {None, ""}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return parsed


def _optional_int(value: Any, name: str, minimum: int, maximum: int) -> int | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _string_list(value: Any, name: str, maximum: int) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        items = value.replace("\r", "\n").replace(",", "\n").split("\n")
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError(f"{name} must be a list")
    normalized: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    if len(normalized) > maximum:
        raise ValueError(f"{name} supports at most {maximum} values")
    return normalized


def validate_settings(payload: Any) -> dict[str, Any]:
    incoming = payload if isinstance(payload, dict) else {}
    settings = default_settings()

    model_id = str(incoming.get("model_id") or settings["model_id"])
    if model_id not in MODEL_LABELS:
        raise ValueError("unknown ElevenLabs transcription model")
    settings["model_id"] = model_id

    language = str(incoming.get("language_code") or "auto").strip().lower()
    if language != "auto" and (len(language) < 2 or len(language) > 3 or not language.isalpha()):
        raise ValueError("language must be auto or a 2-3 letter ISO language code")
    settings["language_code"] = language

    granularity = str(incoming.get("timestamps_granularity") or "word")
    if granularity not in TIMESTAMP_GRANULARITIES:
        raise ValueError("ReelScope requires word or character timestamps for synchronized highlighting")
    settings["timestamps_granularity"] = granularity

    settings["tag_audio_events"] = _bool(incoming.get("tag_audio_events"), True)
    settings["diarize"] = _bool(incoming.get("diarize"))
    settings["num_speakers"] = _optional_int(incoming.get("num_speakers"), "speaker count", 1, 32)
    settings["diarization_threshold"] = _optional_float(
        incoming.get("diarization_threshold"), "diarization threshold", 0.1, 0.4
    )
    settings["no_verbatim"] = _bool(incoming.get("no_verbatim"))
    settings["use_speaker_library"] = _bool(incoming.get("use_speaker_library"))
    settings["detect_speaker_roles"] = _bool(incoming.get("detect_speaker_roles"))
    settings["include_speaker_labels"] = _bool(incoming.get("include_speaker_labels"))
    settings["temperature"] = _optional_float(incoming.get("temperature"), "temperature", 0.0, 2.0)
    settings["seed"] = _optional_int(incoming.get("seed"), "seed", 0, 2_147_483_647)
    settings["use_multi_channel"] = _bool(incoming.get("use_multi_channel"))

    output_style = str(incoming.get("multichannel_output_style") or "combined")
    if output_style not in MULTICHANNEL_STYLES:
        raise ValueError("unknown multi-channel output style")
    settings["multichannel_output_style"] = output_style

    detection = _string_list(incoming.get("entity_detection"), "entity detection", 56)
    redaction = _string_list(incoming.get("entity_redaction"), "entity redaction", 56)
    settings["entity_detection"] = detection
    settings["entity_redaction"] = redaction
    redaction_mode = str(incoming.get("entity_redaction_mode") or "enumerated_entity_type")
    if redaction_mode not in REDACTION_MODES:
        raise ValueError("unknown entity redaction mode")
    settings["entity_redaction_mode"] = redaction_mode

    keyterms = _string_list(incoming.get("keyterms"), "keyterms", 1000)
    for keyterm in keyterms:
        if len(keyterm) >= 50:
            raise ValueError("each keyterm must be shorter than 50 characters")
        if len(keyterm.split()) > 5:
            raise ValueError("each keyterm can contain at most 5 words")
        if any(character in UNSUPPORTED_KEYTERM_CHARACTERS for character in keyterm):
            raise ValueError("keyterms cannot contain angle, brace, bracket, or backslash characters")
    settings["keyterms"] = keyterms
    settings["enable_logging"] = _bool(incoming.get("enable_logging"), True)

    formats = _string_list(incoming.get("additional_formats"), "additional formats", len(ADDITIONAL_FORMATS))
    if any(value not in ADDITIONAL_FORMATS for value in formats):
        raise ValueError("unknown additional transcript format")
    settings["additional_formats"] = formats
    settings["export_include_speakers"] = _bool(incoming.get("export_include_speakers"), True)
    settings["export_include_timestamps"] = _bool(incoming.get("export_include_timestamps"), True)
    settings["export_segment_on_silence"] = _optional_float(
        incoming.get("export_segment_on_silence"), "silence segmentation", 0.0, 3600.0
    )
    settings["export_max_segment_duration"] = _optional_float(
        incoming.get("export_max_segment_duration"), "maximum segment duration", 0.1, 36000.0
    )
    settings["export_max_segment_chars"] = _optional_int(
        incoming.get("export_max_segment_chars"), "maximum segment characters", 1, 1_000_000
    )
    settings["export_max_characters_per_line"] = _optional_int(
        incoming.get("export_max_characters_per_line"), "maximum line characters", 1, 10_000
    )

    if settings["model_id"] == "scribe_v1" and settings["no_verbatim"]:
        raise ValueError("no-verbatim mode requires Scribe v2")
    if settings["use_multi_channel"]:
        if settings["diarize"] or settings["num_speakers"] is not None:
            raise ValueError("multi-channel mode cannot be combined with diarization or speaker count")
        if settings["detect_speaker_roles"] or settings["use_speaker_library"]:
            raise ValueError("multi-channel mode cannot use speaker roles or the speaker library")
        if settings["multichannel_output_style"] == "combined" and (detection or redaction):
            raise ValueError("combined multi-channel output cannot use entity detection or redaction")
    if settings["num_speakers"] is not None and not settings["diarize"]:
        raise ValueError("speaker count requires diarization")
    if settings["diarization_threshold"] is not None:
        if not settings["diarize"] or settings["num_speakers"] is not None:
            raise ValueError("diarization threshold requires diarization with automatic speaker count")
    if (settings["use_speaker_library"] or settings["detect_speaker_roles"]) and not settings["diarize"]:
        raise ValueError("speaker library and role detection require diarization")
    if redaction:
        if not detection:
            raise ValueError("entity redaction requires entity detection")
        if "all" not in detection and not set(redaction).issubset(set(detection)):
            raise ValueError("entity redaction must be a subset of entity detection")
    return settings


def validate_api_key(api_key: str, *, timeout: float = 15.0) -> dict[str, str]:
    key = api_key.strip()
    if len(key) < 16 or len(key) > 256:
        raise ValueError("enter a valid ElevenLabs API key")
    try:
        response = requests.get(f"{API_BASE}/user", headers={"xi-api-key": key}, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError("ElevenLabs could not be reached; check the connection and try again") from exc
    if response.status_code in {401, 403}:
        raise ValueError("ElevenLabs rejected this API key or its IP/scope restrictions")
    if not response.ok:
        raise RuntimeError(f"ElevenLabs key check failed ({response.status_code})")
    payload = response.json()
    subscription = payload.get("subscription") if isinstance(payload, dict) else {}
    tier = str(subscription.get("tier") or subscription.get("status") or "connected") if isinstance(subscription, dict) else "connected"
    return {"tier": tier, "user_id": str(payload.get("user_id") or "")}


def _form_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _export_options(settings: dict[str, Any]) -> list[dict[str, Any]]:
    exports: list[dict[str, Any]] = []
    for requested_format in settings["additional_formats"]:
        export: dict[str, Any] = {
            "format": requested_format,
            "include_speakers": settings["export_include_speakers"],
            "include_timestamps": settings["export_include_timestamps"],
        }
        optional = {
            "segment_on_silence_longer_than_s": settings["export_segment_on_silence"],
            "max_segment_duration_s": settings["export_max_segment_duration"],
            "max_segment_chars": settings["export_max_segment_chars"],
        }
        if requested_format in {"srt", "txt"}:
            optional["max_characters_per_line"] = settings["export_max_characters_per_line"]
        export.update({key: value for key, value in optional.items() if value is not None})
        exports.append(export)
    return exports


def _save_additional_formats(payload: dict[str, Any], output_dir: Path) -> list[dict[str, str]]:
    saved: list[dict[str, str]] = []
    extension_by_format = {
        "docx": ".docx",
        "html": ".html",
        "pdf": ".pdf",
        "srt": ".srt",
        "txt": ".txt",
        "segmented_json": ".json",
    }
    for item in payload.get("additional_formats") or []:
        if not isinstance(item, dict):
            continue
        requested = str(item.get("requested_format") or "")
        extension = extension_by_format.get(requested)
        content = item.get("content")
        if extension is None or not isinstance(content, str):
            continue
        try:
            data = base64.b64decode(content, validate=True) if item.get("is_base64_encoded") else content.encode("utf-8")
        except (ValueError, TypeError):
            continue
        filename = f"elevenlabs-transcript{extension}"
        (output_dir / filename).write_bytes(data)
        saved.append({"format": requested, "filename": filename})
    return saved


def transcribe_to_srt(
    media_path: Path,
    output_path: Path,
    *,
    api_key: str,
    settings: dict[str, Any],
    timeout: float = 3600.0,
) -> dict[str, Any]:
    normalized = validate_settings(settings)
    data: dict[str, Any] = {
        "model_id": normalized["model_id"],
        "tag_audio_events": _form_value(normalized["tag_audio_events"]),
        "timestamps_granularity": normalized["timestamps_granularity"],
        "diarize": _form_value(normalized["diarize"]),
        "no_verbatim": _form_value(normalized["no_verbatim"]),
        "use_speaker_library": _form_value(normalized["use_speaker_library"]),
        "detect_speaker_roles": _form_value(normalized["detect_speaker_roles"]),
        "use_multi_channel": _form_value(normalized["use_multi_channel"]),
        "multichannel_output_style": normalized["multichannel_output_style"],
        "file_format": "other",
    }
    optional = {
        "language_code": None if normalized["language_code"] == "auto" else normalized["language_code"],
        "num_speakers": normalized["num_speakers"],
        "diarization_threshold": normalized["diarization_threshold"],
        "temperature": normalized["temperature"],
        "seed": normalized["seed"],
        "entity_detection": json.dumps(normalized["entity_detection"]) if normalized["entity_detection"] else None,
        "entity_redaction": json.dumps(normalized["entity_redaction"]) if normalized["entity_redaction"] else None,
        "entity_redaction_mode": normalized["entity_redaction_mode"] if normalized["entity_redaction"] else None,
        "keyterms": normalized["keyterms"] or None,
    }
    data.update({key: value for key, value in optional.items() if value is not None})

    files: dict[str, Any] = {}
    export_options = _export_options(normalized)
    if export_options:
        files["additional_formats"] = (None, json.dumps(export_options), "application/json")
    mime_type = mimetypes.guess_type(media_path.name)[0] or "application/octet-stream"
    try:
        with media_path.open("rb") as media:
            files["file"] = (media_path.name, media, mime_type)
            response = requests.post(
                f"{API_BASE}/speech-to-text",
                params={"enable_logging": "true" if normalized["enable_logging"] else "false"},
                headers={"xi-api-key": api_key},
                data=data,
                files=files,
                timeout=timeout,
            )
    except requests.RequestException as exc:
        raise RuntimeError("ElevenLabs transcription could not be reached") from exc
    if response.status_code in {401, 403}:
        raise ValueError("ElevenLabs rejected the saved API key or its permissions")
    if not response.ok:
        message = ""
        try:
            error_payload = response.json()
            detail = error_payload.get("detail") if isinstance(error_payload, dict) else None
            message = str(detail.get("message") if isinstance(detail, dict) else detail or "").strip()
        except (ValueError, TypeError):
            message = ""
        raise RuntimeError(f"ElevenLabs transcription failed ({response.status_code}){': ' + message[:240] if message else ''}")

    payload = response.json()
    transcript_chunks: list[dict[str, Any]] = []
    if isinstance(payload, dict) and isinstance(payload.get("transcripts"), list):
        transcript_chunks = [item for item in payload["transcripts"] if isinstance(item, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("transcripts"), dict):
        transcript_chunks = [item for item in payload["transcripts"].values() if isinstance(item, dict)]
    elif isinstance(payload, dict):
        transcript_chunks = [payload]

    words: list[dict[str, Any]] = []
    for chunk in transcript_chunks:
        words.extend(item for item in (chunk.get("words") or []) if isinstance(item, dict))
    words.sort(key=lambda item: float(item.get("start") or 0.0))

    cues: list[tuple[float, float, str]] = []
    previous_speaker: str | None = None
    for word in words:
        word_type = str(word.get("type") or "word")
        if word_type not in {"word", "audio_event"}:
            continue
        text = str(word.get("text") or "").strip()
        if not text or word.get("start") is None or word.get("end") is None:
            continue
        start = max(0.0, float(word["start"]))
        end = max(start + 0.001, float(word["end"]))
        speaker = str(word.get("speaker_id") or "").strip() or None
        if normalized["include_speaker_labels"] and speaker and speaker != previous_speaker:
            text = f"[{speaker}] {text}"
        if speaker:
            previous_speaker = speaker
        cues.append((start, end, text))
    if not cues:
        raise RuntimeError("ElevenLabs did not return word timestamps")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for position, (start, end, text) in enumerate(cues, start=1):
            handle.write(f"{position}\n{seconds_to_timestamp(start)} --> {seconds_to_timestamp(end)}\n{text}\n\n")
    temporary.replace(output_path)

    additional = _save_additional_formats(payload, output_path.parent)
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if isinstance(entities, list) and entities:
        (output_path.parent / "elevenlabs-entities.json").write_text(
            json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    duration = max(end for _, end, _ in cues)
    language_code = str(payload.get("language_code") or normalized["language_code"] or "unknown")
    return {
        "provider": "elevenlabs",
        "model": normalized["model_id"],
        "model_label": MODEL_LABELS[normalized["model_id"]],
        "device": "cloud",
        "language": language_code,
        "language_probability": float(payload.get("language_probability") or 0.0),
        "duration_seconds": float(payload.get("audio_duration_secs") or duration),
        "segments": len(transcript_chunks),
        "words": len(cues),
        "word_timestamps": True,
        "transcription_id": str(payload.get("transcription_id") or ""),
        "additional_formats": additional,
        "entities_detected": len(entities) if isinstance(entities, list) else 0,
    }
