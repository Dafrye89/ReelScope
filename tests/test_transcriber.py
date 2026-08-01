from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import transcriber


class TranscriberWordTimingTests(unittest.TestCase):
    def test_each_timestamped_word_becomes_its_own_srt_cue(self) -> None:
        segment = SimpleNamespace(
            start=0.1,
            end=1.4,
            text=" Hello, world!",
            words=[
                SimpleNamespace(start=0.1, end=0.55, word=" Hello,"),
                SimpleNamespace(start=0.7, end=1.4, word=" world!"),
            ],
        )
        model = SimpleNamespace(
            transcribe=lambda *_args, **_kwargs: (
                iter([segment]),
                SimpleNamespace(language="en", language_probability=0.99, duration=1.4),
            )
        )

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            transcriber, "_load_model", return_value=(model, "cpu")
        ):
            root = Path(temporary)
            output = root / "transcript.srt"
            result = transcriber.transcribe_to_srt(
                root / "video.mp4",
                output,
                model_key="whisper-turbo",
                language="en",
                cache_dir=root / "models",
            )
            srt = output.read_text(encoding="utf-8")

        self.assertEqual(result["segments"], 1)
        self.assertEqual(result["words"], 2)
        self.assertTrue(result["word_timestamps"])
        self.assertIn("1\n00:00:00,100 --> 00:00:00,550\nHello,", srt)
        self.assertIn("2\n00:00:00,700 --> 00:00:01,400\nworld!", srt)

    def test_missing_backend_word_times_still_produces_word_cues(self) -> None:
        segment = SimpleNamespace(start=2.0, end=4.0, text="two words", words=[])

        self.assertEqual(
            transcriber._word_cues(segment),
            [(2.0, 3.0, "two"), (3.0, 4.0, "words")],
        )


if __name__ == "__main__":
    unittest.main()
