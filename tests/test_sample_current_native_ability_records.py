import unittest
import base64
from scripts.sample_current_native_ability_records import GAME_SHA, QUALIFICATION, validate_report, validate_keys, build_launch

def fixture():
    return {"schemaVersion":1,"contractVersion":"native-current-ability-records-candidate-sample/1","status":"complete","observation":{"qualification":QUALIFICATION,"identity":{"processId":123,"processStartUtcTicks":456,"executableSha256":GAME_SHA},"startedAtUtc":"2026-11-07T00:00:00Z","completedAtUtc":"2026-11-07T00:00:01Z","selector":1,"tlsIndex":2,"collection":3,"records":[{"key":1,"status":"type-verified-candidate","recordAddress":1234,"apiListFilterNonzeroRaw":1,"child":{"status":"null","address":0,"localizationKey":0},"secondaryChild":{"status":"null","address":0,"localizationKey":0},"fullIdCandidate":"A0000000100000000"},{"key":2,"status":"cache-miss","recordAddress":None,"apiListFilterNonzeroRaw":None,"child":None,"secondaryChild":None,"fullIdCandidate":None}]}}

class Tests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_report(fixture(),pid=123,ticks=456,keys=[1,2])["recordCount"],2)
    def test_identity_and_order(self):
        r=fixture(); r["observation"]["identity"]["processStartUtcTicks"]=True
        with self.assertRaises(ValueError): validate_report(r,pid=123,ticks=456,keys=[1,2])
        with self.assertRaises(ValueError): validate_report(fixture(),pid=123,ticks=456,keys=[2,1])
    def test_fields(self):
        for field,value in (("fullIdCandidate","A0000000200000000"),("apiListFilterNonzeroRaw",256),("status","bad")):
            r=fixture(); r["observation"]["records"][0][field]=value
            with self.assertRaises(ValueError): validate_report(r,pid=123,ticks=456,keys=[1,2])
    def test_bulk_launch_is_bounded(self):
        root = r"C:\Users\mrkoo\AppData\Local\RiftReader2\codex-jobs\current-ability-records-F4148B838AF694EF"
        token = "a" * 32
        script = build_launch(root + r"\RiftReader2.Live.exe", root + r"\keys-" + token + ".txt", root + r"\sample-" + token + ".json", 11672, 639296016581575957, "F" * 64)
        self.assertLessEqual(len(base64.b64encode(script.encode("utf-16le"))), 4096)
        self.assertIn("--keys $keys", script)
        with self.assertRaises(ValueError):
            build_launch(root + r"\RiftReader2.Live.exe", r"C:\other\keys.txt", root + r"\sample.json", 11672, 639296016581575957, "F" * 64)

    def test_keys(self):
        for keys in ([1,1],[],[True],[-1],[2**32]):
            with self.assertRaises(ValueError): validate_keys(keys)

if __name__ == "__main__": unittest.main()
