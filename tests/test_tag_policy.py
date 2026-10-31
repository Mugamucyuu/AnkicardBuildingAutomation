import copy
import json
import unittest
from types import SimpleNamespace

from vocab_app.taxonomy import TagCatalog
from vocab_app.tag_review import audit_tags
from vocab_app.pipeline import ImportPipeline
from run_import import OfflineClient


class Reviewer:
    settings = SimpleNamespace()
    responses = []
    def __init__(self, settings=None, transport=None):
        self.transport = transport
    def generate(self, *args, **kwargs):
        return json.dumps(self.responses.pop(0))


def decision(tags):
    return {"decisions": [{"sense_id": "s1", "keep_tags": tags, "tag_reasons": {t: "词义或构件支持此标签。" for t in tags}}]}


class TagPolicyTests(unittest.TestCase):
    def test_required_origin_and_multiple_component_origins(self):
        catalog = TagCatalog.load()
        for language in ("ja", "ko"):
            with self.assertRaises(ValueError): catalog.validate_sense(["pos::noun"], language)
            self.assertEqual(len(catalog.validate_sense(["pos::noun", "origin::loanword", "origin::sino"], language)), 3)
        with self.assertRaises(ValueError): catalog.validate_sense(["pos::noun", "origin::native"], "en")

    def test_reviewer_can_add_geography_and_remove_informal(self):
        content = {"senses": [{"id": "s1", "tags": ["pos::noun", "register::informal"], "tag_reasons": {}}]}
        Reviewer.responses = [decision(["pos::noun", "domain::social_science::geography"])]
        audit_tags(Reviewer(), content, "en", {}, word="peninsula")
        self.assertIn("domain::social_science::geography", content["senses"][0]["tags"])
        self.assertNotIn("register::informal", content["senses"][0]["tags"])
        self.assertIn("domain::social_science::geography", content["senses"][0]["tag_reasons"])

    def test_reviewer_repairs_missing_plants_and_origin(self):
        content = {"senses": [{"id": "s1", "tags": ["pos::noun"], "tag_reasons": {}}]}
        Reviewer.responses = [decision(["pos::noun", "origin::native", "domain::nature::plants"])]
        audit_tags(Reviewer(), content, "ja", {}, word="桜")
        self.assertIn("domain::nature::plants", content["senses"][0]["tags"])

    def test_reviewer_cannot_remove_mandatory_origin_or_partial_mutate(self):
        content = {"senses": [{"id": "s1", "tags": ["pos::noun", "origin::native"], "tag_reasons": {}}]}
        before = copy.deepcopy(content)
        Reviewer.responses = [decision(["pos::noun"])] * 3
        with self.assertRaises(ValueError): audit_tags(Reviewer(), content, "ja", {})
        self.assertEqual(content, before)

    def test_pipeline_preserves_mixed_origins_and_component_reasons(self):
        model = OfflineClient()
        content = json.loads(model.generate("", json.dumps({"word": "猫", "language": "ja"})))
        sense = content["senses"][0]
        sense["tags"] = ["pos::noun", "origin::loanword", "origin::sino"]
        sense["tag_reasons"] = {"pos::noun": "名词", "origin::loanword": "テレビ构件", "origin::sino": "局构件"}
        model.generate = lambda *a, **k: json.dumps(content)
        note = ImportPipeline(model).generate("テレビ局", "ja")
        self.assertIn("origin::loanword", note["note_tags"])
        self.assertIn("origin::sino", note["note_tags"])

    def test_known_but_language_inappropriate_tag_cannot_be_added(self):
        content = {"senses": [{"id": "s1", "tags": ["pos::noun"], "tag_reasons": {}}]}
        Reviewer.responses = [decision(["pos::noun", "regional::kansai"])] * 3
        with self.assertRaises(ValueError): audit_tags(Reviewer(), content, "en", {})
