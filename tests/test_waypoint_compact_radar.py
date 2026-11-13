import json
import os
import tempfile
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from scripts.waypoint_compact_radar import CompactRadar, DEFAULT_CONFIG, load_config, load_exploration, trail_lines
from scripts.waypoint_map import LocalMap


class Api:
    def own_window(self, hwnd): return hwnd
    def show(self, hwnd, rect): self.rect = rect


class RadarTests(unittest.TestCase):
    def test_config_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'radar.json'
            self.assertIsNone(load_config(path))
            path.write_text(json.dumps(DEFAULT_CONFIG))
            self.assertEqual(load_config(path), DEFAULT_CONFIG)
            for change in ({'radius': 3}, {'opacity': float('nan')}, {'enabled': 1}, {'version': True}):
                path.write_text(json.dumps(dict(DEFAULT_CONFIG, **change)))
                self.assertIsNone(load_config(path))

    def test_render_and_clear(self):
        app = QApplication.instance() or QApplication([])
        api = Api(); radar = CompactRadar(api)
        frame = {'clientRect': [-1500, -300, 1200, 800],
                 'playerPose': {'position': {'x': 1, 'z': 2}, 'bearing': 0},
                 'points': [{'number': 1, 'displayLandmark': True}]}
        route = {'points': [{'number': 1, 'xyz': {'x': 2, 'z': 3}},
                            {'number': 2, 'xyz': {'x': 300, 'z': 400}}]}
        radar.present(frame, route, dict(DEFAULT_CONFIG, enabled=True),
                      {'trail': [[(1,2),(2,3)]], 'guidance': {'status':'active','activeIndex':1,'activeName':'Far','distance':20}})
        app.processEvents()
        self.assertTrue(radar.isVisible() and api.rect[0] < 0)
        self.assertGreaterEqual(api.rect[1], frame['clientRect'][1])
        self.assertLessEqual(api.rect[1] + api.rect[3], sum(frame['clientRect'][1::2]))
        self.assertFalse(radar.grab().isNull())
        radar.clear()
        self.assertFalse(radar.isVisible()); self.assertIsNone(radar.exploration)
        radar.present(frame, {'points': []}, dict(DEFAULT_CONFIG, enabled=True, unlocked=True))
        self.assertTrue(radar.isVisible())
        radar.present(frame, route, None)
        self.assertFalse(radar.isVisible()); radar.deleteLater()

    def test_owner_session_freshness_and_separate_segments(self):
        target = dict(hostName='AMD', processId=1, processStartUtcTicks='123', executablePath='C:/rift.exe', executableSha256='a'*64, hwnd=2)
        frame = {'target':target, 'playerPose':{'playerKey':'player'}}
        data = {'version':1, 'owner':{'target':target, 'playerKey':'player', 'sessionId':'session'},
                'acquiredMonotonic':100, 'guidance':None,
                'trail':[[{'x':0,'z':0}, {'x':1,'z':0}], [{'x':3,'z':0}, {'x':4,'z':0}]]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'feedback.json'; path.write_text(json.dumps(data))
            result = load_exploration(path, frame, 'session', 1, now=100.5)
            self.assertEqual(len(trail_lines(LocalMap(0,0,0,264,250,10), result['trail'], (12,12,252,238))), 2)
            self.assertIsNone(load_exploration(path, frame, 'other', 1, now=100.5))
            self.assertIsNone(load_exploration(path, frame, 'session', 1, now=102))
            self.assertIsNone(load_exploration(path, dict(frame, playerPose={'playerKey':'other'}), 'session', 1, now=100.5))
            other = dict(target, processId=3)
            self.assertIsNone(load_exploration(path, dict(frame, target=other), 'session', 1, now=100.5))

if __name__ == '__main__': unittest.main()
