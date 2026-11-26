import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import ecoflow_compatibility as check
from ecoflow_probe import ProbeError

class CompatibilityTest(unittest.TestCase):
    def test_denial_and_absence_are_not_confused(self):
        def fake(path, access, secret, query=None):
            if path == check.DEVICE_LIST:
                return [{"productName": "DELTA 3 Plus", "sn": "secret-serial"}]
            raise ProbeError("EcoFlow rejected request (code 1006)")
        with patch.object(check,"request_api",side_effect=fake):
            r=check.audit("a","s")
        self.assertEqual(r["models"]["DELTA 3 Plus"], {"status":"denied","code":"1006"})
        self.assertEqual(r["models"]["RIVER 3 Plus"], {"status":"not_listed"})
        self.assertNotIn("secret-serial",repr(r))
    def test_new_model_access_can_be_reported(self):
        with patch.object(check,"request_api",side_effect=[
            [{"productName":"RIVER 3 Plus Wireless","sn":"hidden"}],{"soc":42}
        ]):
            r=check.audit("a","s")
        self.assertEqual(r["models"]["RIVER 3 Plus"],{"status":"quota_available"})
        self.assertNotIn("42",repr(r))
    def test_failed_list_is_not_unsupported(self):
        with patch.object(check,"request_api",side_effect=ProbeError("EcoFlow HTTP error 429")):
            r=check.audit("a","s")
        self.assertEqual(r,{"list_status":"error","code":"429","models":{}})
