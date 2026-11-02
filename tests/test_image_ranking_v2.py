import unittest
from unittest.mock import Mock
from vocab_app.image_selection import select_image, rank_candidate, validate_plan
from test_image_selection import picture, PLAN, SENSES

class RankingV2Tests(unittest.TestCase):
 def test_later_query_beats_earlier_acceptable_image(self):
  registry=Mock();registry.image_search.side_effect=[[picture('Curd.jpg','')],[picture('Milk curds.jpg')]]
  result=select_image(registry,'curd','en',SENSES,PLAN)
  self.assertEqual(result.selection['selected_title'],'File:Milk curds.jpg')
 def test_food_obscured_lacquerware_is_penalized(self):
  plan={**PLAN,'query':'lacquerware bowl','anchors':['lacquerware','lacquered'],'context':['bowl'],'avoid_scenes':['rice','soup']}
  food=picture('Rice in lacquerware bowl.jpg','rice in a lacquered bowl')
  empty=picture('Lacquered bowl.jpg','empty bowl')
  self.assertGreater(rank_candidate(empty,plan)[0],rank_candidate(food,plan)[0])
 def test_diagram_preference_and_rasterized_svg(self):
  plan={**PLAN,'kind':'diagram'}
  self.assertGreater(rank_candidate(picture('Curd.png',original_mime='image/svg+xml'),plan)[0],rank_candidate(picture('Curd.jpg'),plan)[0])
 def test_all_network_errors_have_distinct_status(self):
  registry=Mock();registry.image_search.side_effect=OSError('offline')
  self.assertEqual(select_image(registry,'curd','en',SENSES,PLAN).selection['status'],'lookup_failed')
 def test_foreign_label_and_specialized_diagrams_rank_lower(self):
  plan={**PLAN,'kind':'diagram'}
  simple=picture('Simple curd.png',original_mime='image/svg+xml')
  foreign=picture('Curd-vi.png',original_mime='image/svg+xml')
  specialized=picture('Curd theorem.png',original_mime='image/svg+xml')
  self.assertGreater(rank_candidate(simple,plan)[0],rank_candidate(foreign,plan)[0])
  self.assertGreater(rank_candidate(simple,plan)[0],rank_candidate(specialized,plan)[0])
