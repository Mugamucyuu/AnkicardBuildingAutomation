import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from vocab_app.prompts import PromptStore
from vocab_app.settings import ROOT
from vocab_app.ui_service import UIService


class PromptEditorTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "output").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "output")
        self.store = PromptStore(Path(self.temp.name) / "prompts")

    def tearDown(self):
        self.temp.cleanup()

    def test_edit_builtin_keeps_original_and_requires_explicit_activation(self):
        source = "builtin/style_en.txt"
        original = self.store.document(source, "style_en")
        saved = self.store.save_version("English.md", "A new style.\n中文", "style_en",
            source=source, expected_sha256=original["sha256"])
        self.assertEqual(self.store.read(source), original["text"])
        self.assertEqual(self.store.snapshot()["style_en"], original["text"])
        self.store.bind("style_en", saved["id"])
        self.assertEqual(self.store.snapshot()["style_en"], "A new style.\n中文")
        self.assertEqual(next(f for f in saved["manifest"]["files"] if f["id"] == saved["id"])["display_name"], "English.md")

    def test_edit_active_custom_creates_version_and_preserves_snapshots(self):
        first = self.store.save_version("style.md", "First version", "style_en", activate=True)
        snapshot = self.store.snapshot()
        second = self.store.save_version("style.md", "Second version", "style_en",
            source=first["id"], expected_sha256=first["sha256"], activate=True)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.store.read(first["id"]), "First version")
        self.assertEqual(snapshot["style_en"], "First version")
        self.assertEqual(self.store.snapshot()["style_en"], "Second version")
        self.assertEqual(PromptStore(self.store.directory).bindings()["style_en"], second["id"])

    def test_delete_active_restores_default_and_cleans_index(self):
        default = self.store.snapshot()["style_ja"]
        saved = self.store.save_version("style.md", "New Japanese style", "style_ja", activate=True)
        snapshot = self.store.snapshot()
        result = self.store.delete(saved["id"], saved["sha256"])
        self.assertEqual(result["reset_stages"], ["style_ja"])
        self.assertEqual(self.store.snapshot()["style_ja"], default)
        self.assertEqual(snapshot["style_ja"], "New Japanese style")
        self.assertNotIn(saved["id"], (self.store.directory / "types.json").read_text())
        self.assertFalse(any(f["id"] == saved["id"] for f in result["manifest"]["files"]))

    def test_delete_unused_does_not_change_active_and_builtin_is_protected(self):
        active = self.store.save_version("one.md", "Active", "generation", activate=True)
        unused = self.store.save_version("two.md", "Unused", "generation")
        self.store.delete(unused["id"], unused["sha256"])
        self.assertEqual(self.store.snapshot()["generation"], "Active")
        source = "builtin/structured_vocabulary.txt"
        with self.assertRaises(ValueError):
            self.store.delete(source, self.store.document(source)["sha256"])
        self.assertEqual(self.store.bindings()["generation"], active["id"])

    def test_stale_editor_cannot_save_or_delete_changed_source(self):
        saved = self.store.save_version("one.md", "Original", "generation")
        path = self.store.directory / saved["id"].split("/")[1]
        path.write_text("Changed elsewhere", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.save_version("one.md", "My edit", "generation",
                source=saved["id"], expected_sha256=saved["sha256"], activate=True)
        with self.assertRaises(ValueError):
            self.store.delete(saved["id"], saved["sha256"])
        self.assertEqual(path.read_text(encoding="utf-8"), "Changed elsewhere")
        self.assertEqual(self.store.bindings(), {})

    def test_invalid_validation_does_not_create_or_activate_version(self):
        before = self.store.manifest()
        for text in ('{}', 'not json', '[]'):
            with self.assertRaises(ValueError):
                self.store.save_version("rules.txt", text, "validation", activate=True)
        self.assertEqual(self.store.manifest(), before)

    def test_cross_type_edit_and_invalid_paths_are_rejected(self):
        source = "builtin/style_en.txt"
        with self.assertRaises(ValueError):
            self.store.save_version("rules.md", "New", "tag_review", source=source,
                expected_sha256=self.store.document(source)["sha256"])
        for name in ("../file.md", "bad:stream.md", "folder\\file.md", "script.html", "bad\0.md"):
            with self.assertRaises(ValueError): self.store.save_version(name, "New", "generation")
        for file_id in ("custom/../x.md", "custom/x:stream.md", "custom\\x.md"):
            with self.assertRaises(ValueError): self.store.read(file_id)

    def test_supplement_can_save_and_delete_without_global_binding(self):
        saved = self.store.save_version("extra.md", "Extra instructions", "supplement")
        self.assertTrue(self.store.snapshot(supplement=saved["id"])["generation"].endswith("Extra instructions"))
        with self.assertRaises(ValueError):
            self.store.save_version("extra.md", "Extra instructions", "supplement", activate=True)
        self.store.delete(saved["id"], saved["sha256"])
        self.assertEqual(self.store.files("supplement"), [])

    def test_fonts_match_pinned_sources_and_have_licenses(self):
        root = ROOT / "vocab_app/web/fonts"
        for source in json.loads((root / "sources.json").read_text(encoding="utf-8")):
            self.assertEqual(hashlib.sha256((root / source["file"]).read_bytes()).hexdigest(), source["sha256"])
        self.assertEqual(len(list(root.glob("*-OFL.txt"))), 5)

    def test_palette_preferences_migrate_and_persist(self):
        path = Path(self.temp.name) / "settings.json"
        path.write_text(json.dumps({"theme": "dark", "locale": "en"}), encoding="utf-8")
        service = UIService(self.temp.name)
        try:
            self.assertEqual(service.preferences["theme"], "dark")
            self.assertEqual(service.preferences["palette"], "iris")
            for palette in ("ink", "paper", "iris", "graphite"):
                service.update_settings({"palette": palette})
                self.assertEqual(json.loads(path.read_text())["palette"], palette)
                self.assertEqual(json.loads(path.read_text())["theme"], "dark")
            with self.assertRaises(ValueError): service.update_settings({"palette": "unknown"})
        finally:
            service.pool.shutdown()
