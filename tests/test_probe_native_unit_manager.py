"""Synthetic tests: no RIFT process, VM, controller, or credentials required."""
import base64
import copy
import json
import math
import struct
import unittest

from scripts.probe_native_unit_manager import (
    BUILD_SHA, calculate_energy, calculate_health, checked_energy_type, checked_health_type, encoded, entity_hash, find_entity,
    actor_render_pose_candidates, historical_body_yaw_candidate, health_record_fields, inspection_identity, pointer, position_transform_candidates, resource_record_fields,
    RESOURCE_LAYOUTS, coherent_mana_resource_transition, require_disjoint_records,
    require_resource_owner_anchors, revalidate_health_candidate,
    sha, snapshot_bytes,
)


class NativeUnitManagerTests(unittest.TestCase):
    def test_exact_hash_vectors(self):
        vectors = {0: 0, 1: 16807, 2: 33614, 127773: 2147480811,
                   0x7FFFFFFF: 0, 0x80000000: 2147466840,
                   0xFFFFFFFF: 2147466840, 0xFFFE0CE3: 2836}
        for seed, expected in vectors.items():
            with self.subTest(seed=seed):
                self.assertEqual(expected, entity_hash(seed))
                self.assertEqual(expected, entity_hash(0x0354000100000000 | seed))

    @staticmethod
    def table(key=0x035400012FA2D207):
        base, stride, count = 0x20000, 24, 64
        header = struct.pack("<QQQ", base, stride, count)
        bucket = base + (entity_hash(key) % count) * stride
        return header, bucket, key

    def test_inline_exact_full_key(self):
        header, bucket, key = self.table()
        raw = struct.pack("<QQQ", 0, key, 0x60000)
        calls = []
        def read(address, length):
            calls.append((address, length))
            return raw
        result = find_entity(header, key, read)
        self.assertEqual(0x60000, result["entity"])
        self.assertEqual([(bucket, 24)], calls)
        self.assertEqual(1, result["visitedNodes"])

    def test_same_low32_different_full_key_does_not_match(self):
        header, bucket, key = self.table()
        raw = struct.pack("<QQQ", 0, key ^ (1 << 48), 0x60000)
        with self.assertRaisesRegex(ValueError, "player-key-not-found"):
            find_entity(header, key, lambda *_: raw)

    def test_tagged_inline_slot_is_not_a_match(self):
        header, bucket, key = self.table()
        raw = struct.pack("<QQQ", 1, key, 0x60000)
        with self.assertRaisesRegex(ValueError, "player-key-not-found"):
            find_entity(header, key, lambda *_: raw)

    def test_tagged_link_reaches_collision_node(self):
        header, bucket, key = self.table()
        nodes = {bucket: struct.pack("<QQQ", 0x50001, key, 0xDEAD0),
                 0x50000: struct.pack("<QQQ", 0, key, 0x60000)}
        result = find_entity(header, key, lambda address, _: nodes[address])
        self.assertEqual(0x50000, result["node"])
        self.assertEqual(0x60000, result["entity"])
        self.assertEqual(2, result["visitedNodes"])

    def test_inline_mismatch_follows_untagged_link(self):
        header, bucket, key = self.table()
        nodes = {bucket: struct.pack("<QQQ", 0x50000, key + 1, 0xDEAD0),
                 0x50000: struct.pack("<QQQ", 0, key, 0x60000)}
        self.assertEqual(0x60000, find_entity(header, key, lambda a, _: nodes[a])["entity"])

    def test_collision_cycle_rejected(self):
        header, bucket, key = self.table()
        nodes = {bucket: struct.pack("<QQQ", 0x50001, 0, 0),
                 0x50000: struct.pack("<QQQ", 0x50001, 0, 0)}
        with self.assertRaisesRegex(ValueError, "lookup-pointer-cycle"):
            find_entity(header, key, lambda a, _: nodes[a])

    def test_node_budget_rejected(self):
        header, bucket, key = self.table()
        with self.assertRaisesRegex(ValueError, "lookup-node-budget"):
            find_entity(header, key, lambda *_: struct.pack("<QQQ", 0x50001, 0, 0), max_nodes=1)

    def test_short_node_rejected(self):
        header, bucket, key = self.table()
        with self.assertRaisesRegex(ValueError, "lookup-read-hole"):
            find_entity(header, key, lambda *_: b"\0" * 16)

    def test_table_shape_and_payload_bounds_rejected(self):
        header, bucket, key = self.table()
        for bad in (struct.pack("<QQQ", 0x20000, 16, 64),
                    struct.pack("<QQQ", 0x20000, 24, 0),
                    struct.pack("<QQQ", 0x20000, 25, 64)):
            with self.assertRaisesRegex(ValueError, "invalid-table-shape"):
                find_entity(bad, key, lambda *_: b"")
        for value in (0, 0x60001, 0x800000000000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                find_entity(header, key, lambda *_: struct.pack("<QQQ", 0, key, value))

    def test_pointer_bounds(self):
        for value in (0, -1, 0x10001, 0x800000000000, 0x7FFFFFFFFFF8):
            with self.assertRaises(ValueError):
                pointer(value, 24)

    @staticmethod
    def position_component(first_degrees=3.465055, second_degrees=3.464628):
        raw = bytearray(0x110)
        xyz = (7415.63671875, 863.5847778320312, 2928.161376953125)
        struct.pack_into("<fff", raw, 0x48, *xyz)
        struct.pack_into("<fff", raw, 0x88, *xyz)
        for offset, angle in ((0x60, first_degrees), (0x94, second_degrees)):
            c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            struct.pack_into("<9f", raw, offset, c, 0, -s, 0, 1, 0, s, 0, c)
        return raw

    def test_position_transform_candidates_are_structural_only(self):
        raw = self.position_component()
        result = position_transform_candidates(raw, raw[0x48:0xB8])
        self.assertEqual("structural-rotation-candidate", result["status"])
        self.assertTrue(result["inputsStable"])
        self.assertEqual(["0x60", "0x94"],
                         [matrix["sourceOffset"] for matrix in result["matrices"]])
        self.assertAlmostEqual(3.465055, result["matrices"][0]["planarAngleDegreesCandidate"],
                               places=4)
        self.assertAlmostEqual(3.464628, result["matrices"][1]["planarAngleDegreesCandidate"],
                               places=4)
        self.assertLess(result["matrices"][0]["orthonormalError"], 1e-6)
        self.assertAlmostEqual(1, result["matrices"][0]["determinant"], places=5)
        self.assertAlmostEqual(7415.63671875,
                               result["secondaryCachedXyzCandidate"]["x"])
        self.assertIn("facing/axis/passive-freshness/restart-unverified", result["scope"])
        self.assertNotIn("facingDegrees", result)

    def test_position_transform_changes_are_withheld_without_harming_other_data(self):
        raw = self.position_component()
        after = bytearray(raw[0x48:0xB8])
        after[0x60 - 0x48] ^= 1
        result = position_transform_candidates(raw, after)
        self.assertEqual("changed-during-probe", result["status"])
        self.assertFalse(result["inputsStable"])
        self.assertNotIn("matrices", result)
        for component, final in ((raw[:0xB7], raw[0x48:0xB8]), (raw, b""),):
            with self.subTest(length=(len(component), len(final))):
                with self.assertRaisesRegex(ValueError, "read-hole"):
                    position_transform_candidates(component, final)

    def test_position_transform_nonfinite_or_nonrotation_is_unqualified(self):
        raw = self.position_component()
        struct.pack_into("<f", raw, 0x60, float("nan"))
        result = position_transform_candidates(raw, raw[0x48:0xB8])
        self.assertEqual("unavailable", result["status"])
        self.assertEqual("nonfinite-transform", result["reason"])
        raw = self.position_component()
        struct.pack_into("<f", raw, 0x64, 2.0)
        result = position_transform_candidates(raw, raw[0x48:0xB8])
        self.assertEqual("unqualified-matrix-shape", result["status"])
        self.assertIsNone(result["matrices"][0]["planarAngleDegreesCandidate"])

    def test_position_transform_nonfinite_xyz_cannot_enter_complete_review(self):
        for offset, value, reason in ((0x48, float("nan"), "nonfinite-primary-xyz"),
                                      (0x88, float("nan"), "nonfinite-secondary-xyz"),
                                      (0x8C, float("inf"), "nonfinite-secondary-xyz")):
            with self.subTest(offset=offset):
                raw = self.position_component()
                struct.pack_into("<f", raw, offset, value)
                result = position_transform_candidates(raw, raw[0x48:0xB8])
                self.assertEqual("unavailable", result["status"])
                self.assertEqual(reason, result["reason"])
                self.assertNotIn("matrices", result)
                json.dumps(result, allow_nan=False)

    @staticmethod
    def actor_render_fixture():
        position = bytearray(0x70)
        struct.pack_into("<3f", position, 0, 5, 6, 7)
        struct.pack_into("<3f", position, 0x40, 10, 20, 30)
        yaw_y_90 = (0, 0, -1, 0, 1, 0, 1, 0, 0)
        pitch_x_90 = (1, 0, 0, 0, 0, -1, 0, 1, 0)
        struct.pack_into("<9f", position, 0x4C, *yaw_y_90)
        actor = bytearray(0x30)
        struct.pack_into("<9f", actor, 0, *yaw_y_90)
        struct.pack_into("<3f", actor, 0x24, 7, 23, 39)
        model = struct.pack("<9f", *pitch_x_90)
        first = struct.pack("<3f", 1, -2, 3)
        second = struct.pack("<3f", -4, 5, 6)
        render = bytearray(0x30)
        struct.pack_into("<9f", render, 0, 0, -1, 0, 0, 0, -1, 1, 0, 0)
        struct.pack_into("<3f", render, 0x24, 7, 23, 39)
        return position, actor, model, first, second, render

    def test_actor_render_pose_row_major_noncommuting_and_xyz_offsets(self):
        parts = self.actor_render_fixture()
        result = actor_render_pose_candidates(*parts, normal_render_branch=True)
        self.assertEqual("candidate-only", result["status"])
        self.assertEqual([[0, -1, 0], [0, 0, -1], [1, 0, 0]],
                         result["computedRenderRows"])
        reverse_product = [[0, 0, -1], [-1, 0, 0], [0, 1, 0]]
        self.assertNotEqual(reverse_product, result["computedRenderRows"])
        self.assertEqual([5, 6, 7], result["primaryXyzCandidate"])
        self.assertEqual([10, 20, 30], result["secondaryXyzCandidate"])
        self.assertEqual([7, 23, 39], result["computedActorXyz"])
        self.assertEqual(0, result["positionToActorMatrixMaxAbsDelta"])
        self.assertEqual(0, result["actorXyzMaxAbsDelta"])
        self.assertEqual(0, result["renderComparison"]["matrixMaxAbsDelta"])
        self.assertEqual(0, result["renderComparison"]["xyzMaxAbsDelta"])
        self.assertAlmostEqual(1, result["matrixShape"]["composition"]["determinant"])
        self.assertNotIn("facingDegrees", result)
        json.dumps(result, allow_nan=False)

    def test_actor_render_pose_missing_or_alternate_renderer_is_unqualified(self):
        position, actor, model, first, second, render = self.actor_render_fixture()
        result = actor_render_pose_candidates(position, actor, model, first, second,
                                               None, normal_render_branch=True)
        self.assertEqual("not-captured", result["renderComparison"]["status"])
        result = actor_render_pose_candidates(position, actor, model, first, second,
                                               None, normal_render_branch=False)
        self.assertEqual("alternate-branch-unqualified",
                         result["renderComparison"]["status"])
        with self.assertRaisesRegex(ValueError, "actor-render-alternate-branch"):
            actor_render_pose_candidates(position, actor, model, first, second,
                                         render, normal_render_branch=False)
        with self.assertRaisesRegex(ValueError, "actor-render-branch-flag"):
            actor_render_pose_candidates(position, actor, model, first, second,
                                         None, normal_render_branch=1)

    def test_actor_render_pose_rejects_short_or_nonfinite_captured_fields(self):
        original = self.actor_render_fixture()
        for index in range(6):
            with self.subTest(short_field=index):
                parts = list(original)
                parts[index] = parts[index][:-1]
                with self.assertRaisesRegex(ValueError, "actor-render-read-hole"):
                    actor_render_pose_candidates(*parts, normal_render_branch=True)
        for index in range(6):
            with self.subTest(nonfinite_field=index):
                parts = [bytearray(part) for part in original]
                struct.pack_into("<f", parts[index], 0, float("nan"))
                result = actor_render_pose_candidates(*parts, normal_render_branch=True)
                self.assertEqual("unavailable", result["status"])
                self.assertIn("nonfinite-", result["reason"])
                json.dumps(result, allow_nan=False)

    def test_actor_render_pose_scaled_actor_remains_candidate_only(self):
        position, actor, model, first, second, render = self.actor_render_fixture()
        struct.pack_into("<f", actor, 0, 2.0)
        result = actor_render_pose_candidates(position, actor, model, first, second,
                                               render, normal_render_branch=True)
        self.assertEqual("candidate-only", result["status"])
        self.assertGreater(result["matrixShape"]["actor"]["orthonormalError"], 0.1)
        self.assertGreater(result["positionToActorMatrixMaxAbsDelta"], 0.1)
        self.assertGreater(result["renderComparison"]["matrixMaxAbsDelta"], 0.1)
        self.assertNotIn("facingDegrees", result)

    def test_historical_yaw_scaffold_matches_v1_conversion_with_xyz_crosscheck(self):
        window = bytearray(0x2C)
        struct.pack_into("<f", window, 4, math.pi / 2)
        struct.pack_into("<3f", window, 0x20, 11.0, 22.0, 33.0)
        result = historical_body_yaw_candidate(window, (11.02, 22.0, 33.0))
        self.assertEqual("cached-player-linked-candidate", result["status"])
        self.assertTrue(result["selfXyzCorrelated"])
        self.assertAlmostEqual(0.0, result["facingDegreesCandidate"], places=4)
        self.assertIn("unverified", result["qualification"])
        self.assertAlmostEqual(0.02, result["cachedXyzDifference"], places=4)

    def test_historical_yaw_scaffold_exposes_uncorrelated_but_finite_candidate(self):
        window = bytearray(0x2C)
        struct.pack_into("<f", window, 4, 0.0)
        struct.pack_into("<3f", window, 0x20, 1.0, 2.0, 3.0)
        result = historical_body_yaw_candidate(window, (100.0, 2.0, 3.0))
        self.assertEqual("legacy-owner-uncorrelated", result["status"])
        self.assertFalse(result["selfXyzCorrelated"])
        self.assertAlmostEqual(90.0, result["facingDegreesCandidate"])
        struct.pack_into("<f", window, 4, float("nan"))
        self.assertEqual("unavailable",
                         historical_body_yaw_candidate(window, (1.0, 2.0, 3.0))["status"])
        with self.assertRaisesRegex(ValueError, "historical-yaw-window-invalid"):
            historical_body_yaw_candidate(window[:-1], (1.0, 2.0, 3.0))

    def test_health_fields_preserve_raw_inputs_without_claiming_hp(self):
        record = bytearray(128)
        wrapper = bytearray(56)
        struct.pack_into("<q", record, 0x48, 100)
        struct.pack_into("<q", record, 0x50, 200)
        struct.pack_into("<q", record, 0x60, 1234)
        struct.pack_into("<i", record, 0x68, 7)
        struct.pack_into("<ff", record, 0x6C, 1.0, 0.5)
        struct.pack_into("<if", wrapper, 0x30, 7, 12.75)
        result = health_record_fields(record, wrapper)
        self.assertEqual(100, result["baseRaw"])
        self.assertEqual(200, result["maximumRaw"])
        self.assertEqual(1234, result["modifierRaw"])
        self.assertEqual([1.0, 0.5], result["caps"])
        self.assertEqual(12.75, result["wrapperClock"])
        self.assertNotIn("currentHp", result)

    @staticmethod
    def health_revalidation_fixture():
        component, record_address = 0x10000, 0x20000
        wrapper, record = bytearray(56), bytes(128)
        struct.pack_into("<Qif", wrapper, 0x28, component, 7, 100.0)
        anchors = {component + 0x28: bytes(wrapper[0x28:0x30]),
                   0x30000: b"ownerptr", 0x40000: b"recordpt", 0x50000: b"getterpt"}
        final = {**anchors, record_address: record,
                 component + 0x30: bytes(wrapper[0x30:0x38])}
        health = {"status": "type-checked-record-candidate",
                  "fields": NativeUnitManagerTests.health_fields(), "gameClock": 101.0}
        return health, anchors, final, record_address, record, component, bytes(wrapper)

    def test_health_revalidation_unchanged_inputs_can_calculate(self):
        result = revalidate_health_candidate(*self.health_revalidation_fixture())
        self.assertTrue(result["inputsStable"])
        self.assertEqual("calculated-candidate", result["calculatedHealth"]["status"])

    def test_health_revision_or_clock_change_is_mutable_not_ownership_drift(self):
        for offset in (0, 4):
            args = self.health_revalidation_fixture()
            changed = bytearray(args[2][args[5] + 0x30])
            changed[offset] ^= 1
            args[2][args[5] + 0x30] = bytes(changed)
            with self.subTest(offset=offset):
                result = revalidate_health_candidate(*args)
                self.assertFalse(result["inputsStable"])
                self.assertEqual("changed-input-record-candidate", result["status"])
                self.assertEqual({"status": "unavailable", "reason": "inputs-changed"},
                                 result["calculatedHealth"])

    def test_health_record_input_change_remains_unavailable(self):
        args = self.health_revalidation_fixture()
        changed = bytearray(args[4])
        changed[0x48] ^= 1
        args[2][args[3]] = bytes(changed)
        result = revalidate_health_candidate(*args)
        self.assertFalse(result["inputsStable"])
        self.assertEqual("unavailable", result["calculatedHealth"]["status"])

    def test_health_true_owner_record_slot_and_getter_drift_fail_closed(self):
        for address in self.health_revalidation_fixture()[1]:
            args = self.health_revalidation_fixture()
            args[2][address] = b"changed!"
            with self.subTest(address=address), self.assertRaisesRegex(
                    ValueError, "health-ownership-anchor-changed"):
                revalidate_health_candidate(*args)

    def test_health_record_vtable_drift_fails_closed(self):
        args = self.health_revalidation_fixture()
        changed = bytearray(args[4])
        changed[0] ^= 1
        args[2][args[3]] = bytes(changed)
        with self.assertRaisesRegex(ValueError, "health-ownership-anchor-changed"):
            revalidate_health_candidate(*args)

    def test_health_fields_missing_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError, "health-candidate-read-hole"):
            health_record_fields(bytes(127), bytes(56))

    def test_health_fields_nonfinite_rejected(self):
        record = bytearray(128)
        struct.pack_into("<f", record, 0x6C, float("nan"))
        with self.assertRaisesRegex(ValueError, "health-candidate-nonfinite"):
            health_record_fields(record, bytes(56))

    def test_health_type_matches_exact_build_metadata_chain(self):
        base = 0x7FF000000000
        self.assertEqual(0x2C2, checked_health_type(base, base + 0x2C0EE88,
                         base + 0x20CCC60, base + 0x2C281B0, base + 0x20F2480))

    def test_health_type_mismatch_fails_closed(self):
        base = 0x140000000
        expected = [base + value for value in (0x2C0EE88, 0x20CCC60, 0x2C281B0, 0x20F2480)]
        for index in range(4):
            changed = list(expected)
            changed[index] = 0
            with self.assertRaisesRegex(ValueError, "health-type-fingerprint"):
                checked_health_type(base, *changed)

    def test_energy_type_matches_exact_build_metadata_chain(self):
        base = 0x7FF000000000
        code = checked_energy_type(base, base + 0x2D19498,
                                   base + 0x231BEB0, base + 0x2D1D420, base + 0x233E9B0)
        self.assertEqual(0x072B, code)
        self.assertNotEqual(0x072A, code)  # Mana's untraced type must not be borrowed.

    def test_energy_type_mismatch_fails_closed(self):
        base = 0x140000000
        expected = [base + value for value in (0x2D19498, 0x231BEB0, 0x2D1D420, 0x233E9B0)]
        for index in range(4):
            changed = list(expected)
            changed[index] = 0
            with self.subTest(field=index), self.assertRaisesRegex(ValueError, "energy-type-fingerprint"):
                checked_energy_type(base, *changed)
        with self.assertRaisesRegex(ValueError, "energy-type-fingerprint"):
            checked_energy_type(base + 0x1000, *expected)  # Reject mismatched module image base.

    @staticmethod
    def health_fields(**updates):
        result = {"baseRaw": 100, "maximumRaw": 200, "modifierRaw": 10000,
                  "recordRevision": 7, "wrapperRevision": 7,
                  "wrapperClock": 100.0, "caps": [1.0, 1.0]}
        result.update(updates)
        return result

    def test_health_calculation_preserves_native_float_constant(self):
        fields = self.health_fields()
        # Native float-derived -0.01 is slightly smaller in magnitude:
        # trunc(10000 * -0.009999999776482582) == -99, not -100.
        self.assertEqual(199, calculate_health(fields, 101.75)["current"])
        self.assertEqual(200, calculate_health(fields, 102.0)["current"])

    def test_health_base_zero_and_alive_floor(self):
        self.assertEqual(0, calculate_health(self.health_fields(baseRaw=0), 101)["current"])
        self.assertEqual(1, calculate_health(self.health_fields(modifierRaw=-20000), 101)["current"])

    def test_health_fraction_cap_returns_before_alive_floor(self):
        self.assertEqual(50, calculate_health(self.health_fields(caps=[1.0, 0.25]), 102)["current"])
        self.assertEqual(0, calculate_health(self.health_fields(caps=[0.0, 1.0]), 102)["current"])

    def test_full_health_stays_bounded(self):
        fields = self.health_fields(baseRaw=14830, maximumRaw=14830, modifierRaw=13138,
                                    wrapperClock=43139.0546875)
        self.assertEqual(14830, calculate_health(fields, 50000)["current"])

    def test_health_calculation_rejects_unqualified_domains(self):
        cases = [(self.health_fields(wrapperRevision=6), 101),
                 (self.health_fields(), 99),
                 (self.health_fields(maximumRaw=0), 101),
                 (self.health_fields(caps=[float("nan"), 1]), 101),
                 (self.health_fields(caps=[1.1, 1]), 101),
                 (self.health_fields(modifierRaw=1 << 40), 101),
                 (self.health_fields(wrapperClock=-3e38), 3e38)]
        for fields, clock in cases:
            with self.subTest(fields=fields, clock=clock):
                self.assertEqual("unavailable", calculate_health(fields, clock)["status"])

    @staticmethod
    def resource_pair(kind: int):
        layout = RESOURCE_LAYOUTS[kind]
        record, wrapper = bytearray(64), bytearray(48)
        struct.pack_into("<i", record, layout["base"], 123)
        struct.pack_into("<i", record, layout["maximum"], 200)
        struct.pack_into("<i", record, layout["rate"], -15)
        struct.pack_into("<i", record, layout["revision"], 7)
        struct.pack_into("<i", wrapper, layout["wrapperRevision"], 7)
        struct.pack_into("<f", wrapper, layout["wrapperClock"], 24.5)
        return record, wrapper

    def test_mana_resource_layout_is_kind_three_and_untyped(self):
        record, wrapper = self.resource_pair(3)
        result = resource_record_fields(3, record, wrapper)
        self.assertEqual("mana", result["name"])
        self.assertEqual("0x072A", result["expectedNativeResolverTypeUnverified"])
        self.assertEqual((123, 200, -15),
                         (result["baseRaw"], result["maximumRaw"], result["rateRaw"]))
        self.assertEqual(24.5, result["wrapperClock"])
        self.assertTrue(result["revisionConsistent"])
        self.assertNotIn("current", result)
        self.assertNotIn("currentMana", result)

    def test_energy_resource_layout_is_kind_four_and_untyped(self):
        record, wrapper = self.resource_pair(4)
        result = resource_record_fields(4, record, wrapper)
        self.assertEqual("energy", result["name"])
        self.assertEqual("0x072B", result["expectedNativeResolverTypeUnverified"])
        self.assertEqual((123, 200, -15),
                         (result["baseRaw"], result["maximumRaw"], result["rateRaw"]))
        self.assertTrue(result["revisionConsistent"])
        self.assertNotIn("current", result)

    @staticmethod
    def energy_fields(**updates):
        fields = {"kind": 4, "baseRaw": 80, "maximumRaw": 100, "rateRaw": 2000,
                  "recordRevision": 5, "wrapperRevision": 5, "wrapperClock": 100.0}
        fields.update(updates)
        return fields

    def test_energy_calculation_regeneration_and_drain(self):
        regenerated = calculate_energy(self.energy_fields(), 101.0)
        self.assertEqual("calculated-candidate", regenerated["status"])
        self.assertEqual((100, 100, -20), (regenerated["current"],
                         regenerated["maximum"], regenerated["truncatedRateAdjustment"]))
        self.assertEqual("0x133F2C0", regenerated["formulaRva"])
        drained = calculate_energy(self.energy_fields(rateRaw=-2000), 101.0)
        self.assertEqual((60, 20), (drained["current"], drained["truncatedRateAdjustment"]))
        self.assertEqual(0, calculate_energy(self.energy_fields(rateRaw=-20000), 101.0)["current"])

    def test_energy_calculation_finite_fractional_live_record_replay(self):
        # Reuses *recorded raw inputs*; not a fresh game/API truth comparison.
        fields = self.energy_fields(baseRaw=100, maximumRaw=100, rateRaw=2000,
                                    wrapperClock=60910.4375)
        before = dict(fields)
        result = calculate_energy(fields, 61062.40625)
        self.assertEqual((100, 100, -3039), (result["current"], result["maximum"],
                         result["truncatedRateAdjustment"]))
        self.assertEqual(151.96875, result["elapsedSeconds"])
        self.assertEqual(before, fields)  # Read-only calculator cannot mutate record/cache.

    def test_energy_calculation_preserves_cvtdq2ps_rounding(self):
        # 16,777,217 is not exactly representable as float32: native rounds to 16,777,216.
        result = calculate_energy(self.energy_fields(baseRaw=100, maximumRaw=200000000,
                                                     rateRaw=16777217), 1100.0)
        self.assertEqual("calculated-candidate", result["status"])
        self.assertEqual(-167772160, result["truncatedRateAdjustment"])
        self.assertEqual(167772260, result["current"])

    def test_energy_calculation_fails_closed_for_unsafe_domains(self):
        unsafe = [(self.energy_fields(kind=3), 101),
                  (self.energy_fields(recordRevision=4), 101),
                  (self.energy_fields(wrapperRevision=4), 101),
                  (self.energy_fields(maximumRaw=0), 101),
                  (self.energy_fields(baseRaw=-1), 101),
                  (self.energy_fields(wrapperClock=float("nan")), 101),
                  (self.energy_fields(), float("inf")),
                  (self.energy_fields(), True),
                  (self.energy_fields(), 99),
                  (self.energy_fields(baseRaw=(1 << 31) - 1), 101),
                  (self.energy_fields(rateRaw=(1 << 31) - 1), 10000)]
        for fields, clock in unsafe:
            with self.subTest(fields=fields, clock=clock):
                self.assertEqual("unavailable", calculate_energy(fields, clock)["status"])

    def test_resource_kinds_never_share_a_faked_type_check(self):
        mana, m_wrapper = self.resource_pair(3)
        energy, e_wrapper = self.resource_pair(4)
        self.assertNotEqual(resource_record_fields(3, mana, m_wrapper)[
                            "expectedNativeResolverTypeUnverified"],
                            resource_record_fields(4, energy, e_wrapper)[
                            "expectedNativeResolverTypeUnverified"])
        self.assertEqual({3, 4}, set(RESOURCE_LAYOUTS))

    def test_other_resource_kind_is_not_applicable_not_zero(self):
        for kind in (0, 2, 5, -1, 100, None, "3"):
            with self.subTest(kind=kind):
                self.assertEqual({"status": "not-applicable", "kind": kind},
                                 resource_record_fields(kind, b"", b""))

    def test_health_and_resource_record_alias_fails_closed(self):
        self.assertIsNone(require_disjoint_records(None, None))
        self.assertIsNone(require_disjoint_records(0x10000, None))
        self.assertIsNone(require_disjoint_records(None, 0x10000))
        self.assertIsNone(require_disjoint_records(0x10000, 0x20000))
        with self.assertRaisesRegex(ValueError, "health-resource-record-alias"):
            require_disjoint_records(0x10000, 0x10000)

    def test_resource_revision_mismatch_remains_unqualified(self):
        for kind in (3, 4):
            record, wrapper = self.resource_pair(kind)
            struct.pack_into("<i", record, RESOURCE_LAYOUTS[kind]["revision"], 8)
            result = resource_record_fields(kind, record, wrapper)
            self.assertFalse(result["revisionConsistent"])
            self.assertNotIn("current", result)

    def test_mana_coherent_cache_transition_is_retained(self):
        before_record, before_wrapper = self.resource_pair(3)
        after_record, after_wrapper = bytearray(before_record), bytearray(before_wrapper)
        struct.pack_into("<i", before_wrapper, 0x18, 9)
        struct.pack_into("<i", before_record, 0x28, 9)
        struct.pack_into("<f", before_wrapper, 0x20, 24.0)
        struct.pack_into("<i", after_wrapper, 0x18, 10)
        struct.pack_into("<i", after_record, 0x28, 10)
        struct.pack_into("<i", after_record, 0x20, 8)
        struct.pack_into("<i", after_wrapper, 0x1C, 8)
        struct.pack_into("<f", after_wrapper, 0x20, 25.0)
        struct.pack_into("<f", after_wrapper, 0x24, 25.5)
        result = coherent_mana_resource_transition(
            bytes(before_record), bytes(before_wrapper), bytes(after_record), bytes(after_wrapper))
        self.assertEqual("coherent-cache-transition", result["status"])
        self.assertEqual((7, 8), (result["beforeFields"]["recordRevision"],
                                  result["afterFields"]["recordRevision"]))
        self.assertEqual([24.0, 24.5], result["beforeClocks"])
        self.assertEqual([25.0, 25.5], result["afterClocks"])

    def test_mana_failed_baseline_artifact_replays_as_coherent_transition(self):
        # Exact resource bytes retained in ad2e2c438b9341d7a3f0457686db28b5.
        before_record = bytes.fromhex(
            "d8ac31f2f77f00000200000000000000fb000000000000004f2600008c0f0000"
            "120000008c0f000014000000640000000cfeffff64000000f0554df2f77f0000")
        after_record = bytearray(before_record)
        after_record[0x20:0x24] = (19).to_bytes(4, "little", signed=True)
        after_record[0x28:0x2C] = (21).to_bytes(4, "little", signed=True)
        before_wrapper = bytes.fromhex(
            "48f502f2f77f0000208cf31ab8020000308cf31ab80200001400000012000000"
            "9c3595479c3595475300000000000000")
        after_wrapper = bytes.fromhex(
            "48f502f2f77f0000208cf31ab8020000308cf31ab80200001500000013000000"
            "6bab95476bab95475300000000000000")
        result = coherent_mana_resource_transition(
            before_record, before_wrapper, bytes(after_record), after_wrapper)
        self.assertEqual("coherent-cache-transition", result["status"])
        self.assertEqual((18, 19), (result["beforeFields"]["recordRevision"],
                                   result["afterFields"]["recordRevision"]))
        self.assertEqual([76395.21875, 76395.21875], result["beforeClocks"])
        self.assertEqual([76630.8359375, 76630.8359375], result["afterClocks"])

    def test_mana_transition_rejects_immutable_or_mixed_revision_change(self):
        record, wrapper = self.resource_pair(3)
        immutable = bytearray(record)
        immutable[8] ^= 1
        with self.assertRaisesRegex(ValueError, "immutable-owner-or-record"):
            coherent_mana_resource_transition(bytes(record), bytes(wrapper),
                                               bytes(immutable), bytes(wrapper))
        mixed = bytearray(record)
        struct.pack_into("<i", mixed, 0x20, 8)
        with self.assertRaisesRegex(ValueError, "mixed-revisions"):
            coherent_mana_resource_transition(bytes(record), bytes(wrapper),
                                               bytes(mixed), bytes(wrapper))

    def test_mana_transition_rejects_backward_or_nonfinite_clock(self):
        record, wrapper = self.resource_pair(3)
        backward = bytearray(wrapper)
        struct.pack_into("<f", backward, 0x24, 23.0)
        with self.assertRaisesRegex(ValueError, "clock-invalid-or-backward"):
            coherent_mana_resource_transition(bytes(record), bytes(wrapper),
                                               bytes(record), bytes(backward))
        invalid = bytearray(wrapper)
        struct.pack_into("<f", invalid, 0x20, float("nan"))
        with self.assertRaisesRegex(ValueError, "clock-invalid-or-backward"):
            coherent_mana_resource_transition(bytes(record), bytes(wrapper),
                                               bytes(record), bytes(invalid))

    def test_resource_owner_post_final_recheck_rejects_detach_or_missing_anchor(self):
        expected = {0x1000: b"owner", 0x2000: b"type"}
        self.assertIsNone(require_resource_owner_anchors(expected, dict(expected)))
        with self.assertRaisesRegex(ValueError, "detached-after-final"):
            require_resource_owner_anchors(
                expected, {0x1000: b"other", 0x2000: b"type"},
                "resource-owner-detached-after-final")
        with self.assertRaisesRegex(ValueError, "detached-after-final"):
            require_resource_owner_anchors(
                expected, {0x1000: b"owner"},
                "resource-owner-detached-after-final")

    def test_resource_owner_post_final_recheck_rejects_clock_root_mutation(self):
        # Represents the module clock-root RVA included with manager/player roots.
        expected = {0x140000000 + 0x33DC2B0: b"clockptr", 0x2000: b"player"}
        actual = dict(expected)
        actual[0x140000000 + 0x33DC2B0] = b"changed!"
        with self.assertRaisesRegex(ValueError, "detached-after-final"):
            require_resource_owner_anchors(
                expected, actual, "resource-owner-detached-after-final")

    def test_resource_short_or_nonfinite_record_is_rejected(self):
        for kind in (3, 4):
            record, wrapper = self.resource_pair(kind)
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, "resource-candidate-read-hole"):
                    resource_record_fields(kind, record[:63], wrapper)
                with self.assertRaisesRegex(ValueError, "resource-candidate-read-hole"):
                    resource_record_fields(kind, record, wrapper[:47])
                struct.pack_into("<f", wrapper, RESOURCE_LAYOUTS[kind]["wrapperClock"], float("nan"))
                with self.assertRaisesRegex(ValueError, "resource-candidate-nonfinite-clock"):
                    resource_record_fields(kind, record, wrapper)

    @staticmethod
    def inspection():
        target = {"processId": 1234, "processStartUtcTicks": 123456789,
                  "executableSha256": BUILD_SHA}
        return {"schemaVersion": 1, "contractVersion": "native-target-inspection/1",
                "target": dict(target, executablePath=r"C:\RIFT\rift_x64.exe",
                               moduleBaseAddress="0x140000000", moduleSize=63164416),
                "suggestedRequest": {"target": target}}

    def test_inspection_converts_module_base(self):
        identity, target = inspection_identity(self.inspection())
        self.assertEqual(0x140000000, identity["moduleBaseAddress"])
        self.assertEqual(BUILD_SHA, target["executableSha256"])

    def test_wrong_build_or_inconsistent_inspection_rejected(self):
        report = self.inspection()
        report["target"]["executableSha256"] = "A" * 64
        with self.assertRaisesRegex(ValueError, "wrong-build"):
            inspection_identity(report)
        report = self.inspection()
        report["suggestedRequest"]["target"]["processId"] += 1
        with self.assertRaisesRegex(ValueError, "wrong-build"):
            inspection_identity(report)

    def snapshot(self):
        identity, target = inspection_identity(self.inspection())
        request = {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot-request/1",
                   "target": target, "maxDurationMilliseconds": 10000,
                   "ranges": [{"addressKind": "module-relative-rva",
                               "address": "0x100", "byteLength": 8}]}
        raw = struct.pack("<Q", 0x20000)
        report = {"schemaVersion": 1, "evidenceKind": "native-memory-snapshot/1",
                  "status": "complete", "identity": identity,
                  "source": {"requestSha256": sha(encoded(request))},
                  "chunks": [{"address": "0x140000100", "status": "success",
                              "requestedByteLength": 8, "bytesRead": 8,
                              "bytesBase64": base64.b64encode(raw).decode(),
                              "bytesSha256": sha(raw)}]}
        return report, request, identity, raw

    def test_snapshot_full_identity_and_hashes(self):
        report, request, identity, raw = self.snapshot()
        self.assertEqual({0x140000100: raw}, snapshot_bytes(report, request, identity))

    def test_snapshot_holes_and_corruption_rejected(self):
        original, request, identity, _ = self.snapshot()
        changes = [
            lambda r: r.update(status="partial"),
            lambda r: r["identity"].update(processStartUtcTicks=999),
            lambda r: r["source"].update(requestSha256="A" * 64),
            lambda r: r["chunks"][0].update(bytesSha256="B" * 64),
            lambda r: r["chunks"][0].update(bytesRead=4),
            lambda r: r["chunks"].clear(),
            lambda r: r["chunks"].append(copy.deepcopy(r["chunks"][0])),
        ]
        for change in changes:
            report = copy.deepcopy(original)
            change(report)
            with self.assertRaises(ValueError):
                snapshot_bytes(report, request, identity)


if __name__ == "__main__":
    unittest.main()
