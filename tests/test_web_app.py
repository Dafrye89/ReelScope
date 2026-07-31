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


class WebAppHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.jobs_dir = Path(self.temp_dir.name) / "jobs"
        self.job_id = "a" * 32
        self.job_dir = self.jobs_dir / self.job_id
        self.frames_dir = self.job_dir / "frames"
        self.frames_dir.mkdir(parents=True)

        Image.new("RGB", (320, 180), "#6d5dfc").save(self.frames_dir / "00000001_t000000000ms.jpg")
        Image.new("RGB", (320, 180), "#151d2d").save(self.frames_dir / "00000002_t000000040ms.jpg")
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

        self.jobs_patch = patch.object(web_app, "JOBS_DIR", self.jobs_dir)
        self.jobs_patch.start()
        with web_app.jobs_lock:
            web_app.jobs.clear()
        web_app.app.config.update(TESTING=True)
        self.client = web_app.app.test_client()

    def tearDown(self) -> None:
        with web_app.jobs_lock:
            web_app.jobs.clear()
        self.jobs_patch.stop()
        self.temp_dir.cleanup()

    def test_completed_job_is_restored_and_listed(self) -> None:
        response = self.client.get("/api/jobs")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["jobs"]), 1)
        job = payload["jobs"][0]
        self.assertEqual(job["filename"], "demo clip.mp4")
        self.assertEqual(job["frames_count"], 2)
        self.assertEqual(job["width"], 320)
        self.assertEqual(job["height"], 180)
        self.assertTrue(job["thumbnail"].endswith(".jpg"))

    def test_detail_exposes_frames_and_serves_image(self) -> None:
        detail = self.client.get(f"/api/jobs/{self.job_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.get_json()
        self.assertEqual(len(payload["frames"]), 2)

        frame = self.client.get(f"/jobs/{self.job_id}/frames/{payload['frames'][0]}")
        try:
            self.assertEqual(frame.status_code, 200)
            self.assertEqual(frame.mimetype, "image/jpeg")
        finally:
            frame.close()

    def test_png_and_zip_exports(self) -> None:
        png = self.client.get(f"/api/jobs/{self.job_id}/frame/0/download.png")
        self.assertEqual(png.status_code, 200)
        self.assertEqual(png.mimetype, "image/png")
        with Image.open(io.BytesIO(png.data)) as image:
            self.assertEqual(image.size, (320, 180))

        archive = self.client.get(f"/api/jobs/{self.job_id}/download.zip?format=jpg")
        self.assertEqual(archive.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(archive.data)) as bundle:
            names = bundle.namelist()
        self.assertTrue(any(name.endswith("meta.json") for name in names))
        self.assertEqual(sum(name.endswith(".jpg") for name in names), 2)

    def test_invalid_job_id_is_rejected(self) -> None:
        response = self.client.get("/api/jobs/not-a-job")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
