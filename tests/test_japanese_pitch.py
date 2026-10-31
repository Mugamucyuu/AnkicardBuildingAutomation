import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vocab_app.japanese_pitch import lookup, lookup_kanjium, parse_ubiq, lookup_ubiq, moras, ubiq_page
from vocab_app.media import MediaResult
from vocab_app.settings import ROOT


class JapanesePitchTests(unittest.TestCase):
    def test_bundled_kanjium_word_reading_and_variants(self):
        for word, reading, positions in [("入れ墨", "いれずみ", [0]), ("湿気る", "しける", [2, 0]),
                                          ("湿気る", "しっける", [3]), ("刺青", "しせい", [0])]:
            with self.subTest(word=word, reading=reading):
                result = lookup_kanjium(word, reading)
                self.assertEqual([p["nucleus"] for p in result.pitch_accents], positions)
                self.assertTrue(all(p["reading"] == reading for p in result.pitch_accents))
                self.assertTrue(all(p["license"] == "CC BY-SA 4.0" for p in result.pitch_accents))

    def test_local_hit_does_not_query_other_pitch_sources(self):
        with patch("vocab_app.japanese_pitch.lookup_ojad", side_effect=AssertionError("No network")), \
             patch("vocab_app.japanese_pitch.lookup_ubiq", side_effect=AssertionError("No network")):
            result = lookup("入れ墨", "いれずみ")
        self.assertEqual(result.pitch_accents[0]["source"], "Kanjium")
        self.assertEqual(len(result.lookup_attempts), 1)

    def test_reading_mismatch_cannot_keep_previous_headword_reading(self):
        self.assertEqual(lookup_kanjium("橋", "いれずみ").pitch_accents, [])
        self.assertNotIn("箸", [p["reading_scope"] for p in lookup_kanjium("橋", "はし").pitch_accents])

    def test_kana_query_scopes_homophones_to_their_own_headwords(self):
        result = lookup_kanjium("しける", "しける")
        self.assertTrue(result.pitch_accents)
        self.assertTrue(all(p["reading"] == "しける" for p in result.pitch_accents))
        self.assertIn("湿気る", [p["reading_scope"] for p in result.pitch_accents])

    def test_missing_dataset_falls_back_to_ojad_before_ubiq(self):
        result = MediaResult(pitch_accents=[{"source": "OJAD"}])
        with patch("vocab_app.japanese_pitch.lookup_kanjium", side_effect=FileNotFoundError), \
             patch("vocab_app.japanese_pitch.lookup_ojad", return_value=result), \
             patch("vocab_app.japanese_pitch.lookup_ubiq") as ubiq:
            found = lookup("word", "よみ")
        self.assertEqual([a["source"] for a in found.lookup_attempts], ["Kanjium", "OJAD"])
        self.assertEqual(found.pitch_accents[0]["source"], "OJAD")
        ubiq.assert_not_called()

    def test_ubiq_is_third_and_all_missing_is_explicit(self):
        for third in (MediaResult(pitch_accents=[{"source": "U-biq"}]), MediaResult()):
            with patch("vocab_app.japanese_pitch.lookup_kanjium", return_value=MediaResult()), \
                 patch("vocab_app.japanese_pitch.lookup_ojad", return_value=MediaResult()), \
                 patch("vocab_app.japanese_pitch.lookup_ubiq", return_value=third):
                found = lookup("word", "よみ")
            self.assertEqual([a["source"] for a in found.lookup_attempts], ["Kanjium", "OJAD", "U-biq"])
            self.assertEqual(bool(found.warnings), not bool(third.pitch_accents))

    def test_checksum_failure_does_not_use_corrupt_data(self):
        (ROOT / "output").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as folder:
            path = Path(folder) / "accents.tsv"
            path.write_text("猫\tねこ\t1\n", encoding="utf-8")
            path.with_name("metadata.json").write_text(json.dumps({"sha256": "wrong"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                lookup_kanjium("猫", "ねこ", path)

    def test_mora_count_handles_small_kana_sokuon_and_long_vowels(self):
        self.assertEqual(moras("キャット"), ["きゃ", "っ", "と"])
        self.assertEqual(moras("コーヒー"), ["こ", "ー", "ひ", "ー"])

    def test_ubiq_shift_jis_and_spelling_match(self):
        markup = '<table><tr><td><span class="a1">い</span><span class="a4">れずみ</span> (入墨)</td></tr></table>'
        with patch("vocab_app.japanese_pitch.fetch", return_value=markup.encode("cp932")):
            result = lookup_ubiq("入れ墨", "いれずみ")
        self.assertEqual(result.pitch_accents[0]["nucleus"], 0)
        self.assertEqual(result.pitch_accents[0]["pattern"], "LHHH")
        self.assertEqual(result.pitch_accents[0]["reading_scope"], "入墨")

    def test_ubiq_atamadaka_odaka_and_homophone_rejection(self):
        rain = '<tr><td><span class="a2">あ</span><span class="a3">め</span> (雨)</td></tr>'
        bridge = '<tr><td><span class="a1">は</span><span class="a2">し</span> (橋)</td></tr>'
        self.assertEqual(parse_ubiq(rain, "雨", "あめ", "https://accent.u-biq.org/a.html").pitch_accents[0]["nucleus"], 1)
        self.assertEqual(parse_ubiq(bridge, "橋", "はし", "https://accent.u-biq.org/ha.html").pitch_accents[0]["nucleus"], 2)
        self.assertEqual(parse_ubiq(bridge, "箸", "はし", "https://accent.u-biq.org/ha.html").pitch_accents, [])

    def test_ubiq_pages_use_actual_site_names_and_voicing_groups(self):
        self.assertEqual(ubiq_page("しける"), "https://accent.u-biq.org/si.html")
        self.assertEqual(ubiq_page("じかん"), "https://accent.u-biq.org/si.html")
        self.assertEqual(ubiq_page("ふね"), "https://accent.u-biq.org/hu.html")
        self.assertEqual(lookup_ubiq("入れ墨").lookup_attempts[0]["status"], "needs_reading")
