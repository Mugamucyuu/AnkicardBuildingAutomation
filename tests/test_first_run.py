"""Collection setup is tested in memory; never touch a user's Anki profile."""
import copy
import tempfile
from pathlib import Path
import unittest

from vocab_app.anki import AnkiClient, MODEL_NAME, FIELDS
from vocab_app.examples import OfflineClient
from vocab_app.pipeline import ImportPipeline
from vocab_app.taxonomy import TagCatalog
from vocab_app.settings import ROOT
from vocab_app.ui_service import UIService


class Collection:
    def __init__(self, populated=False):
        self.tags = ["domain::nature::plants::trees", "旧标签"] if populated else []
        self.decks = ["Personal"] if populated else []
        self.models = {"Basic": ["Front", "Back"]} if populated else {}
        self.old_note = {"id": 99, "fields": {"Front": "Existing"}, "reviews": 42}
        self.notes = [copy.deepcopy(self.old_note)] if populated else []
        self.calls = []
    def __call__(self, url, payload, **kwargs):
        action, params = payload["action"], payload["params"]
        self.calls.append(action)
        if action == "getTags": result = self.tags
        elif action == "deckNames": result = list(self.decks)
        elif action == "modelNames": result = list(self.models)
        elif action == "modelFieldNames": result = self.models[params["modelName"]]
        elif action == "createDeck":
            self.decks.append(params["deck"]); result = 1
        elif action == "createModel":
            self.models[params["modelName"]] = params["inOrderFields"]
            result = {"id": 1}
        elif action == "addNote":
            self.notes.append(copy.deepcopy(params["note"])); result = len(self.notes) + 100
        else: raise AssertionError(action)
        return {"result": copy.deepcopy(result), "error": None}


def live_fixture():
    note = ImportPipeline(OfflineClient()).generate("apple", "en")
    note["provenance"]["provider"] = "deepseek"
    return note


class FirstRunTests(unittest.TestCase):
    def test_empty_collection_creates_note_type_and_deck_once(self):
        collection = Collection()
        client = AnkiClient(transport=collection)
        client.add_preview(live_fixture(), "English")
        client.add_preview(live_fixture(), "English")
        self.assertEqual(collection.calls.count("createDeck"), 1)
        self.assertEqual(collection.calls.count("createModel"), 1)
        self.assertEqual(collection.models[MODEL_NAME], list(FIELDS))
        self.assertIn("Word", collection.notes[0]["fields"])

    def test_populated_collection_and_review_history_are_preserved(self):
        collection = Collection(populated=True)
        before_models = copy.deepcopy(collection.models)
        AnkiClient(transport=collection).add_preview(live_fixture(), "Personal")
        self.assertEqual(collection.notes[0], collection.old_note)
        self.assertEqual(collection.models["Basic"], before_models["Basic"])
        self.assertNotIn("createDeck", collection.calls)
        self.assertEqual(collection.notes[1]["deckName"], "Personal")

    def test_incompatible_same_named_type_is_not_modified(self):
        collection = Collection(populated=True)
        collection.models[MODEL_NAME] = ["Unrelated", "Fields"]
        AnkiClient(transport=collection).add_preview(live_fixture(), "Personal")
        self.assertEqual(collection.models[MODEL_NAME], ["Unrelated", "Fields"])
        self.assertEqual(collection.notes[-1]["modelName"], MODEL_NAME + " (2)")

    def test_api_key_passed_only_in_request_not_error(self):
        payloads = []
        def transport(url, payload, **kwargs):
            payloads.append(payload)
            return {"result": 6, "error": None}
        self.assertEqual(AnkiClient(transport=transport, api_key="unit-test-key").invoke("version"), 6)
        self.assertEqual(payloads[0]["key"], "unit-test-key")

    def test_empty_and_nonstandard_tags_allow_starter_pos_and_origins(self):
        for populated in (False, True):
            catalog = TagCatalog.from_anki(AnkiClient(transport=Collection(populated)))
            for language, word in (("en", "apple"), ("ja", "猫"), ("ko", "나무")):
                note = ImportPipeline(OfflineClient(), tag_catalog=catalog).generate(word, language)
                self.assertIn("pos::noun", note["note_tags"])
                if language != "en": self.assertIn("origin::native", note["note_tags"])

    def test_fresh_ui_has_only_generic_examples_and_uses_writable_state(self):
        (ROOT / "output").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory:
            service = UIService(directory, anki=AnkiClient(transport=Collection()))
            try:
                self.assertEqual(service.bootstrap()["vocabulary"], ["en.txt", "ja.txt", "ko.txt"])
                self.assertEqual(service.list_jobs(), [])
                self.assertIn("peninsula", service.vocabulary("en.txt")["text"])
                self.assertEqual(service.tags()["snapshot"]["anki_tags"], [])
                self.assertEqual(service.metadata_path, Path(directory) / "tag_metadata.json")
            finally:
                service.pool.shutdown()

    def test_invalid_deck_is_rejected_before_creating_anki_resources(self):
        for deck in ("", "a::::b", "a\nb"):
            collection = Collection()
            with self.assertRaises(ValueError): AnkiClient(transport=collection).add_preview(live_fixture(), deck)
            self.assertNotIn("createDeck", collection.calls)
            self.assertNotIn("createModel", collection.calls)
