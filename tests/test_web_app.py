from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import web_app
from auth_store import AuthStore


class WebAppHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.jobs_dir = self.data_dir / "jobs"
        self.job_id = "a" * 32
        self.job_dir = self.jobs_dir / self.job_id
        self.frames_dir = self.job_dir / "frames"
        self.frames_dir.mkdir(parents=True)

        Image.new("RGB", (320, 180), "#6d5dfc").save(self.frames_dir / "00000001_t000000000ms.jpg")
        Image.new("RGB", (320, 180), "#151d2d").save(self.frames_dir / "00000002_t000000040ms.jpg")
        (self.job_dir / "upload.mp4").write_bytes(b"mock video")
        meta = {
            "job_id": self.job_id,
            "original_filename": "demo clip.mp4",
            "created_utc": "2026-07-31T20:00:00+00:00",
            "result": {
                "frames_written": 2,
                "expected_frames": 2,
                "image_ext": ".jpg",
                "fps": 25.0,
                "requested_sample_fps": 5.0,
                "width": 320,
                "height": 180,
                "source_frame_count": 10,
                "source_size_bytes": 1024,
                "processed_utc": "2026-07-31T20:00:01+00:00",
            },
        }
        (self.job_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        self.store = AuthStore(self.data_dir / "test.sqlite3")
        self.owner = self.store.create_user("owner", "correct-horse", "2026-07-31T20:00:00+00:00")
        self.other = self.store.create_user("other", "battery-staple", "2026-07-31T20:00:00+00:00")
        self.store.assign_job(self.owner.id, self.job_id, "2026-07-31T20:00:00+00:00")

        self.jobs_patch = patch.object(web_app, "JOBS_DIR", self.jobs_dir)
        self.data_patch = patch.object(web_app, "DATA_DIR", self.data_dir)
        self.auth_patch = patch.object(web_app, "auth_store", self.store)
        self.jobs_patch.start()
        self.data_patch.start()
        self.auth_patch.start()
        with web_app.jobs_lock:
            web_app.jobs.clear()
        web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        self.client = web_app.app.test_client()
        self._login_as(self.owner.id)

    def tearDown(self) -> None:
        with web_app.jobs_lock:
            web_app.jobs.clear()
        self.auth_patch.stop()
        self.data_patch.stop()
        self.jobs_patch.stop()
        self.temp_dir.cleanup()

    def _login_as(self, user_id: int) -> None:
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = user_id
            session["csrf_token"] = "test-csrf-token-with-at-least-32-characters"

    def test_unauthenticated_api_is_rejected(self) -> None:
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.get("/api/jobs")
        self.assertEqual(response.status_code, 401)

    def test_completed_job_is_restored_and_listed_for_owner(self) -> None:
        response = self.client.get("/api/jobs")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["jobs"]), 1)
        job = payload["jobs"][0]
        self.assertEqual(job["filename"], "demo clip.mp4")
        self.assertEqual(job["frames_count"], 2)
        self.assertTrue(job["video_available"])

    def test_detail_exposes_frames_and_serves_video(self) -> None:
        detail = self.client.get(f"/api/jobs/{self.job_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.get_json()
        self.assertEqual(len(payload["frames"]), 2)

        with self.client.get(f"/jobs/{self.job_id}/frames/{payload['frames'][0]}") as frame:
            self.assertEqual(frame.status_code, 200)
            self.assertEqual(frame.mimetype, "image/jpeg")

        with self.client.get(f"/jobs/{self.job_id}/video", headers={"Range": "bytes=0-3"}) as video:
            self.assertIn(video.status_code, {200, 206})
            self.assertTrue(video.data)

    def test_png_and_zip_exports(self) -> None:
        png = self.client.get(f"/api/jobs/{self.job_id}/frame/0/download.png")
        self.assertEqual(png.status_code, 200)
        with Image.open(io.BytesIO(png.data)) as image:
            self.assertEqual(image.size, (320, 180))

        archive = self.client.get(f"/api/jobs/{self.job_id}/download.zip?format=jpg")
        self.assertEqual(archive.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(archive.data)) as bundle:
            names = bundle.namelist()
        self.assertTrue(any(name.endswith("meta.json") for name in names))
        self.assertEqual(sum(name.endswith(".jpg") for name in names), 2)

        selected = self.client.post(
            f"/api/jobs/{self.job_id}/download-selected.zip",
            json={"indices": [1]},
            headers={"X-CSRF-Token": "test-csrf-token-with-at-least-32-characters"},
        )
        self.assertEqual(selected.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(selected.data)) as bundle:
            selected_names = bundle.namelist()
        self.assertEqual(len(selected_names), 1)
        self.assertTrue(selected_names[0].endswith("00000002_t000000040ms.jpg"))

        invalid_selection = self.client.post(
            f"/api/jobs/{self.job_id}/download-selected.zip",
            json={"indices": [99]},
            headers={"X-CSRF-Token": "test-csrf-token-with-at-least-32-characters"},
        )
        self.assertEqual(invalid_selection.status_code, 400)

    def test_other_user_cannot_access_any_job_artifact(self) -> None:
        (self.job_dir / "transcript.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nPrivate\n", encoding="utf-8")
        (self.job_dir / "elevenlabs-transcript.txt").write_text("Private export", encoding="utf-8")
        (self.job_dir / "transcription.json").write_text(
            '{"state":"done","additional_formats":[{"format":"txt","filename":"elevenlabs-transcript.txt"}]}',
            encoding="utf-8",
        )
        self._login_as(self.other.id)
        routes = [
            f"/api/jobs/{self.job_id}",
            f"/jobs/{self.job_id}/frames/00000001_t000000000ms.jpg",
            f"/jobs/{self.job_id}/video",
            f"/api/jobs/{self.job_id}/frame/0/download.png",
            f"/api/jobs/{self.job_id}/download.zip",
            f"/api/jobs/{self.job_id}/transcription",
            f"/api/jobs/{self.job_id}/transcript",
            f"/api/jobs/{self.job_id}/transcript.srt",
            f"/api/jobs/{self.job_id}/transcript-export/elevenlabs-transcript.txt",
        ]
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 404)
        selected = self.client.post(
            f"/api/jobs/{self.job_id}/download-selected.zip",
            json={"indices": [0]},
            headers={"X-CSRF-Token": "test-csrf-token-with-at-least-32-characters"},
        )
        self.assertEqual(selected.status_code, 404)

    def test_transcription_start_requires_csrf_and_queues_owned_job(self) -> None:
        response = self.client.post(f"/api/jobs/{self.job_id}/transcribe", json={"model": "whisper-turbo"})
        self.assertEqual(response.status_code, 400)

        with patch.object(web_app.transcription_executor, "submit") as submit:
            response = self.client.post(
                f"/api/jobs/{self.job_id}/transcribe",
                json={"model": "whisper-turbo", "language": "auto"},
                headers={"X-CSRF-Token": "test-csrf-token-with-at-least-32-characters"},
            )
        self.assertEqual(response.status_code, 202)
        submit.assert_called_once()

    def test_elevenlabs_key_is_validated_encrypted_and_private_to_account(self) -> None:
        initial = self.client.get("/api/account/transcription-settings")
        self.assertEqual(initial.status_code, 200)
        self.assertNotIn("api_key", initial.get_json())

        payload = {
            "provider": "elevenlabs",
            "local": {"model": "whisper-turbo", "language": "auto"},
            "elevenlabs": {"model_id": "scribe_v2", "language_code": "auto"},
            "api_key": "elevenlabs-secret-key-1234",
        }
        with patch.object(web_app, "validate_elevenlabs_api_key", return_value={"tier": "creator"}) as validate:
            response = self.client.put(
                "/api/account/transcription-settings",
                json=payload,
                headers={"X-CSRF-Token": "test-csrf-token-with-at-least-32-characters"},
            )
        self.assertEqual(response.status_code, 200)
        saved = response.get_json()
        self.assertTrue(saved["api_key_configured"])
        self.assertEqual(saved["api_key_suffix"], "1234")
        self.assertNotIn("api_key", saved)
        self.assertNotIn("elevenlabs-secret-key", response.get_data(as_text=True))
        validate.assert_called_once_with("elevenlabs-secret-key-1234")

        stored = self.store.get_transcription_settings(self.owner.id)
        self.assertIsNotNone(stored)
        self.assertNotIn(b"elevenlabs-secret-key", bytes(stored["elevenlabs_api_key_encrypted"]))

        self._login_as(self.other.id)
        other_settings = self.client.get("/api/account/transcription-settings").get_json()
        self.assertFalse(other_settings["api_key_configured"])
        self.assertEqual(other_settings["provider"], "local")

    def test_elevenlabs_settings_reject_incompatible_options(self) -> None:
        response = self.client.put(
            "/api/account/transcription-settings",
            json={
                "provider": "local",
                "local": {"model": "whisper-turbo", "language": "auto"},
                "elevenlabs": {"model_id": "scribe_v2", "use_multi_channel": True, "diarize": True},
            },
            headers={"X-CSRF-Token": "test-csrf-token-with-at-least-32-characters"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("multi-channel", response.get_json()["error"])

    def test_transcript_is_visible_editable_and_rewrites_srt(self) -> None:
        transcript = (
            "1\n00:00:00,000 --> 00:00:01,500\nOriginal first cue.\n\n"
            "2\n00:00:01,500 --> 00:00:03,000\nOriginal second cue.\n\n"
        )
        (self.job_dir / "transcript.srt").write_text(transcript, encoding="utf-8")
        (self.job_dir / "transcription.json").write_text(
            '{"state":"done","segments":2,"model_label":"Whisper Large-v3 Turbo"}', encoding="utf-8"
        )

        response = self.client.get(f"/api/jobs/{self.job_id}/transcript")
        self.assertEqual(response.status_code, 200)
        cues = response.get_json()["cues"]
        self.assertEqual(cues[0]["start"], 0.0)
        self.assertEqual(cues[1]["end"], 3.0)

        updates = [{"index": 1, "text": "Corrected first cue."}, {"index": 2, "text": "Corrected second cue."}]
        saved = self.client.put(
            f"/api/jobs/{self.job_id}/transcript",
            json={"cues": updates},
            headers={"X-CSRF-Token": "test-csrf-token-with-at-least-32-characters"},
        )
        self.assertEqual(saved.status_code, 200)
        rewritten = (self.job_dir / "transcript.srt").read_text(encoding="utf-8")
        self.assertIn("Corrected first cue.", rewritten)
        self.assertIn("00:00:01,500 --> 00:00:03,000", rewritten)

    def test_completed_new_upload_automatically_queues_transcription(self) -> None:
        with patch.object(web_app.transcription_executor, "submit") as submit:
            web_app._auto_transcribe_after_extraction(self.job_id)
        status = json.loads((self.job_dir / "transcription.json").read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "queued")
        self.assertTrue(status["automatic"])
        self.assertEqual(status["model"], "whisper-turbo")
        submit.assert_called_once()

    def test_registration_and_login_use_username_and_password_only(self) -> None:
        with self.client.session_transaction() as session:
            session.clear()
            session["csrf_token"] = "test-csrf-token-with-at-least-32-characters"
        response = self.client.post(
            "/register",
            data={
                "username": "new_user",
                "password": "secure-passphrase",
                "csrf_token": "test-csrf-token-with-at-least-32-characters",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.store.authenticate("new_user", "secure-passphrase"))

    def test_registration_can_be_disabled_for_private_instances(self) -> None:
        with patch.object(web_app, "ALLOW_REGISTRATION", False):
            response = self.client.get("/register")
            login = self.client.get("/login")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Create an account", login.get_data(as_text=True))

    def test_health_and_browser_security_headers(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("object-src 'none'", response.headers["Content-Security-Policy"])

    def test_unrecognized_host_is_rejected_when_allowlist_is_configured(self) -> None:
        with patch.object(web_app, "TRUSTED_HOSTS", {"reelscope.example.com"}):
            rejected = self.client.get("/healthz", headers={"Host": "attacker.example"})
            accepted = self.client.get("/healthz", headers={"Host": "reelscope.example.com"})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(accepted.status_code, 200)

    def test_invalid_job_id_is_rejected(self) -> None:
        response = self.client.get("/api/jobs/not-a-job")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
