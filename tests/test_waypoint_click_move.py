import math
import unittest
from types import SimpleNamespace as NS

from scripts.waypoint_click_move import ClickMoveError, project_map_click, validate_map_origin
from scripts.waypoint_map import LocalMap


class ClickMoveTests(unittest.TestCase):
    def setUp(self):
        self.view = LocalMap(x=100, z=200, bearing=37, width=330, height=220, radius=50)

    def test_projection_reuses_local_map_inverse_and_is_input_free(self):
        for world in ((100, 200), (112.5, 190.25), (86, 215)):
            canvas = self.view.world_to_canvas(*world)
            result = project_map_click(self.view, *canvas)
            self.assertAlmostEqual(world[0], result["x"])
            self.assertAlmostEqual(world[1], result["z"])
            self.assertEqual((canvas[0], canvas[1]), (result["canvasX"], result["canvasY"]))
            self.assertEqual("map-world-xz", result["kind"])
            self.assertFalse(result["heightKnown"])
            self.assertFalse(result["terrainAvailable"])
            self.assertFalse(result["inputSent"])

    def test_negative_body_bearing_projection_uses_the_same_inverse(self):
        view = LocalMap(x=100, z=200, bearing=-170, width=330, height=220, radius=50)
        world = (112.5, 190.25)
        canvas = view.world_to_canvas(*world)
        result = project_map_click(view, *canvas)
        self.assertAlmostEqual(world[0], result["x"])
        self.assertAlmostEqual(world[1], result["z"])

    def test_inset_edges_are_inclusive_and_outside_is_refused(self):
        for click in ((12, 12), (318, 208)):
            self.assertEqual(click, (project_map_click(self.view, *click)["canvasX"],
                                     project_map_click(self.view, *click)["canvasY"]))
        for click in ((11.999, 12), (12, 11.999), (318.001, 100), (100, 208.001)):
            with self.subTest(click=click), self.assertRaisesRegex(ClickMoveError, "inside"):
                project_map_click(self.view, *click)

    def test_nonfinite_bool_and_invalid_view_values_are_refused(self):
        for x, y in ((True, 50), (50, False), (math.nan, 50), (50, math.inf)):
            with self.subTest(x=x, y=y), self.assertRaises(ClickMoveError):
                project_map_click(self.view, x, y)
        for view in (NS(**self.view.__dict__),
                     LocalMap(100, 200, 37, 24, 220, 50),
                     LocalMap(100, 200, 37, 330, 220, 7),
                     LocalMap(100, 200, 360, 330, 220, 50),
                     LocalMap(100, 200, -180.001, 330, 220, 50),
                     LocalMap(True, 200, 37, 330, 220, 50)):
            with self.subTest(view=view), self.assertRaises(ClickMoveError):
                project_map_click(view, 100, 100)

    def test_origin_accepts_thresholds_and_wrapped_heading(self):
        exact = validate_map_origin(LocalMap(0, 0, 359.8, 330, 220, 50),
                                    {"x": .03, "z": .04}, .3)
        self.assertAlmostEqual(.05, exact["originChange"])
        self.assertAlmostEqual(.5, exact["headingChange"])
        self.assertFalse(exact["inputSent"])
        wrapped = validate_map_origin(LocalMap(0, 0, .2, 330, 220, 50), NS(x=0, z=0), 359.8)
        self.assertAlmostEqual(.4, wrapped["headingChange"])
        signed_wrap = validate_map_origin(LocalMap(0, 0, -179.8, 330, 220, 50),
                                          NS(x=0, z=0), 179.8)
        self.assertAlmostEqual(.4, signed_wrap["headingChange"])
        with self.assertRaisesRegex(ClickMoveError, "turned"):
            validate_map_origin(LocalMap(0, 0, -179, 330, 220, 50), NS(x=0, z=0), 179)

    def test_origin_rejects_stale_position_heading_and_invalid_values(self):
        with self.assertRaisesRegex(ClickMoveError, "moved"):
            validate_map_origin(self.view, {"x": 100.051, "z": 200}, 37)
        with self.assertRaisesRegex(ClickMoveError, "turned"):
            validate_map_origin(self.view, {"x": 100, "z": 200}, 37.501)
        for position, bearing in (({"x": True, "z": 200}, 37), ({"x": 100}, 37),
                                  ({"x": 100, "z": 200}, math.nan),
                                  ({"x": 100, "z": 200}, 360)):
            with self.subTest(position=position, bearing=bearing), self.assertRaises(ClickMoveError):
                validate_map_origin(self.view, position, bearing)


if __name__ == "__main__": unittest.main()
