import math
import unittest

from scripts.waypoint_map import LocalMap, ZOOM_RADII, draw_route, fit_route_radius, route_length


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
                for radius in ZOOM_RADII:
                    view = LocalMap(7424.7, 2946.2, bearing, width, height, radius)
                    for px, pz in ((7424.7, 2946.2), (7418.4, 2950.1), (7429, 2944)):
                        x, z = view.canvas_to_world(*view.world_to_canvas(px, pz))
                        self.assertAlmostEqual(x, px, places=9)
                        self.assertAlmostEqual(z, pz, places=9)

    def test_fit_nearby_loop_empty_and_far_points(self):
        loop = [("Start", 100, 200), ("Corner", 101, 201), ("Far", 104, 200),
                ("Return", 101, 200)]
        self.assertEqual(5, fit_route_radius(100, 200, loop))
        self.assertEqual(2, fit_route_radius(100, 200, []))
        self.assertEqual(2, fit_route_radius(100, 200, [("Here", 100, 200)]))
        self.assertEqual(10, fit_route_radius(0, 0, [("Needs room", 5, 0)]))
        self.assertEqual(20, fit_route_radius(0, 0, [("Beyond preview", 50, 0)]))
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                fit_route_radius(0, 0, [("Invalid", bad, 0)])

    def test_ring_labels_follow_radius_and_default_stays_five_ten(self):
        class Canvas:
            def __init__(self): self.calls = []
            def __getattr__(self, name):
                return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
        for radius, labels in ((2, ["1", "2"]), (5, ["2.5", "5"]),
                               (10, ["5", "10"]), (20, ["10", "20"])):
            canvas = Canvas()
            draw_route(canvas, LocalMap(0, 0, 0, 300, 300, radius), [], set())
            actual = [kwargs["text"] for name, args, kwargs in canvas.calls
                      if name == "create_text" and kwargs.get("fill") == "#8b9da9"]
            self.assertEqual(labels, actual)
        self.assertEqual(10, LocalMap(0, 0, 0, 300, 300).radius)

    def test_playback_states_and_reversed_order_keep_selection_visible(self):
        class Canvas:
            def __init__(self): self.calls = []
            def __getattr__(self, name):
                return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
        view = LocalMap(0, 0, 0, 300, 300)
        points = [("c", "C", 0, 3), ("b", "B", 0, 2), ("a", "A", 0, 1)]
        canvas = Canvas()
        draw_route(canvas, view, points, {"c"}, completed={"c"}, active="b")
        dots = [call for call in canvas.calls if call[0] == "create_oval" and "fill" in call[2]]
        self.assertEqual([d[2]["fill"] for d in dots], ["#719c88", "#ffb454", "#63b3ed"])
        self.assertEqual([d[2]["outline"] for d in dots], ["#ffffff", "#101c25", "#101c25"])
        lines = [call for call in canvas.calls if call[0] == "create_line" and call[2].get("dash") == (4, 3)]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0][1], (*view.world_to_canvas(0, 3), *view.world_to_canvas(0, 2)))
        self.assertEqual(lines[1][1], (*view.world_to_canvas(0, 2), *view.world_to_canvas(0, 1)))
        labels = [c[2]["text"] for c in canvas.calls if c[0] == "create_text" and c[2].get("anchor") == "sw"]
        self.assertEqual(labels, ["1", "2", "3"])

    def test_default_selection_colors_remain_unchanged(self):
        class Canvas:
            def __init__(self): self.calls = []
            def __getattr__(self, name):
                return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
        canvas = Canvas()
        draw_route(canvas, LocalMap(0, 0, 0, 300, 300), [("a", "A", 0, 1), ("b", "B", 0, 2)], {"a"})
        dots = [c for c in canvas.calls if c[0] == "create_oval" and "fill" in c[2]]
        self.assertEqual([d[2]["fill"] for d in dots], ["#ffb454", "#63b3ed"])
        self.assertEqual(dots[0][2]["outline"], "#101c25")
        lines = [c for c in canvas.calls if c[0] == "create_line" and c[2].get("dash") == (4, 3)]
        self.assertEqual(lines[0][1], (150, 150, *LocalMap(0, 0, 0, 300, 300).world_to_canvas(0, 1)))

    def test_route_preview_includes_start_and_every_leg(self):
        self.assertEqual(route_length(0, 0, [("A", 3, 4), ("B", 3, 0)]), 9)
        self.assertEqual(route_length(0, 0, []), 0)


if __name__ == "__main__":
    unittest.main()
