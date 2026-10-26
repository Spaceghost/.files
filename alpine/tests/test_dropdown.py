from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'alpine/desktop/.local/bin/oldbook-dropdown'
LOADER = SourceFileLoader('oldbook_dropdown', str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
DROPDOWN = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(DROPDOWN)


class DropdownGeometryTests(unittest.TestCase):
    def test_helper_hands_native_mark_to_the_console_being_toggled(self):
        source = SCRIPT.read_text()
        self.assertIn("DROPDOWN_MARK not in node.get('marks', [])", source)
        self.assertIn("mark --add {DROPDOWN_MARK}", source)

    def test_fills_usable_width_directly_below_bar(self):
        output = {'rect': {'x': 0, 'y': 0, 'width': 1440, 'height': 900}}
        workspace = {'rect': {'x': 0, 'y': 39, 'width': 1440, 'height': 861}}
        self.assertEqual(DROPDOWN.geometry(output, workspace),
                         (0, 39, 1440, 468))

    def test_uses_output_offset_and_workspace_inset(self):
        output = {'rect': {'x': 1440, 'y': 100, 'width': 1440, 'height': 900}}
        workspace = {'rect': {'x': 1440, 'y': 139, 'width': 1440, 'height': 861}}
        self.assertEqual(DROPDOWN.geometry(output, workspace),
                         (1440, 139, 1440, 468))


if __name__ == '__main__':
    unittest.main()
