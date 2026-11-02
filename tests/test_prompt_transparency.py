import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from vocab_app.prompts import default_prompts, assemble_generation
from vocab_app.quality import readability_issues, generate_content
from vocab_app.validation import validation_scope
from vocab_app.request_trace import recording_transport
from vocab_app.settings import ROOT


def content(examples=3):
    return {'senses':[{'id':'s1','definition':'A **clear** explanation.','examples':['Natural example.']*examples,'tags':['pos::noun']}],
            'analysis':{'etymology':'The **source** is clear.','nuance':'A **neutral** everyday word.','synonyms':'A **specific contrast** with a near synonym.',
                        'collocations':[{'phrase':'**sample phrase**','explanation':'A short explanation of meaning and use.'}]}}

class PromptTransparencyTests(unittest.TestCase):
    def test_default_main_request_keeps_component_order(self):
        prompts=default_prompts()
        for language in ('en','ja','ko'):
            expected=prompts['generation']+'\n\n'+prompts['tag_policy']+'\n\n'+prompts['style_'+language]
            self.assertEqual(assemble_generation(prompts,language),expected)
            self.assertEqual(assemble_generation(prompts,language,True),expected+'\n\n'+prompts['image_plan'])

    def test_user_can_reduce_examples_and_change_feedback(self):
        prompts=default_prompts();settings=json.loads(prompts['validation'])
        settings['rules']['minimum_examples']['en']=1
        model=Mock();model.generate.return_value=json.dumps(content(1))
        result,_=generate_content(model,'instruction','{}','en',enforce=True,attempts=1,_validation=json.dumps(settings))
        self.assertEqual(len(result['senses'][0]['examples']),1)
        self.assertTrue(any('at least 3' in m for m in readability_issues(content(1),'en')))
        settings['rules']['minimum_examples']['en']=3
        settings['messages']['quality_018']='CUSTOM EXAMPLES {v0}: {v1}'
        model.generate.side_effect=[json.dumps(content(1)),json.dumps(content(3))]
        generate_content(model,'instruction','{}','en',enforce=True,_validation=json.dumps(settings))
        self.assertIn('CUSTOM EXAMPLES 0: 3',model.generate.call_args.args[1])

    def test_custom_content_checks_are_isolated_between_calls(self):
        settings=json.loads(default_prompts()['validation'])
        settings['rules']['check_emphasis']=False
        value=content();value['analysis']['etymology']='Plain text.'
        scoped=validation_scope(readability_issues)
        self.assertFalse(scoped(value,'en',_validation=json.dumps(settings)))
        self.assertTrue(readability_issues(value,'en'))

    def test_request_trace_preserves_payload_not_auth_headers(self):
        (ROOT/'output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            transport=Mock(return_value={'choices':[]})
            traced=recording_transport(directory,transport)
            payload={'model':'test','messages':[{'role':'system','content':'A'},{'role':'user','content':'B\nrepair'}]}
            traced('https://example.test',payload,headers={'Authorization':'Bearer PRIVATE-TEST-KEY'})
            saved=Path(directory,'001.json').read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE-TEST-KEY',saved)
            self.assertEqual(json.loads(saved)['request'],payload)
            self.assertEqual(transport.call_args.args[1],payload)
            recording_transport(directory,transport)('https://example.test',payload)
            self.assertTrue(Path(directory,'002.json').exists())

    def test_ui_preview_and_actual_records_match_saved_payload(self):
        from vocab_app.ui_service import UIService,write_json
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            service=UIService(directory)
            try:
                preview=service.prompt_preview('ko',images=True)
                self.assertEqual(preview['generation'],assemble_generation(service.prompts.snapshot(),'ko',True))
                service.jobs['test']={'items':[{'word':'값'}]}
                root=Path(directory,'jobs/test')
                write_json(root/'prompts.json',service.prompts.snapshot())
                payload={'model':'test','messages':[{'role':'user','content':'REAL TAGS / SOURCES / REPAIR'}]}
                recording_transport(root/'requests/0',Mock(return_value={}))('https://example.test',payload)
                record=service.prompt_requests('test',0)
                self.assertEqual(record['requests'][0]['request'],payload)
                self.assertIn('validation',record['snapshot'])
            finally:service.pool.shutdown()
