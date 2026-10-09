import QtQuick
import QtTest
import "../../quickshell/.config/quickshell/labfy-sway/controlcenter"

TestCase {
    name: "SessionExitGate"

    Component {
        id: gateComponent
        SessionExitGate {
            actions: [
                { id: "lock", label: "Verrouiller", command: ["/home/fy59/.local/bin/labfy-lock"] },
                { id: "suspend", label: "Veille", command: ["systemctl", "suspend"] },
                { id: "logout", label: "Déconnexion", confirmTitle: "Se déconnecter ?",
                    description: "La session SwayFX en cours sera fermée.", checkpointReason: "logout",
                    command: ["uwsm", "stop"] },
                { id: "reboot", label: "Redémarrer", checkpointReason: "reboot",
                    command: ["systemctl", "reboot"] },
                { id: "poweroff", label: "Éteindre", checkpointReason: "poweroff",
                    command: ["systemctl", "poweroff"] }
            ]
        }
    }

    Component {
        id: signalSpyComponent
        SignalSpy {}
    }

    function createGate() {
        return createTemporaryObject(gateComponent, this);
    }

    function createSpy(target, signalName) {
        return createTemporaryObject(signalSpyComponent, this, {
            target: target,
            signalName: signalName
        });
    }

    function test_logout_success_sequences_checkpoint_before_command() {
        const gate = createGate();
        const checkpointSpy = createSpy(gate, "checkpointRequested");
        const commandSpy = createSpy(gate, "commandRequested");
        gate.requestAction("logout");
        compare(gate.pendingAction.id, "logout");
        compare(gate.pendingAction.label, "Déconnexion");
        compare(gate.pendingAction.command, ["uwsm", "stop"]);
        compare(gate.pendingAction.confirmTitle, "Se déconnecter ?");
        compare(gate.pendingAction.description, "La session SwayFX en cours sera fermée.");
        gate.confirmAction("logout");
        compare(checkpointSpy.count, 1);
        compare(checkpointSpy.signalArguments[0][0], "logout");
        compare(commandSpy.count, 0);
        verify(gate.busy);
        compare(gate.checkpointAction.id, "logout");
        gate.confirmAction("logout");
        compare(checkpointSpy.count, 1);
        gate.pendingAction = null;
        gate.checkpointFinished(0, 0, '{"status":"success"}', "");
        compare(commandSpy.count, 1);
        compare(commandSpy.signalArguments[0][0], ["uwsm", "stop"]);
        verify(!gate.busy);
    }

    function test_checkpoint_failure_blocks_command_and_preserves_escape() {
        const gate = createGate();
        const failureSpy = createSpy(gate, "checkpointFailed");
        const commandSpy = createSpy(gate, "commandRequested");
        gate.requestAction("logout");
        gate.confirmAction("logout");
        gate.checkpointFinished(1, 0, "", "capture failed");
        compare(commandSpy.count, 0);
        compare(failureSpy.count, 1);
        compare(gate.pendingAction.id, "logout");
        compare(gate.errorMessage, "capture failed");
        gate.quitWithoutCheckpoint();
        compare(commandSpy.count, 1);
        compare(commandSpy.signalArguments[0][0], ["uwsm", "stop"]);
    }

    function test_cancel_after_failure_never_dispatches() {
        const gate = createGate();
        const commandSpy = createSpy(gate, "commandRequested");
        gate.requestAction("logout");
        gate.confirmAction("logout");
        gate.checkpointFinished(1, 0, "", "capture failed");
        gate.cancel();
        compare(commandSpy.count, 0);
        compare(gate.pendingAction, null);
    }

    function test_reboot_and_poweroff_sequence() {
        const expected = {
            reboot: ["systemctl", "reboot"],
            poweroff: ["systemctl", "poweroff"]
        };
        for (const actionId in expected) {
            const gate = createGate();
            const checkpointSpy = createSpy(gate, "checkpointRequested");
            const commandSpy = createSpy(gate, "commandRequested");
            gate.requestAction(actionId);
            gate.confirmAction(actionId);
            compare(checkpointSpy.count, 1);
            compare(checkpointSpy.signalArguments[0][0], actionId);
            compare(commandSpy.count, 0);
            gate.checkpointFinished(0, 0, '{"status":"success"}', "");
            compare(commandSpy.count, 1);
            compare(commandSpy.signalArguments[0][0], expected[actionId]);
        }
    }

    function test_reboot_and_poweroff_failure_never_dispatch() {
        for (const actionId of ["reboot", "poweroff"]) {
            const gate = createGate();
            const commandSpy = createSpy(gate, "commandRequested");
            gate.requestAction(actionId);
            gate.confirmAction(actionId);
            gate.checkpointFinished(1, 0, "", "capture failed");
            compare(commandSpy.count, 0);
            compare(gate.pendingAction.id, actionId);
        }
    }

    function test_lock_and_suspend_keep_existing_contract() {
        const gate = createGate();
        const checkpointSpy = createSpy(gate, "checkpointRequested");
        const commandSpy = createSpy(gate, "commandRequested");
        gate.requestAction("lock");
        compare(commandSpy.count, 1);
        compare(commandSpy.signalArguments[0][0], ["/home/fy59/.local/bin/labfy-lock"]);
        compare(checkpointSpy.count, 0);
        gate.requestAction("suspend");
        compare(gate.pendingAction.id, "suspend");
        gate.confirmAction("suspend");
        compare(commandSpy.count, 2);
        compare(commandSpy.signalArguments[1][0], ["systemctl", "suspend"]);
        compare(checkpointSpy.count, 0);
    }
}
