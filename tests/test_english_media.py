import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from vocab_app.english_media import cambridge, oxford, longman, lookup, audio_result
from vocab_app.media import MediaResult
from vocab_app.public_media import download_assets, PublicMediaRegistry


class EnglishMediaTests(unittest.TestCase):
    def test_cambridge_new_page_spacing_and_us_after_uk(self):
        markup = '''<h1>English pronunciation  of  curd</h1>
        <audio><source src="/us/media/english/uk_pron/curd.mp3"></audio>
        <audio><source src="/us/media/english/us_pron/curd.mp3"></audio>
        <audio><source src="/us/media/english/us_pron/phoneme.mp3"></audio>'''
        with patch('vocab_app.english_media.fetch', return_value=markup):
            result = cambridge('curd')
        self.assertTrue(result.assets[0]['url'].endswith('/us_pron/curd.mp3'))
        self.assertEqual(result.assets[0]['variety'], 'US')

    def test_cambridge_rejects_related_entry(self):
        markup = '<h1>English pronunciation of curdle</h1><a class="hw">curd</a><audio><source src="/us/media/english/us_pron/curdle.mp3"></audio>'
        with patch('vocab_app.english_media.fetch', return_value=markup):
            self.assertFalse(cambridge('curd').assets)

    def test_cambridge_ipa_is_from_us_region(self):
        markup = '''<h1>English pronunciation of curd</h1><span class="ipa">kɜːd</span>
        <span data-pron-region="US"><audio><source src="/us/media/english/us_pron/curd.mp3"></audio><span class="ipa">kɝːd</span></span>'''
        with patch('vocab_app.english_media.fetch', return_value=markup):
            self.assertEqual(cambridge('curd').pronunciation_text, '/kɝːd/')

    def test_oxford_matches_head_and_american_block(self):
        markup = '''<div class="phons_n_am" wd="curdle"><div class="pron-us" data-src-mp3="https://www.oxfordlearnersdictionaries.com/media/english/us_pron/wrong.mp3"></div></div>
        <div class="phons_n_am" wd="curd"><div class="pron-us" data-src-mp3="https://www.oxfordlearnersdictionaries.com/media/english/us_pron/curd.mp3"></div><span class="phon">/kɜːrd/</span></div>'''
        with patch('vocab_app.english_media.fetch', return_value=markup):
            result = oxford('curd')
        self.assertTrue(result.assets[0]['url'].endswith('/curd.mp3'))
        self.assertEqual(result.pronunciation_text, '/kɜːrd/')

    def test_longman_rejects_related_and_british_audio(self):
        markup = '''<span class="brefile" title="Play British pronunciation of curd" data-src-mp3="https://www.ldoceonline.com/media/english/breProns/curd.mp3"></span>
        <span class="amefile" title="Play American pronunciation of curdle" data-src-mp3="https://www.ldoceonline.com/media/english/ameProns/curdle.mp3"></span>
        <span class="amefile" title="Play American pronunciation of curd" data-src-mp3="https://www.ldoceonline.com/media/english/ameProns/curd.mp3?version=1"></span>'''
        with patch('vocab_app.english_media.fetch', return_value=markup):
            result = longman('curd')
        self.assertTrue(result.assets[0]['url'].endswith('/curd.mp3?version=1'))

    def test_download_failure_continues_to_next_source(self):
        registry = Mock()
        registry.wiktionary.return_value = audio_result('https://upload.wikimedia.org/broken.mp3', 'https://en.wiktionary.org/wiki/curd', 'Wiktionary')
        fallback = audio_result('https://dictionary.cambridge.org/us_pron/curd.mp3', 'https://dictionary.cambridge.org/', 'Cambridge')
        def download(result, directory):
            if result.assets[0]['url'].endswith('broken.mp3'):
                result.assets = []
            return result
        with patch('vocab_app.english_media.cambridge', return_value=fallback), patch('vocab_app.public_media.download_assets', side_effect=download):
            result = lookup(registry, 'curd', 'unused', sources=('wiktionary', 'cambridge'))
        self.assertEqual([a['status'] for a in result.lookup_attempts], ['download_failed', 'downloaded'])
        self.assertEqual(result.assets[0]['attribution'], 'Cambridge')

    def test_rejects_html_disguised_as_mp3(self):
        result = audio_result('https://www.ldoceonline.com/media/english/ameProns/curd.mp3', '', '')
        root = Path(__file__).resolve().parents[1] / 'output'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder, patch('vocab_app.public_media.fetch', return_value=b'<html>blocked</html>'):
            self.assertFalse(download_assets(result, folder).assets)

    def test_named_source_is_exposed_by_registry(self):
        with patch('vocab_app.english_media.oxford', return_value=MediaResult()) as adapter:
            PublicMediaRegistry().lookup('oxford', 'en', 'curd')
            adapter.assert_called_once_with('curd')


if __name__ == '__main__':
    unittest.main()
