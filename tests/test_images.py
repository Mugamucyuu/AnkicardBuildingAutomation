import tempfile
import unittest
from unittest.mock import patch

from run_import import main
from vocab_app.media import MediaResult
from vocab_app.public_media import PublicMediaRegistry, download_assets
from vocab_app.settings import ROOT


def image(name):
    return MediaResult(assets=[{"kind": "image", "url": "https://upload.wikimedia.org/" + name + ".jpg",
                              "attribution": "Photographer", "license": "CC BY-SA",
                              "source_page": "https://commons.wikimedia.org/wiki/File:" + name}])


class ImageTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "output").mkdir(exist_ok=True)

    def test_search_preserves_order_and_skips_unusable_metadata(self):
        registry = PublicMediaRegistry()
        with patch.object(registry, "image_candidates", return_value=["bad", "first", "later"]), \
             patch.object(registry, "image", side_effect=[ValueError("metadata"), image("first")]) as lookup:
            result = registry.lookup("commons", "ja", "猫")
        self.assertEqual(result.selection["selected_title"], "first")
        self.assertEqual(result.selection["query"], "猫")
        self.assertEqual(lookup.call_count, 2)

    def test_download_failure_falls_back_to_next_search_hit(self):
        result = image("first")
        result.selection = {"strategy": "first_available", "candidate_titles": ["first", "second"],
                            "selected_title": "first"}
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory, \
             patch("vocab_app.public_media.fetch", side_effect=[OSError("unavailable"), b"\xff\xd8\xffimage"]), \
             patch.object(PublicMediaRegistry, "image", return_value=image("second")):
            result = download_assets(result, directory)
        self.assertEqual(result.selection["selected_title"], "second")
        self.assertEqual(len(result.assets), 1)
        self.assertIn("local_path", result.assets[0])

    def test_empty_or_failed_search_is_nonfatal(self):
        for value in ([], OSError("network")):
            with self.subTest(value=value), patch.object(PublicMediaRegistry, "image_candidates") as search:
                if isinstance(value, Exception):
                    search.side_effect = value
                else:
                    search.return_value = value
                result = PublicMediaRegistry().lookup("commons", "ko", "나무")
                self.assertEqual(result.assets, [])
                self.assertTrue(result.warnings)

    def test_html_response_is_not_saved_as_picture(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory, \
             patch("vocab_app.public_media.fetch", return_value=b"<html>Service unavailable</html>"):
            result = download_assets(image("invalid"), directory)
        self.assertEqual(result.assets, [])

    def test_cli_explicit_images_download_and_render_without_model_call(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory, \
             patch.object(PublicMediaRegistry, "select_image", return_value=image("cat")), \
             patch("vocab_app.public_media.fetch", return_value=b"\xff\xd8\xffimage"):
            self.assertEqual(main(["--language", "ja", "--word", "猫", "--image-source", "auto",
                                   "--output-dir", directory]), 0)
            from pathlib import Path
            preview = next(Path(directory).glob("*.html")).read_text(encoding="utf-8")
            self.assertIn('<img src="media/', preview)
            self.assertIn("Photographer", preview)
