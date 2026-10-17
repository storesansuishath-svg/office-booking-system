import ast
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")
EXPECTED = ["Civic (บัส)", "Civic (บอล)", "Camry (ตุ้ม)", "MG-EP (เนก)"]


def assignment(name):
    for node in ast.parse(SOURCE).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "set":
                return set()
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing {name}")


class FourDriverCarsProductionTests(unittest.TestCase):
    def test_four_named_driver_cars_are_configured(self):
        self.assertEqual(assignment("SYS_CARS"), EXPECTED)
        self.assertEqual(assignment("SELF_DRIVE_CARS"), set())
        self.assertEqual(assignment("DRIVER_CONFLICT_GROUPS"), {})

    def test_masked_phone_links_are_available(self):
        for masked, dial in [("9305", "0639305458"), ("8388", "0988388055"), ("0402", "0810402527")]:
            self.assertIn(f'href="tel:{dial}"', SOURCE)
            self.assertIn(f">{masked} · กดโทร</a>", SOURCE)
        self.assertIn("<b>โทร:</b> รออัปเดต", SOURCE)

    def test_calendar_reads_legacy_booking_names(self):
        self.assertIn("database_resources = sorted({", SOURCE)
        self.assertIn("row[\"resource\"] in get_conflict_resources(resource)", SOURCE)


if __name__ == "__main__":
    unittest.main()
