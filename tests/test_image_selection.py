import copy
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from run_import import OfflineClient
from vocab_app.image_selection import select_image, validate_plan, rank_candidate
from vocab_app.media import MediaResult
from vocab_app.pipeline import ImportPipeline
from vocab_app.public_media import PublicMediaRegistry, download_assets
from vocab_app.settings import ROOT

PLAN = {'sense_id': 's1', 'query': 'milk curds', 'anchors': ['curd', 'curds'], 'context': ['milk', 'cheese'], 'exclude': ['lemon', 'film']}
SENSES = [{'id': 's1', 'definition': 'Coagulated milk'}]


def picture(title, description='milk cheese', **extra):
    return {'title': 'File:' + title, 'kind': 'image', 'url': 'https://upload.wikimedia.org/' + title,
            'width': 1200, 'height': 800, 'description': description, 'license': 'CC BY-SA',
            'attribution': 'Photographer', 'source_page': 'https://commons.wikimedia.org/wiki/File:' + title, **extra}


class ImageSelectionTests(unittest.TestCase):
    def test_rejects_abstract_and_invalid_plans_without_network(self):
        registry = Mock()
        for plan in (None, {'sense_id': 'unknown', **{k:v for k,v in PLAN.items() if k!='sense_id'}}, {**PLAN, 'query': 'https://bad.test'}):
            result = select_image(registry, 'curd', 'en', SENSES, plan)
            self.assertFalse(result.assets)
        registry.image_search.assert_not_called()

    def test_ranks_subject_photo_above_first_unrelated_result(self):
        registry = Mock()
        registry.image_search.return_value = [picture('Lemon curd.jpg'), picture('Milk curds.jpg'), picture('Cheese processing.jpg', 'curds in milk')]
        result = select_image(registry, 'curd', 'en', SENSES, PLAN)
        self.assertEqual(result.selection['selected_title'], 'File:Milk curds.jpg')
        self.assertEqual(result.selection['sense_id'], 's1')
        self.assertNotIn('File:Lemon curd.jpg', [a['title'] for a in result.selection['approved_assets']])
        self.assertEqual(registry.image_search.call_count, 2)

    def test_rejects_missing_subject_and_substring_match(self):
        for asset in (picture('Food.jpg', 'a bowl of milk'), picture('Curdle-logo.png', 'curdle software')):
            self.assertLess(rank_candidate(asset, PLAN)[0], 5)

    def test_rejects_logo_unless_requested_and_checks_dimensions(self):
        for asset in (picture('Curd logo.png'), picture('Curd.jpg', width=80), picture('Curd.jpg', width=8000, height=200), picture('Curd.jpg', license='')):
            self.assertLess(rank_candidate(asset, PLAN)[0], 5)

    def test_fallback_keeps_sense_context_and_abstains(self):
        registry = Mock()
        registry.image_search.return_value = [picture('Snow.jpg', 'unrelated')]
        result = select_image(registry, 'curd', 'en', SENSES, PLAN)
        self.assertFalse(result.assets)
        self.assertEqual(registry.image_search.call_count, 2)
        self.assertEqual(registry.image_search.call_args.args[0], 'curd milk')

    def test_weak_description_requires_supporting_context(self):
        self.assertLess(rank_candidate(picture('Festival.jpg', 'A person named Curd.'), PLAN)[0], 5)

    def test_download_fallback_uses_only_approved_ranked_candidates(self):
        first, second = picture('Milk curds.jpg'), picture('Curd.jpg')
        result = MediaResult(assets=[first], selection={'strategy':'sense_metadata_v1', 'selected_title':first['title'],
                                                    'approved_assets':[first,second], 'candidates':[{'title':'Bad.jpg', 'score':-100}]})
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as folder, patch('vocab_app.public_media.fetch', side_effect=[OSError(), b'\xff\xd8\xfftest']), patch.object(PublicMediaRegistry,'image') as legacy:
            result = download_assets(result, folder)
        self.assertEqual(result.selection['selected_title'], second['title'])
        self.assertEqual(result.selection['status'], 'downloaded')
        legacy.assert_not_called()

    def test_batch_search_has_metadata_without_per_image_fetch(self):
        data = {'query':{'pages':{'1':{'title':'File:Milk curds.jpg','index':1,'imageinfo':[{'url':'https://upload.wikimedia.org/curd.jpg','width':1200,'height':900,'extmetadata':{'Artist':{'value':'A'},'LicenseShortName':{'value':'CC0'},'ImageDescription':{'value':'Milk <b>curds</b>'}}}]}}}}
        with patch('vocab_app.public_media.api', return_value=data) as api:
            assets = PublicMediaRegistry().image_search('milk curds')
        self.assertEqual(api.call_count, 1)
        self.assertEqual(assets[0]['description'], 'Milk curds')

    def test_article_representative_must_match_context(self):
        asset = picture('Curd Setting.jpg', representative_article={'title':'Curd','extract':'Curd is obtained by coagulating milk.'})
        registry = Mock()
        registry.representative_image.return_value = [asset]
        result = select_image(registry,'curd','en',SENSES,{**PLAN,'topic':'Curd'})
        self.assertEqual(result.selection['selected_title'], asset['title'])
        self.assertTrue(registry.image_search.called)
        wrong = picture('Circle.jpg', representative_article={'title':'Squatting','extract':'Occupying an abandoned building.'})
        self.assertLess(rank_candidate(wrong,{'anchors':['squatting'],'context':['posture'],'query':'person squatting','exclude':[]})[0],5)

    def test_disambiguation_page_is_rejected_before_media_download(self):
        data = {'query':{'pages':{'1':{'title':'Azure','pageimage':'Wrong.jpg','pageprops':{'disambiguation':''}}}}}
        with patch('vocab_app.public_media.api',return_value=data), patch.object(PublicMediaRegistry,'image') as image:
            self.assertFalse(PublicMediaRegistry().representative_image('Azure'))
            image.assert_not_called()

    def test_article_failure_falls_back_to_ranked_commons(self):
        registry = Mock()
        registry.representative_image.side_effect = OSError('network')
        registry.image_search.return_value = [picture('Milk curds.jpg')]
        result = select_image(registry,'curd','en',SENSES,{**PLAN,'topic':'Curd'})
        self.assertTrue(result.assets)
        self.assertEqual(result.lookup_attempts[0]['error_type'],'OSError')

    def test_plan_is_reused_from_single_generation_response(self):
        fixture = json.loads((ROOT/'tests/fixtures/vocabulary.json').read_text(encoding='utf-8'))['en:apple']
        fixture = copy.deepcopy(fixture)
        plan = {'sense_id':'s1','query':'apple fruit','anchors':['apple','apples'],'context':['fruit'],'exclude':['computer']}
        fixture['image_plan'] = plan
        model = Mock(settings=OfflineClient().settings, enforce_readability=False)
        model.generate.return_value = json.dumps(fixture)
        registry = PublicMediaRegistry()
        with patch.object(registry,'select_image',return_value=MediaResult()) as select:
            ImportPipeline(model,registry).generate('apple','en',image_source='auto')
        self.assertEqual(model.generate.call_count, 1)
        select.assert_called_once_with('apple','en',fixture['senses'],plan)
        self.assertIn('image_plan',model.generate.call_args.args[0])

    def test_no_image_does_not_add_prompt_or_search(self):
        model = Mock(settings=OfflineClient().settings, enforce_readability=False)
        model.generate.return_value = OfflineClient().generate('', json.dumps({'word':'apple','language':'en'}))
        registry = Mock(wraps=PublicMediaRegistry())
        ImportPipeline(model,registry).generate('apple','en')
        self.assertNotIn('image_plan',model.generate.call_args.args[0])
        registry.select_image.assert_not_called()


if __name__ == '__main__':
    unittest.main()
