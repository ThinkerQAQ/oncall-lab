import unittest

from verify_trace import verify


def fixture():
    def span(name, id_, parent=None):
        result = {"name": name, "spanId": id_, "traceId": "all-the-same-trace"}
        if parent is not None:
            result["parentSpanId"] = parent
        return result

    return {
        "batches": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "GatewayService"}}]},
                "scopeSpans": [{"spans": [
                    span("HTTP GET /metadata", "root"),
                    span("metadata.MetadataService/GetMetadata", "client", "root"),
                ]}],
            },
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "MetadataService"}}]},
                "scopeSpans": [{"spans": [span("metadata.MetadataService/GetMetadata", "server", "client")]}],
            },
        ]
    }


class TraceVerificationTests(unittest.TestCase):
    def test_expected_chain(self):
        self.assertEqual(verify(fixture()), 3)

    def test_wrong_parent(self):
        data = fixture()
        data["batches"][1]["scopeSpans"][0]["spans"][0]["parentSpanId"] = "some-other-trace-parent"
        with self.assertRaises(ValueError):
            verify(data)

    def test_missing_server(self):
        data = fixture()
        data["batches"][1]["scopeSpans"][0]["spans"].clear()
        with self.assertRaises(ValueError):
            verify(data)

    def test_different_trace_id(self):
        data = fixture()
        data["batches"][1]["scopeSpans"][0]["spans"][0]["traceId"] = "other-id"
        with self.assertRaises(ValueError):
            verify(data)


if __name__ == "__main__":
    unittest.main()
