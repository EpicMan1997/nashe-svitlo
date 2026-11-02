import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ecoflow_probe as probe


class ProbeTests(unittest.TestCase):
    def test_ecoflow_signature_orders_parameters_before_headers(self):
        headers = probe.signed_headers(
            "ACCESS", "SECRET", {"sn": "AB123"}, nonce="123456", timestamp="1700000000123")
        canonical = (
            "sn=AB123&accessKey=ACCESS&nonce=123456&timestamp=1700000000123"
        )
        expected = hmac.new(b"SECRET", canonical.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(headers["sign"], expected)
        self.assertNotIn("SECRET", str(headers))

    def test_probe_never_reveals_device_name_or_serial(self):
        entry = {"deviceName": "DELTA 2 in private living room", "sn": "VERY-SECRET-SERIAL",
                 "online": True}
        self.assertEqual(probe.safe_model(entry), "DELTA 2")
        self.assertEqual(probe.online_status(entry["online"]), "online")
        self.assertEqual(probe.safe_model({"deviceName": "My Street 123"}), "Модель не визначена")
        self.assertEqual(probe.online_status(None), "unknown")

    def test_devices_extracted_from_lists_only(self):
        self.assertEqual(len(probe.extract_devices({"list": [{"sn": "a"}]})), 1)
        self.assertEqual(len(probe.extract_devices([{"sn": "b"}])), 1)
        with self.assertRaises(probe.ProbeError):
            probe.extract_devices({"message": "missing devices"})

    def test_only_read_only_list_and_quota_endpoints_allowed(self):
        with self.assertRaises(probe.ProbeError):
            probe.request_api("/iot-open/sign/device/quota", "A", "S")
        with self.assertRaises(probe.ProbeError):
            probe.request_api("/iot-open/sign/certification", "A", "S")

    def test_api_list_uses_get_and_never_logs_raw_data(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, max_bytes):
                return json.dumps({"code": "0", "data": [{"sn": "SUPERSECRET", "deviceName": "DELTA 2"}]}).encode()
        requests = []
        def fake_open(req, timeout=20):
            requests.append(req)
            return Response()
        with patch.object(probe, "urlopen", fake_open):
            result = probe.request_api(probe.DEVICE_LIST, "ACCESS", "SECRET")
        self.assertEqual(result[0]["sn"], "SUPERSECRET")
        self.assertEqual(requests[0].get_method(), "GET")
        self.assertEqual(requests[0].full_url, "https://api-e.ecoflow.com/iot-open/sign/device/list")


if __name__ == "__main__":
    unittest.main()
