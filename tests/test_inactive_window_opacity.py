"""Réapplication événementielle de l'opacité, sans serveur Sway réel."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / 'sway/.config/sway/scripts/inactive-windows-transparency.py'
SPEC = importlib.util.spec_from_file_location('inactive_opacity', SOURCE)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class OpacityTest(unittest.TestCase):
    def test_normal_sun_and_immediate_restore(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(module, 'STATE', Path(folder) / 'effective.json'):
            focused = mock.Mock(focused=True)
            inactive = mock.Mock(focused=False)
            ipc = mock.Mock()
            ipc.get_tree.return_value.leaves.return_value = [focused, inactive]
            for profile, expected in [('normal', '0.85'), ('sun-light', '1.0'),
                                      ('sun-dark', '1.0'), ('normal', '0.85')]:
                module.STATE.write_text(json.dumps({'effectiveMode': profile}))
                module.apply_all(ipc)
                focused.command.assert_called_with('opacity 1.0')
                inactive.command.assert_called_with('opacity ' + expected)
