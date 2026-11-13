import math
import unittest

from scripts.waypoint_map import LocalMap, ZOOM_RADII, draw_route, fit_route_radius, route_length
from scripts.waypoint_ui_theme import PALETTE


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
                      if name == "create_text" and kwargs.get("tags") == "range-label"]
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
        dots = [call for call in canvas.calls if call[2].get("tags") == "waypoint-node"]
        self.assertEqual([d[2]["fill"] for d in dots], [PALETTE["mint"], PALETTE["gold"], PALETTE["blue"]])
        rings = [call for call in canvas.calls if call[2].get("tags") == "selection-ring"]
        self.assertEqual(len(rings), 2)  # Selection remains visible even on completed mint.
        lines = [call for call in canvas.calls if call[2].get("tags") == "route-connector"]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0][1], (*view.world_to_canvas(0, 3), *view.world_to_canvas(0, 2)))
        self.assertEqual(lines[1][1], (*view.world_to_canvas(0, 2), *view.world_to_canvas(0, 1)))
        labels = [c[2]["text"] for c in canvas.calls if c[2].get("tags") == "waypoint-number"]
        self.assertEqual(labels, ["1", "2", "3"])

    def test_default_selection_and_actual_start_connector_remain_distinct(self):
        class Canvas:
            def __init__(self): self.calls = []
            def __getattr__(self, name):
                return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
        canvas = Canvas()
        draw_route(canvas, LocalMap(0, 0, 0, 300, 300), [("a", "A", 0, 1), ("b", "B", 0, 2)], {"a"})
        dots = [c for c in canvas.calls if c[2].get("tags") == "waypoint-node"]
        self.assertEqual([d[2]["fill"] for d in dots], [PALETTE["gold"], PALETTE["blue"]])
        self.assertEqual(dots[0][2]["outline"], PALETTE["inset"])
        lines = [c for c in canvas.calls if c[2].get("tags") == "route-connector"]
        self.assertEqual(lines[0][1], (150, 150, *LocalMap(0, 0, 0, 300, 300).world_to_canvas(0, 1)))

    def test_crowded_number_lanes_preserve_true_nodes_and_clear_player(self):
        class Canvas:
            def __init__(self): self.calls = []
            def __getattr__(self, name):
                return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
        for width, height in ((300, 280), (440, 370)):
            with self.subTest(size=(width, height)):
                canvas = Canvas()
                view = LocalMap(0, 0, 37, width, height, 10)
                points = [(str(i), "Close", .01*i, .01*i) for i in range(7)]
                draw_route(canvas, view, points, {"2"})
                nodes = [c[1] for c in canvas.calls if c[2].get("tags") == "waypoint-node"]
                self.assertEqual(len(nodes), 7)
                for node, (_, _, x, z) in zip(nodes, points):
                    expected = view.world_to_canvas(x, z)
                    self.assertAlmostEqual((node[0]+node[2])/2, expected[0])
                    self.assertAlmostEqual((node[1]+node[3])/2, expected[1])
                boxes = [c[1] for c in canvas.calls if c[2].get("tags") == "number-badge"]
                boxes.append((width/2-20, height/2-20, width/2+20, height/2+37))
                for index, box in enumerate(boxes[:-1]):
                    self.assertTrue(0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)
                    for other in boxes[index+1:]:
                        self.assertTrue(box[2] <= other[0] or other[2] <= box[0]
                                        or box[3] <= other[1] or other[3] <= box[1])

    def test_far_points_do_not_become_false_edge_nodes_and_segments_clip(self):
        class Canvas:
            def __init__(self): self.calls = []
            def __getattr__(self, name):
                return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
        canvas = Canvas()
        view = LocalMap(0, 0, 0, 300, 280, 2)
        draw_route(canvas, view, [("a", "Far", 100, 0), ("b", "Far", -100, 0)], set())
        self.assertFalse(any(c[2].get("tags") == "waypoint-node" for c in canvas.calls))
        lines = [c[1] for c in canvas.calls if c[2].get("tags") == "route-connector"]
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertTrue(all(12 <= value <= 288 for value in line[::2]))
            self.assertTrue(all(12 <= value <= 268 for value in line[1::2]))
        self.assertGreater(abs(view.world_to_canvas(100, 0)[0]), 300)

    def test_route_preview_includes_start_and_every_leg(self):
        self.assertEqual(route_length(0, 0, [("A", 3, 4), ("B", 3, 0)]), 9)
        self.assertEqual(route_length(0, 0, []), 0)


if __name__ == "__main__":
    unittest.main()
