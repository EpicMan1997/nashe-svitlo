"""Public EcoFlow scheduled snapshot must not leak serials or assign DELTA 2 by guess."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ecoflow_publish as pub


class PublishedEcoFlowTests(unittest.TestCase):
    DEVICES = [
        {"sn": "PRIVATE-PO", "deviceName": "PowerOcean"},
        {"sn": "PRIVATE-DP3", "deviceName": "DELTA Pro 3"},
        {"sn": "PRIVATE-D3", "deviceName": "DELTA 3 Plus"},
        {"sn": "PRIVATE-D2-1", "deviceName": "DELTA 2"},
        {"sn": "PRIVATE-D2-2", "deviceName": "DELTA 2"},
        {"sn": "PRIVATE-D2-3", "deviceName": "DELTA 2"},
        {"sn": "PRIVATE-R2", "deviceName": "RIVER 2"},
        {"sn": "PRIVATE-R3", "deviceName": "RIVER 3 Plus"},
    ]

    def mock_api(self, path, access, secret, query=None):
        if path == pub.DEVICE_LIST:
            return self.DEVICES
        if path == pub.DEVICE_QUOTA:
            sn = query["sn"]
            if sn == "PRIVATE-DP3":
                return {"cmsBattSoc": 73, "powInSumW": 0, "powOutSumW": 250}
            if sn.startswith("PRIVATE-D2"):
                return {"pd.soc": {"PRIVATE-D2-1": 30, "PRIVATE-D2-2": 80,
                                   "PRIVATE-D2-3": 0}[sn],
                        "pd.wattsInSum": 0, "pd.wattsOutSum": 175}
        raise pub.ProbeError("unsupported model")

    def test_snapshot_is_sanitized_and_never_maps_unknown_delta2_location(self):
        with patch.object(pub, "request_api", self.mock_api):
            doc = pub.build_snapshot("ACCESS-PRIVATE", "SECRET-PRIVATE",
                                     datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc))
        self.assertEqual(len(doc["devices"]), 4)
        self.assertEqual(doc["devices"]["dacha:dp3"]["socPercent"], 73)
        self.assertEqual(doc["devices"]["unassigned:delta2-3"]["socPercent"], 0)
        self.assertEqual(doc["availability"]["dacha:d2"], "unassigned")
        self.assertEqual(doc["availability"]["dacha:d3p"], "unsupported")
        self.assertEqual(doc["availability"]["home:po"], "unsupported")
        self.assertEqual(doc["availability"]["dacha:dp3eb"], "unavailable")
        for bad_key in ("dacha:d2", "solovky:d2", "naumenky:d2", "home:po", "dacha:d3p"):
            self.assertNotIn(bad_key, doc["devices"])
        payload = json.dumps(doc)
        for private in ("PRIVATE-", "ACCESS-PRIVATE", "SECRET-PRIVATE", "deviceName", "sn"):
            self.assertNotIn(private, payload)

    def test_missing_or_rejected_readings_are_not_zero_or_demo(self):
        def api(path, access, secret, query=None):
            if path == pub.DEVICE_LIST:
                return self.DEVICES
            if query and query.get("sn") == "PRIVATE-DP3":
                return {"cmsBattSoc": -30, "powInSumW": None}
            raise pub.ProbeError("1006")
        with patch.object(pub, "request_api", api):
            doc = pub.build_snapshot("A", "B")
        self.assertEqual(doc["devices"], {})
        self.assertEqual(doc["availability"]["dacha:dp3"], "unavailable")
        self.assertEqual(len(doc["unassigned"]), 3)

    def test_ambiguous_delta_pro_3_serial_never_claims_location(self):
        devices = [self.DEVICES[1], {"sn": "OTHER-DP3", "deviceName": "DELTA Pro 3"}]
        with patch.object(pub, "request_api", return_value=devices):
            doc = pub.build_snapshot("A", "B")
        self.assertNotIn("dacha:dp3", doc["devices"])


if __name__ == "__main__":
    unittest.main()
