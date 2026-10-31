import json,unittest
from unittest.mock import Mock,patch
from vocab_app.research import ResearchCollector,domain_matches
from vocab_app.taxonomy import TagCatalog
from vocab_app.tag_review import audit_tags
from vocab_app.preview import paragraphs
from vocab_app.expanded_media import ojad
from vocab_app.public_media import PublicMediaRegistry
class ImprovementsTests(unittest.TestCase):
 def setUp(self):
  lookup=patch("vocab_app.research.wiktionary_entry",return_value=None)
  lookup.start();self.addCleanup(lookup.stop)
 def test_exact_dictionary_entry_avoids_unrelated_search_hits(self):
  search=Mock()
  entry={"url":"https://en.wiktionary.org/wiki/값#Korean","title":"값","excerpt":"price; value","content_type":"dictionary_entry_excerpt"}
  with patch("vocab_app.research.wiktionary_entry",return_value=entry):
   result=ResearchCollector(search).collect("값","ko","sources",["wiktionary"])
  self.assertEqual(result["sources"][0]["url"],entry["url"])
  search.search.assert_not_called()
 def test_independent_never_searches(self):
  search=Mock()
  self.assertEqual(ResearchCollector(search).collect("word","en")["sources"],[])
  search.search.assert_not_called()
 def test_selected_sources_filters_unselected_hosts(self):
  search=Mock()
  search.search.return_value=[{"url":"https://en.wiktionary.org/wiki/word","content":"real evidence","title":"Word"},{"url":"https://bad.example/en.wiktionary.org","content":"not selected"}]
  result=ResearchCollector(search).collect("word","en","sources",["wiktionary"])
  self.assertEqual(len(result["sources"]),1)
 def test_web_uses_planned_query(self):
  search=Mock();search.search.return_value=[{"url":"https://example.com/word","summary":"usable summary"}]
  plan=Mock(return_value="planned query")
  ResearchCollector(search).collect("word","en","web",planner=plan)
  search.search.assert_called_once_with("planned query")
 def test_korean_dictionary_query_prioritizes_exact_headword(self):
  search=Mock();search.search.return_value=[{"url":"https://en.wiktionary.org/wiki/값","content":"Korean: price; value"}]
  ResearchCollector(search).collect("값","ko","sources",["wiktionary"])
  search.search.assert_called_once_with('"값" site:en.wiktionary.org')
 def test_korean_dictionary_rejects_related_hanja_as_substitute(self):
  search=Mock();search.search.return_value=[{"url":"https://en.wiktionary.org/wiki/値","content":"related hanja, not the headword"}]
  with self.assertRaises(ValueError):ResearchCollector(search).collect("값","ko","sources",["wiktionary"])
 def test_no_grounding_does_not_fall_back_silently(self):
  search=Mock();search.search.return_value=[]
  with self.assertRaises(ValueError):ResearchCollector(search).collect("word","en","sources",["wiktionary"])
 def test_regional_rules(self):
  c=TagCatalog.load()
  self.assertEqual(c.validate(["regional"],"ko"),["regional"])
  self.assertEqual(c.validate(["regional::kansai"],"ja"),["regional::kansai"])
  for tag,lang in [("regional","en"),("regional::us","ja"),("region::ja::standard","ja")]:
   with self.assertRaises(ValueError):c.validate([tag],lang)
 def test_comparison_headings_separate_paragraphs(self):
  result=paragraphs("**A vs. B:** First difference. **A vs. C:** Second difference.")
  self.assertEqual(result.count("<p>"),2)
  self.assertEqual(paragraphs("Context & Tone: Neutral. Emphasis: State.").count("<p>"),2)
 def test_pitch_is_taken_from_public_page(self):
  responses=[{"parse":{"sections":[{"line":"Japanese","level":"2","index":"1"}]}},{"parse":{"text":{"*":"(Tokyo) おーりょー (Heiban – [0])"}}}]
  with patch("vocab_app.public_media.api",side_effect=responses):
   result=PublicMediaRegistry().wiktionary("横領","ja")
  self.assertIn("[0]",result.pitch_accents[0]["label"])
 def test_ojad_rejects_other_verbs_potential_form(self):
  markup='<tr><p class="midashi_word">敷く・敷きます</p><td class="katsuyo katsuyo_jisho_js"><span class="char">し</span><span class="char">く</span><a id="837_1_1_female"></a></td></tr>'
  with patch("vocab_app.ojad.fetch",return_value=markup):
   self.assertEqual(ojad("しける").assets,[])
