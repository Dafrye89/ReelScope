from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import elevenlabs_transcriber


class MockResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self) -> dict:
        return self._payload


class ElevenLabsTranscriberTests(unittest.TestCase):
    def test_scribe_words_become_individual_srt_cues_and_exports_are_saved(self) -> None:
        payload = {
            "language_code": "eng",
            "language_probability": 0.99,
            "audio_duration_secs": 1.2,
            "transcription_id": "scribe-test",
            "words": [
                {"text": "Hello", "start": 0.0, "end": 0.4, "type": "word", "speaker_id": "speaker_0"},
                {"text": " ", "start": 0.4, "end": 0.45, "type": "spacing", "speaker_id": "speaker_0"},
                {"text": "world", "start": 0.45, "end": 0.9, "type": "word", "speaker_id": "speaker_0"},
            ],
            "additional_formats": [
                {
                    "requested_format": "docx",
                    "file_extension": "docx",
                    "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "is_base64_encoded": True,
                    "content": base64.b64encode(b"mock-docx").decode("ascii"),
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            media = root / "sample.mp4"
            media.write_bytes(b"video")
            output = root / "transcript.srt"
            settings = elevenlabs_transcriber.default_settings()
            settings["additional_formats"] = ["docx"]
            settings["include_speaker_labels"] = True
            with patch.object(elevenlabs_transcriber.requests, "post", return_value=MockResponse(payload)) as post:
                result = elevenlabs_transcriber.transcribe_to_srt(
                    media,
                    output,
                    api_key="test-key-with-enough-characters",
                    settings=settings,
                )

            transcript = output.read_text(encoding="utf-8")
            self.assertIn("[speaker_0] Hello", transcript)
            self.assertIn("00:00:00,450 --> 00:00:00,900\nworld", transcript)
            self.assertEqual(transcript.count("-->"), 2)
            self.assertEqual((root / "elevenlabs-transcript.docx").read_bytes(), b"mock-docx")
            self.assertEqual(result["provider"], "elevenlabs")
            self.assertEqual(result["words"], 2)
            self.assertEqual(result["additional_formats"][0]["filename"], "elevenlabs-transcript.docx")
            request_kwargs = post.call_args.kwargs
            self.assertEqual(request_kwargs["headers"]["xi-api-key"], "test-key-with-enough-characters")
            self.assertEqual(request_kwargs["data"]["timestamps_granularity"], "word")

    def test_incompatible_options_are_rejected_before_api_use(self) -> None:
        settings = elevenlabs_transcriber.default_settings()
        settings.update({"use_multi_channel": True, "diarize": True})
        with self.assertRaisesRegex(ValueError, "multi-channel mode"):
            elevenlabs_transcriber.validate_settings(settings)

        settings = elevenlabs_transcriber.default_settings()
        settings.update({"model_id": "scribe_v1", "no_verbatim": True})
        with self.assertRaisesRegex(ValueError, "Scribe v2"):
            elevenlabs_transcriber.validate_settings(settings)


if __name__ == "__main__":
    unittest.main()
