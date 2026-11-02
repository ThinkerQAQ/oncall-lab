import unittest
from verify_loki import verify


def record(name, trace):
    return {'stream': {'instance': name}, 'values': [['1', '{"trace_id":"'+trace+'"}']]}

class LokiVerificationTests(unittest.TestCase):
    def test_matches(self):
        payload = {'status': 'success', 'data': {'result': [record('gateway-zone-a1', 'same'), record('metadata-zone-a1','same')]}}
        self.assertEqual(len(verify(payload, 'same')), 2)

    def test_refuses_missing_backend(self):
        payload = {'status': 'success', 'data': {'result': [record('gateway-zone-a1','same')]}}
        with self.assertRaises(ValueError): verify(payload, 'same')

    def test_refuses_different_trace(self):
        payload = {'status': 'success', 'data': {'result': [record('gateway-zone-a1','same'),record('metadata-zone-a1','different')]}}
        with self.assertRaises(ValueError): verify(payload, 'same')

if __name__ == '__main__': unittest.main()
