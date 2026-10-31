import copy
import json
import unittest
from unittest.mock import Mock

from vocab_app.quality import explanation_language_issues, generate_content


class OutputLanguageTests(unittest.TestCase):
    def test_korean_definitions_must_be_chinese_in_every_mode(self):
        for mode in ("independent", "web", "sources"):
            content = {"senses": [{"definition": "물건을 사고파는 데 드는 **돈의 액수**.", "examples": []}],
                       "analysis": {}, "research": {"mode": mode}}
            self.assertTrue(any("definition" in issue for issue in explanation_language_issues(content, "ko")))

    def test_chinese_explanations_allow_korean_terms_and_forms(self):
        content = {"senses": [{"definition": "商品的**价格**，即买卖时需要支付的金额。",
                                "examples": ["값이 비싸요.（价格很贵。）"]}],
                   "analysis": {"synonyms": "**가격**强调商品价格；값还可表示抽象价值。",
                                "inflections": "无词形变化；可搭配助词：값이、값을、값의。",
                                "collocations": [{"phrase": "**값이 비싸다**", "explanation": "表示价格高，常用于买东西时评价商品。"}]}}
        self.assertEqual(explanation_language_issues(content, "ko"), [])

    def test_korean_analysis_collocations_and_example_translations_checked(self):
        content = {"senses": [{"examples": ["값이 비싸요."]}],
                   "analysis": {"nuance": "일상에서 자주 쓰는 표현입니다.",
                                "collocations": [{"explanation": "물건이 비쌀 때 사용하는 표현입니다."}]}}
        issues = explanation_language_issues(content, "ko")
        for field in ("examples[0]", "analysis.nuance", "collocations[0].explanation"):
            self.assertTrue(any(field in issue for issue in issues))

    def test_japanese_english_subheadings_rejected(self):
        for label in ("Context & Tone", "Emphasis", "Native-speaker impressions", "Native Speaker Analysis"):
            content = {"analysis": {"nuance": "**" + label + "**\n日常的な語である。"}}
            self.assertTrue(explanation_language_issues(content, "ja"))

    def test_japanese_headings_allow_original_etymological_words(self):
        content = {"analysis": {"etymology": "英語の **tattoo** に相当する。Wiktionary の資料も参照。",
                                "nuance": "**使用場面・語調**\n一般的な語。\n\n**強調点**\n身体装飾を示す。"}}
        self.assertEqual(explanation_language_issues(content, "ja"), [])

    def test_language_drift_requests_a_model_rewrite(self):
        good = {"reading": "いれずみ", "alternative_forms": "入墨",
                "senses": [{"definition": "皮膚に**模様**などを描くこと。", "tags": ["pos::noun", "origin::native"], "examples": ["一。", "二。", "三。", "四。"]}],
                "analysis": {"etymology": "「入れる」と「墨」の**複合語**と考えられる。",
                             "nuance": "**使用場面・語調**\n身体への**装飾**について使う。",
                             "synonyms": "**タトゥーとの違い**\n現代の**装飾**を指すことが多い。",
                             "collocations": [{"phrase": "**入れ墨を入れる**", "explanation": "皮膚に模様を描く行為を表す一般的な言い方。"}]}}
        bad = copy.deepcopy(good)
        bad["analysis"]["nuance"] = "**Context & Tone**\n身体への**装飾**について使う。"
        model = Mock()
        model.generate.side_effect = [json.dumps(bad), json.dumps(good)]
        result, quality = generate_content(model, "instruction", "{}", "ja", enforce=True)
        self.assertEqual(result, good)
        self.assertEqual(quality["attempts"], 2)
        self.assertIn("Japanese subheadings", model.generate.call_args.args[1])
