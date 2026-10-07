import QtQuick
import QtTest

TestCase {
    name: "SessionExitGateV2"
    function gate() {
        const component = Qt.createComponent("../../../quickshell/.config/quickshell/labfy-sway/controlcenter/SessionExitGate.qml");
        compare(component.status, Component.Ready, component.errorString());
        return createTemporaryObject(component, this, {
            checkpointSuccessStatus: "saved",
            actions: [
                {id: "logout", checkpointReason: "logout", command: ["uwsm", "stop"]},
                {id: "reboot", checkpointReason: "reboot", command: ["systemctl", "reboot"]},
                {id: "poweroff", checkpointReason: "poweroff", command: ["systemctl", "poweroff"]}
            ]
        });
    }
    Component { id: spyComponent; SignalSpy {} }
    function test_saved_releases_only_confirmed_action() {
        for (const action of ["logout", "reboot", "poweroff"]) {
            const g = gate();
            const spy = createTemporaryObject(spyComponent, this, {target: g, signalName: "commandRequested"});
            g.requestAction(action);
            g.confirmAction(action);
            verify(g.busy);
            compare(spy.count, 0);
            g.checkpointFinished(0, 0, '{"status":"saved"}', "");
            compare(spy.count, 1);
            compare(spy.signalArguments[0][0], action === "logout" ? ["uwsm", "stop"] : ["systemctl", action]);
        }
    }
    function test_error_or_legacy_success_never_exits() {
        for (const response of ["{}", "invalid", '{"status":"success"}', '{"status":"failed"}']) {
            const g = gate();
            const spy = createTemporaryObject(spyComponent, this, {target: g, signalName: "commandRequested"});
            g.requestAction("logout"); g.confirmAction("logout");
            g.checkpointFinished(0, 0, response, "");
            compare(spy.count, 0);
            verify(!g.busy);
            g.cancel();
            compare(spy.count, 0);
        }
    }
    function test_quit_without_saving_requires_explicit_call() {
        const g = gate();
        const spy = createTemporaryObject(spyComponent, this, {target: g, signalName: "commandRequested"});
        g.requestAction("logout"); g.confirmAction("logout");
        g.quitWithoutCheckpoint(); compare(spy.count, 0);
        g.checkpointFinished(2, 0, '{"status":"saved"}', "échec");
        compare(spy.count, 0);
        g.quitWithoutCheckpoint(); compare(spy.count, 1);
    }
}
