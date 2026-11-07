import copy
import unittest
from scripts.sample_current_native_ability_maps import GAME_SHA, QUALIFICATION, validate_report

def fixture():
    entry = {"address": 4096, "key": 1, "rawHex": "000000000000000001000000000000000000803f00000040", "valueRawHex":"0000803f", "value":1.0, "secondaryRawHex":"00000040", "secondary":2.0}
    return {"schemaVersion":1,"contractVersion":"native-current-ability-maps-candidate-sample/1","status":"complete","qualification":QUALIFICATION,"observation":{"identity":{"processId":123,"processStartUtcTicks":456,"executableSha256":GAME_SHA},"qualification":QUALIFICATION,"startedAtUtc":"2026-11-07T00:00:00Z","completedAtUtc":"2026-11-07T00:00:01Z","nativeUnitKey":1,"context":2,"clockPointer":3,"clockBefore":1.0,"clockAfter":2.0,"maps":[{"offset":448,"bucketBase":4096,"stride":40,"bucketCount":1,"entryCount":1,"entries":[entry]},{"offset":576,"bucketBase":0,"stride":24,"bucketCount":0,"entryCount":0,"entries":[]}]}}

class ValidationTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_report(fixture(),pid=123,ticks=456)["entryCount"],1)
    def test_identity(self):
        for key, val in (("processId",124),("processStartUtcTicks",True),("processStartUtcTicks",456.0)):
            report=fixture(); report["observation"]["identity"][key]=val
            with self.assertRaises(ValueError): validate_report(report,pid=123,ticks=456)
    def test_count_and_clock(self):
        for field, value in (("entryCount",2),("clockAfter",0)):
            report=fixture(); obs=report["observation"]
            (obs["maps"][0] if field=="entryCount" else obs)[field]=value
            with self.assertRaises(ValueError): validate_report(report,pid=123,ticks=456)
    def test_bad_hex_and_scalar(self):
        for field,val in (("rawHex","z"*48),("value",2.0)):
            report=fixture(); report["observation"]["maps"][0]["entries"][0][field]=val
            with self.assertRaises(ValueError): validate_report(report,pid=123,ticks=456)

if __name__ == "__main__": unittest.main()
