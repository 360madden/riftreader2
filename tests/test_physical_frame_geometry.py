"""Client-to-frame pixel mapping must bind physical geometry and remain optional."""
from copy import deepcopy
import unittest

from scripts import physical_turn_visual_pair as visual


def receipt():
    geometry = {'visibleFrameLeft': -1920, 'visibleFrameTop': 6, 'visibleFrameRight': 0,
                'visibleFrameBottom': 1038, 'clientScreenLeft': -1920, 'clientScreenTop': 29,
                'clientWidth': 1920, 'clientHeight': 1009, 'coordinateSpace': 'physical-screen-pixels'}
    target = {'width': 1920, 'height': 1009, 'windowGeometry': geometry}
    return {'frameWidth': 1920, 'frameHeight': 1032, 'targetBefore': target,
            'targetAfter': deepcopy(target), 'clientFrameMapping': {
                'status': 'available-candidate', 'unavailableReason': None,
                'frameWidth': 1920, 'frameHeight': 1032, 'clientLeft': 0, 'clientTop': 23,
                'clientWidth': 1920, 'clientHeight': 1009,
                'coordinateSpace': 'top-left-frame-physical-pixels', 'basis': 'matching-dwm-visible-frame-size'}}


class PhysicalFrameGeometryTests(unittest.TestCase):
    def test_negative_screen_origin_and_titlebar_are_accounted_for(self):
        mapping = visual.client_frame_mapping(receipt())
        point = visual.project_client_point_to_frame(
            {'status': 'available-candidate', 'normalizedX': .5, 'normalizedY': .5}, mapping)
        self.assertEqual(960, point['frameX'])
        self.assertEqual(527.5, point['frameY'])
        self.assertTrue(point['insideFrameCandidate'])

    def test_changed_bounds_forged_offset_or_coordinate_space_fail(self):
        for fault in ('changed', 'offset', 'frame-size', 'space', 'client-size'):
            with self.subTest(fault=fault):
                report = receipt()
                if fault == 'changed': report['targetAfter']['windowGeometry']['clientScreenTop'] += 1
                if fault == 'offset': report['clientFrameMapping']['clientTop'] += 1
                if fault == 'frame-size': report['frameHeight'] += 1
                if fault == 'space': report['targetBefore']['windowGeometry']['coordinateSpace'] = 'logical'
                if fault == 'client-size': report['targetBefore']['width'] -= 1
                with self.assertRaises(ValueError):
                    visual.client_frame_mapping(report)

    def test_legacy_and_unavailable_geometry_keep_frame_usable_without_pixels(self):
        self.assertEqual('unavailable', visual.client_frame_mapping({})['status'])
        report = receipt()
        report['clientFrameMapping'].update(status='unavailable', unavailableReason='size-mismatch',
                                           clientLeft=None, clientTop=None, clientWidth=None, clientHeight=None)
        mapping = visual.client_frame_mapping(report)
        value = visual.project_client_point_to_frame(
            {'status': 'available-candidate', 'normalizedX': .5, 'normalizedY': .5}, mapping)
        self.assertEqual('size-mismatch', value['reason'])
        self.assertNotIn('frameX', value)

    def test_outside_points_are_not_clipped_into_frame(self):
        mapping = visual.client_frame_mapping(receipt())
        point = visual.project_client_point_to_frame(
            {'status': 'available-candidate', 'normalizedX': 1.2, 'normalizedY': -.1}, mapping)
        self.assertFalse(point['insideFrameCandidate'])
        self.assertGreater(point['frameX'], 1920)
        self.assertEqual('unavailable', visual.project_client_point_to_frame(
            {'status': 'nonpositive-or-small-clip-w'}, mapping)['status'])

    def test_titlebar_point_is_inside_frame_but_outside_client(self):
        point = visual.project_client_point_to_frame(
            {'status': 'available-candidate', 'normalizedX': .5, 'normalizedY': -.01},
            visual.client_frame_mapping(receipt()))
        self.assertTrue(point['insideFrameCandidate'])
        self.assertFalse(point['insideClientCandidate'])
