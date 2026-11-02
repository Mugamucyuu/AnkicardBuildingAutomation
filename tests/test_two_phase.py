import copy
import json
import unittest
from unittest.mock import Mock
from test_quality import valid_content
from vocab_app.quality import readability_issues, generate_content
from vocab_app.formatting import format_content, formatting_changes
from vocab_app.prompts import default_prompts
from vocab_app.repair import RepairValidationError


def plain(value):
    if isinstance(value,str):return value.replace('**','')
    if isinstance(value,list):return [plain(x) for x in value]
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    return value


class TwoPhaseTests(unittest.TestCase):
    def test_plain_content_passes_content_phase_but_not_final_format_checks(self):
        value=plain(valid_content());model=Mock();model.generate.return_value=json.dumps(value)
        result,check=generate_content(model,'CONTENT','{}','en',enforce=True,content_only=True)
        self.assertEqual(result,value);self.assertEqual(check['attempts'],1)
        self.assertTrue(readability_issues(result,'en'))
        self.assertFalse(readability_issues(result,'en',formatting=False))

    def test_content_phase_keeps_substantive_requirements(self):
        value=plain(valid_content());value['analysis']['collocations']=[];value['senses'][0]['examples']=[]
        issues=readability_issues(value,'en',formatting=False)
        self.assertTrue(any('collocations' in s for s in issues))
        self.assertTrue(any('examples' in s for s in issues))
        value=plain(valid_content());value['analysis']['nuance']=''
        self.assertTrue(readability_issues(value,'en',formatting=False))

    def test_formatter_receives_numeric_rules_and_preserves_content(self):
        original=plain(valid_content());model=Mock();model.generate.return_value=json.dumps(valid_content())
        result,check=format_content(model,original,'en',default_prompts()['formatting'],'Fix {issues}')
        self.assertEqual(result,valid_content());self.assertEqual(check['attempts'],1)
        context,card=model.generate.call_args.args[1].split('not the context above:\n')
        request=json.loads(context.split('\n\nReturn only')[0])
        self.assertEqual(request['format_rules']['max_bold_ratio'],.65)
        self.assertEqual(json.loads(card),original)
        self.assertNotIn('allowed_tags',request)

    def test_exact_echo_envelope_is_unwrapped_but_card_is_still_protected(self):
        original=plain(valid_content())
        def echo(system,user,**kwargs):
            context=user.split('\n\nReturn only')[0]
            return json.dumps({**json.loads(context),'content':valid_content()})
        model=Mock();model.generate.side_effect=echo
        result,_=format_content(model,original,'en','FORMAT','Fix {issues}')
        self.assertEqual(result,valid_content())
        changed=valid_content();changed['senses'][0]['examples'][0]='Changed meaning.'
        def bad_echo(system,user,**kwargs):
            context=json.loads(user.split('\n\nReturn only')[0])
            return json.dumps({**context,'content':changed})
        model.generate.side_effect=bad_echo
        with self.assertRaises(RepairValidationError):
            format_content(model,original,'en','FORMAT','Fix {issues}')

    def test_formatter_rejects_content_changes_and_repairs_latest_draft(self):
        original=plain(valid_content());changed=valid_content();changed['senses'][0]['examples'][0]='Invented new example.'
        model=Mock();model.generate.side_effect=[json.dumps(changed),json.dumps(valid_content())]
        result,check=format_content(model,original,'en','FORMAT','Fix {issues}')
        self.assertEqual(check['attempts'],2)
        self.assertEqual(result['senses'][0]['examples'],original['senses'][0]['examples'])
        self.assertIn('senses[0].examples[0]',model.generate.call_args.args[1])
        self.assertIn('previous_response',model.generate.call_args.args[1])

    def test_format_failure_keeps_drafts_and_never_relaxes_checks(self):
        original=plain(valid_content());model=Mock();model.generate.return_value=json.dumps(original)
        with self.assertRaises(RepairValidationError) as raised:
            format_content(model,original,'en','FORMAT','Fix {issues}')
        self.assertEqual(raised.exception.stage,'formatting')
        self.assertEqual(len(raised.exception.repair_history),3)

    def test_protected_values_and_word_boundaries_cannot_change(self):
        original={'senses':[{'definition':'This is nowhere.'}],'reading':'ねこ','tags':['pos::noun']}
        altered=copy.deepcopy(original);altered['senses'][0]['definition']='This is **now here**.'
        self.assertTrue(formatting_changes(original,altered))
        altered=copy.deepcopy(original);altered['reading']='いぬ'
        self.assertTrue(formatting_changes(original,altered))
        altered=copy.deepcopy(original);altered['senses'][0]['definition']='This is **nowhere**.'
        self.assertFalse(formatting_changes(original,altered))

    def test_valid_existing_format_skips_unnecessary_call(self):
        model=Mock();value=valid_content()
        result,check=format_content(model,value,'en','FORMAT','Fix {issues}')
        self.assertEqual(result,value);self.assertEqual(check['attempts'],0);model.generate.assert_not_called()

    def test_live_pipeline_orders_content_formatting_then_tag_audit(self):
        from vocab_app.pipeline import ImportPipeline
        from vocab_app.providers import ModelClient
        from vocab_app.settings import Settings
        from vocab_app.taxonomy import TagCatalog
        prompts=default_prompts();formatted=valid_content()
        formatted['senses'][0].update(id='s1',tags=['pos::noun'],tag_reasons={'pos::noun':'Names a light.'})
        stages=[]
        def transport(url,payload,**kwargs):
            system=payload['messages'][0]['content']
            if system==prompts['formatting']:
                stages.append('formatting');value=formatted
            elif system.startswith(prompts['tag_review']):
                stages.append('audit')
                value={'decisions':[{'sense_id':'s1','keep_tags':['pos::noun'],'tag_reasons':{'pos::noun':'Names a light.'}}]}
            else:
                stages.append('content');value=plain(formatted)
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}
        model=ModelClient(Settings('deepseek','deepseek-flash'),transport)
        from unittest.mock import patch
        with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'FAKE-LOCAL-TEST-KEY'}):
            note=ImportPipeline(model,tag_catalog=TagCatalog.load(),prompts=prompts).generate('lantern','en')
        self.assertEqual(stages,['content','formatting','audit'])
        self.assertTrue(note['quality_check']['formatting']['passed'])
        self.assertEqual(note['senses'][0]['definition'],formatted['senses'][0]['definition'])


if __name__=='__main__':unittest.main()
