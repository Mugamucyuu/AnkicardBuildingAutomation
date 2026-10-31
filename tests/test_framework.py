import copy
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from run_import import OfflineClient, main
from vocab_app.anki import AnkiClient
from vocab_app.pipeline import ImportPipeline
from vocab_app.preview import render_preview
from vocab_app.providers import ModelClient
from vocab_app.settings import Settings, ROOT
from vocab_app.taxonomy import TagCatalog
from vocab_app.transport import ServiceError, request_json
from urllib.error import HTTPError

FIXTURE = json.loads((ROOT / "tests/fixtures/vocabulary.json").read_text(encoding="utf-8"))

class FakeModel:
    settings = Settings("openai", "test-model")
    def __init__(self, content):
        self.content = content
    def generate(self, *args, **kwargs):
        return json.dumps(self.content, ensure_ascii=False)

class FrameworkTests(unittest.TestCase):
    def test_offline_all_languages_no_network(self):
        with patch("vocab_app.transport.urlopen", side_effect=AssertionError("No network")):
            for language, word in (("en", "apple"), ("ja", "猫"), ("ko", "나무")):
                note = ImportPipeline(OfflineClient()).generate(word, language)
                self.assertEqual(note["note_tags"], ["pos::noun"] if language == "en" else ["origin::native", "pos::noun"])
                self.assertEqual(note["provenance"]["provider"], "offline")
                self.assertEqual(note["pronunciation"]["assets"], [])
                self.assertTrue(note["review_required"])

    def test_unknown_and_language_inappropriate_tags_rejected(self):
        catalog = TagCatalog.load()
        for tags, lang in [(["pos::particle"], "ja"), (["origin::native"], "en"),
                           (["medium::written"], "en"), (["region::ja"], "ja"),
                           (["region::en::us"], "ko")]:
            with self.subTest(tags=tags), self.assertRaises(ValueError):
                catalog.validate(tags, lang)

    def test_invalid_ai_result_does_not_reach_export(self):
        for change in ("duplicate_id", "empty_example", "missing_reason", "missing_origin"):
            content = copy.deepcopy(FIXTURE["ja:猫"])
            if change == "duplicate_id":
                content["senses"].append(copy.deepcopy(content["senses"][0]))
            elif change == "empty_example":
                content["senses"][0]["examples"] = [""]
            elif change == "missing_reason":
                content["senses"][0]["tag_reasons"] = {}
            else:
                content["senses"][0]["tags"] = ["pos::noun"]
            with self.subTest(change=change), self.assertRaises(ValueError):
                ImportPipeline(FakeModel(content)).generate("猫", "ja")

    def test_parent_tags_deduplicated(self):
        tags = TagCatalog.load().validate(["domain::technology", "domain::technology::computing"], "en")
        self.assertEqual(tags, ["domain::technology::computing"])

    def test_proposals_cannot_restore_removed_categories(self):
        for tag, parent in [("pos::particle", "pos"), ("region::en::au", "region::en"),
                            ("medium::spoken", "medium"),
                            ("domain::technology::computing::programming", "domain::technology::computing")]:
            proposal = {"tag": tag, "parent": parent, "label_zh": "说明", "definition_zh": "定义", "rationale_zh": "理由"}
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                TagCatalog.load().add_proposals([proposal], "en")

    def test_new_broad_domain_preview_and_export_gate(self):
        content = copy.deepcopy(FIXTURE["en:apple"])
        content["proposed_tags"] = [{
            "tag": "domain::technology::robotics", "parent": "domain::technology",
            "label_zh": "机器人技术", "definition_zh": "机器人系统的宽泛领域",
            "rationale_zh": "示例新领域", "aliases": [],
        }]
        content["senses"][0]["tags"].append("domain::technology::robotics")
        content["senses"][0]["tag_reasons"]["domain::technology::robotics"] = "测试用提案"
        note = ImportPipeline(FakeModel(content)).generate("apple", "en")
        self.assertEqual(note["proposed_tags"][0]["status"], "needs_review")
        self.assertNotIn("domain::technology::robotics", TagCatalog.load().entries)
        with self.assertRaises(ValueError):
            AnkiClient(transport=lambda *a, **k: self.fail("No Anki request")).add_preview(note, "English")

    def test_preview_escapes_model_html(self):
        note = ImportPipeline(OfflineClient()).generate("apple", "en")
        note["senses"][0]["definition"] = '<script>alert("x")</script>'
        html = render_preview(note)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_provider_payloads_and_parsing(self):
        for provider in ("deepseek", "openai"):
            requests = []
            def transport(url, payload, **kwargs):
                requests.append((url, payload, kwargs))
                if provider == "openai":
                    return {"status": "completed", "output": [
                        {"type": "reasoning"},
                        {"type": "message", "content": [{"type": "output_text", "text": "{}"}]},
                    ]}
                return {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
            variable = "OPENAI_API_KEY" if provider == "openai" else "DEEPSEEK_API_KEY"
            with patch.dict(os.environ, {variable: "unit-test-placeholder"}):
                client = ModelClient(Settings(provider, "test-model"), transport)
                self.assertEqual(client.generate("Return JSON", "word", json_output=True), "{}")
            url, payload, kwargs = requests[0]
            self.assertNotIn("unit-test-placeholder", json.dumps(payload))
            if provider == "openai":
                self.assertEqual(url, "https://api.openai.com/v1/responses")
                self.assertFalse(payload["store"])
                self.assertIn("text", payload)
            else:
                self.assertIn("response_format", payload)

    def test_missing_credentials_prevent_network(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                ModelClient(Settings("openai", "test"), lambda *a, **k: self.fail("Network")).generate("s", "u")

    def test_truncated_response_rejected(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "placeholder"}):
            client = ModelClient(Settings("deepseek", "test"), lambda *a, **k: {
                "choices": [{"finish_reason": "length", "message": {"content": "{}"}}]})
            with self.assertRaises(ServiceError):
                client.generate("s", "u")

    def test_transport_errors_do_not_leak_response_or_auth(self):
        error = HTTPError("https://example.test", 401, "SECRET_BODY", {}, io.BytesIO(b"SECRET_BODY"))
        with patch("vocab_app.transport.urlopen", side_effect=error):
            with self.assertRaises(ServiceError) as caught:
                request_json("https://example.test", {}, headers={"Authorization": "SECRET_HEADER"})
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertIn("401", str(caught.exception))

    def test_anki_import_validates_then_preserves_tags(self):
        actions = []
        def transport(url, payload, **kwargs):
            actions.append(payload)
            result = {"getTags": [], "deckNames": ["English"], "modelFieldNames": ["正面", "背面", "笔记"], "addNote": 123}[payload["action"]]
            return {"result": result, "error": None}
        note = ImportPipeline(OfflineClient()).generate("apple", "en")
        note["provenance"]["provider"] = "openai"
        self.assertEqual(AnkiClient(transport=transport).add_preview(note, "English", model="AI-note"), 123)
        self.assertEqual(actions[-1]["params"]["note"]["tags"], ["pos::noun"])

    def test_cli_default_only_writes_preview(self):
        folder = ROOT / "output/test-preview"
        folder.mkdir(parents=True, exist_ok=True)
        with patch("vocab_app.transport.urlopen", side_effect=AssertionError("No network")):
            self.assertEqual(main(["--output-dir", str(folder)]), 0)
            self.assertEqual(len(list(Path(folder).glob("*.html"))), 1)
            self.assertEqual(len(list(Path(folder).glob("*.json"))), 1)

    def test_offline_cannot_import(self):
        with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit):
            main(["--import-anki", "--deck", "English"])

    def test_import_reads_reviewed_preview_without_regeneration(self):
        folder = ROOT / "output/test-import"
        folder.mkdir(parents=True, exist_ok=True)
        preview = folder / "reviewed.json"
        note = ImportPipeline(OfflineClient()).generate("apple", "en")
        note["provenance"]["provider"] = "openai"
        preview.write_text(json.dumps(note), encoding="utf-8")
        with patch.object(AnkiClient, "add_preview", return_value=321) as add, patch.object(ModelClient, "generate", side_effect=AssertionError("No regeneration")):
            self.assertEqual(main(["--import-anki", "--import-preview", str(preview), "--deck", "English"]), 0)
        self.assertEqual(add.call_args.args[0]["word"], "apple")

    def test_offline_preview_rejected_before_anki_request(self):
        note = ImportPipeline(OfflineClient()).generate("apple", "en")
        with self.assertRaises(ValueError):
            AnkiClient(transport=lambda *a, **k: self.fail("No request")).add_preview(note, "English")

if __name__ == "__main__":
    unittest.main()
