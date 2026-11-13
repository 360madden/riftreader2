"""Pure height evidence and vertical caution boundaries."""
from copy import deepcopy
import unittest

from scripts.waypoint_height_context import height_context, height_cue, measured_heights
from scripts.waypoint_measurements import measurement, parse_marker_projection_route


class HeightContextTests(unittest.TestCase):
    def point(self, y, kind="measured"):
        return dict(xyz=dict(x=1, y=y, z=2), displayHeightKind=kind)

    def test_measured_above_below_and_one_unit_boundary(self):
        for delta, relation, warning, cue in ((1, "near", False, ""), (-1, "near", False, ""),
                (1.01, "above", True, "↑"), (-1.01, "below", True, "↓"), (0, "near", False, "")):
            with self.subTest(delta=delta):
                context = height_context(self.point(10 + delta), 10)
                self.assertAlmostEqual(context['deltaY'], delta)
                self.assertEqual(context['verticalRelation'], relation)
                self.assertEqual(context['floorWarning'], warning)
                self.assertEqual(height_cue(context), cue)
                self.assertEqual('possible other floor' in context['label'], warning)

    def test_every_resolved_estimate_stays_approximate_without_floor_claim(self):
        for kind in ('nearest-measured-estimate', 'startup-player-estimate'):
            for delta, cue in ((4, '~↑'), (-4, '~↓'), (0, '~')):
                context = height_context(self.point(10 + delta, kind), 10)
                self.assertEqual(context['heightKind'], kind)
                self.assertFalse(context['floorWarning'])
                self.assertTrue(context['label'].startswith('approx.'))
                self.assertNotIn('floor', context['label'])
                self.assertEqual(height_cue(context), cue)

    def test_missing_or_nonfinite_height_never_becomes_measured_difference(self):
        for value in (None, True, '5', float('nan'), float('inf')):
            context = height_context(self.point(value), 1)
            self.assertEqual(context['heightKind'], 'unknown')
            self.assertIsNone(context['deltaY'])
            self.assertEqual(context['verticalRelation'], 'unknown')
            self.assertFalse(context['floorWarning'])
        for point in ({'xyz': {'y': 5}}, self.point(5, 'unresolved-estimate'), None):
            self.assertEqual(height_context(point, 1)['heightKind'], 'unknown')

    def test_bad_player_height_preserves_provenance_but_has_no_difference(self):
        for value in (None, True, '5', float('nan'), float('inf')):
            context = height_context(self.point(5), value)
            self.assertEqual(context['heightKind'], 'measured')
            self.assertIsNone(context['deltaY'])
            self.assertEqual(context['verticalRelation'], 'unknown')
            self.assertFalse(context['floorWarning'])

    def test_projected_and_route_rows_match_without_mutation(self):
        point = self.point(12, 'nearest-measured-estimate')
        before = deepcopy(point)
        projected = dict(displayHeightCandidate=12, displayHeightKind='nearest-measured-estimate')
        self.assertEqual(height_context(point, 10), height_context(projected, 10))
        self.assertEqual(point, before)

    def test_admission_preserves_receipt_and_unknown_stored_y(self):
        identity = dict(machine='AMD-DESKTOP', gameBuildSha256='a'*64, unitKey='123')
        receipt = measurement(dict(x=1, y=12, z=2), identity, 'native.json', '2026-11-13T00:00:00Z')
        document = dict(waypoints=[['Measured', 1, 2], ['Typed', 3, 4]], heights=[12, 99],
                        pointMeasurements=[receipt, None])
        before = deepcopy(document)
        points = parse_marker_projection_route(document, identity)['points']
        self.assertTrue(height_context(points[0], 10)['floorWarning'])
        self.assertEqual(height_context(points[1], 10)['heightKind'], 'unknown')
        self.assertIsNone(points[1]['xyz']['y'])
        self.assertEqual(document, before)
        self.assertEqual(measured_heights(document), [12, None])

    def test_recorded_observations_supply_heights_but_weak_recording_does_not(self):
        document = dict(waypoints=[['A', 1, 2]], heights=[12], recording=dict(
            version=1, complete=True, identity=dict(machine='AMD-DESKTOP',
                gameBuildSha256='a'*64, unitKey='123'), sources=['native.json'],
            firstObservedAtUtc='2026-11-13T00:00:00Z', lastObservedAtUtc='2026-11-13T00:00:01Z'))
        self.assertEqual(measured_heights(document), [12])
        document['recording'].pop('sources')
        self.assertEqual(measured_heights(document), [None])


if __name__ == '__main__':
    unittest.main()
