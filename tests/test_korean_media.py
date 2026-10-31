import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from vocab_app.korean_media import krdict, daum
from vocab_app.public_media import PublicMediaRegistry, download_assets
from vocab_app.media import MediaResult
from vocab_app.expanded_media import lookup_expanded
from vocab_app.settings import ROOT


class KoreanMediaTests(unittest.TestCase):
    def test_phonetic_hangul_joins_nested_morpheme_markup(self):
        markup = '<li><span class="IPA">[tɕaŋnankam]</span></li><li>Phonetic hangul: <span>[<span>장</span>난<b>깜</b>]</span></li>'
        responses = [{"parse": {"sections": [{"line": "Korean", "level": "2", "index": "1"}]}}, {"parse": {"text": {"*": markup}}}]
        with patch("vocab_app.public_media.api", side_effect=responses):
            result = PublicMediaRegistry().wiktionary("장난감", "ko")
        self.assertEqual(result.phonetic_hangul[0]["text"], "[장난깜]")

    def test_krdict_selects_exact_head_not_substring_and_only_pronunciation_audio(self):
        search = '''<a href="javascript:checkSubmit('1','Y');"><span class="word_type1_17">장난감 가게</span></a><a href="javascript:checkSubmit('2','Y');"><span class="word_type1_17">장난감</span></a>'''
        detail = '''<dl><dt>Pronunciation</dt><dd>[장난깜<a href="javascript:fnSoundPlay('https://krdicmedia.korean.go.kr/toy.mp3');">듣기</a>]</dd></dl>'''
        with patch("vocab_app.korean_media.fetch", side_effect=[search, detail]) as fetch:
            result = krdict("장난감")
        self.assertIn("ParaWordNo=2", fetch.call_args.args[0])
        self.assertEqual(result.phonetic_hangul[0]["text"], "[장난깜]")
        self.assertEqual(len(result.assets), 1)

    def test_daum_uses_korean_headword_and_https_audio(self):
        search = '<a href="/word/view.do?wordid=kkw123">장난감</a>'
        detail = '<span class="txt_cleanword">장난감</span><em class="txt_info">발음<a data-url="http://t1.daumcdn.net/language/toy"></a></em>'
        with patch("vocab_app.korean_media.fetch", side_effect=[search, detail]):
            result = daum("장난감")
        self.assertEqual(result.assets[0]["url"], "https://t1.daumcdn.net/language/toy")

    def test_korean_fallback_keeps_wiktionary_hangul_with_dictionary_audio(self):
        registry = Mock()
        registry.wiktionary.return_value = MediaResult(phonetic_hangul=[{"text": "[장난깜]", "source": "Wiktionary"}])
        registry.korean.return_value = MediaResult(assets=[{"kind": "audio"}], phonetic_hangul=[{"text": "[장난깜]", "source": "KRdict"}])
        with patch("vocab_app.korean_media.daum", side_effect=AssertionError("Already complete")):
            result = lookup_expanded(registry, "ko", "장난감")
        self.assertEqual(result.phonetic_hangul[0]["source"], "Wiktionary")
        self.assertEqual(len(result.phonetic_hangul), 1)
        self.assertEqual(len(result.assets), 1)

    def test_extensionless_daum_mp3_download_is_validated(self):
        (ROOT / "output").mkdir(exist_ok=True)
        for content, expected in ((b"ID3audio", 1), (b"<html>error</html>", 0)):
            with tempfile.TemporaryDirectory(dir=ROOT / "output") as folder, patch("vocab_app.public_media.fetch", return_value=content):
                result = download_assets(MediaResult(assets=[{"kind": "audio", "url": "https://t1.daumcdn.net/language/toy"}]), folder)
            self.assertEqual(len(result.assets), expected)

    def test_missing_ko_phonetic_hangul_not_replaced_by_spelling(self):
        from run_import import OfflineClient
        from vocab_app.pipeline import ImportPipeline
        from vocab_app.preview import render_preview
        note = ImportPipeline(OfflineClient()).generate("나무", "ko")
        self.assertIn("实际读音（韩文）", render_preview(note))
        self.assertIn("公开来源未确认", render_preview(note))
