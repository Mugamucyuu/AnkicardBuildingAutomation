import copy
import unittest
from unittest.mock import Mock
from vocab_app.quality import readability_issues, generate_content
import json

def valid_content():
    return {
        "senses":[{"definition":"A **portable light** used for illumination.","examples":["One.","Two.","Three."]}],
        "analysis":{
            "etymology":"From **Latin lanterna**, through French into Middle English.",
            "nuance":"Usually implies **a protected light**, often portable and useful outdoors.",
            "synonyms":"Unlike a **flashlight**, a lantern usually lights a surrounding area.",
            "collocations":[{"phrase":"**camping lantern**","explanation":"A portable light for illuminating the area around a campsite."}]
        }
    }

class QualityTests(unittest.TestCase):
    def test_missing_etymology_emphasis_is_rejected(self):
        content=valid_content()
        content["analysis"]["etymology"]="From Latin, through French."
        self.assertTrue(any("etymology" in issue for issue in readability_issues(content,"en")))

    def test_bare_collocation_translation_is_rejected(self):
        content=valid_content()
        content["analysis"]["collocations"]=[{"phrase":"**나무를 심다**","explanation":"种树"}]
        self.assertTrue(any("explanation" in issue for issue in readability_issues(content,"ko")))

    def test_failed_quality_requests_model_correction(self):
        content=valid_content()
        bad=copy.deepcopy(content)
        bad["analysis"]["etymology"]="Missing emphasis."
        model=Mock()
        model.generate.side_effect=[json.dumps(bad),json.dumps(content)]
        result,check=generate_content(model,"Return JSON","word","en",enforce=True)
        self.assertEqual(check["attempts"],2)
        self.assertEqual(result,content)
        self.assertIn("analysis.etymology",model.generate.call_args.args[1])

    def test_repeated_failure_does_not_publish(self):
        model=Mock()
        model.generate.return_value="{}"
        with self.assertRaises(ValueError):
            generate_content(model,"system","user","en",enforce=True)
        self.assertEqual(model.generate.call_count,3)
