import base64
import copy
from pathlib import Path
import tempfile
import unittest

from run_import import OfflineClient
from vocab_app.pipeline import ImportPipeline
from vocab_app.anki import AnkiClient
from vocab_app.settings import ROOT


class AnkiMediaImportTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "output").mkdir(exist_ok=True)
        self.note = ImportPipeline(OfflineClient()).generate("apple", "en")
        self.note["provenance"]["provider"] = "deepseek"
        self.actions = []
        self.stored = {}
        self.corrupt = False

    def transport(self, url, payload, **kwargs):
        action = payload["action"]
        params = payload["params"]
        self.actions.append(payload)
        values = {"getTags": [], "deckNames": ["English"], "modelFieldNames": ["正面", "背面", "笔记"], "addNote": 123}
        if action == "storeMediaFile":
            self.assertFalse(params["deleteExisting"])
            name = params["filename"].replace(".mp3", " (1).mp3")
            self.stored[name] = params["data"]
            value = name
        elif action == "retrieveMediaFile":
            value = base64.b64encode(b"wrong").decode() if self.corrupt else self.stored[params["filename"]]
        else:
            value = values[action]
        return {"result": value, "error": None}

    def test_media_roundtrip_native_audio_image_paths_and_no_preview_mutation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as folder:
            media = Path(folder) / "media";media.mkdir()
            (media / "a.mp3").write_bytes(b"audio sample")
            (media / "b.jpg").write_bytes(b"image sample")
            self.note["pronunciation"]["assets"] = [{"kind": "audio", "local_path": "media/a.mp3"}]
            self.note["images"]["assets"] = [{"kind": "image", "local_path": "media/b.jpg"}]
            original = copy.deepcopy(self.note)
            client = AnkiClient(transport=self.transport)
            self.assertEqual(client.add_preview(self.note, "English", model="AI-note", media_root=folder), 123)
        body = self.actions[-1]["params"]["note"]["fields"]["背面"]
        self.assertIn("[sound:vocab-", body)
        self.assertIn(" (1).mp3]", body)
        self.assertIn('<img src="vocab-', body)
        self.assertNotIn('src="media/', body)
        self.assertEqual(self.note, original)
        self.assertEqual(len(client.last_import_media), 2)

    def test_missing_or_traversal_media_never_uploads(self):
        for path in ("media/missing.mp3", "../private.mp3"):
            with self.subTest(path=path), tempfile.TemporaryDirectory(dir=ROOT / "output") as folder:
                self.note["pronunciation"]["assets"] = [{"kind": "audio", "local_path": path}]
                with self.assertRaises(ValueError):
                    AnkiClient(transport=self.transport).add_preview(self.note, "English", model="AI-note", media_root=folder)
        self.assertFalse(any(p["action"] in ("storeMediaFile", "addNote") for p in self.actions))

    def test_corrupt_upload_does_not_add_note(self):
        self.corrupt = True
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as folder:
            media = Path(folder) / "media";media.mkdir();(media / "a.mp3").write_bytes(b"audio")
            self.note["pronunciation"]["assets"] = [{"kind": "audio", "local_path": "media/a.mp3"}]
            with self.assertRaises(ValueError):
                AnkiClient(transport=self.transport).add_preview(self.note, "English", model="AI-note", media_root=folder)
        self.assertFalse(any(p["action"] == "addNote" for p in self.actions))
