from __future__ import annotations

import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROL_CENTER = ROOT / "quickshell/.config/quickshell/labfy-sway/controlcenter/ControlCenter.qml"
SESSION_PAGE = ROOT / "quickshell/.config/quickshell/labfy-sway/controlcenter/SessionPage.qml"
SESSION_MANAGER = ROOT / "quickshell/.config/quickshell/labfy-sway/controlcenter/SessionManager.qml"


class SessionManagerQmlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.control = CONTROL_CENTER.read_text(encoding="utf-8")
        self.session_page = SESSION_PAGE.read_text(encoding="utf-8")
        self.manager = SESSION_MANAGER.read_text(encoding="utf-8")

    def test_navigation_preserves_power_session_and_adds_manager(self) -> None:
        self.assertIn('logout", label: "Déconnexion"', self.control)
        self.assertIn('command: ["uwsm", "stop"]', self.control)
        self.assertIn("sessionManager: 12", self.control)
        self.assertIn('onManagerRequested: popup.openPage("sessionManager")', self.control)
        self.assertIn('onBackRequested: popup.openPage("session")', self.control)
        self.assertIn('label: "Gestionnaire de sessions"', self.session_page)

    def test_backend_is_xdg_relative_and_every_command_is_argv(self) -> None:
        self.assertIn('Quickshell.env("XDG_CONFIG_HOME")', self.manager)
        self.assertIn('/quickshell/labfy-sway/session/session_snapshot.py', self.manager)
        self.assertNotIn("/home/fy59", self.manager)
        self.assertIn('const argv = ["python3", backend, "--compact"]', self.manager)
        self.assertNotRegex(self.manager, re.compile(r"\b(?:sh|bash)\s+-c\b"))
        self.assertNotIn("Quickshell.execDetached", self.manager)

    def test_user_mutations_are_explicit_and_restore_is_confirmed(self) -> None:
        self.assertIn('view = exists ? "duplicate" : "create"', self.manager)
        self.assertIn('page.view = "deleteConfirm"', self.manager)
        self.assertIn('page.view = "restoreConfirm"', self.manager)
        self.assertIn('page.run("apply", page.selectedSession.name)', self.manager)
        self.assertIn('if (kind === "apply") argv.push("--execute")', self.manager)
        self.assertNotIn("Timer {", self.manager)
        self.assertNotIn("running: true", self.manager)

    def test_process_contract_keeps_streams_separate_and_checks_exit(self) -> None:
        self.assertIn("stdout: StdioCollector", self.manager)
        self.assertIn("stderr: StdioCollector", self.manager)
        self.assertIn("exitCode !== 0 || exitStatus !== 0", self.manager)
        self.assertIn("JSON.parse(text)", self.manager)
        self.assertIn('value.read_only !== true', self.manager)

    def test_required_limitations_and_preflight_authority_are_visible(self) -> None:
        self.assertIn("L’état interne des applications n’est pas garanti", self.manager)
        self.assertIn("Les proportions exactes des splits ne sont pas restaurées", self.manager)
        self.assertIn("Un plan frais et le preflight seront recalculés", self.manager)
        self.assertIn("RESTORE_ALREADY_RUNNING", self.manager)


if __name__ == "__main__":
    unittest.main()
