import unittest
from unittest.mock import patch
from pathlib import Path
from vocab_app.public_media import PublicMediaRegistry,download_assets
from vocab_app.media import MediaResult
from vocab_app.settings import ROOT

class MediaTests(unittest.TestCase):
    def test_american_ipa_ignores_phoneme_inside_qualifier(self):
        markup='<li>General American, without <span class="IPA">/æ/</span> raising <a>IPA</a><sup>key</sup>: <span class="IPA">/ˈlæntɚn/</span></li>'
        responses=[{"parse":{"sections":[{"line":"English","level":"2","index":"1"}]}},
                   {"parse":{"text":{"*":markup}}}]
        with patch("vocab_app.public_media.api",side_effect=responses):
            result=PublicMediaRegistry().wiktionary("lantern","en")
        self.assertEqual(result.pronunciation_text,"/ˈlæntɚn/")

    def test_lingualibre_pronunciation_selected_instead_of_song(self):
        markup='<span class="IPA">[sakura]</span><audio data-mwtitle="LL-Q5287_(jpn)-Higa4-さくら.wav"><source src="//upload.wikimedia.org/example.mp3" type="audio/mpeg"></audio><audio data-mwtitle="Sakura_Sakura.song.ogg"></audio>'
        responses=[{"parse":{"sections":[{"line":"Japanese","level":"2","index":"1"}]}},
                   {"parse":{"text":{"*":markup}}}]
        metadata={"url":"https://upload.wikimedia.org/example.wav","source_page":"https://commons.wikimedia.org/wiki/File:Example","attribution":"Speaker","license":"CC0"}
        with patch("vocab_app.public_media.api",side_effect=responses),patch("vocab_app.public_media.commons_metadata",return_value=metadata) as lookup:
            result=PublicMediaRegistry().wiktionary("桜","ja")
        self.assertIn("LL-Q5287",lookup.call_args.args[0])
        self.assertEqual(len(result.assets),1)
        self.assertTrue(result.assets[0]["url"].endswith(".mp3"))

    def test_commons_thumbnail_download_host_allowed(self):
        asset={"kind":"image","url":"https://thumb.wikimedia.org/test.jpg"}
        with patch("vocab_app.public_media.fetch",return_value=b"\xff\xd8\xfftest-image"):
            result=download_assets(MediaResult(assets=[asset]),ROOT/"output/test-media")
        self.assertEqual(len(result.assets),1)
        self.assertTrue(result.assets[0]["local_path"].startswith("media/"))

    def test_unknown_media_host_rejected(self):
        with patch("vocab_app.public_media.fetch",side_effect=AssertionError("No download")):
            result=download_assets(MediaResult(assets=[{"url":"https://example.test/test.jpg"}]),ROOT/"output/test-media")
        self.assertEqual(result.assets,[])
        self.assertTrue(result.warnings)
