"""TEST_ONLY: Firefox-provider deferral in the real startup QML, private Sway."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from common import REPO, BACKEND
from lab import Lab
from phase3b_ui import FAKE, HARNESS


def main():
    with Lab() as lab:
        config = lab.directory / "config-provider"
        base = config / "quickshell/labfy-sway"
        base.mkdir(parents=True)
        source = REPO / "quickshell/.config/quickshell/labfy-sway"
        shutil.copytree(source / "sessionui", base / "sessionui")
        (base / "controlcenter").mkdir()
        shutil.copyfile(source / "SessionStartupPromptV2.qml", base / "SessionStartupPromptV2.qml")
        shutil.copyfile(BACKEND / "controlcenter/ActionButton.qml", base / "controlcenter/ActionButton.qml")
        (base / "theme").mkdir()
        (base / "theme/qmldir").write_text("singleton Theme 1.0 Theme.qml\n")
        colors = "popupBackground foreground secondaryForeground lavender buttonBackground emphasisBackground border danger"
        (base / "theme/Theme.qml").write_text(
            "pragma Singleton\nimport QtQuick\nQtObject {\n" +
            "\n".join("property color " + color + ': "#333333"' for color in colors.split()) + "\n}\n")
        backend = FAKE.replace(
            "{'status':'failed', 'reason':'APPLICATION_WINDOWS_INCOMPLETE'}",
            "{'status':'DEFERRED', 'reason':'FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE'}", 1)
        (base / "session-v2.py").write_text(backend)
        harness = HARNESS.replace(
            "if (prompt.failed) prompt.restoreRequested();",
            """if (!prompt.retryAllowed || !prompt.awaitingUserFocus || prompt.focusable
                || prompt.failureMessage.indexOf("Firefox") < 0
                || prompt.failureMessage.indexOf("focus stable") >= 0) {
                console.error("UI_TEST_FAIL_PROVIDER"); Qt.quit(); return;
            }""")
        (base / "shell.qml").write_text(harness)
        calls_path = lab.directory / "provider.calls"
        env = dict(lab.env, XDG_CONFIG_HOME=str(config), LABFY_UI_MODE="failure",
                   LABFY_UI_LOG=str(calls_path))
        binary = os.environ.get("LABFY_TEST_QUICKSHELL", "qs")
        result = subprocess.run([binary, "-p", str(base), "--no-color"],
                                env=env, text=True, capture_output=True, timeout=15)
        output = result.stdout + result.stderr
        assert "UI_TEST_PASS" in output and "UI_TEST_FAIL" not in output, output
        calls = calls_path.read_text().splitlines()
        assert calls.count("apply-last") == 1, calls
        assert "acknowledge-startup" not in calls and "restore-status" not in calls, calls
        evidence = {"status": "PASS", "reason": "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE",
                    "correct_explanation": True, "manual_retry_available": True,
                    "no_focus_capture": True, "backend_calls": calls}
        (lab.directory / "provider-ui-result.json").write_text(json.dumps(evidence, indent=2))
        print("PROVIDER_UI=" + json.dumps(evidence), flush=True)
        print("TEST_ONLY_DIRECTORY=" + str(lab.directory), flush=True)


if __name__ == "__main__":
    main()
