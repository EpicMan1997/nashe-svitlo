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
                return {"cmsBattSoc": 73, "powInSumW": 0, "powOutSumW": 250, "cmsDsgRemTime": 612}
            if sn.startswith("PRIVATE-D2"):
                return {"pd.soc": {"PRIVATE-D2-1": 30, "PRIVATE-D2-2": 80,
                                   "PRIVATE-D2-3": 0}[sn],
                        "pd.wattsInSum": 0, "pd.wattsOutSum": 175, "pd.remainTime": 111}
        raise pub.ProbeError("unsupported model")

    def test_snapshot_is_sanitized_and_never_maps_unknown_delta2_location(self):
        with patch.object(pub, "request_api", self.mock_api):
            doc = pub.build_snapshot("ACCESS-PRIVATE", "SECRET-PRIVATE",
                                     datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc), bindings={})
        self.assertEqual(len(doc["devices"]), 4)
        self.assertEqual(doc["devices"]["dacha:dp3"]["socPercent"], 73)
        self.assertEqual(doc["devices"]["dacha:dp3"]["runtimeMinutes"], 612)
        self.assertEqual(doc["devices"]["unassigned:delta2-1"]["runtimeMinutes"], 111)
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
            doc = pub.build_snapshot("A", "B", bindings={})
        self.assertEqual(doc["devices"], {})
        self.assertEqual(doc["availability"]["dacha:dp3"], "invalid_data")
        self.assertEqual(len(doc["unassigned"]), 3)

    def test_verified_location_bindings_and_expansion_battery_soc(self):
        secret = "TEST_SECRET_ONLY"
        stable = {key: pub.fingerprint(serial, secret) for key, serial in (
            ("dacha:d2", "PRIVATE-D2-3"),
            ("solovky:d2", "PRIVATE-D2-1"),
            ("naumenky:d2", "PRIVATE-D2-2"),
        )}
        def api(path, access, secret_key, query=None):
            if path == pub.DEVICE_LIST:
                return list(reversed(self.DEVICES))
            if path == pub.DEVICE_QUOTA:
                sn = query["sn"]
                if sn == "PRIVATE-DP3":
                    return {"cmsBattSoc": 89.3, "bmsBattSoc": 90.4,
                            "cmsBattFullEnergy": 8192, "powInSumW": 0, "powOutSumW": 172}
                if sn.startswith("PRIVATE-D2"):
                    soc = {"PRIVATE-D2-1": 80, "PRIVATE-D2-2": 91, "PRIVATE-D2-3": 98}[sn]
                    return {"pd.soc": soc, "bms_bmsStatus.soc": soc,
                            "bms_slave.soc": {"PRIVATE-D2-1": 80,
                                              "PRIVATE-D2-2": 46,
                                              "PRIVATE-D2-3": None}[sn],
                            "pd.wattsInSum": 0, "pd.wattsOutSum": 100}
            raise pub.ProbeError("1006")
        with patch.object(pub, "request_api", api):
            doc = pub.build_snapshot("ACCESS", secret, bindings=stable)
        self.assertEqual(doc["unassigned"], [])
        self.assertEqual(doc["devices"]["dacha:d2"]["socPercent"], 98)
        self.assertEqual(doc["devices"]["solovky:d2"]["socPercent"], 80)
        self.assertNotIn("solovky:d2eb", doc["devices"])
        self.assertEqual(doc["devices"]["naumenky:d2"]["socPercent"], 91)
        self.assertEqual(doc["devices"]["dacha:dp3"]["socPercent"], 89.3)
        self.assertNotIn("dacha:dp3eb", doc["devices"])
        self.assertFalse(doc["devices"]["dacha:dp3"].get("estimated", False))
        self.assertNotIn("naumenky:d2eb", doc["devices"])
        self.assertEqual(doc["availability"]["solovky:d2eb"], "unavailable")
        self.assertEqual(doc["availability"]["dacha:dp3eb"], "unavailable")
        for key in ("dacha:d2", "solovky:d2", "naumenky:d2", "dacha:dp3"):
            self.assertEqual(doc["availability"][key], "readable")
        self.assertNotIn("PRIVATE", json.dumps(doc))
        self.assertNotIn(secret, json.dumps(doc))

    def test_reported_system_charge_not_individual_pack_estimate(self):
        secret = "TEST_ONLY"
        stable = {key: pub.fingerprint(serial, secret) for key, serial in (
            ("dacha:d2", "PRIVATE-D2-3"),
            ("solovky:d2", "PRIVATE-D2-1"),
            ("naumenky:d2", "PRIVATE-D2-2"),
        )}
        def api(path, access, secret_key, query=None):
            if path == pub.DEVICE_LIST:
                return self.DEVICES
            if path == pub.DEVICE_QUOTA:
                sn = query["sn"]
                if sn == "PRIVATE-DP3":
                    return {"cmsBattSoc": 90.37937, "bmsBattSoc": 96,
                            "cmsBattFullEnergy": 8192, "powInSumW": 0,
                            "powOutSumW": 171}
                if sn == "PRIVATE-D2-1":
                    return {"pd.soc": 80.46, "bms_bmsStatus.soc": 70,
                            "bms_slave.soc": 60,
                            "pd.wattsInSum": 0, "pd.wattsOutSum": 40}
                if sn.startswith("PRIVATE-D2"):
                    return {"pd.soc": 91, "pd.wattsInSum": 0, "pd.wattsOutSum": 0}
            raise pub.ProbeError("1006")
        with patch.object(pub, "request_api", api):
            doc = pub.build_snapshot("ACCESS", secret, bindings=stable)
        self.assertEqual(doc["devices"]["dacha:dp3"]["socPercent"], 90.4)
        self.assertEqual(doc["devices"]["solovky:d2"]["socPercent"], 80.5)
        self.assertNotIn("dacha:dp3eb", doc["devices"])
        self.assertNotIn("solovky:d2eb", doc["devices"])
        self.assertNotIn("estimated", json.dumps(doc))

    def test_temporary_delta2_errors_are_classified_without_exposing_identity(self):
        secret = "TEST_PRIVATE_KEY"
        bindings = {key: pub.fingerprint(serial, secret) for key, serial in (
            ("dacha:d2", "PRIVATE-D2-3"),
            ("solovky:d2", "PRIVATE-D2-1"),
            ("naumenky:d2", "PRIVATE-D2-2"),
        )}
        def api(path, access, secret_key, query=None):
            if path == pub.DEVICE_LIST:
                # DELTA 2 of Dacha temporarily absent from the account list.
                return [self.DEVICES[1], self.DEVICES[4], self.DEVICES[5]]
            if path == pub.DEVICE_QUOTA:
                sn = query["sn"]
                if sn == "PRIVATE-DP3":
                    return {"cmsBattSoc": 70, "powInSumW": 0, "powOutSumW": 80}
                if sn == "PRIVATE-D2-2":
                    raise pub.ProbeError("EcoFlow HTTP error 429")
                if sn == "PRIVATE-D2-3":
                    raise pub.ProbeError("EcoFlow rejected request (code 1006)")
            raise pub.ProbeError("unavailable")
        with patch.object(pub, "request_api", api):
            doc = pub.build_snapshot("ACCESS", secret, bindings=bindings)
        self.assertEqual(doc["availability"]["dacha:d2"], "api_error")
        self.assertEqual(doc["availability"]["solovky:d2"], "not_listed")
        self.assertEqual(doc["availability"]["naumenky:d2"], "rate_limited")
        self.assertEqual(doc["availability"]["dacha:dp3"], "readable")
        public = json.dumps(doc)
        for private in ("PRIVATE-", "TEST_PRIVATE_KEY", "ACCESS"):
            self.assertNotIn(private, public)

    def test_public_error_classifier_never_reflects_raw_provider_message(self):
        self.assertEqual(pub.public_error_status(pub.ProbeError("EcoFlow HTTP error 429")),
                         "rate_limited")
        self.assertEqual(pub.public_error_status(pub.ProbeError("code 1006")),
                         "api_error")
        self.assertEqual(pub.public_error_status(pub.ProbeError("unavailable")),
                         "api_error")
        self.assertEqual(pub.public_error_code(pub.ProbeError("EcoFlow HTTP error 429")),
                         "code_429")
        self.assertEqual(pub.public_error_code(pub.ProbeError("EcoFlow rejected request (code 1006)")),
                         "code_1006")
        self.assertEqual(pub.public_error_code(pub.ProbeError("Could not reach EcoFlow EU API")),
                         "network")

    def test_ambiguous_delta_pro_3_serial_never_claims_location(self):
        devices = [self.DEVICES[1], {"sn": "OTHER-DP3", "deviceName": "DELTA Pro 3"}]
        with patch.object(pub, "request_api", return_value=devices):
            doc = pub.build_snapshot("A", "B", bindings={})
        self.assertNotIn("dacha:dp3", doc["devices"])


if __name__ == "__main__":
    unittest.main()
