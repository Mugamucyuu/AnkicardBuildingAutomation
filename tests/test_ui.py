import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from run_import import OfflineClient
from run_ui import make_handler
from vocab_app.pipeline import ImportPipeline
from vocab_app.anki import AnkiClient
from vocab_app.research import ResearchCollector
from vocab_app.prompts import DEFAULTS
from vocab_app.settings import ROOT
from vocab_app.ui_service import UIService, parse_words, write_json


class FakeAnki:
    def __init__(self):
        self.writes = 0
        self.found = []
    def invoke(self, action, **params):
        if action == "getTags": return ["domain::nature::plants::trees", "旧标签"]
        if action == "deckNames": return ["English", "日本語", "한국어"]
        if action == "version": return 6
        if action == "findNotes": return self.found
        raise AssertionError(action)
    def add_preview(self, *args, **kwargs):
        self.writes += 1
        return 321


class UIServiceTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "output").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "output")
        self.anki = FakeAnki()
        self.service = UIService(self.temp.name, self.anki)
    def tearDown(self):
        self.service.pool.shutdown(wait=True)
        self.temp.cleanup()

    def test_parser_keeps_phrases_and_removes_duplicates(self):
        self.assertEqual(parse_words("# English\n- pine after, curd、curd\n2. peninsula"), ["pine after", "curd", "peninsula"])
        with self.assertRaises(ValueError): parse_words("x" * 201)

    def test_all_prompts_replaceable_snapshots_are_immutable(self):
        store = self.service.prompts
        before = store.snapshot()
        for stage in DEFAULTS:
            file_id = store.upload("my.md", "Custom instructions", stage)
            store.bind(stage, file_id)
        after = store.snapshot()
        self.assertTrue(all(v == "Custom instructions" for v in after.values()))
        self.assertNotEqual(before["generation"], after["generation"])
        store.bind("generation", None)
        self.assertEqual(store.snapshot()["generation"], before["generation"])
        for bad in ("../key.txt", "C:\\key.md", "bad.html"):
            with self.assertRaises(ValueError): store.upload(bad, "data")
        with self.assertRaises(ValueError): store.read("builtin/../../config.py")

    def test_prompt_categories_enforced_on_binding_read_and_supplement(self):
        store = self.service.prompts
        japanese = store.upload("ja.MD", "Japanese instructions", "style_ja")
        extra = store.upload("extra.md", "Extra instructions", "supplement")
        store.bind("style_ja", japanese)
        self.assertIn(japanese, [f["id"] for f in store.files("style_ja")])
        self.assertNotIn(japanese, [f["id"] for f in store.files("tag_review")])
        with self.assertRaises(ValueError): store.bind("tag_review", japanese)
        with self.assertRaises(ValueError): store.read(japanese, "generation")
        with self.assertRaises(ValueError): store.snapshot({"generation": japanese})
        with self.assertRaises(ValueError): store.snapshot(supplement=japanese)
        snapshot = store.snapshot(supplement=extra)
        self.assertTrue(snapshot["generation"].endswith("\n\nExtra instructions"))
        self.assertEqual(snapshot["style_ja"], "Japanese instructions")
        reloaded = type(store)(store.directory)
        self.assertEqual(reloaded.files("supplement")[0]["id"], extra)

    def test_existing_bound_upload_keeps_type_unbound_files_not_guessed(self):
        directory = self.service.prompts.directory
        directory.mkdir(parents=True)
        (directory / "old.md").write_text("Earlier instructions", encoding="utf-8")
        (directory / "unknown.md").write_text("Unknown purpose", encoding="utf-8")
        write_json(directory / "bindings.json", {"style_en": "custom/old.md"})
        self.assertEqual(self.service.prompts.files("style_en")[-1]["id"], "custom/old.md")
        self.assertEqual(self.service.prompts.files("unclassified")[0]["id"], "custom/unknown.md")
        self.assertEqual(self.service.prompts.snapshot()["style_en"], "Earlier instructions")

    def test_three_language_offline_jobs_persist_without_network_or_anki_writes(self):
        with patch("vocab_app.transport.urlopen", side_effect=AssertionError("No network")):
            for lang, word in (("en", "apple"), ("ja", "猫"), ("ko", "나무")):
                self.service.create_job({"language": lang, "text": word, "provider": "offline", "mode": "independent"})
            self.service.pool.shutdown(wait=True)
        for job in self.service.list_jobs():
            self.assertEqual(job["items"][0]["status"], "ready")
            root = Path(self.temp.name) / "jobs" / job["id"]
            self.assertTrue((root / "0.html").exists())
            note = json.loads((root / "0.json").read_text(encoding="utf-8"))
            self.assertEqual(set(note["prompt_sha256"]), set(DEFAULTS))
            with self.assertRaises(ValueError): self.service.import_item(job["id"], 0, "English")
        self.assertEqual(self.anki.writes, 0)
        reloaded = UIService(self.temp.name, self.anki)
        self.assertEqual(len(reloaded.list_jobs()), 3)
        reloaded.pool.shutdown()

    def test_credentials_never_persist_or_return(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.service.update_settings({"locale": "ja", "keys": {"deepseek": "test-secret-123"}})
            self.assertTrue(response["credentials"]["deepseek"])
            self.assertNotIn("test-secret", json.dumps(response))
            self.assertNotIn("test-secret", self.service.settings_path.read_text())
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "test-secret-123")

    def test_tree_includes_deep_user_tags_and_excluded_tags(self):
        data = self.service.tags()
        self.assertTrue(next(e for e in data["entries"] if e["tag"] == "domain::nature::plants::trees")["in_anki"])
        self.assertTrue(next(e for e in data["entries"] if e["tag"] == "旧标签")["excluded"])

    def test_import_idempotency_and_recovery_after_uncertain_result(self):
        note = ImportPipeline(OfflineClient()).generate("apple", "en")
        note["provenance"]["provider"] = "deepseek"
        job = {"id": "test-job", "created": "2026", "status": "complete", "config": {"deck": "English"}, "items": [{"status": "ready", "word": "apple", "note_id": None}]}
        self.service.jobs[job["id"]] = job
        write_json(Path(self.temp.name) / "jobs/test-job/0.json", note)
        self.assertEqual(self.service.import_item(job["id"], 0)["note_id"], 321)
        self.assertEqual(self.service.import_item(job["id"], 0)["note_id"], 321)
        self.assertEqual(self.anki.writes, 1)
        job["items"][0].update(status="uncertain", note_id=None)
        self.anki.found = [654]
        self.assertEqual(self.service.import_item(job["id"], 0)["note_id"], 654)
        self.assertEqual(self.anki.writes, 1)

    def test_auto_import_failure_keeps_preview_and_does_not_regenerate(self):
        note = ImportPipeline(OfflineClient()).generate("apple", "en")
        note["provenance"]["provider"] = "deepseek"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}), patch("vocab_app.ui_service.ImportPipeline") as pipeline:
            pipeline.return_value.generate.return_value = note
            with patch.object(self.anki, "add_preview", side_effect=RuntimeError("Anki unavailable")):
                job = self.service.create_job({"language": "en", "text": "apple", "provider": "deepseek", "model": "test", "mode": "independent", "tag_source": "seed", "audio": "none", "image": "none", "auto_import": True, "deck": "English"})
                self.service.pool.shutdown(wait=True)
        saved = self.service.jobs[job["id"]]
        self.assertEqual(saved["items"][0]["status"], "import_failed")
        self.assertTrue(saved["items"][0]["preview"])
        with self.assertRaises(ValueError): self.service.retry(job["id"])

    def test_approved_proposals_still_validate_and_default_import_stays_blocked(self):
        note = ImportPipeline(OfflineClient()).generate("apple", "en")
        note["provenance"]["provider"] = "deepseek"
        tag = "domain::technology::robotics"
        note["proposed_tags"] = [{"tag": tag, "parent": "domain::technology", "label_zh": "机器人", "definition_zh": "机器人领域", "rationale_zh": "测试"}]
        note["senses"][0]["tags"].append(tag)
        note["note_tags"] = sorted(note["note_tags"] + [tag])
        responses = {"getTags": [], "deckNames": ["English"], "modelFieldNames": ["正面", "背面", "笔记"], "addNote": 432}
        calls = []
        def transport(url, payload, **kwargs):
            calls.append(payload["action"])
            return {"error": None, "result": responses[payload["action"]]}
        client = AnkiClient(transport=transport)
        with self.assertRaises(ValueError): client.add_preview(note, "English")
        self.assertEqual(calls, [])
        note["proposal_review"] = {"decision": "approve"}
        self.assertEqual(client.add_preview(note, "English", model="AI-note", approved_proposals=[tag]), 432)
        self.assertEqual(calls.count("addNote"), 1)

    def test_free_dictionary_exact_entry_does_not_need_search(self):
        payload = [{"word": "curd", "meanings": [{"partOfSpeech": "noun", "definitions": [{"definition": "Coagulated milk.", "example": "The curd is ready."}]}]}]
        with patch("vocab_app.public_media.fetch", return_value=json.dumps(payload)):
            search = unittest.mock.Mock()
            result = ResearchCollector(search).collect("curd", "en", "sources", ["free_dictionary"])
        self.assertEqual(result["sources"][0]["id"], "S1")
        self.assertIn("Coagulated milk", result["sources"][0]["excerpt"])
        search.search.assert_not_called()


class UIHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "output")
        self.service = UIService(self.temp.name, FakeAnki())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service, "test-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.service.pool.shutdown(wait=True)
        self.temp.cleanup()
    def request(self, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        connection.request("GET" if body is None else "POST", path, body=json.dumps(body) if body is not None else None, headers=headers or {})
        response = connection.getresponse()
        result = (response.status, response.read())
        connection.close()
        return result
    def test_browser_origin_and_token_protect_mutations(self):
        self.assertEqual(self.request("/api/bootstrap", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("/api/bootstrap", headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.request("/api/settings", {"locale": "en"})[0], 403)
        self.assertEqual(self.request("/api/parse", {"text": "curd"}, {"Content-Type": "application/json", "X-Vocab-Token": "test-token"})[0], 200)
        self.assertEqual(self.request("/preview/../settings.json")[0], 404)
        self.assertEqual(self.request("/config.py")[0], 404)

    def test_offline_job_through_http(self):
        status, body = self.request("/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["token"], "test-token")
        status, body = self.request("/api/jobs", {"language": "en", "text": "apple", "provider": "offline", "mode": "independent"}, {"Content-Type": "application/json", "X-Vocab-Token": "test-token"})
        self.assertEqual(status, 200)
        self.service.pool.shutdown(wait=True)
        job_id = json.loads(body)["id"]
        status, preview = self.request(f"/preview/{job_id}/0.html")
        self.assertEqual(status, 200)
        self.assertIn(b"apple", preview)
        self.assertEqual(self.request(f"/preview/{job_id}/prompts.json")[0], 404)


if __name__ == "__main__":
    unittest.main()
