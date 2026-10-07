#!/usr/bin/env python3
"""Exécuter le contrat QML de sortie de session sans commande système réelle."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
QML_TEST = ROOT / "tests/qml/tst_session_exit_gate.qml"
QML_TEST_RUNNER = Path("/usr/lib/qt6/bin/qmltestrunner")


class SessionExitGateQmlTest(unittest.TestCase):
    def test_mocked_session_exit_contracts(self) -> None:
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [str(QML_TEST_RUNNER), "-input", str(QML_TEST), "-o", "-,txt"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
