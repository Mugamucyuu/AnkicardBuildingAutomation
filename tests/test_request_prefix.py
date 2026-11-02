"""The cache optimization changes JSON ordering, never instructions or data."""
import json
import copy
import unittest

from vocab_app.pipeline import ImportPipeline
from vocab_app.examples import OfflineClient
from vocab_app.taxonomy import TagCatalog
from vocab_app.prompts import default_prompts, assemble_generation
from vocab_app.tag_review import audit_tags


class Capture(OfflineClient):
    def generate(self, system, user, **kwargs):
        self.last = (system, user)
        return super().generate(system, user, **kwargs)


class RequestPrefixTests(unittest.TestCase):
    def test_generation_preserves_values_and_instructions_for_all_languages(self):
        prompts=default_prompts()
        for language,word in [('en','apple'),('ja','猫'),('ko','나무')]:
            model=Capture()
            catalog=TagCatalog.load()
            pipeline=ImportPipeline(model,tag_catalog=catalog,prompts=prompts)
            pipeline.generate(word,language)
            system,user=model.last
            expected={'word':word,'language':language,**catalog.prompt_context(language),
                      'research':{'mode':'independent','sources':[],'queries':[]}}
            self.assertEqual(json.loads(user),expected)
            self.assertEqual(system,assemble_generation(prompts,language,False))
            prefix=json.dumps(catalog.prompt_context(language),ensure_ascii=False)[:-1]
            self.assertTrue(user.startswith(prefix+', '))
            self.assertLess(user.index('"allowed_tags"'),user.index('"word"'))

    def test_audit_retains_catalog_and_proposals_before_per_word_fields(self):
        prompts=default_prompts()
        catalog=TagCatalog.load()
        content={'word':'apple','senses':[{'id':'s1','tags':['pos::noun']}],'analysis':{'nuance':'unchanged'}}
        captured=[]
        class Reviewer:
            def __init__(self,settings=None,transport=None):
                self.settings=settings;self.transport=transport
            def generate(self,system,user,**kwargs):
                captured.append((system,user))
                return json.dumps({'decisions':[{'sense_id':'s1','keep_tags':['pos::noun'],'tag_reasons':{'pos::noun':'Names a fruit.'}}]})
        for word in ['apple','peninsula']:
            expected=copy.deepcopy({'word':word,'reading':'','language':'en','senses':content['senses'],
                      'analysis':content['analysis'],'sources':[],**catalog.prompt_context('en')})
            audit_tags(Reviewer(),content,'en',{'sources':[]},word=word,catalog=catalog,prompts=prompts)
            system,user=captured[-1]
            self.assertEqual(json.loads(user),expected)
            self.assertEqual(system,prompts['tag_review']+'\n\n'+prompts['tag_policy'])
            self.assertLess(user.index('"allowed_tags"'),user.index('"word"'))
        self.assertEqual(captured[0][1].split('"word":')[0],captured[1][1].split('"word":')[0])


if __name__=='__main__':unittest.main()
