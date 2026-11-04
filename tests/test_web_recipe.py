"""Regression tests for the production W7 entry point and media mismatches."""
import json
import os
import unittest
from unittest.mock import patch

from test_quality import valid_content
from vocab_app.formatting import format_web_content, formatting_changes
from vocab_app.image_selection import rank_candidate, validate_plan
from vocab_app.pipeline import ImportPipeline
from vocab_app.prompts import default_prompts
from vocab_app.providers import ModelClient
from vocab_app.settings import Settings
from vocab_app.taxonomy import TagCatalog
from vocab_app.web_recipe import supports_recipe
from vocab_app.web_research import select_evidence


class WebRecipeTests(unittest.TestCase):
    def test_web_pipeline_uses_compact_shared_prefix_and_local_search(self):
        content = valid_content()
        content['senses'][0].update(id='s1', tags=['pos::noun'])
        content['analysis']['etymology'] += ' [S1]'
        content['analysis']['nuance'] = (
            '**Context & Tone:** A **useful portable light** on outdoor trips and around campsites. '
            '**Emphasis:** The light **illuminates the area** and may be carried from place to place.'
        )
        # Reproduce the prematurely closed model response seen during live profiles.
        tail = {'image_plan': None, 'proposed_tags': []}
        raw = json.dumps(content) + ',' + json.dumps(tail)[1:]
        decisions = {'decisions':[{'sense_id':'s1','keep_tags':['pos::noun'],
                                   'tag_reasons':{'pos::noun':'It names a kind of light.'}}]}
        requests = []

        def transport(url, payload, **kwargs):
            system, user = (item['content'] for item in payload['messages'])
            requests.append((system, json.loads(user)))
            answer = json.dumps(decisions) if 'Review and repair vocabulary tags' in system else raw
            return {'choices':[{'finish_reason':'stop','message':{'content':answer}}]}

        with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'fixture-key'}), patch(
            'vocab_app.research.request_json', return_value={'results':[{
                'url':'https://dictionary.cambridge.org/dictionary/english/lantern',
                'title':'Lantern definition', 'content':'A lantern is a portable light.',
            }]}
        ) as search:
            note = ImportPipeline(ModelClient(Settings('deepseek','deepseek-flash'),transport),
                                  tag_catalog=TagCatalog.load()).generate('lantern','en',generation_mode='web')
        self.assertEqual(note['generation_recipe'], 'web-v1')
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0][0].split('Phase instructions:')[0],
                         requests[1][0].split('Phase instructions:')[0])
        self.assertNotIn('allowed_tags', requests[0][1])
        self.assertTrue(search.call_args.args[1]['query'].startswith('"lantern"'))
        self.assertEqual(search.call_args.args[1]['count'], 8)
        self.assertEqual(note['senses'][0]['tags'], ['pos::noun'])
        self.assertIn('\n\n', note['analysis']['nuance'])

    def test_recipe_only_for_builtin_english_and_japanese_flash_web(self):
        prompts = default_prompts()
        self.assertTrue(supports_recipe('deepseek','deepseek-flash','ja','web',prompts))
        self.assertFalse(supports_recipe('deepseek','deepseek-flash','ko','web',prompts))
        self.assertFalse(supports_recipe('deepseek','deepseek-flash','ja','sources',prompts))
        self.assertFalse(supports_recipe('openai','example','ja','web',prompts))
        prompts['generation'] += '\nUser supplement'
        self.assertFalse(supports_recipe('deepseek','deepseek-flash','ja','web',prompts))

    def test_repair_overbold_uses_only_original_substrings(self):
        original = valid_content()
        original['analysis']['nuance'] = '**A practical portable light for outdoor use.**'
        class Editor:
            def generate(self, system, user, *, json_output):
                self.request = json.loads(user)
                return '{"spans":{"nuance":["portable light"]}}'
        editor = Editor()
        result, check = format_web_content(editor, original, 'en', 'full', 'repair', 'exact')
        self.assertEqual(editor.request['fields']['nuance'], 'A practical portable light for outdoor use.')
        self.assertEqual(result['analysis']['nuance'], 'A practical **portable light** for outdoor use.')
        self.assertEqual(formatting_changes(original,result), [])
        self.assertEqual(check['attempts'], 1)

    def test_navigation_page_cannot_displace_exact_entry(self):
        entry = {'url':'https://kotobank.jp/word/example','title':'横領とは？','content':'横領の定義'}
        nav = {**entry,'title':'横領を解説文に含む用語の検索結果'}
        self.assertEqual(select_evidence([nav,entry],'横領','ja'), [entry])


class MediaRegressionTests(unittest.TestCase):
    def test_reject_document_thumbnail_and_ambiguous_diagram_title(self):
        plan = validate_plan({'sense_id':'s1','query':'blood vessel anastomosis diagram',
            'anchors':['anastomosis'],'context':['branching','interconnection']}, [{'id':'s1'}])
        self.assertEqual(plan['kind'], 'diagram')
        candidate = {'url':'https://upload.wikimedia.org/example.png','license':'CC BY-SA',
                     'attribution':'Author','width':800,'height':800,'original_mime':'image/png'}
        moth = {**candidate,'title':'File:Clostera anastomosis female.jpg'}
        pdf = {**candidate,'title':'File:Anastomosis diagram.pdf','original_mime':'application/pdf'}
        diagram = {**candidate,'title':'File:Vascular anastomosis diagram.png'}
        self.assertLess(rank_candidate(moth,plan)[0], 5)
        self.assertLess(rank_candidate(pdf,plan)[0], 5)
        self.assertGreaterEqual(rank_candidate(diagram,plan)[0], 5)
