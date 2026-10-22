"""Vrai moteur Qt QML, logique production intacte, surfaces et backend simulés.

Seule la plomberie PanelWindow/layer-shell est remplacée par Item. Aucune
preuve de causalité Wayland physique : backingWindowVisible est simulé.
"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ.pop('WAYLAND_DISPLAY', None)
os.environ.pop('SWAYSOCK', None)
import json
from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QUrl, QMetaObject, Qt, QObject, QCoreApplication, QEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest
ROOT = Path(os.environ.get('FOCUS_SOURCE', Path(__file__).resolve().parents[2]))
APP = QGuiApplication.instance() or QGuiApplication([])

class QmlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for name in ('theme', 'sessionui', 'controlcenter'): (self.dir / name).mkdir()
        source = (ROOT / 'SessionStartupPromptV2.qml').read_text()
        source = source.replace('import Quickshell\n', '').replace('import Quickshell.Wayland\n', '')
        source = source.replace('PanelWindow {', '''Item {
    property color color
    property var screen
    property int exclusionMode
    property int exclusiveZone
    property bool aboveWindows
    property bool focusable
    property bool holdSurface: false
    property bool backingWindowVisible: visible || holdSurface
''')
        source = source.replace('id: modal', 'id: modal; objectName: "modal"')
        source = '\n'.join(line for line in source.splitlines() if 'WlrLayershell.' not in line and 'exclusionMode:' not in line and 'anchors { top: true' not in line)
        (self.dir / 'SessionStartupPromptV2.qml').write_text(source)
        (self.dir / 'sessionui/Protocol.js').write_text((ROOT / 'sessionui/Protocol.js').read_text())
        (self.dir / 'sessionui/qmldir').write_text('singleton SessionV2Service 1.0 SessionV2Service.qml\n')
        service_source = (ROOT / 'sessionui/SessionV2Service.qml').read_text()
        service_source = service_source.replace('import Quickshell\n', '').replace('import Quickshell.Io\n', '')
        service_source = service_source.replace('Quickshell.env(', 'testEnv(')
        service_source = service_source.replace('id: service', 'id: service; property var calls: []; function testEnv(name) { return ""; }', 1)
        service_source = service_source.replace('property Process backendProcess: Process {', '''property Process backendProcess: Process {
            onRunningChanged: {
                if (running) service.calls = service.calls.concat([{kind: service.operation,
                    visible: service.client.visible, focusable: service.client.focusable,
                    backing: service.client.backingWindowVisible}]);
            }
        ''', 1)
        (self.dir / 'sessionui/SessionV2Service.qml').write_text(service_source)
        (self.dir / 'sessionui/Process.qml').write_text('''import QtQuick
QtObject {
    property bool running: false
    property var command: []
    property QtObject stdout
    property QtObject stderr
    signal exited(int exitCode, int exitStatus)
    // This focus fixture models only an already unlocked service. Private-bus
    // and headless keyring tests exercise the real transport/prompt lifecycle.
    onRunningChanged: {
        if (running && command.indexOf("keyring-status") >= 0) Qt.callLater(() => {
            stdout.text = JSON.stringify({state:"KEYRING_READY", reason:"KEYRING_UNLOCKED"});
            running = false; exited(0, 0);
        });
    }
}''')
        (self.dir / 'sessionui/StdioCollector.qml').write_text('import QtQuick\nQtObject { property bool waitForEnd; property string text: "" }')
        (self.dir / 'sessionui/IpcHandler.qml').write_text('import QtQuick\nQtObject { property string target }')
        (self.dir / 'theme/qmldir').write_text('singleton Theme 1.0 Theme.qml\n')
        (self.dir / 'theme/Theme.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { property color foreground: "white"; property color secondaryForeground: "white"; property color popupBackground: "black"; property color lavender: "blue" }')
        (self.dir / 'controlcenter/ActionButton.qml').write_text('import QtQuick\nItem { property string label; signal clicked() }')
        (self.dir / 'Harness.qml').write_text('''import QtQuick
import "sessionui"
Item {
    property alias prompt: prompt
    property var replacement: null
    property var service: SessionV2Service
    function finish(kind, value, okay) {
        SessionV2Service.backendProcess.stdout.text = JSON.stringify(value);
        SessionV2Service.backendProcess.running = false;
        SessionV2Service.backendProcess.exited(okay ? 0 : 2, 0);
    }
    SessionStartupPromptV2 { id: prompt; objectName: "prompt"; startupHost: false; barWindow: ({screen: null}) }
}''')
        self.engine = QQmlEngine()
        self.component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(self.dir / 'Harness.qml')))
        self.root = self.component.create()
        self.assertIsNotNone(self.root, '\n'.join(e.toString() for e in self.component.errors()))
        self.prompt = self.root.findChild(QObject, 'prompt')
        self.service = self.root.property('service')
        QTest.qWait(5)  # finish the asynchronous fixture's initial D-Bus check
        self.service.setProperty('keyringState', 'KEYRING_READY')
    def tearDown(self):
        self.root.deleteLater(); self.engine.deleteLater(); QTest.qWait(1); self.tmp.cleanup()
    def call(self, name): QMetaObject.invokeMethod(self.prompt, name, Qt.DirectConnection)
    def js(self, expression):
        value = QQmlExpression(self.engine.rootContext(), self.root, expression)
        result = value.evaluate()
        self.assertFalse(value.hasError(), value.error().toString())
        return result
    def finish(self, kind, value, okay=True):
        self.js('finish(' + json.dumps(kind) + ',' + json.dumps(value) + ',' + ('true' if okay else 'false') + ')')
    def calls(self): return self.service.property('calls').toVariant()
    def open(self):
        self.prompt.setProperty('visible', True)
        QTest.qWait(800)
        self.assertTrue(self.prompt.property('interactionArmed'))
    def test_click_releases_before_unique_trigger(self):
        self.open(); self.call('restoreRequested'); self.call('restoreRequested')
        QTest.qWait(150)
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], dict(kind='apply-last', visible=False, focusable=False, backing=False))
    def test_surface_still_active_prevents_trigger(self):
        self.open(); self.prompt.setProperty('holdSurface', True); self.call('restoreRequested')
        QTest.qWait(1700)
        self.assertEqual(self.calls(), [])
        self.assertTrue(self.prompt.property('visible'))
        self.assertTrue(self.prompt.property('failed'))
        self.assertFalse(self.prompt.property('focusable'))


    def test_arm_enter_escape_do_not_restore(self):
        self.prompt.setProperty('visible', True)
        self.call('restoreRequested')
        self.assertEqual(self.calls(), [])
        modal = self.prompt.findChild(QQuickItem, 'modal')
        for key in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape, Qt.Key_Space):
            event = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
            QCoreApplication.sendEvent(modal, event)
            self.assertTrue(event.isAccepted())
        self.assertEqual(self.calls(), [])
    def test_rapid_reactivation_cancels_wait(self):
        self.open(); self.call('restoreRequested')
        self.prompt.setProperty('visible', True)
        QTest.qWait(100)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.service.property('busy'))
        self.assertTrue(self.prompt.property('failed'))
    def test_surface_disappears_later_then_single_trigger(self):
        self.open(); self.prompt.setProperty('holdSurface', True); self.call('restoreRequested')
        QTest.qWait(100)
        self.assertEqual(self.calls(), [])
        self.assertTrue(self.service.property('busy'))
        self.prompt.setProperty('holdSurface', False)
        QTest.qWait(100)
        self.assertEqual(len(self.calls()), 1)
        self.assertTrue(self.prompt.property('inProgress'))
        self.assertFalse(self.prompt.property('visible'))
        self.assertFalse(self.prompt.property('focusable'))
    def test_destroy_during_wait_cancels_reservation(self):
        self.open(); self.call('restoreRequested'); self.prompt.deleteLater()
        QTest.qWait(100)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.service.property('busy'))
    def test_deferred_retry_and_new_session_accessible(self):
        self.open(); self.call('restoreRequested'); QTest.qWait(100)
        self.finish('apply-last', dict(status='DEFERRED', reason='RESTORE_FOCUS_UNAVAILABLE'), False)
        self.assertTrue(self.prompt.property('visible'))
        self.assertTrue(self.prompt.property('retryAllowed'))
        self.assertTrue(self.prompt.property('awaitingUserFocus'))
        self.assertFalse(self.prompt.property('focusable'))
        QTest.qWait(100)
        self.assertEqual(len(self.calls()), 1)  # Jamais de retry automatique.
        self.call('restoreRequested')  # Délai d'armement réappliqué.
        self.assertEqual(len(self.calls()), 1)
        QTest.qWait(800); self.call('restoreRequested'); QTest.qWait(100)
        self.assertEqual([x['kind'] for x in self.calls()], ['apply-last', 'apply-last'])
        self.assertTrue(all(not x['focusable'] and not x['backing'] for x in self.calls()))
        self.finish('apply-last', dict(status='DEFERRED', reason='RESTORE_FOCUS_UNAVAILABLE'), False)
        QTest.qWait(800); self.call('newSessionRequested')
        self.assertEqual(self.calls()[-1]['kind'], 'ack-new')
        self.finish('ack-new', dict(status='acknowledged', choice='new'))
        self.assertFalse(self.prompt.property('visible'))
    def test_prewarm_deferred_keeps_explicit_retry_and_explains_live_windows(self):
        self.open(); self.call('restoreRequested'); QTest.qWait(100)
        self.finish('apply-last', dict(status='DEFERRED', reason='APPLICATION_LAUNCH_FAILED'), False)
        self.assertTrue(self.prompt.property('retryAllowed'))
        self.assertFalse(self.prompt.property('focusable'))
        self.assertIn('fenêtres ouvertes sont conservées', self.prompt.property('failureMessage'))
        QTest.qWait(850)
        self.assertEqual([x['kind'] for x in self.calls()], ['apply-last'])
        self.call('restoreRequested'); QTest.qWait(100)
        self.assertEqual([x['kind'] for x in self.calls()], ['apply-last', 'apply-last'])

    def test_restart_deferred_keeps_explicit_retry_without_keyboard_capture(self):
        self.js('service.run("startup-status", "", "", prompt)')
        self.finish('startup-status', dict(eligible=True, claimed=True, deferred=True, interrupted=True))
        self.assertTrue(self.prompt.property('retryAllowed'))
        self.assertTrue(self.prompt.property('awaitingUserFocus'))
        self.assertFalse(self.prompt.property('focusable'))
        QTest.qWait(850)
        self.assertEqual([x['kind'] for x in self.calls()], ['startup-status'])
        self.call('restoreRequested'); QTest.qWait(100)
        self.assertEqual([x['kind'] for x in self.calls()], ['startup-status', 'apply-last'])

    def test_backend_error_reopens_details_no_automatic_retry(self):
        self.open(); self.call('restoreRequested'); QTest.qWait(100)
        self.finish('apply-last', dict(status='failed', reason='RECOVERY_REQUIRED'), False)
        self.assertTrue(self.prompt.property('visible'))
        self.assertEqual(self.calls()[-1]['kind'], 'restore-status')
        self.finish('restore-status', dict(phase='cleanup-error', reason='RECOVERY_REQUIRED'))
        QTest.qWait(800); self.call('restoreRequested')
        self.assertEqual(len(self.calls()), 2)
        self.call('newSessionRequested')
        self.assertEqual(self.calls()[-1]['kind'], 'ack-new')
    def test_success_ack_is_required_and_nonfocusable(self):
        self.open(); self.call('restoreRequested'); QTest.qWait(100)
        result = dict(schema='labfy.sway.session-v2-restore-attempt', version=1, status='success',
            final_tree_verified=True, final_focus_verified=True, slots_expected=1, slots_filled=1,
            applications_expected=1, applications_observed=1, anchors_created=0, anchors_cleaned=0,
            helpers_suspended=0, helpers_resumed=0, identity_level='exact', transaction_id='a'*32)
        self.finish('apply-last', result)
        self.assertEqual(self.calls()[-1]['kind'], 'ack-restored')
        self.assertFalse(self.prompt.property('visible'))
        self.finish('ack-restored', dict(status='acknowledged', choice='restored'))
        self.assertTrue(self.prompt.property('restored'))
        self.assertFalse(self.prompt.property('focusable'))
        QTest.qWait(650)
        self.assertFalse(self.prompt.property('visible'))
    def test_restart_backend_busy_then_interrupted_never_auto_applies(self):
        self.js('service.run("startup-status", "", "", prompt)')
        self.finish('startup-status', dict(eligible=True, claimed=True, in_progress=True))
        self.assertTrue(self.prompt.property('watchingBackend'))
        self.assertFalse(self.prompt.property('visible'))
        QTest.qWait(1050)
        self.assertEqual(self.calls()[-1]['kind'], 'startup-status')
        self.finish('startup-status', dict(eligible=True, claimed=True, in_progress=False, interrupted=True))
        self.assertTrue(self.prompt.property('failed'))
        self.assertTrue(self.prompt.property('visible'))
        self.assertEqual(self.calls()[-1]['kind'], 'restore-status')
        self.assertNotIn('apply-last', [x['kind'] for x in self.calls()])


    def test_owner_recreated_while_backend_running_retries_only_status(self):
        self.open(); self.call('restoreRequested'); QTest.qWait(100)
        self.prompt.deleteLater(); QTest.qWait(1)
        self.js('replacement = Qt.createComponent(' + json.dumps(QUrl.fromLocalFile(str(self.dir / "SessionStartupPromptV2.qml")).toString()) + ').createObject(this, {startupHost:true, barWindow:({screen:null})})')
        self.assertTrue(self.js("!!replacement")[0])
        QTest.qWait(450)
        self.assertEqual([x['kind'] for x in self.calls()], ['apply-last'])
        self.finish('apply-last', dict(status='failed', reason='RECOVERY_REQUIRED'), False)
        QTest.qWait(450)
        self.assertEqual([x['kind'] for x in self.calls()], ['apply-last', 'startup-status'])
        self.finish('startup-status', dict(eligible=True, claimed=True, interrupted=True))
        self.assertEqual(self.calls()[-1]['kind'], 'restore-status')

    def test_keyring_gate_requires_ready_and_explicit_click(self):
        self.service.setProperty('keyringState', 'KEYRING_LOCKED')
        self.open(); self.call('restoreRequested'); QTest.qWait(100)
        self.assertFalse(self.prompt.property('attempted'))
        self.assertEqual(self.calls(), [])
        self.service.setProperty('keyringState', 'KEYRING_READY')
        QTest.qWait(150)
        self.assertEqual(self.calls(), [])
        self.call('restoreRequested'); QTest.qWait(100)
        self.assertEqual([x['kind'] for x in self.calls()], ['apply-last'])

    def test_new_session_during_keyring_unlock_remains_accessible(self):
        self.service.setProperty('keyringState', 'KEYRING_LOCKED')
        self.open(); self.call('unlockRequested'); QTest.qWait(100)
        self.assertTrue(self.service.property('keyringBusy'))
        self.assertFalse(self.prompt.property('focusable'))
        self.call('newSessionRequested')
        self.assertEqual([x['kind'] for x in self.calls()], ['ack-new'])
        self.assertFalse(self.service.property('keyringBusy'))

if __name__ == '__main__': unittest.main()
