import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from run_import import OfflineClient
from vocab_app.pipeline import ImportPipeline
from vocab_app.taxonomy import TagCatalog
from vocab_app.tag_review import audit_tags
from vocab_app.settings import ROOT


CUSTOM = "domain::nature::plants::trees"


def synced(tags):
    client = Mock()
    client.invoke.return_value = tags
    return TagCatalog.from_anki(client)


class CapturingReviewer:
    settings = None
    payload = None
    transport = None
    def __init__(self, settings=None, transport=None):
        pass
    def generate(self, instruction, user, **kwargs):
        type(self).payload = json.loads(user)
        return json.dumps({"decisions": [{"sense_id": "s1", "keep_tags": ["pos::noun", CUSTOM],
                           "tag_reasons": {"pos::noun": "Noun", CUSTOM: "A tree"}}]})


class AnkiTagSnapshotTests(unittest.TestCase):
    def test_exact_unique_legacy_name_equivalence_avoids_duplicate_labels(self):
        catalog = synced(["geography"])
        self.assertEqual(catalog.validate_sense(["geography", "domain::social_science::geography", "pos::noun"], "en"), ["geography", "pos::noun"])
        self.assertEqual(catalog.prompt_context("en")["equivalent_tags"], [{"preferred": "geography", "equivalent": "domain::social_science::geography"}])
    def test_import_existing_deep_tag_but_block_automatic_deep_proposal(self):
        catalog = synced([CUSTOM])
        self.assertIn(CUSTOM, catalog.validate_sense([CUSTOM, "pos::noun"], "en"))
        self.assertEqual(catalog.entries[CUSTOM]["source"], "anki")
        with self.assertRaises(ValueError):
            catalog.add_proposals([{"tag": CUSTOM + "::cherry", "parent": CUSTOM, "label_zh": "樱树", "definition_zh": "樱树", "rationale_zh": "test"}], "ja")

    def test_invalid_legacy_tags_are_visible_but_not_assignable(self):
        catalog = synced(["植物", "pos::particle", "origin::mixed", "region::us", "geography"])
        self.assertEqual(len(catalog.snapshot["excluded"]), 4)
        self.assertIn("geography", catalog.entries)
        self.assertNotIn("植物", catalog.entries)
        with self.assertRaises(ValueError): catalog.validate_sense(["pos::particle", "origin::mixed"], "ja")

    def test_synthesized_parent_is_group_not_automatic_assignment(self):
        catalog = synced(["my_topics::maritime::coasts"])
        self.assertEqual(catalog.entries["my_topics"]["kind"], "group")
        self.assertIn("my_topics::maritime::coasts", catalog.validate(["my_topics::maritime::coasts"], "en"))

    def test_new_batch_observes_new_tags_while_existing_snapshot_stays_fixed(self):
        client = Mock()
        client.invoke.return_value = []
        first = TagCatalog.from_anki(client)
        client.invoke.return_value = [CUSTOM]
        second = TagCatalog.from_anki(client)
        self.assertNotIn(CUSTOM, first.entries)
        self.assertIn(CUSTOM, second.entries)
        self.assertNotEqual(first.snapshot_info()["id"], second.snapshot_info()["id"])

    def test_no_description_is_explicit_and_optional_metadata_applies(self):
        catalog = synced([CUSTOM])
        self.assertEqual(catalog.entries[CUSTOM]["description_source"], "name_only")
        (ROOT / "output").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as folder:
            path = Path(folder) / "metadata.json"
            path.write_text(json.dumps({"tags": {CUSTOM: {"definition_zh": "树木名称", "languages": ["ja"]}}}), encoding="utf-8")
            client = Mock();client.invoke.return_value = [CUSTOM]
            catalog = TagCatalog.from_anki(client, path)
        self.assertEqual(catalog.entries[CUSTOM]["description_source"], "user_metadata")
        self.assertNotIn(CUSTOM, [e["tag"] for e in catalog.prompt_context("en")["allowed_tags"]])

    def test_pipeline_review_and_validation_share_snapshot_without_anki_reread(self):
        catalog = synced([CUSTOM])
        fixture = json.loads(OfflineClient().generate("", json.dumps({"language": "en", "word": "apple"})))
        fixture["senses"][0]["tags"].append(CUSTOM)
        fixture["senses"][0]["tag_reasons"][CUSTOM] = "test tree sense"
        model = OfflineClient()
        captured = []
        def generate(instruction, user, **kwargs):
            captured.append(json.loads(user))
            return json.dumps(fixture)
        model.generate = generate
        with patch("vocab_app.anki.AnkiClient.invoke", side_effect=AssertionError("No reread")):
            note = ImportPipeline(model, tag_catalog=catalog).generate("apple", "en")
            review = audit_tags(CapturingReviewer(), note, "en", {}, catalog=catalog)
        self.assertEqual(captured[0]["tag_snapshot"]["id"], CapturingReviewer.payload["tag_snapshot"]["id"])
        self.assertEqual(note["tag_snapshot"]["id"], catalog.snapshot_info()["id"])
        self.assertIn(CUSTOM, CapturingReviewer.payload["allowed_tags"][-1]["tag"])

    def test_import_rechecks_current_anki_user_tag_not_snapshot_claim(self):
        from vocab_app.anki import AnkiClient
        note = ImportPipeline(OfflineClient(), tag_catalog=synced([CUSTOM])).generate("apple", "en")
        note["provenance"]["provider"] = "deepseek"
        note["senses"][0]["tags"].append(CUSTOM)
        note["note_tags"] = sorted(note["senses"][0]["tags"])
        actions = []
        def transport(url, payload, **kwargs):
            actions.append(payload["action"])
            values = {"getTags": [], "deckNames": ["English"]}
            return {"result": values[payload["action"]], "error": None}
        with self.assertRaises(ValueError): AnkiClient(transport=transport).add_preview(note, "English")
        self.assertEqual(actions, ["getTags"])
