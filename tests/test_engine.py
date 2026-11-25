import json, unittest
from pathlib import Path
from fabintel.project import AnalysisCancelled, analyze
from fabintel.contracts import validate_envelope
BASE=Path(__file__).resolve().parent.parent
class EngineCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.positive=json.loads((BASE/'fixtures'/'case_positive.json').read_text())
        cls.negative=json.loads((BASE/'fixtures'/'case_negative.json').read_text())
        cls.oracle=json.loads((BASE/'fixtures'/'independent_oracle.json').read_text())
    def test_fixed_positive_oracle(self):
        result=analyze(self.positive); validate_envelope(result)
        self.assertEqual(result['status'],self.oracle['positive_status'])
        self.assertTrue(any(self.oracle['claim_contains'] in c['statement'] for c in result['claims']))
        self.assertEqual(result['mode'],'SYNTHETIC_DEMO')
    def test_fixed_negative_oracle(self):
        result=analyze(self.negative)
        self.assertEqual(result['status'],self.oracle['negative_status'])
        self.assertEqual(result['claims'],[])
        self.assertTrue(result['limitations'])
    def test_deterministic(self):
        self.assertEqual(analyze(self.positive),analyze(self.positive))
    def test_never_claim_caused_or_control(self):
        result=analyze(self.positive)
        self.assertTrue(all(c['category'] not in ('CAUSAL_ESTIMATE','INTERVENTION_VALIDATED') for c in result['claims']))
    def test_cancellation_interrupts_analysis_without_returning_partial_evidence(self):
        checks=0
        def cancel_after_first_event():
            nonlocal checks
            checks+=1
            return checks>=4
        with self.assertRaises(AnalysisCancelled):
            analyze(self.positive,cancel_check=cancel_after_first_event)
        self.assertGreaterEqual(checks,4)
        self.assertEqual(analyze(self.positive)['status'],self.oracle['positive_status'])
if __name__=='__main__':unittest.main()
