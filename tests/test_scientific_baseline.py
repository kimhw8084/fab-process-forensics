import unittest
from fabintel.project import analyze
class SpecializedTests(unittest.TestCase):
 def test_no_guess_on_missing_chamber(self):
  source={'id':'SYN_PROCESS','approved_semantic_version':'SYN-1','grain':'one event','source_hash':'a'*64}
  relation={'id':'SYN_REL','approved':True,'source_ids':['SYN_PROCESS'],'keys':['wafer_id','step_instance_id','timestamp','chamber_id'],'cardinality':'one event to one wafer','grain':'one event','effective_start':'2026-11-20T00:00:00+00:00','effective_end':'2026-11-22T00:00:00+00:00'}
  data={'wafer_id':'W1','events':[{'wafer_id':'W1','step_instance_id':'X','operation':'ETCH','timestamp':'2026-11-21T01:00:00+00:00','chamber_id':None,'source_id':'SYN_PROCESS','relationship_id':'SYN_REL','approved_relationship':True}], 'sources':[source], 'relationships':[relation], 'suspected_exposure':{'chamber_id':'C1','start':'2026-11-21T00:00:00+00:00','end':'2026-11-21T03:00:00+00:00'}}
  v=analyze(data)
  self.assertEqual(v['status'],'PARTIAL')
  exposure_claim=next(c for c in v['claims'] if 'exact-chamber/window processing matches' in c['statement'])
  self.assertIn("exact-chamber/window processing matches = []",exposure_claim['statement'])
  self.assertTrue(any('missing chamber assignment' in note for note in v['limitations']))
 def test_refuse_naive_timestamp(self):
  data={'wafer_id':'W1','events':[{'wafer_id':'W1','step_instance_id':'X','operation':'ETCH','timestamp':'2026-11-21T01:00:00','chamber_id':'C1','approved_relationship':True}]}
  self.assertEqual(analyze(data)['status'],'REFUSED')
