import copy
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "probe_native_mana_descriptor",
    Path(__file__).parents[1] / "scripts/probe_native_mana_descriptor.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


MODULE = 0x140000000


def report():
    return {
        "status": "complete",
        "vmIdentity": {"vmx": r"c:\rift-lab-1\rift-lab.vmx", "port": 5905,
                       "logEpoch": "2026-11-06T00:00:00Z", "pid": 111,
                       "startTicks": 222},
        "readerSha256": "A" * 64,
        "workflowSha256": "B" * 64,
        "probeSha256": "C" * 64,
        "sourceStableAtPublish": True,
        "identity": {"processId": 123, "processStartUtcTicks": 456,
                     "executableSha256": probe.BUILD_SHA,
                     "moduleBaseAddress": MODULE, "moduleSize": 0x4000000},
        "nativePlayerUnitId": "u035400012FA2D678",
        "resourceRecordCandidate": {
            "kind": 3, "name": "mana", "status": "untyped-record-candidate",
            "inputsStable": True, "resourceWrapper": "0x20000000",
            "referenceSlot": "0x20000100", "record": "0x20000200",
            "recordVtableRva": "0x2A6ACD8",
            "candidateDescriptorGetterRva": "0x1CCB460",
            "fields": {"revisionConsistent": True,
                       "expectedNativeResolverTypeUnverified": "0x072A",
                       "baseRaw": 3980, "maximumRaw": 3980, "rateRaw": 9807,
                       "recordRevision": 8, "wrapperRevision": 8,
                       "wrapperClock": 100.0},
            "gameClock": 101.0,
            "observedAtUtc": "2026-11-06T00:00:01Z",
            "observationIntervalUtc": {
                "startedAtUtc": "2026-11-06T00:00:00Z",
                "completedAtUtc": "2026-11-06T00:00:01Z"},
            "mutableTransition": {
                "afterFields": {"revisionConsistent": True,
                                "expectedNativeResolverTypeUnverified": "0x072A",
                                "baseRaw": 3980, "maximumRaw": 3980, "rateRaw": 9807,
                                "recordRevision": 8, "wrapperRevision": 8,
                                "wrapperClock": 100.0},
                "afterSecondaryRevision": 10},
        },
    }


def advance(report_value, *, revision=9, secondary=11, wrapper_clock=102.0,
            game_clock=103.0, base=3970):
    resource = report_value["resourceRecordCandidate"]
    resource["fields"].update(baseRaw=base, recordRevision=revision,
                              wrapperRevision=revision, wrapperClock=wrapper_clock)
    resource["mutableTransition"]["afterFields"] = copy.deepcopy(resource["fields"])
    resource["mutableTransition"]["afterSecondaryRevision"] = secondary
    resource["gameClock"] = game_clock
    resource["observedAtUtc"] = "2026-11-06T00:00:03Z"
    resource["observationIntervalUtc"] = {
        "startedAtUtc": "2026-11-06T00:00:02Z",
        "completedAtUtc": "2026-11-06T00:00:03Z"}


def descriptor_bytes():
    return {
        MODULE + probe.RECORD_VTABLE_RVA + 0x40:
            struct.pack("<Q", MODULE + probe.DESCRIPTOR_GETTER_RVA),
        MODULE + probe.DESCRIPTOR_GLOBAL_RVA:
            struct.pack("<Q", MODULE + probe.DESCRIPTOR_VTABLE_RVA),
        MODULE + probe.DESCRIPTOR_VTABLE_RVA + 8:
            struct.pack("<Q", MODULE + probe.TYPE_GETTER_RVA),
    }


class ManaDescriptorProbeTests(unittest.TestCase):
    def test_deadline_constants_describe_initiation_only(self):
        self.assertEqual(240, probe.OWNER_PHASE_INITIATION_DEADLINE_SECONDS)
        self.assertEqual(120, probe.DESCRIPTOR_PHASE_INITIATION_DEADLINE_SECONDS)
        self.assertFalse(hasattr(probe, "OWNER_PHASE_BUDGET_SECONDS"))
        self.assertFalse(hasattr(probe, "DESCRIPTOR_PHASE_BUDGET_SECONDS"))

    def test_exact_live_fingerprint_returns_kind_three_type(self):
        result = probe.verify_descriptor_bytes(MODULE, descriptor_bytes())
        self.assertEqual("0x072A", result["typeCode"])
        self.assertEqual("0x1CF9F10", result["typeGetterRva"])

    def test_each_live_slot_mismatch_fails_closed(self):
        for address in descriptor_bytes():
            changed = descriptor_bytes()
            changed[address] = struct.pack("<Q", MODULE + 1)
            with self.subTest(address=hex(address)), self.assertRaisesRegex(
                    ValueError, "mana-descriptor-live-slot-mismatch"):
                probe.verify_descriptor_bytes(MODULE, changed)
        missing = descriptor_bytes()
        missing.pop(next(iter(missing)))
        with self.assertRaisesRegex(ValueError, "mana-descriptor-ranges-incomplete"):
            probe.verify_descriptor_bytes(MODULE, missing)

    def test_owner_bracket_requires_same_epoch_player_and_record(self):
        before = report()
        after_same_owner = copy.deepcopy(before)
        after_same_owner["resourceRecordCandidate"].update(
            observedAtUtc="2026-11-06T00:00:03Z",
            observationIntervalUtc={"startedAtUtc": "2026-11-06T00:00:02Z",
                                    "completedAtUtc": "2026-11-06T00:00:03Z"})
        self.assertEqual("u035400012FA2D678",
                         probe.verify_owner_bracket(before, after_same_owner)["nativePlayerUnitId"])
        mutations = [
            lambda r: r["vmIdentity"].update(logEpoch="2026-11-06T00:01:00Z"),
            lambda r: r["identity"].update(processStartUtcTicks=457),
            lambda r: r.update(nativePlayerUnitId="u1"),
            lambda r: r["resourceRecordCandidate"].update(record="0x20000300"),
        ]
        for mutate in mutations:
            after = copy.deepcopy(before)
            mutate(after)
            with self.assertRaisesRegex(ValueError, "changed-across-descriptor-read"):
                probe.verify_owner_bracket(before, after)

    def test_owner_bracket_retains_coherent_advancing_cache_epoch(self):
        before = report()
        after = copy.deepcopy(before)
        advance(after)
        bracket = probe.verify_owner_bracket(before, after)["ownerBracket"]
        self.assertEqual("coherent-cache-epoch-advanced", bracket["status"])
        self.assertEqual(8, bracket["before"]["fields"]["recordRevision"])
        self.assertEqual(9, bracket["after"]["fields"]["recordRevision"])
        self.assertEqual(3970, bracket["after"]["fields"]["baseRaw"])
        self.assertEqual(1.0, bracket["gapSeconds"])
        self.assertIn("not a semantic Mana-freshness claim", bracket["limitations"][2])

    def test_owner_bracket_rejects_backward_or_incoherent_cache_epoch(self):
        mutations = [
            (lambda r: advance(r, revision=7), "mutable-epoch-backward"),
            (lambda r: advance(r, secondary=9), "mutable-epoch-backward"),
            (lambda r: advance(r, wrapper_clock=99.0), "mutable-epoch-backward"),
            (lambda r: advance(r, game_clock=99.0), "mutable-epoch-backward"),
            (lambda r: (advance(r), r["resourceRecordCandidate"]["fields"].update(
                wrapperRevision=10)), "mutable-revision-incoherent"),
            (lambda r: (advance(r), r["resourceRecordCandidate"].update(
                observedAtUtc="2026-11-06T00:00:04Z")), "observation-interval-invalid"),
            (lambda r: (advance(r), r["resourceRecordCandidate"]["fields"].update(
                recordRevision=True, wrapperRevision=True),
                r["resourceRecordCandidate"]["mutableTransition"]["afterFields"].update(
                    recordRevision=True, wrapperRevision=True)), "mutable-integer-invalid"),
        ]
        for mutate, reason in mutations:
            after = copy.deepcopy(report())
            mutate(after)
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                probe.verify_owner_bracket(report(), after)

    def test_descriptor_phase_requires_vm_reader_workflow_and_owner_source(self):
        signature = probe.owner_signature(report())
        probe.verify_phase_bindings(signature, signature["vmIdentity"], "A" * 64,
                                    "B" * 64, "C" * 64)
        changes = [
            (dict(signature["vmIdentity"], pid=999), "A" * 64, "B" * 64, "C" * 64,
             "mana-vm-epoch"),
            (signature["vmIdentity"], "D" * 64, "B" * 64, "C" * 64, "reader-workflow"),
            (signature["vmIdentity"], "A" * 64, "D" * 64, "C" * 64, "reader-workflow"),
            (signature["vmIdentity"], "A" * 64, "B" * 64, "D" * 64, "reader-workflow"),
        ]
        for vm, reader, workflow, source, reason in changes:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                probe.verify_phase_bindings(signature, vm, reader, workflow, source)

    def test_source_pin_detects_mid_run_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe.py"
            path.write_bytes(b"original")
            expected = probe.owner_probe.sha(path.read_bytes())
            probe.require_source_unchanged(path, expected)
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "source-changed-during-run"):
                probe.require_source_unchanged(path, expected)

    def test_untyped_or_energy_record_is_rejected(self):
        for field, value in (("kind", 4), ("name", "energy"),
                             ("recordVtableRva", "0x2D19498"),
                             ("candidateDescriptorGetterRva", "0x231BEB0"),
                             ("inputsStable", False)):
            candidate = report()
            candidate["resourceRecordCandidate"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                probe.owner_signature(candidate)
        candidate = report()
        candidate["sourceStableAtPublish"] = False
        with self.assertRaises(ValueError):
            probe.owner_signature(candidate)

    def test_checked_type_rejects_boolean_or_shifted_module(self):
        with self.assertRaisesRegex(ValueError, "mana-type-fingerprint-mismatch"):
            probe.checked_mana_type(True, 0, 0, 0, 0)
        with self.assertRaisesRegex(ValueError, "mana-type-fingerprint-mismatch"):
            probe.checked_mana_type(
                MODULE + 0x1000, MODULE + probe.RECORD_VTABLE_RVA,
                MODULE + probe.DESCRIPTOR_GETTER_RVA, MODULE + probe.DESCRIPTOR_VTABLE_RVA,
                MODULE + probe.TYPE_GETTER_RVA)


if __name__ == "__main__":
    unittest.main()
