import unittest
from unittest.mock import Mock, patch

from vocab_app.media import MediaResult
from vocab_app.ojad import parse, lookup
from vocab_app.expanded_media import lookup_expanded
from vocab_app.public_media import PublicMediaRegistry
from vocab_app.pipeline import ImportPipeline
from run_import import OfflineClient
import json


PAGE = "https://www.gavo.t.u-tokyo.ac.jp/ojad/search/index/word:test"


def block(kana, nucleus, sound=""):
    spans = "".join(f'<span class="mola_{i} {"accent_top" if i == nucleus else ""}"><span class="char">{char}</span></span>' for i, char in enumerate(kana, 1))
    return '<div class="katsuyo_proc"><p><span class="accented_word">' + spans + '</span></p>' + (f'<a id="{sound}"></a>' if sound else '') + '</div>'


def row(head, *variants):
    return '<table><tr><td><p class="midashi_word">' + head + '</p></td><td class="katsuyo katsuyo_jisho_js">' + ''.join(variants) + '</td></tr></table>'


class OjadTests(unittest.TestCase):
    def test_noun_without_recording_still_has_accent(self):
        result = parse(row("雨", block("あめ", 1)), "雨", PAGE)
        self.assertEqual(result.assets, [])
        self.assertEqual(result.pitch_accents[0]["nucleus"], 1)
        self.assertEqual(result.pitch_accents[0]["pattern"], "HL")

    def test_multiple_variants_are_parsed_independently(self):
        result = parse(row("言葉", block("ことば", 0), block("ことば", 2)), "言葉", PAGE)
        self.assertEqual([p["nucleus"] for p in result.pitch_accents], [0, 2])
        self.assertEqual([p["mora_count"] for p in result.pitch_accents], [3, 3])
        self.assertEqual([p["pattern"] for p in result.pitch_accents], ["LHH", "LHL"])

    def test_accent_without_mora_markup_is_not_guessed_as_zero(self):
        self.assertEqual(parse(row("雨", '<span class="accented_word">あめ</span>'), "雨", PAGE).pitch_accents, [])

    def test_male_recording_supported(self):
        result = parse(row("食べる・食べます", block("たべる", 2, "1238_1_1_male")), "食べる", PAGE)
        self.assertIn("/male/012/1238_1_1_male.mp3", result.assets[0]["url"])

    def test_reading_fallback_preserves_orthographic_identity(self):
        result = parse(row("入墨", block("いれずみ", 0)), "入れ墨", PAGE, "いれずみ")
        self.assertEqual(result.pitch_accents[0]["reading_scope"], "入墨")
        self.assertEqual(parse(row("箸", block("はし", 1)), "橋", PAGE, "はし").pitch_accents, [])

    def test_potential_form_does_not_match_dictionary_form(self):
        markup = row("敷く・敷きます", block("しく", 0)) + '<td class="katsuyo_kano_js">しける</td>'
        self.assertEqual(parse(markup, "しける", PAGE).pitch_accents, [])

    def test_reading_search_attempt_is_recorded(self):
        with patch("vocab_app.ojad.fetch", side_effect=["<table></table>", row("入墨", block("いれずみ", 0))]) as fetch:
            result = lookup("入れ墨", "いれずみ")
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(result.lookup_attempts[-1]["query"], "いれずみ")
        self.assertEqual(len(result.pitch_accents), 1)

    def test_automatic_japanese_accent_uses_configured_chain(self):
        registry = Mock()
        registry.wiktionary.return_value = MediaResult(pitch_accents=[{"source": "Wiktionary", "label": "other"}])
        preferred = MediaResult(pitch_accents=[{"source": "Kanjium", "label": "東京式 [1] 頭高型"}], lookup_attempts=[{"source": "Kanjium", "status": "matched"}])
        registry.japanese_accent.return_value = preferred
        with patch("vocab_app.expanded_media.ojad", return_value=preferred):
            result = lookup_expanded(registry, "ja", "雨")
        self.assertEqual(result.lookup_attempts[0]["source"], "Kanjium")
        self.assertEqual(result.pitch_accents, preferred.pitch_accents)

    def test_explicit_ojad_source_is_available(self):
        with patch("vocab_app.ojad.fetch", return_value=row("雨", block("あめ", 1))):
            result = PublicMediaRegistry().lookup("ojad", "ja", "雨")
        self.assertEqual(result.pitch_accents[0]["source"], "OJAD")

    def test_wiktionary_does_not_add_a_fourth_pitch_fallback(self):
        registry = Mock()
        registry.wiktionary.return_value = MediaResult(pitch_accents=[{"label": "fallback"}])
        registry.japanese_accent.return_value = MediaResult()
        with patch("vocab_app.expanded_media.ojad", return_value=MediaResult()):
            result = lookup_expanded(registry, "ja", "入れ墨")
        self.assertEqual(result.pitch_accents, [])

    def test_pipeline_retries_accent_with_generated_reading(self):
        fixture = json.loads(OfflineClient().generate("", json.dumps({"language": "ja", "word": "猫"})))
        fixture["reading"] = "ねこ"
        model = Mock()
        model.settings = OfflineClient.settings
        model.enforce_readability = False
        model.generate.return_value = json.dumps(fixture)
        registry = Mock()
        registry.lookup.return_value = MediaResult(pitch_accents=[{"label": "Wiktionary fallback"}])
        registry.japanese_accent.return_value = MediaResult(pitch_accents=[{"source": "OJAD", "label": "東京式 [1] 頭高型"}])
        note = ImportPipeline(model, registry).generate("猫", "ja", pronunciation_source="auto")
        registry.japanese_accent.assert_called_once_with("猫", "ねこ")
        self.assertEqual(note["pronunciation"]["pitch_accents"][0]["source"], "OJAD")
