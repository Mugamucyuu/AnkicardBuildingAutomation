import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from tests.test_ui import FakeAnki
from vocab_app.examples import OfflineClient
from vocab_app.pipeline import ImportPipeline
from vocab_app.settings import ROOT
from vocab_app.ui_service import UIService, write_json


class BatchWorkflowTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "output").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "output")
        self.anki = FakeAnki()
        self.service = UIService(self.temp.name, self.anki)
        self.note = ImportPipeline(OfflineClient()).generate("apple", "en")
        self.note["provenance"]["provider"] = "deepseek"

    def tearDown(self):
        self.service.pool.shutdown(wait=True)
        self.temp.cleanup()

    def drain(self):
        self.service.pool.submit(lambda: None).result(timeout=15)

    def generate(self, **options):
        return self.service.create_job({"language": "en", "text": "apple,pear,plum,peach",
            "provider": "deepseek", "model": "test", "mode": "independent", "tag_source": "seed",
            "audio": "none", "image": "none", "deck": "English", **options})

    def prepare(self, count=3):
        job = {"id": "batch", "created": "2026", "status": "complete", "cancel": False,
               "config": {"provider": "deepseek", "deck": "English", "tag_source": "seed"},
               "items": [{"status": "ready", "word": str(i), "note_id": None} for i in range(count)]}
        self.service.jobs[job["id"]] = job
        for i in range(count):
            note = copy.deepcopy(self.note)
            note["provenance"]["run_id"] += str(i)
            write_json(Path(self.temp.name) / f"jobs/batch/{i}.json", note)
        self.service.save(job)
        return job

    def test_concurrency_settings_validation_persistence_and_snapshot(self):
        self.assertEqual(self.service.preferences["concurrency"], 4)
        self.service.update_settings({"concurrency": 2})
        for invalid in (0, 33, True, 1.5, "4", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.service.update_settings({"concurrency": invalid})
            with self.assertRaises(ValueError):
                self.generate(concurrency=invalid)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test"}), patch("vocab_app.ui_service.ImportPipeline") as pipeline:
            pipeline.return_value.generate.return_value = self.note
            job = self.generate()
            self.service.update_settings({"concurrency": 3})
            self.drain()
        self.assertEqual(job["config"]["concurrency"], 2)
        reloaded = UIService(self.temp.name, self.anki)
        try:
            self.assertEqual(reloaded.preferences["concurrency"], 3)
        finally:
            reloaded.pool.shutdown()

    def test_parallel_overlap_limit_failure_isolation_and_retry(self):
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        active = peak = 0
        calls = []
        def generate(word, *args):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                calls.append(word)
            try:
                barrier.wait(timeout=5)
                if word == "pear":
                    raise RuntimeError("test failure")
                return copy.deepcopy(self.note)
            finally:
                with lock:
                    active -= 1
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test"}), patch("vocab_app.ui_service.ImportPipeline") as pipeline:
            pipeline.return_value.generate.side_effect = generate
            job = self.generate(concurrency=2)
            self.drain()
            saved = self.service.jobs[job["id"]]
            self.assertEqual(peak, 2)
            self.assertEqual([i["status"] for i in saved["items"]], ["ready", "failed", "ready", "ready"])
            pipeline.return_value.generate.side_effect = lambda *args: copy.deepcopy(self.note)
            self.service.retry(job["id"])
            self.drain()
            self.assertTrue(all(i["status"] == "ready" for i in saved["items"]))
            self.assertEqual(pipeline.return_value.generate.call_count, 5)

    def test_cancel_stops_queued_words_and_waits_for_inflight(self):
        entered, release = threading.Event(), threading.Event()
        def generate(*args):
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test timeout")
            return copy.deepcopy(self.note)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test"}), patch("vocab_app.ui_service.ImportPipeline") as pipeline:
            pipeline.return_value.generate.side_effect = generate
            job = self.generate(concurrency=1)
            try:
                self.assertTrue(entered.wait(timeout=5))
                self.service.cancel(job["id"])
            finally:
                release.set()
            self.drain()
            saved = self.service.jobs[job["id"]]
            self.assertEqual(pipeline.return_value.generate.call_count, 1)
            self.assertEqual(saved["status"], "cancelled")
            self.assertEqual([i["status"] for i in saved["items"]], ["ready", "cancelled", "cancelled", "cancelled"])

    def test_bulk_failure_continues_and_retry_skips_successes(self):
        job = self.prepare()
        job["items"].append({"status": "failed", "note_id": None})
        with patch.object(self.anki, "add_preview", side_effect=[321, RuntimeError("offline"), 322]):
            self.service.import_all("batch", "New deck")
            self.drain()
        self.assertEqual(job["bulk_import"], {"status": "complete", "total": 3, "imported": 2, "failed": 1, "skipped": 1, "deck": "New deck"})
        self.assertEqual(job["items"][1]["status"], "import_failed")
        self.service.import_all("batch")
        self.drain()
        self.assertEqual(job["bulk_import"]["imported"], 1)
        self.assertEqual(self.anki.writes, 1)
        with self.assertRaises(ValueError):
            self.service.import_all("batch")

    def test_bulk_deduplicates_clicks_and_recovers_uncertain_import(self):
        job = self.prepare(1)
        job["items"][0]["status"] = "uncertain"
        self.anki.found = [654]
        entered, release = threading.Event(), threading.Event()
        self.service.pool.submit(lambda: (entered.set(), release.wait(timeout=5)))
        try:
            self.assertTrue(entered.wait(timeout=5))
            first = self.service.import_all("batch")
            self.assertEqual(first, self.service.import_all("batch"))
            with self.assertRaises(ValueError):
                self.service.retry("batch")
        finally:
            release.set()
        self.drain()
        self.assertEqual(job["items"][0]["note_id"], 654)
        self.assertEqual(self.anki.writes, 0)

    def test_bulk_approves_new_tags_together_and_validates(self):
        job = self.prepare(2)
        tag = "domain::technology::robotics"
        proposal = {"tag": tag, "parent": "domain::technology", "label_zh": "机器人", "definition_zh": "机器人领域", "rationale_zh": "测试"}
        for i in range(2):
            path = Path(self.temp.name) / f"jobs/batch/{i}.json"
            note = json.loads(path.read_text(encoding="utf-8"))
            note["proposed_tags"] = [proposal]
            note["note_tags"].append(tag)
            note["senses"][0]["tags"].append(tag)
            job["items"][i]["proposals"] = [proposal]
            write_json(path, note)
        with self.assertRaises(ValueError):
            self.service.import_all("batch")
        self.service.import_all("batch", approve_new_tags=True)
        self.drain()
        self.assertEqual(job["bulk_import"]["imported"], 2)
        self.assertTrue(all(not i["proposals"] for i in job["items"]))
        self.assertIn(tag, json.loads(self.service.metadata_path.read_text(encoding="utf-8"))["tags"])

    def test_bulk_rejects_running_and_offline_jobs_and_marks_restart(self):
        job = self.prepare(1)
        for status, provider in (("running", "deepseek"), ("complete", "offline")):
            job["status"], job["config"]["provider"] = status, provider
            with self.assertRaises(ValueError):
                self.service.import_all("batch")
        job["items"][0]["status"] = "importing"
        job["bulk_import"] = {"status": "running", "total": 1, "imported": 0, "failed": 0, "skipped": 0}
        self.service.save(job)
        reloaded = UIService(self.temp.name, self.anki)
        try:
            self.assertEqual(reloaded.jobs["batch"]["bulk_import"]["status"], "interrupted")
            self.assertEqual(reloaded.jobs["batch"]["items"][0]["status"], "uncertain")
        finally:
            reloaded.pool.shutdown()

    def test_parallel_media_paths_remain_importable_including_audio_fallback(self):
        def download(result, directory, relative_prefix="media"):
            directory.mkdir(parents=True, exist_ok=True)
            for asset in result.assets:
                (directory / "shared.png").write_bytes(b"image")
                asset["local_path"] = relative_prefix + "/shared.png"
            return result
        def audio(word, directory):
            from vocab_app.media import MediaResult
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "shared.mp3").write_bytes(b"audio")
            return MediaResult(assets=[{"kind": "audio", "local_path": "media/shared.mp3"}])
        note = copy.deepcopy(self.note)
        note["images"]["assets"] = [{"kind": "image", "url": "https://example.com/shared.png"}]
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test"}), patch("vocab_app.ui_service.ImportPipeline") as pipeline, \
                patch("vocab_app.public_media.download_assets", side_effect=download), \
                patch("vocab_app.public_media.PublicMediaRegistry.english_audio", side_effect=audio):
            pipeline.return_value.generate.side_effect = lambda *args: copy.deepcopy(note)
            job = self.generate(audio="auto", image="auto", concurrency=2)
            self.drain()
        root = Path(self.temp.name) / "jobs" / job["id"]
        for i, item in enumerate(self.service.jobs[job["id"]]["items"]):
            self.assertEqual(item["status"], "ready")
            saved = json.loads((root / f"{i}.json").read_text(encoding="utf-8"))
            for group, suffix in (("pronunciation", "mp3"), ("images", "png")):
                relative = saved[group]["assets"][0]["local_path"]
                self.assertEqual(relative, f"media/{i}-shared.{suffix}")
                self.assertTrue((root / relative).is_file())
