import json
import unittest
from verify_alert_history import verify


def event(before, after):
    return ['1', json.dumps({'ruleUID': 'oncall_zone_a_timeout', 'previous': before, 'current': after})]

class AlertHistoryTests(unittest.TestCase):
    def test_both_transitions(self):
        d={'status':'success','data':{'result':[{'stream':{'from':'state-history'},'values':[event('Normal','Alerting'),event('Alerting','Normal')]}]}}
        self.assertEqual(len(verify(d)), 2)
    def test_missing_recovery(self):
        d={'status':'success','data':{'result':[{'stream':{'from':'state-history'},'values':[event('Normal','Alerting')]}]}}
        with self.assertRaises(ValueError):verify(d)

if __name__ == '__main__':unittest.main()
