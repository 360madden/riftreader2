import math
import unittest

from scripts.waypoint_map import LocalMap, route_length


class LocalMapTests(unittest.TestCase):
    def test_forward_and_right_match_measured_rift_key_convention(self):
        view = LocalMap(100, 200, 0, 300, 300)
        self.assertEqual(view.world_to_canvas(100, 200), (150, 150))
        self.assertLess(view.world_to_canvas(100, 201)[1], 150)
        self.assertGreater(view.world_to_canvas(99, 200)[0], 150)
        self.assertLess(view.world_to_canvas(101, 200)[0], 150)

    def test_current_facing_rotates_forward_and_right(self):
        view = LocalMap(100, 200, 90, 300, 300)
        self.assertLess(view.world_to_canvas(101, 200)[1], 150)
        self.assertGreater(view.world_to_canvas(100, 201)[0], 150)

    def test_round_trip_retains_world_point_across_headings_and_canvas_sizes(self):
        for bearing in (-179.9, -90, -4.7, 0, 67, 179.9):
            for width, height in ((300, 300), (350, 260), (600, 400)):
                view = LocalMap(7424.7, 2946.2, bearing, width, height)
                for px, pz in ((7424.7, 2946.2), (7418.4, 2950.1), (7429, 2944)):
                    x, z = view.canvas_to_world(*view.world_to_canvas(px, pz))
                    self.assertAlmostEqual(x, px, places=9)
                    self.assertAlmostEqual(z, pz, places=9)

    def test_route_preview_includes_start_and_every_leg(self):
        self.assertEqual(route_length(0, 0, [("A", 3, 4), ("B", 3, 0)]), 9)
        self.assertEqual(route_length(0, 0, []), 0)


if __name__ == "__main__":
    unittest.main()
