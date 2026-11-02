import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ecoflow_live_normalize import LocationTelemetry, StationReading, nested_get


class EcoflowLiveNormalizeTests(unittest.TestCase):
    def test_delta_pro_3_uses_observed_raw_fields(self):
        station = StationReading("dacha:dp3", "delta_pro_3")
        self.assertTrue(station.update({
            "params": {"cmsBattSoc": 76, "powInSumW": 0, "powOutSumW": 460}
        }, 1_700_000_000))
        reading = station.snapshot(1_700_000_004)
        self.assertEqual(reading["socPercent"], 76)
        self.assertEqual(reading["inputW"], 0)
        self.assertEqual(reading["outputW"], 460)
        self.assertEqual(reading["operation"], "discharging")
        self.assertNotIn("serial", reading)

    def test_delta_2_nested_rest_and_mqtt_fields(self):
        station = StationReading("solovky:d2", "delta_2")
        station.update({"pd.soc": 43, "pd.wattsInSum": 150,
                        "pd.wattsOutSum": 45}, 100)
        self.assertEqual(station.snapshot(102)["operation"], "unknown")
        station.update({"params": {"pd": {"soc": 44, "wattsInSum": 150,
                                         "wattsOutSum": 0}}}, 103)
        self.assertEqual(station.snapshot(103)["operation"], "charging")
        self.assertEqual(station.snapshot(103)["socPercent"], 44)

    def test_incremental_mqtt_delta_does_not_refresh_old_power(self):
        station = StationReading("dacha:d2", "delta_2")
        station.update({"pd.soc": 60, "pd.wattsInSum": 0,
                        "pd.wattsOutSum": 700}, 100)
        station.update({"params": {"pd": {"soc": 61}}}, 131)
        reading = station.snapshot(131)
        self.assertEqual(reading["socPercent"], 61)
        self.assertNotIn("inputW", reading)
        self.assertNotIn("outputW", reading)
        self.assertEqual(reading["operation"], "unknown")

    def test_stale_or_unsupported_device_never_falls_back_to_demo(self):
        station = StationReading("dacha:dp3", "delta_pro_3")
        self.assertFalse(station.update({"cmsBattSoc": -50, "powInSumW": False,
                                          "powOutSumW": 25000}, 100))
        self.assertIsNone(station.snapshot(105))
        station.update({"cmsBattSoc": 0}, 100)
        self.assertEqual(station.snapshot(100)["socPercent"], 0)
        self.assertIsNone(station.snapshot(131))
        other = StationReading("home:po", "power_ocean")
        self.assertFalse(other.update({"cmsBattSoc": 90}, 100))

    def test_private_serial_mapping_not_present_in_public_payload(self):
        gateway = LocationTelemetry({
            "SECRET-SN-12345": {"key": "dacha:dp3", "model": "delta_pro_3"},
            "SECRET-SN-67890": {"key": "naumenky:d2", "model": "delta_2"},
        })
        self.assertTrue(gateway.ingest("SECRET-SN-12345", {
            "params": {"cmsBattSoc": 83}}, 100))
        self.assertFalse(gateway.ingest("UNKNOWN", {"params": {"cmsBattSoc": 77}}, 100))
        public = gateway.public_devices(100)
        self.assertEqual(set(public), {"dacha:dp3"})
        self.assertNotIn("SECRET-SN", str(public))
        self.assertEqual(public["dacha:dp3"]["socPercent"], 83)
        with self.assertRaises(ValueError):
            LocationTelemetry({"SN1": {"key": "dacha:dp3", "model": "delta_pro_3"},
                               "SN2": {"key": "dacha:dp3", "model": "delta_2"}})

    def test_read_number_never_confuses_false_zero_and_duplicate_modules(self):
        self.assertEqual(nested_get({"pd": {"soc": 0}}, "pd.soc"), 0)
        station = StationReading("dacha:d2", "delta_2")
        station.update({"pd": {"soc": False, "wattsInSum": 0}}, 100)
        self.assertNotIn("socPercent", station.snapshot(100))
        self.assertEqual(station.snapshot(100)["inputW"], 0)


if __name__ == "__main__":
    unittest.main()
